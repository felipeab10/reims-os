#!/usr/bin/env python3
"""Conservative QMP/serial/process supervisor for one appliance boot."""
import argparse
import datetime as dt
import json
import os
import selectors
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

PANIC = "Debugger called: <panic>"
CLASSES = ("GUEST_SHUTDOWN", "GUEST_REBOOT", "GUEST_KERNEL_PANIC", "QEMU_FATAL", "REIMS_FATAL", "EXTERNAL_SIGNAL", "UNKNOWN_EXIT")

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        try:
            directory = os.open(path.parent, os.O_DIRECTORY)
            os.fsync(directory)
            os.close(directory)
        except OSError:
            pass
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def log_event(path, source, name, **extra):
    row = {"timestamp": now(), "source": source, "event": name}
    row.update(extra)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())

def direct_children(pid):
    try:
        return [int(x) for x in Path(f"/proc/{pid}/task/{pid}/children").read_text().split()]
    except (OSError, ValueError):
        return []

def proc_evidence(pid):
    try:
        exe = os.readlink(f"/proc/{pid}/exe")
    except OSError:
        exe = None
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        cmdline = [x.decode(errors="replace") for x in raw if x]
    except OSError:
        cmdline = None
    return {"pid": pid, "exe": exe, "cmdline": cmdline}

def _qmp_terminal(facts):
    return next((event for event in reversed(facts.get("qmp_events", [])) if event in ("SHUTDOWN", "RESET")), None)


def _runtime_log_text(facts):
    text = facts.get("qemu_log_text", "")
    offset = facts.get("qemu_runtime_log_offset")
    if offset is None:
        return text
    return text[offset:]


def _fatal_evidence(facts):
    text = _runtime_log_text(facts)
    upper = text.upper()
    if "VK_ERROR_DEVICE_LOST" in upper or ("VULKAN" in upper and "DEVICE LOST" in upper):
        return ("REIMS_FATAL", "vulkan_device_lost", {"source": "qemu_log", "marker": "VK_ERROR_DEVICE_LOST"})
    if "SEGMENTATION FAULT" in upper or "SIGSEGV" in upper:
        return ("QEMU_FATAL", "qemu_runtime_segfault", {"source": "qemu_log", "marker": "segmentation fault"})
    if "ABORTED" in upper or "ASSERTION FAILED" in upper or "QEMU: ASSERT" in upper:
        return ("QEMU_FATAL", "qemu_runtime_abort", {"source": "qemu_log", "marker": "runtime abort/assertion"})
    if facts.get("qemu_exit") is not None and facts["qemu_exit"] != 0 and facts.get("external_signal") is None:
        return ("QEMU_FATAL", "qemu_exit_nonzero", {"source": "process", "exit_code": facts["qemu_exit"]})
    if facts.get("launcher_exit") is not None and not facts.get("qemu_identified") and facts["launcher_exit"] != 0:
        return ("REIMS_FATAL", "launcher_exit_nonzero", {"source": "process", "exit_code": facts["launcher_exit"]})
    return None


def classify_session(facts):
    sources = ["serial", "qmp", "process", "qemu_log", "supervisor_signal"]
    if facts.get("host_kernel_log_available"):
        sources.append("host_kernel_log")
    if facts.get("panic"):
        decision = ("GUEST_KERNEL_PANIC", "serial_kernel_panic", {"source": "serial", "marker": PANIC})
    else:
        fatal = _fatal_evidence(facts)
        if fatal:
            decision = fatal
        elif facts.get("external_signal") is not None:
            decision = ("EXTERNAL_SIGNAL", "supervisor_signal", {"source": "supervisor", "signal": facts["external_signal"]})
        else:
            terminal = _qmp_terminal(facts)
            if terminal == "SHUTDOWN":
                decision = ("GUEST_SHUTDOWN", "qmp_shutdown", {"source": "qmp", "event": "SHUTDOWN"})
            elif terminal == "RESET" and facts.get("appliance_state") == "installed":
                decision = ("GUEST_REBOOT", "qmp_reset", {"source": "qmp", "event": "RESET"})
            else:
                decision = ("UNKNOWN_EXIT", "insufficient_evidence", {"source": "process"})
    classification, reason, primary = decision
    return {"classification": classification, "classification_reason": reason,
            "primary_evidence": primary, "sources_consulted": sources,
            "recovery_required": classification in {"GUEST_KERNEL_PANIC", "QEMU_FATAL", "REIMS_FATAL", "UNKNOWN_EXIT"}}


# Backward-compatible entry point retained for T005 callers.
def classify(facts):
    return classify_session(facts)["classification"]


def transition_recovery():
    root = Path(os.environ.get("REIMS_STATE_ROOT", "/var/lib/reims"))
    state_path = root / "state.json"
    if not state_path.exists():
        return {"required": True, "attempted": False, "succeeded": False,
                "error": "state_unavailable"}
    script = Path(__file__).with_name("reims-state.py")
    try:
        result = subprocess.run([sys.executable, str(script), "transition", "recovery"],
                                env=os.environ.copy(), capture_output=True, text=True)
    except OSError as exc:
        return {"required": True, "attempted": True, "succeeded": False, "error": str(exc)}
    if result.returncode == 0:
        return {"required": True, "attempted": True, "succeeded": True, "error": None}
    return {"required": True, "attempted": True, "succeeded": False,
            "error": (result.stderr or result.stdout or "transition failed").strip()}


def run(args):
    started = now()
    root = Path(args.log_root or os.environ.get("REIMS_LOG_ROOT", "/var/log/reims"))
    session_id = "boot-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    session = root / session_id
    session.mkdir(parents=True)
    lifecycle = session / "lifecycle.log"
    result_path = session / "result.json"
    qemu_log = session / "qemu.log"
    preserved_serial = session / "serial.log"
    run_dir = Path(args.run_dir)
    qmp_path = run_dir / "qmp.path"
    try:
        old_qmp = (qmp_path.stat().st_ino, qmp_path.stat().st_mtime_ns, qmp_path.read_text().strip())
    except OSError:
        old_qmp = None
    serial_before = set(run_dir.glob("serial-*.log"))
    facts = {
        "appliance_state": args.appliance_state, "panic": False,
        "external_signal": None, "launcher_exit": None, "qemu_exit": None,
        "qemu_identified": False, "launcher_had_child": False,
        "qemu_pid": None, "qemu_proc": None, "serial_path": None,
        "serial_ambiguous": False, "qmp_available": False,
        "qmp_handshake_failed": False, "qmp_protocol_error": False, "qmp_socket": None,
        "qmp_events": [], "qmp_raw": [], "qemu_runtime_log_offset": None,
        "qemu_log_text": "", "panic_context": [], "host_kernel_log_available": False,
    }
    log_event(lifecycle, "supervisor", "session_start", session_id=session_id,
              vm_id=args.vm_id, appliance_state=args.appliance_state)
    output = qemu_log.open("w", encoding="utf-8")
    launcher = subprocess.Popen(args.command, stdout=output, stderr=subprocess.STDOUT,
                                start_new_session=True, cwd=os.getcwd())
    log_event(lifecycle, "process", "start", launcher_pid=launcher.pid)
    stop = threading.Event()
    qmp_done = threading.Event()

    def forward(signum, _frame):
        if facts["external_signal"] is None:
            facts["external_signal"] = signal.Signals(signum).name
            log_event(lifecycle, "supervisor", "external_signal", signal=facts["external_signal"])
            try:
                os.killpg(launcher.pid, signum)
            except ProcessLookupError:
                pass

    old_handlers = {s: signal.signal(s, forward) for s in (signal.SIGTERM, signal.SIGINT)}

    def accept_qemu(candidates):
        if facts["qemu_identified"]:
            return
        if len(candidates) == 1:
            pid = candidates[0]
            facts["qemu_identified"] = True
            facts["qemu_pid"] = pid
            facts["qemu_proc"] = proc_evidence(pid)
            try:
                facts["qemu_runtime_log_offset"] = qemu_log.stat().st_size
            except OSError:
                facts["qemu_runtime_log_offset"] = 0
            log_event(lifecycle, "process", "qemu_identified", qemu_pid=pid, proc=facts["qemu_proc"],
                      qemu_runtime_log_offset=facts["qemu_runtime_log_offset"])
        elif len(candidates) > 1:
            log_event(lifecycle, "process", "qemu_pid_ambiguous", candidates=candidates)

    def qmp_reader():
        deadline = None
        sock = None
        selector = None
        buffer = b""
        handshake = False
        handshake_deadline = None
        last_data = time.monotonic()
        while not stop.is_set():
            if sock is None:
                if launcher.poll() is not None:
                    break
                try:
                    if not qmp_path.exists():
                        time.sleep(0.02); continue
                    state = (qmp_path.stat().st_ino, qmp_path.stat().st_mtime_ns, qmp_path.read_text().strip())
                    if old_qmp is not None and state == old_qmp:
                        time.sleep(0.02); continue
                    if not state[2]:
                        time.sleep(0.02); continue
                    candidate = state[2]
                    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    sock.settimeout(1.0)
                    sock.connect(candidate)
                    sock.setblocking(False)
                    selector = selectors.DefaultSelector()
                    selector.register(sock, selectors.EVENT_READ)
                    facts["qmp_socket"] = candidate
                    handshake_deadline = time.monotonic() + 5
                except (OSError, ValueError):
                    if sock is not None:
                        try: sock.close()
                        except OSError: pass
                    sock = None; selector = None
                    time.sleep(0.05)
                    continue
            events = selector.select(0.1) if selector else []
            if not events:
                if handshake == "capability_sent" and launcher.poll() is not None:
                    break
                if handshake is False and handshake_deadline and time.monotonic() > handshake_deadline:
                    facts["qmp_handshake_failed"] = True
                    break
                if launcher.poll() is not None and time.monotonic() - last_data > 0.35:
                    break
                continue
            try:
                chunk = sock.recv(65536)
            except BlockingIOError:
                continue
            except OSError:
                facts["qmp_handshake_failed"] = not handshake
                break
            if not chunk:
                break
            last_data = time.monotonic()
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    facts["qmp_handshake_failed"] = True
                    continue
                facts["qmp_raw"].append(message)
                if not handshake:
                    if not isinstance(message, dict) or not isinstance(message.get("QMP"), dict):
                        facts["qmp_handshake_failed"] = True
                        break
                    try:
                        sock.sendall(b'{"execute":"qmp_capabilities"}\n')
                    except OSError:
                        facts["qmp_handshake_failed"] = True
                        break
                    handshake = "capability_sent"
                    continue
                if isinstance(message, dict) and "error" in message:
                    facts["qmp_protocol_error"] = True
                    log_event(lifecycle, "qmp", "QMP_ERROR", raw=message)
                    continue
                if handshake == "capability_sent":
                    if not isinstance(message, dict) or "return" not in message:
                        facts["qmp_handshake_failed"] = True
                        break
                    handshake = True
                    cs = direct_children(launcher.pid)
                    if len(cs) == 1:
                        accept_qemu(cs)
                    elif len(cs) > 1:
                        log_event(lifecycle, "process", "qemu_pid_ambiguous", candidates=cs)
                    facts["qmp_available"] = True
                    log_event(lifecycle, "qmp", "ready", socket=facts["qmp_socket"])
                    continue
                if handshake is True and isinstance(message, dict) and "event" in message:
                    event_name = message["event"]
                    facts["qmp_events"].append(event_name)
                    log_event(lifecycle, "qmp", event_name, raw=message)
                    if event_name == "RESET" and args.appliance_state == "installing":
                        log_event(lifecycle, "qmp", "INSTALLER_RESET", phase="installing")
            if facts["qmp_handshake_failed"]:
                break
        if facts["qmp_available"] is False and facts["qmp_handshake_failed"] is False:
            log_event(lifecycle, "qmp", "unavailable")
        if selector:
            try: selector.close()
            except OSError: pass
        if sock:
            try: sock.close()
            except OSError: pass
        qmp_done.set()

    def serial_reader():
        while not stop.is_set() and launcher.poll() is None:
            fresh = [p for p in run_dir.glob("serial-*.log") if p not in serial_before]
            if len(fresh) == 1:
                facts["serial_path"] = fresh[0]
            elif len(fresh) > 1:
                facts["serial_ambiguous"] = True
            if facts["serial_path"] and facts["serial_path"].exists():
                if PANIC in facts["serial_path"].read_text(errors="replace") and not facts["panic"]:
                    facts["panic"] = True
                    log_event(lifecycle, "serial", "GUEST_KERNEL_PANIC")
            time.sleep(0.03)

    tq = threading.Thread(target=qmp_reader, daemon=True)
    ts = threading.Thread(target=serial_reader, daemon=True)
    tq.start(); ts.start()
    while launcher.poll() is None:
        children_now = direct_children(launcher.pid)
        if children_now:
            facts["launcher_had_child"] = True
        time.sleep(0.02)
    facts["launcher_exit"] = launcher.returncode
    log_event(lifecycle, "process", "exit", code=launcher.returncode)
    tq.join(0.6)
    stop.set()
    tq.join(0.6)
    ts.join(1.0)
    for s, handler in old_handlers.items():
        signal.signal(s, handler)
    output.close()
    # Mandatory final serial discovery and complete reread before classification.
    fresh = [p for p in run_dir.glob("serial-*.log") if p not in serial_before]
    if facts["serial_path"] is None and len(fresh) == 1:
        facts["serial_path"] = fresh[0]
    elif len(fresh) > 1:
        facts["serial_ambiguous"] = True
    if facts["serial_path"] and facts["serial_path"].exists():
        serial_text = facts["serial_path"].read_text(errors="replace")
        if PANIC in serial_text:
            facts["panic"] = True
            lines = serial_text.splitlines()
            marker_index = next((i for i, line in enumerate(lines) if PANIC in line), 0)
            context = lines[max(0, marker_index - 2):marker_index + 3]
            facts["panic_context"] = [line for line in context if any(token in line for token in (PANIC, "panic(", "AppleParavirtGPU", "AppleParavirtPageTable", "IOAcceleratorFamily2"))]
        preserved_serial.write_text(serial_text, encoding="utf-8")
    else:
        log_event(lifecycle, "serial", "serial_missing")
    if facts["qemu_identified"]:
        facts["qemu_exit"] = facts["launcher_exit"]
    facts["qemu_log_text"] = qemu_log.read_text(errors="replace")
    if facts["qemu_runtime_log_offset"] is None:
        facts["qemu_runtime_log_offset"] = 0
    limitations = []
    if not facts["qmp_available"]:
        limitations.append("qmp_handshake_failed" if facts["qmp_handshake_failed"] else "qmp_unavailable")
    if facts["qmp_protocol_error"]: limitations.append("qmp_protocol_error")
    if facts["serial_ambiguous"]: limitations.append("serial_ambiguous")
    if not facts["serial_path"]: limitations.append("serial_missing")
    if not facts["qemu_identified"] and facts["launcher_had_child"] and facts["qmp_available"]:
        limitations.append("qemu_pid_ambiguous")
    facts["qmp_unavailable"] = not facts["qmp_available"]
    decision = classify_session(facts)
    classification = decision["classification"]
    log_event(lifecycle, "supervisor", "classification", classification=classification,
              reason=decision["classification_reason"], primary_evidence=decision["primary_evidence"])
    recovery = {"required": decision["recovery_required"], "attempted": False,
                "succeeded": None, "error": None}
    if recovery["required"]:
        recovery = transition_recovery()
        if not recovery["succeeded"]:
            limitations.append("recovery_transition_failed")
    evidence = []
    if facts["panic"]: evidence.append("serial:" + PANIC)
    if facts["external_signal"]: evidence.append("signal:" + facts["external_signal"])
    if facts["qemu_exit"] is not None and facts["qemu_exit"] != 0: evidence.append(f"process:qemu_exit:{facts['qemu_exit']}")
    for event_name in facts["qmp_events"]: evidence.append("qmp:" + event_name)
    ended = now()
    data = {"schema": 1, "session_id": session_id, "vm_id": args.vm_id,
            "appliance_state": args.appliance_state, "classification": classification,
            "started_at": started, "ended_at": ended, "launcher_pid": launcher.pid,
            "qemu_pid": facts["qemu_pid"], "launcher_exit_code": facts["launcher_exit"],
            "qemu_exit_code": facts["qemu_exit"], "external_signal": facts["external_signal"],
            "qmp": {"available": facts["qmp_available"], "socket": facts["qmp_socket"],
                    "events": facts["qmp_events"], "last_event": facts["qmp_events"][-1] if facts["qmp_events"] else None,
                    "raw_events": facts["qmp_raw"]},
            "serial": {"source": str(facts["serial_path"]) if facts["serial_path"] else None,
                       "preserved": str(preserved_serial) if preserved_serial.exists() else None,
                       "panic_detected": facts["panic"]},
            "process": {"launcher_had_child": facts["launcher_had_child"], "qemu": facts["qemu_proc"]},
            "evidence": evidence, "limitations": limitations,
            "classification_reason": decision["classification_reason"],
            "primary_evidence": decision["primary_evidence"],
            "sources_consulted": decision["sources_consulted"],
            "recovery_required": decision["recovery_required"], "recovery": recovery,
            "diagnostics": {"panic_context": facts["panic_context"],
                            "qemu_runtime_log_offset": facts["qemu_runtime_log_offset"],
                            "host_kernel_log_source": "UNAVAILABLE"}}
    atomic(result_path, data)
    latest = root / "latest"
    temp_latest = root / (".latest-" + session_id)
    try: temp_latest.unlink()
    except FileNotFoundError: pass
    temp_latest.symlink_to(session.name)
    os.replace(temp_latest, latest)
    return 128 + (-facts["launcher_exit"]) if facts["launcher_exit"] < 0 else facts["launcher_exit"]

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--vm-id", required=True)
    run_parser.add_argument("--appliance-state", required=True)
    run_parser.add_argument("--run-dir", required=True)
    run_parser.add_argument("--log-root")
    run_parser.add_argument("--qmp-timeout", type=float, default=30)
    run_parser.add_argument("--serial-timeout", type=float, default=2)
    run_parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command[:1] == ["--"]: args.command = args.command[1:]
    if not args.command: parser.error("run requires command after --")
    return run(args)

if __name__ == "__main__":
    sys.exit(main())
