#!/usr/bin/env python3
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "scripts" / "reims-host-action.py"
spec = importlib.util.spec_from_file_location("reims_host_action", MODULE_PATH)
action = importlib.util.module_from_spec(spec)
spec.loader.exec_module(action)

class T006HostPoweroffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.session = Path(self.tmp.name) / "session"
        self.session.mkdir()
        self.result_path = self.session / "result.json"
        (self.session / "lifecycle.log").write_text("{\"event\":\"classification\"}\n")
        self.calls = []
        self.order = []

    def tearDown(self):
        self.tmp.cleanup()

    def write_result(self, classification="GUEST_SHUTDOWN", state="installed", recovery=False, **extra):
        result = {"schema": 1, "session_id": "session-test", "classification": classification,
                  "appliance_state": state, "recovery_required": recovery,
                  "launcher_exit_code": 0, "qemu_exit_code": 0}
        result.update(extra)
        self.result_path.write_text(json.dumps(result))
        return result

    def fake_executor(self, command, check=True):
        self.calls.append((command, check))
        self.order.append("systemctl")

    def fake_sync(self):
        self.order.append("sync")

    def test_dry_run_single_poweroff(self):
        self.write_result()
        first = action.consume(self.result_path, mode="dry-run")
        second = action.consume(self.result_path, mode="dry-run")
        self.assertEqual(first["status"], "WOULD_POWEROFF")
        self.assertEqual(second["status"], "ALREADY_CLAIMED")
        events = [json.loads(line)["event"] for line in (self.session / "lifecycle.log").read_text().splitlines()]
        self.assertEqual(events.count("WOULD_POWEROFF"), 1)
        self.assertEqual(json.loads((self.session / "host-action.json").read_text())["schema"], 1)
        print("T006_WOULD_POWEROFF=PASS")
        print("T006_DRY_RUN_IDEMPOTENT=PASS")
        print("T006_HOST_ACTION_AUDIT=PASS")

    def test_default_disabled(self):
        self.write_result()
        old = os.environ.pop("REIMS_HOST_ACTION_MODE", None)
        try:
            result = action.consume(self.result_path)
        finally:
            if old is not None: os.environ["REIMS_HOST_ACTION_MODE"] = old
        self.assertEqual(result["status"], "HOST_ACTION_DISABLED")
        self.assertFalse(self.calls)
        print("T006_DEFAULT_DISABLED=PASS")

    def test_systemd_mock_and_order(self):
        self.write_result()
        result = action.consume(self.result_path, mode="systemd", executor=self.fake_executor, sync_fn=self.fake_sync)
        self.assertEqual(result["status"], "HOST_POWEROFF_REQUESTED")
        self.assertEqual(self.calls, [(["systemctl", "poweroff"], True)])
        self.assertEqual(self.order, ["sync", "systemctl"])
        self.assertTrue((self.session / "host-action.claim").exists())
        again = action.consume(self.result_path, mode="systemd", executor=self.fake_executor, sync_fn=self.fake_sync)
        self.assertEqual(again["status"], "ALREADY_CLAIMED")
        self.assertEqual(len(self.calls), 1)
        print("T006_SYSTEMD_COMMAND=PASS")
        print("T006_SYNC_BEFORE_POWEROFF=PASS")
        print("T006_SYSTEMD_IDEMPOTENT=PASS")

    def test_noneligible_matrix(self):
        cases = [("GUEST_SHUTDOWN", "installing", "T006_INSTALLING_NO_POWEROFF"),
                 ("GUEST_REBOOT", "installed", "T006_REBOOT_NO_POWEROFF"),
                 ("GUEST_KERNEL_PANIC", "installed", "T006_PANIC_NO_POWEROFF"),
                 ("QEMU_FATAL", "installed", "T006_QEMU_FATAL_NO_POWEROFF"),
                 ("REIMS_FATAL", "installed", "T006_REIMS_FATAL_NO_POWEROFF"),
                 ("EXTERNAL_SIGNAL", "installed", "T006_EXTERNAL_SIGNAL_NO_POWEROFF"),
                 ("UNKNOWN_EXIT", "installed", "T006_UNKNOWN_NO_POWEROFF")]
        for classification, state, marker in cases:
            self.write_result(classification, state)
            result = action.consume(self.result_path, mode="dry-run")
            self.assertEqual(result["status"], "NO_ACTION")
            self.assertFalse((self.session / "host-action.claim").exists())
            print(marker + "=PASS")

    def test_guards_and_rc0(self):
        self.write_result(recovery=True)
        self.assertEqual(action.consume(self.result_path, mode="dry-run")["status"], "NO_ACTION")
        print("T006_RECOVERY_GUARD=PASS")
        self.write_result(classification="UNKNOWN_EXIT", launcher_exit_code=0, qemu_exit_code=0)
        self.assertEqual(action.consume(self.result_path, mode="dry-run")["status"], "NO_ACTION")
        print("T006_RC0_NOT_POWEROFF=PASS")
        self.write_result()
        self.assertEqual(action.consume(self.result_path, mode="banana")["status"], "NO_ACTION")
        print("T006_UNKNOWN_MODE_SAFE=PASS")

    def test_final_result_only_and_result_before_action(self):
        self.write_result()
        (self.session / "qemu.log").write_text("VK_ERROR_DEVICE_LOST\nSHUTDOWN\n")
        original = self.result_path.read_bytes()
        seen = []
        def executor(command, check=True):
            seen.append(json.loads(self.result_path.read_text())["classification"])
            self.calls.append((command, check))
        result = action.consume(self.result_path, mode="systemd", executor=executor, sync_fn=lambda: seen.append("synced"))
        self.assertEqual(result["status"], "HOST_POWEROFF_REQUESTED")
        self.assertEqual(seen, ["synced", "GUEST_SHUTDOWN"])
        self.assertEqual(self.result_path.read_bytes(), original)
        self.assertEqual(len(self.calls), 1)
        print("T006_FINAL_RESULT_ONLY=PASS")
        print("T006_RESULT_BEFORE_ACTION=PASS")

    def test_invalid_result_safe(self):
        self.result_path.write_text("not json")
        result = action.consume(self.result_path, mode="systemd", executor=self.fake_executor)
        self.assertEqual(result["status"], "NO_ACTION")
        self.assertFalse(self.calls)
        self.assertTrue(json.loads((self.session / "host-action.json").read_text()))
        self.assertFalse(list(self.session.glob(".host-action.json.*")))
        print("T006_HOST_ACTION_AUDIT=PASS")

if __name__ == "__main__":
    ok = unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.loadTestsFromTestCase(T006HostPoweroffTests)).wasSuccessful()
    if ok: print("T006_CONTROLLED_TEST_PASS")
