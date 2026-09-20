#!/usr/bin/env python3
"""Consume a persisted T008 result and optionally request a host lifecycle action."""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ALLOWED_MODES = {"disabled", "dry-run", "systemd"}
ELIGIBLE = {"GUEST_SHUTDOWN": "poweroff", "GUEST_REBOOT": "reboot"}
ACTION_STATUSES = {
    "poweroff": {"WOULD_POWEROFF", "HOST_POWEROFF_REQUESTED", "HOST_POWEROFF_FAILED"},
    "reboot": {"WOULD_REBOOT", "HOST_REBOOT_REQUESTED", "HOST_REBOOT_FAILED"},
}

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def append_event(path, event, **extra):
    row = {"timestamp": now(), "source": "host_action", "event": event}
    row.update(extra)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())

def _audit(session, result, mode, status, error=None):
    value = {
        "schema": 1,
        "session_id": result.get("session_id", session.name),
        "classification": result.get("classification"),
        "appliance_state": result.get("appliance_state"),
        "action": next((action for action, statuses in ACTION_STATUSES.items() if status in statuses), "none"),
        "mode": mode,
        "status": status,
        "timestamp": now(),
    }
    if error is not None:
        value["error"] = error
    atomic_json(session / "host-action.json", value)
    return value

def _existing_audit(session):
    try:
        return json.loads((session / "host-action.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

def _claim(session):
    claim = session / "host-action.claim"
    try:
        fd = os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(now() + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return True
    except FileExistsError:
        return False

def _load_result(result_path):
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, "result_unreadable: " + str(exc)
    if result.get("schema") != 1:
        return None, "schema_unknown"
    for field in ("classification", "appliance_state", "recovery_required"):
        if field not in result:
            return None, "result_missing_" + field
    return result, None

def consume(result_path, mode=None, executor=None, sync_fn=None):
    result_path = Path(result_path)
    session = result_path.parent
    mode = os.environ.get("REIMS_HOST_ACTION_MODE", "disabled") if mode is None else mode
    lifecycle = session / "lifecycle.log"
    result, error = _load_result(result_path)
    if error:
        audit = _audit(session, {"session_id": session.name}, mode, "NO_ACTION", error)
        if lifecycle.parent.exists(): append_event(lifecycle, "HOST_ACTION_INVALID_RESULT", error=error)
        return audit
    if mode not in ALLOWED_MODES:
        audit = _audit(session, result, mode, "NO_ACTION", "unknown_mode")
        append_event(lifecycle, "HOST_ACTION_INVALID_MODE", mode=mode)
        return audit
    action = ELIGIBLE.get(result["classification"])
    eligible = (action is not None and result["appliance_state"] == "installed" and
                result["recovery_required"] is False)
    if not eligible:
        audit = _audit(session, result, mode, "NO_ACTION", "not_eligible")
        append_event(lifecycle, "HOST_ACTION_NO_ACTION", reason="not_eligible")
        return audit
    if mode == "disabled":
        audit = _audit(session, result, mode, "HOST_ACTION_DISABLED")
        append_event(lifecycle, "HOST_ACTION_DISABLED", action=action)
        return audit
    if not _claim(session):
        existing = _existing_audit(session)
        append_event(lifecycle, "HOST_ACTION_ALREADY_CLAIMED")
        if existing is not None:
            response = dict(existing)
            response["status"] = "ALREADY_CLAIMED"
            return response
        return {"status": "ALREADY_CLAIMED"}
    if mode == "dry-run":
        status = "WOULD_" + action.upper()
        audit = _audit(session, result, mode, status)
        append_event(lifecycle, status)
        return audit
    requested = "HOST_" + action.upper() + "_REQUESTED"
    failed = "HOST_" + action.upper() + "_FAILED"
    audit = _audit(session, result, mode, requested)
    append_event(lifecycle, requested)
    try:
        (sync_fn if sync_fn is not None else os.sync)()
    except Exception as exc:
        error = "sync_failed: " + str(exc)
        audit = _audit(session, result, mode, failed, error)
        append_event(lifecycle, failed, error=error)
        return audit
    try:
        (executor or subprocess.run)(["systemctl", action], check=True)
    except Exception as exc:
        audit = _audit(session, result, mode, failed, str(exc))
        append_event(lifecycle, failed, error=str(exc))
    return audit

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("result_json", type=Path)
    args = parser.parse_args()
    audit = consume(args.result_json)
    return 0 if audit["status"] not in {"HOST_POWEROFF_FAILED", "HOST_REBOOT_FAILED"} else 1

if __name__ == "__main__":
    sys.exit(main())
