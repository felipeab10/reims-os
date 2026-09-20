#!/usr/bin/env python3
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "scripts" / "reims-host-action.py"
T005_PATH = ROOT / "tests" / "t005-supervisor.py"
spec5 = importlib.util.spec_from_file_location("t005_fixture", T005_PATH)
t005_fixture = importlib.util.module_from_spec(spec5)
spec5.loader.exec_module(t005_fixture)
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
                 ("GUEST_REBOOT", "installing", "T006_REBOOT_NO_POWEROFF"),
                 ("GUEST_KERNEL_PANIC", "installed", "T006_PANIC_NO_POWEROFF"),
                 ("QEMU_FATAL", "installed", "T006_QEMU_FATAL_NO_POWEROFF"),
                 ("REIMS_FATAL", "installed", "T006_REIMS_FATAL_NO_POWEROFF"),
                 ("EXTERNAL_SIGNAL", "installed", "T006_EXTERNAL_SIGNAL_NO_POWEROFF"),
                 ("UNKNOWN_EXIT", "installed", "T006_UNKNOWN_NO_POWEROFF")]
        for classification, state, marker in cases:
            self.session.joinpath("host-action.claim").unlink(missing_ok=True)
            self.write_result(classification, state)
            result = action.consume(self.result_path, mode="dry-run")
            expected = "WOULD_REBOOT" if classification == "GUEST_REBOOT" and state == "installed" else "NO_ACTION"
            self.assertEqual(result["status"], expected)
            if classification == "GUEST_REBOOT" and state == "installed":
                self.assertEqual(result["action"], "reboot")
                self.assertFalse(self.calls)
                self.assertFalse((self.session / "host-action.claim").exists())
            else:
                self.assertEqual(result["action"], "none")
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

    def test_audit_preservation_and_disabled_claim(self):
        self.write_result()
        first = action.consume(self.result_path, mode="dry-run")
        original = json.loads((self.session / "host-action.json").read_text())
        second = action.consume(self.result_path, mode="dry-run")
        self.assertEqual(second["status"], "ALREADY_CLAIMED")
        self.assertEqual(json.loads((self.session / "host-action.json").read_text()), original)
        print("T006_IDEMPOTENT_AUDIT_PRESERVED=PASS")
        self.session.joinpath("host-action.claim").unlink()
        self.write_result()
        disabled = action.consume(self.result_path, mode="disabled")
        self.assertEqual(disabled["status"], "HOST_ACTION_DISABLED")
        self.assertFalse((self.session / "host-action.claim").exists())
        dry = action.consume(self.result_path, mode="dry-run")
        self.assertEqual(dry["status"], "WOULD_POWEROFF")
        print("T006_DISABLED_NO_CLAIM=PASS")

    def test_systemd_and_sync_failures_preserve_audit(self):
        self.write_result()
        failed = action.consume(self.result_path, mode="systemd", executor=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("systemctl denied")), sync_fn=lambda: None)
        self.assertEqual(failed["status"], "HOST_POWEROFF_FAILED")
        original = json.loads((self.session / "host-action.json").read_text())
        again = action.consume(self.result_path, mode="systemd", executor=self.fake_executor)
        self.assertEqual(again["status"], "ALREADY_CLAIMED")
        self.assertEqual(json.loads((self.session / "host-action.json").read_text()), original)
        print("T006_SYSTEMD_FAILURE_AUDIT=PASS")
        print("T006_FAILED_AUDIT_PRESERVED=PASS")
        self.session.joinpath("host-action.claim").unlink()
        self.write_result()
        sync_failed = action.consume(self.result_path, mode="systemd", executor=self.fake_executor, sync_fn=lambda: (_ for _ in ()).throw(RuntimeError("flush failed")))
        self.assertEqual(sync_failed["status"], "HOST_POWEROFF_FAILED")
        self.assertIn("sync_failed", sync_failed["error"])
        self.assertFalse(self.calls)
        print("T006_SYNC_FAILURE_NO_POWEROFF=PASS")

    def test_supervisor_integration(self):
        fake = self.session.parent / "fake.py"
        fake.write_text(t005_fixture.FAKE)
        fake.chmod(0o755)
        boot = self.session.parent / "boot.py"; boot.write_text(t005_fixture.BOOT); boot.chmod(0o755)
        run = self.session.parent / "run"; logs = self.session.parent / "logs"; run.mkdir(); logs.mkdir()
        env = os.environ.copy(); env["REIMS_STATE_ROOT"] = str(self.session.parent / "state"); env["REIMS_HOST_ACTION_MODE"] = "dry-run"
        state = ROOT / "scripts" / "reims-state.py"
        subprocess.run([sys.executable, str(state), "configure", "--vm-id", "reims-0123456789abcdef", "--macos", "sequoia", "--cpu", "4", "--ram-gb", "8", "--disk-gb", "80"], env=env, check=True, capture_output=True)
        subprocess.run([sys.executable, str(state), "transition", "installed"], env=env, check=True, capture_output=True)
        proc = subprocess.run([sys.executable, str(ROOT / "scripts/reims-supervisor.py"), "run", "--vm-id", "reims-0123456789abcdef", "--appliance-state", "installed", "--run-dir", str(run), "--log-root", str(logs), "--", str(boot), str(fake), str(run), "shutdown", "0", "0.15", "0"], env=env, cwd=ROOT, capture_output=True, text=True)
        session = next(logs.glob("*/result.json")).parent
        result_path = session / "result.json"
        host_action_path = session / "host-action.json"
        self.assertTrue(result_path.exists())
        result = json.loads(result_path.read_text())
        if result["classification"] != "GUEST_SHUTDOWN":
            raise AssertionError(json.dumps({"result": result, "stderr": proc.stderr, "stdout": proc.stdout}, indent=2))
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(host_action_path.exists())
        audit = json.loads(host_action_path.read_text())
        self.assertEqual(audit["status"], "WOULD_POWEROFF")
        self.assertEqual(audit["classification"], "GUEST_SHUTDOWN")
        self.assertEqual(audit["appliance_state"], "installed")
        events = [json.loads(line)["event"] for line in (session / "lifecycle.log").read_text().splitlines()]
        self.assertLess(events.index("classification"), events.index("WOULD_POWEROFF"))
        self.assertEqual(events.count("WOULD_POWEROFF"), 1)
        print("T006_SUPERVISOR_INTEGRATION=PASS"); print("T006_RESULT_BEFORE_ACTION=PASS"); print("T006_CLASSIFICATION_BEFORE_ACTION=PASS")

    def test_supervisor_unknown_no_poweroff(self):
        fake = self.session.parent / "fake.py"
        fake.write_text(t005_fixture.FAKE)
        fake.chmod(0o755)
        boot = self.session.parent / "boot.py"; boot.write_text(t005_fixture.BOOT); boot.chmod(0o755)
        run = self.session.parent / "run"; logs = self.session.parent / "logs"; run.mkdir(); logs.mkdir()
        env = os.environ.copy(); env["REIMS_STATE_ROOT"] = str(self.session.parent / "state"); env["REIMS_HOST_ACTION_MODE"] = "dry-run"
        state = ROOT / "scripts" / "reims-state.py"
        vm_id = "reims-0123456789abcdef"
        subprocess.run([sys.executable, str(state), "configure", "--vm-id", vm_id, "--macos", "sequoia", "--cpu", "4", "--ram-gb", "8", "--disk-gb", "80"], env=env, check=True, capture_output=True)
        subprocess.run([sys.executable, str(state), "transition", "installed"], env=env, check=True, capture_output=True)
        proc = subprocess.run([sys.executable, str(ROOT / "scripts/reims-supervisor.py"), "run", "--vm-id", vm_id, "--appliance-state", "installed", "--run-dir", str(run), "--log-root", str(logs), "--", str(boot), str(fake), str(run), "no-qmp", "0", "0.15", "0"], env=env, cwd=ROOT, capture_output=True, text=True)
        session = next(logs.glob("*/result.json")).parent
        result_path = session / "result.json"; host_action_path = session / "host-action.json"
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(result_path.exists()); result = json.loads(result_path.read_text())
        self.assertEqual(result["classification"], "UNKNOWN_EXIT")
        self.assertTrue(host_action_path.exists()); audit = json.loads(host_action_path.read_text())
        self.assertEqual(audit["status"], "NO_ACTION")
        events = [json.loads(line)["event"] for line in (session / "lifecycle.log").read_text().splitlines()]
        self.assertNotIn("WOULD_POWEROFF", events)
        self.assertFalse((session / "host-action.claim").exists())
        print("T006_SUPERVISOR_UNKNOWN_NO_POWEROFF=PASS")

    def test_consumer_failure_preserves_result_and_rc(self):
        fake = self.session.parent / "fake.py"
        fake.write_text(t005_fixture.FAKE)
        fake.chmod(0o755)
        boot = self.session.parent / "boot.py"; boot.write_text(t005_fixture.BOOT); boot.chmod(0o755)
        fake_bin = self.session.parent / "bin"; fake_bin.mkdir()
        systemctl_log = self.session.parent / "systemctl.argv"
        fake_systemctl = fake_bin / "systemctl"
        fake_systemctl.write_text("#!/bin/sh\nprintf '%s\n' \"$@\" > \"$SYSTEMCTL_LOG\"\nexit 77\n")
        fake_systemctl.chmod(0o755)
        run = self.session.parent / "run"; logs = self.session.parent / "logs"; run.mkdir(); logs.mkdir()
        env = os.environ.copy()
        env["REIMS_STATE_ROOT"] = str(self.session.parent / "state")
        env["REIMS_HOST_ACTION_MODE"] = "systemd"
        env["SYSTEMCTL_LOG"] = str(systemctl_log)
        env["PATH"] = str(fake_bin) + os.pathsep + env["PATH"]
        state = ROOT / "scripts" / "reims-state.py"
        vm_id = "reims-0123456789abcdef"
        subprocess.run([sys.executable, str(state), "configure", "--vm-id", vm_id, "--macos", "sequoia", "--cpu", "4", "--ram-gb", "8", "--disk-gb", "80"], env=env, check=True, capture_output=True)
        subprocess.run([sys.executable, str(state), "transition", "installed"], env=env, check=True, capture_output=True)
        proc = subprocess.run([sys.executable, str(ROOT / "scripts/reims-supervisor.py"), "run", "--vm-id", vm_id, "--appliance-state", "installed", "--run-dir", str(run), "--log-root", str(logs), "--", str(boot), str(fake), str(run), "shutdown", "0", "0.15", "0"], env=env, cwd=ROOT, capture_output=True, text=True)
        session = next(logs.glob("*/result.json")).parent
        result_path = session / "result.json"; host_action_path = session / "host-action.json"
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(result_path.exists())
        result = json.loads(result_path.read_text())
        self.assertEqual(result["classification"], "GUEST_SHUTDOWN")
        self.assertEqual(result["classification_reason"], "qmp_guest_shutdown")
        self.assertTrue(host_action_path.exists())
        audit = json.loads(host_action_path.read_text())
        self.assertEqual(audit["status"], "HOST_POWEROFF_FAILED")
        self.assertIn("77", audit["error"])
        self.assertTrue(systemctl_log.exists())
        self.assertEqual(systemctl_log.read_text().splitlines(), ["poweroff"])
        events = [json.loads(line)["event"] for line in (session / "lifecycle.log").read_text().splitlines()]
        for event in ("classification", "HOST_POWEROFF_REQUESTED", "HOST_POWEROFF_FAILED", "HOST_ACTION_CONSUMER_FAILED"):
            self.assertIn(event, events)
        self.assertLess(events.index("classification"), events.index("HOST_POWEROFF_REQUESTED"))
        self.assertLess(events.index("HOST_POWEROFF_REQUESTED"), events.index("HOST_POWEROFF_FAILED"))
        self.assertLess(events.index("HOST_POWEROFF_FAILED"), events.index("HOST_ACTION_CONSUMER_FAILED"))
        print("T006_CONSUMER_FAILURE_PRESERVES_RESULT=PASS")
        print("T006_CONSUMER_FAILURE_PRESERVES_RC=PASS")
        print("T006_CONSUMER_FAILURE_FAKE_SYSTEMCTL=PASS")

    def test_regression_harnesses_force_disabled(self):
        t005 = (ROOT / "tests/t005-supervisor.py").read_text()
        t008 = (ROOT / "tests/t008-lifecycle-classification.py").read_text()
        self.assertIn("REIMS_HOST_ACTION_MODE']='disabled'", t005)
        self.assertIn('REIMS_HOST_ACTION_MODE"] = "disabled"', t008)
        print("T006_REGRESSION_HOST_ACTION_DISABLED=PASS")

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
