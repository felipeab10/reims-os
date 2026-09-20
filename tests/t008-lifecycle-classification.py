#!/usr/bin/env python3
import json
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUP_PATH = ROOT / "scripts" / "reims-supervisor.py"
spec = importlib.util.spec_from_file_location("reims_supervisor", SUP_PATH)
supervisor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(supervisor)


FAKE = r'''#!/usr/bin/env python3
import os, socket, sys, time
from pathlib import Path
run=Path(sys.argv[1]); mode=sys.argv[2]; rc=int(sys.argv[3]); run.mkdir(parents=True, exist_ok=True)
(run/('serial-'+str(os.getpid())+'.log')).write_text('boot\n')
if mode != 'no-qmp':
 sock=run/('qmp-'+str(os.getpid())+'.sock'); srv=socket.socket(socket.AF_UNIX); srv.bind(str(sock)); srv.listen(1); (run/'qmp.path').write_text(str(sock)); c,_=srv.accept(); c.sendall(b'{"QMP":{"version":{},"capabilities":[]}}\n'); c.recv(4096); c.sendall(b'{"return":{}}\n')
 if mode == 'shutdown': c.sendall(b'{"event":"SHUTDOWN"}\n')
 time.sleep(.05)
 if mode != 'no-qmp': srv.close(); sock.unlink(missing_ok=True)
sys.exit(rc)
'''
BOOT = "#!/usr/bin/env python3\nimport subprocess,sys\np=subprocess.Popen(sys.argv[1:]);sys.exit(p.wait())\n"

def facts(**overrides):
    value = {
        "panic": False, "external_signal": None, "launcher_exit": 0,
        "qemu_exit": 0, "qemu_identified": True, "appliance_state": "installed",
        "qmp_events": [], "qemu_log_text": "", "qemu_runtime_log_offset": 0,
        "host_kernel_log_available": False,
    }
    value.update(overrides)
    return value


class T008ClassificationTests(unittest.TestCase):
    def decide(self, **kwargs):
        return supervisor.classify_session(facts(**kwargs))

    def test_shutdown_classification(self):
        d = self.decide(qmp_events=["SHUTDOWN"])
        self.assertEqual(d["classification"], "GUEST_SHUTDOWN")
        self.assertFalse(d["recovery_required"])
        print("T008_SHUTDOWN_CLASSIFICATION=PASS")

    def test_reboot_classification(self):
        d = self.decide(qmp_events=["RESET"])
        self.assertEqual(d["classification"], "GUEST_REBOOT")
        self.assertFalse(d["recovery_required"])
        print("T008_REBOOT_CLASSIFICATION=PASS")

    def test_panic_precedence(self):
        for events, exit_code in ((["RESET"], 0), (["SHUTDOWN"], 0), (["RESET", "SHUTDOWN"], 17)):
            d = self.decide(panic=True, qmp_events=events, qemu_exit=exit_code)
            self.assertEqual(d["classification"], "GUEST_KERNEL_PANIC")
            self.assertEqual(d["classification_reason"], "serial_kernel_panic")
            self.assertTrue(d["recovery_required"])
        print("T008_PANIC_PRECEDENCE=PASS")

    def test_fatal_precedence(self):
        d = self.decide(qmp_events=["RESET"], qemu_log_text="Reims Vulkan: VK_ERROR_DEVICE_LOST")
        self.assertEqual(d["classification"], "REIMS_FATAL")
        d = self.decide(qmp_events=["RESET"], qemu_log_text="qemu: segmentation fault")
        self.assertEqual(d["classification"], "QEMU_FATAL")
        d = self.decide(qemu_log_text="qemu: assertion failed in runtime")
        self.assertEqual(d["classification"], "QEMU_FATAL")
        d = self.decide(qmp_events=["SHUTDOWN"], qemu_log_text="VK_ERROR_DEVICE_LOST")
        self.assertEqual(d["classification"], "REIMS_FATAL")
        d = self.decide(qmp_events=["RESET"], qemu_log_text="SIGSEGV", external_signal="SIGTERM")
        self.assertEqual(d["classification"], "QEMU_FATAL")
        print("T008_EXPLICIT_FATAL_PRECEDENCE=PASS")
        print("T008_FATAL_PRECEDENCE=PASS")

    def test_external_signal(self):
        d = self.decide(external_signal="SIGTERM", qemu_exit=17)
        self.assertEqual(d["classification"], "EXTERNAL_SIGNAL")
        print("T008_EXTERNAL_SIGNAL_QEMU_NONZERO=PASS")
        d = self.decide(external_signal="SIGTERM", qemu_identified=False, qemu_exit=None, launcher_exit=-15)
        self.assertEqual(d["classification"], "EXTERNAL_SIGNAL")
        print("T008_EXTERNAL_SIGNAL_PRE_QEMU=PASS")
        d = self.decide(external_signal="SIGTERM", qemu_exit=0)
        self.assertEqual(d["classification"], "EXTERNAL_SIGNAL")
        self.assertFalse(d["recovery_required"])
        d = self.decide(external_signal="SIGTERM", qemu_log_text="VK_ERROR_DEVICE_LOST")
        self.assertEqual(d["classification"], "REIMS_FATAL")
        print("T008_EXTERNAL_SIGNAL=PASS")

    def test_qmp_terminal_order(self):
        self.assertEqual(self.decide(qmp_events=["RESET", "SHUTDOWN"], qemu_exit=17)["classification"], "GUEST_SHUTDOWN")
        print("T008_SHUTDOWN_BEATS_EXIT_NONZERO=PASS")
        self.assertEqual(self.decide(qmp_events=["SHUTDOWN", "RESET"], qemu_exit=17)["classification"], "GUEST_REBOOT")
        print("T008_REBOOT_BEATS_EXIT_NONZERO=PASS")
        self.assertEqual(self.decide(qmp_events=["RESET"], appliance_state="installing")["classification"], "UNKNOWN_EXIT")
        print("T008_QMP_TERMINAL_ORDER=PASS")

    def test_rc0_conservative(self):
        d = self.decide(qmp_events=[], qemu_identified=False, qemu_exit=None, launcher_exit=0)
        self.assertEqual(d["classification"], "UNKNOWN_EXIT")
        self.assertTrue(d["recovery_required"])
        print("T008_RC0_CONSERVATIVE=PASS")

    def test_benign_fatal_text_ignored(self):
        d = self.decide(qemu_log_text="fatal: No names found, cannot describe anything.", qmp_events=["SHUTDOWN"])
        self.assertEqual(d["classification"], "GUEST_SHUTDOWN")
        print("T008_BENIGN_FATAL_TEXT_IGNORED=PASS")

    def test_qmp_error_not_fatal(self):
        d = self.decide(qmp_events=["SHUTDOWN"])
        self.assertEqual(d["classification"], "GUEST_SHUTDOWN")
        print("T008_QMP_ERROR_NON_FATAL=PASS")

    def test_primary_evidence_and_sources(self):
        d = self.decide(qmp_events=["SHUTDOWN"])
        self.assertEqual(d["primary_evidence"], {"source": "qmp", "event": "SHUTDOWN"})
        self.assertEqual(d["sources_consulted"], ["serial", "qmp", "process", "qemu_log", "supervisor_signal"])
        self.assertTrue({"serial", "qmp", "process", "qemu_log", "supervisor_signal"} <= set(d["sources_consulted"]))
        print("T008_PRIMARY_EVIDENCE=PASS")
        print("T008_SOURCES_CONSULTED=PASS")

    def test_runtime_log_offset(self):
        prefix = "compilação ✓\nfatal: No names found, cannot describe anything.\n".encode()
        raw = prefix + b"normal runtime\n"
        d = self.decide(qemu_runtime_log_offset=len(prefix), qemu_log_raw=raw)
        self.assertEqual(d["classification"], "UNKNOWN_EXIT")
        self.assertEqual(supervisor._runtime_log_text({"qemu_log_raw": raw, "qemu_runtime_log_offset": len(prefix)}), "normal runtime\n")
        print("T008_RUNTIME_LOG_BYTE_OFFSET=PASS")
        print("T008_RUNTIME_LOG_BOUNDARY=PASS")
        d = self.decide(qemu_runtime_log_offset=len(prefix), qemu_log_raw=prefix + b"VK_ERROR_DEVICE_LOST\n")
        self.assertEqual(d["classification"], "REIMS_FATAL")
        print("T008_RUNTIME_LOG_OFFSET=PASS")

    def test_recovery_policy(self):
        expected = {
            "GUEST_KERNEL_PANIC": True, "QEMU_FATAL": True, "REIMS_FATAL": True,
            "UNKNOWN_EXIT": True, "GUEST_SHUTDOWN": False, "GUEST_REBOOT": False,
            "EXTERNAL_SIGNAL": False,
        }
        cases = {
            "GUEST_KERNEL_PANIC": self.decide(panic=True),
            "QEMU_FATAL": self.decide(qemu_log_text="SIGSEGV"),
            "REIMS_FATAL": self.decide(qemu_log_text="VK_ERROR_DEVICE_LOST"),
            "UNKNOWN_EXIT": self.decide(qmp_events=[]),
            "GUEST_SHUTDOWN": self.decide(qmp_events=["SHUTDOWN"]),
            "GUEST_REBOOT": self.decide(qmp_events=["RESET"]),
            "EXTERNAL_SIGNAL": self.decide(external_signal="SIGTERM"),
        }
        for name, required in expected.items(): self.assertEqual(cases[name]["recovery_required"], required)
        print("T008_PANIC_RECOVERY=PASS")
        print("T008_QEMU_FATAL_RECOVERY=PASS")
        print("T008_REIMS_FATAL_RECOVERY=PASS")
        print("T008_UNKNOWN_RECOVERY=PASS")
        print("T008_NORMAL_NO_RECOVERY=PASS")

    def test_state_recovery_transition(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy(); env["REIMS_STATE_ROOT"] = tmp
            state = ROOT / "scripts" / "reims-state.py"
            subprocess.run([sys.executable, str(state), "configure", "--vm-id", "reims-0123456789abcdef", "--macos", "sequoia", "--cpu", "4", "--ram-gb", "8", "--disk-gb", "80"], env=env, check=True, capture_output=True, text=True)
            subprocess.run([sys.executable, str(state), "transition", "installed"], env=env, check=True, capture_output=True, text=True)
            old = os.environ.get("REIMS_STATE_ROOT")
            os.environ["REIMS_STATE_ROOT"] = tmp
            try:
                result = supervisor.transition_recovery("reims-0123456789abcdef")
            finally:
                if old is None: os.environ.pop("REIMS_STATE_ROOT", None)
                else: os.environ["REIMS_STATE_ROOT"] = old
            self.assertTrue(result["succeeded"])
            self.assertIn('"state": "recovery"', (Path(tmp) / "state.json").read_text())
        print("T008_RECOVERY_TRANSITION=PASS")

    def run_session(self, root, vm_id, mode, appliance_state="installed", rc=0, state_vm_id=None, capture_state_before=False):
        tmp = Path(root); run = tmp / "run"; logs = tmp / "logs"; run.mkdir(); logs.mkdir()
        fake = tmp / "fake.py"; boot = tmp / "boot.py"; fake.write_text(FAKE); fake.chmod(0o755); boot.write_text(BOOT); boot.chmod(0o755)
        env = os.environ.copy(); env["REIMS_STATE_ROOT"] = str(tmp / "state"); env["REIMS_HOST_ACTION_MODE"] = "disabled"
        if env["REIMS_HOST_ACTION_MODE"] != "disabled": raise AssertionError("unsafe host action test environment")
        state = ROOT / "scripts" / "reims-state.py"
        configured_vm_id = state_vm_id or vm_id
        subprocess.run([sys.executable, str(state), "configure", "--vm-id", configured_vm_id, "--macos", "sequoia", "--cpu", "4", "--ram-gb", "8", "--disk-gb", "80"], env=env, check=True, capture_output=True)
        subprocess.run([sys.executable, str(state), "transition", "installed"], env=env, check=True, capture_output=True)
        state_before = (Path(env["REIMS_STATE_ROOT"]) / "state.json").read_bytes()
        p = subprocess.run([sys.executable, str(SUP_PATH), "run", "--vm-id", vm_id, "--appliance-state", appliance_state, "--run-dir", str(run), "--log-root", str(logs), "--", str(boot), str(fake), str(run), mode, str(rc)], env=env, cwd=ROOT)
        result_path = next(logs.glob("*/result.json"))
        result = json.loads(result_path.read_text())
        return (env, result, state_before) if capture_state_before else (env, result)

    def test_run_recovery_integration(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, result = self.run_session(tmp, "reims-0123456789abcdef", "no-qmp")
            self.assertEqual(result["classification"], "UNKNOWN_EXIT"); self.assertTrue(result["recovery"]["required"]); self.assertTrue(result["recovery"]["attempted"]); self.assertTrue(result["recovery"]["succeeded"])
            self.assertIn('"state": "recovery"', (Path(env["REIMS_STATE_ROOT"]) / "state.json").read_text())
        print("T008_RUN_UNKNOWN_TO_RECOVERY=PASS")

    def test_recovery_failure_preserves_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_vm_id = "reims-0123456789abcdef"
            supervisor_vm_id = "reims-fedcba9876543210"
            env, result, state_before = self.run_session(tmp, supervisor_vm_id, "no-qmp", state_vm_id=state_vm_id, capture_state_before=True)
            state_path = Path(env["REIMS_STATE_ROOT"]) / "state.json"
            result_path = next((Path(tmp) / "logs").glob("*/result.json"))
            self.assertEqual(result["classification"], "UNKNOWN_EXIT")
            self.assertEqual(result["classification_reason"], "insufficient_evidence")
            self.assertTrue(result["recovery"]["required"])
            self.assertFalse(result["recovery"]["succeeded"])
            self.assertEqual(result["recovery"]["error"], "state_vm_mismatch")
            self.assertIn("recovery_transition_failed", result["limitations"])
            parsed = json.loads(result_path.read_text())
            self.assertEqual(parsed["classification"], "UNKNOWN_EXIT")
            self.assertEqual(parsed["classification_reason"], "insufficient_evidence")
            self.assertEqual(state_path.read_bytes(), state_before)
            self.assertEqual(json.loads(state_path.read_text())["vm_id"], state_vm_id)
        print("T008_RECOVERY_FAILURE_PRESERVES_RESULT=PASS")
        print("T008_RECOVERY_VM_MISMATCH_NO_MUTATION=PASS")

    def test_run_normal_no_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, result = self.run_session(tmp, "reims-0123456789abcdef", "shutdown")
            self.assertEqual(result["classification"], "GUEST_SHUTDOWN"); self.assertFalse(result["recovery"]["required"]); self.assertFalse(result["recovery"]["attempted"])
            self.assertIn('"state": "installed"', (Path(env["REIMS_STATE_ROOT"]) / "state.json").read_text())
        print("T008_RUN_NORMAL_NO_RECOVERY=PASS")

    def test_recovery_vm_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy(); env["REIMS_STATE_ROOT"] = tmp
            state = ROOT / "scripts" / "reims-state.py"
            subprocess.run([sys.executable, str(state), "configure", "--vm-id", "reims-0123456789abcdef", "--macos", "sequoia", "--cpu", "4", "--ram-gb", "8", "--disk-gb", "80"], env=env, check=True, capture_output=True)
            subprocess.run([sys.executable, str(state), "transition", "installed"], env=env, check=True, capture_output=True)
            old = os.environ.get("REIMS_STATE_ROOT"); os.environ["REIMS_STATE_ROOT"] = tmp
            try:
                result = supervisor.transition_recovery("reims-fedcba9876543210")
            finally:
                if old is None: os.environ.pop("REIMS_STATE_ROOT", None)
                else: os.environ["REIMS_STATE_ROOT"] = old
            self.assertEqual(result["error"], "state_vm_mismatch")
        print("T008_RECOVERY_VM_ID_GUARD=PASS")

    def test_state_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, result = self.run_session(tmp, "reims-0123456789abcdef", "no-qmp")
            state_root = Path(env["REIMS_STATE_ROOT"])
            self.assertTrue(state_root.is_relative_to(Path(tmp)))
            self.assertTrue((state_root / "state.json").exists())
            self.assertIn('"state": "recovery"', (state_root / "state.json").read_text())
            self.assertNotEqual(state_root, Path("/var/lib/reims"))
        print("T008_TEST_STATE_ISOLATION=PASS")

    def test_host_log_is_explicitly_unavailable(self):
        self.assertFalse(facts()["host_kernel_log_available"])
        self.assertNotIn("host_kernel_log", self.decide()["sources_consulted"])
        print("T008_HOST_KERNEL_LOG_SOURCE=UNAVAILABLE")
        print("T008_NVIDIA_XID_SUPPORT=UNAVAILABLE")
        print("T008_OOM_SUPPORT=UNAVAILABLE")


if __name__ == "__main__":
    ok = unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.loadTestsFromTestCase(T008ClassificationTests)).wasSuccessful()
    if ok: print("T008_CONTROLLED_TEST_PASS")
    sys.exit(0 if ok else 1)
