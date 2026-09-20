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
ACTION_PATH = ROOT / "scripts/reims-host-action.py"
T005_PATH = ROOT / "tests/t005-supervisor.py"
spec = importlib.util.spec_from_file_location("reims_host_action", ACTION_PATH)
action = importlib.util.module_from_spec(spec); spec.loader.exec_module(action)
spec5 = importlib.util.spec_from_file_location("t005_fixture", T005_PATH)
t005 = importlib.util.module_from_spec(spec5); spec5.loader.exec_module(t005)

class T007HostRebootTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.session = Path(self.tmp.name) / "session"; self.session.mkdir()
        self.result_path = self.session / "result.json"; (self.session / "lifecycle.log").write_text('{"event":"classification"}\n')
        self.calls = []; self.order = []
    def tearDown(self): self.tmp.cleanup()
    def write_result(self, classification="GUEST_REBOOT", state="installed", recovery=False):
        self.result_path.write_text(json.dumps({"schema":1,"session_id":"t007","classification":classification,"appliance_state":state,"recovery_required":recovery}))
    def executor(self, command, check=True): self.calls.append((command,check)); self.order.append("systemctl")
    def sync(self): self.order.append("sync")
    def test_reboot_dry_run_and_idempotence(self):
        self.write_result(); first=action.consume(self.result_path, mode="dry-run"); second=action.consume(self.result_path, mode="dry-run")
        self.assertEqual(first["action"],"reboot"); self.assertEqual(first["status"],"WOULD_REBOOT"); self.assertEqual(second["status"],"ALREADY_CLAIMED")
        audit=json.loads((self.session/"host-action.json").read_text()); self.assertEqual(audit["status"],"WOULD_REBOOT"); self.assertEqual(audit["action"],"reboot")
        print("T007_WOULD_REBOOT=PASS"); print("T007_REBOOT_IDEMPOTENT=PASS")
    def test_reboot_systemd_command_and_order(self):
        self.write_result(); result=action.consume(self.result_path, mode="systemd", executor=self.executor, sync_fn=self.sync)
        self.assertEqual(result["status"],"HOST_REBOOT_REQUESTED"); self.assertEqual(self.calls,[(["systemctl","reboot"],True)]); self.assertEqual(self.order,["sync","systemctl"])
        print("T007_SYSTEMD_REBOOT_COMMAND=PASS"); print("T007_SYNC_BEFORE_REBOOT=PASS")
    def test_guards_and_separation(self):
        for classification,state,marker in [("GUEST_REBOOT","installing","T007_INSTALLING_NO_REBOOT"),("GUEST_SHUTDOWN","installed","T007_SHUTDOWN_IS_POWEROFF"),("GUEST_KERNEL_PANIC","installed","T007_PANIC_NO_REBOOT"),("QEMU_FATAL","installed","T007_QEMU_FATAL_NO_REBOOT"),("REIMS_FATAL","installed","T007_REIMS_FATAL_NO_REBOOT"),("EXTERNAL_SIGNAL","installed","T007_EXTERNAL_SIGNAL_NO_REBOOT"),("UNKNOWN_EXIT","installed","T007_UNKNOWN_NO_REBOOT")]:
            self.session.joinpath("host-action.claim").unlink(missing_ok=True); self.write_result(classification,state); result=action.consume(self.result_path,mode="dry-run"); expected="WOULD_POWEROFF" if classification == "GUEST_SHUTDOWN" else "NO_ACTION"; self.assertEqual(result["status"],expected); self.assertFalse((self.session/"host-action.claim").exists()) if expected == "NO_ACTION" else None; print(marker+"=PASS")
    def test_disabled_unknown_recovery_and_final_only(self):
        self.write_result(); self.assertEqual(action.consume(self.result_path,mode="disabled")["status"],"HOST_ACTION_DISABLED"); self.assertFalse((self.session/"host-action.claim").exists())
        self.write_result(recovery=True); self.assertEqual(action.consume(self.result_path,mode="dry-run")["status"],"NO_ACTION")
        self.write_result(); self.assertEqual(action.consume(self.result_path,mode="banana")["status"],"NO_ACTION"); self.session.joinpath("host-action.claim").unlink(missing_ok=True); self.write_result(); (self.session/"qemu.log").write_text("VK_ERROR_DEVICE_LOST SHUTDOWN"); (self.session/"serial.log").write_text("Debugger called: <panic>"); original=self.result_path.read_bytes(); result=action.consume(self.result_path,mode="dry-run"); self.assertEqual(result["action"],"reboot"); self.assertEqual(result["status"],"WOULD_REBOOT"); self.assertEqual(self.result_path.read_bytes(),original)
        self.session.joinpath("host-action.claim").unlink(); self.write_result(); calls=[]; result=action.consume(self.result_path,mode="systemd",executor=lambda command,check=True: calls.append((command,check)),sync_fn=self.sync); self.assertEqual(result["status"],"HOST_REBOOT_REQUESTED"); self.assertEqual(calls,[(["systemctl","reboot"],True)])
        print("T007_DISABLED_NO_CLAIM=PASS"); print("T007_RECOVERY_GUARD=PASS"); print("T007_UNKNOWN_MODE_SAFE=PASS"); print("T007_FINAL_RESULT_ONLY=PASS")

    def test_installing_systemd_no_reboot(self):
        self.write_result(state="installing"); calls=[]; result=action.consume(self.result_path,mode="systemd",executor=lambda *args,**kwargs: calls.append(args))
        self.assertEqual(result["status"],"NO_ACTION"); self.assertEqual(result["action"],"none"); self.assertEqual(calls,[]); self.assertFalse((self.session/"host-action.claim").exists()); events=[json.loads(x)["event"] for x in (self.session/"lifecycle.log").read_text().splitlines()]; self.assertNotIn("HOST_REBOOT_REQUESTED",events); self.assertNotIn("HOST_REBOOT_FAILED",events)
        print("T007_INSTALLING_SYSTEMD_NO_REBOOT=PASS")
    def test_failure_audit_preserved(self):
        self.write_result(); failed=action.consume(self.result_path,mode="systemd",executor=lambda *a,**k: (_ for _ in ()).throw(RuntimeError("reboot denied")),sync_fn=self.sync); self.assertEqual(failed["status"],"HOST_REBOOT_FAILED"); original=json.loads((self.session/"host-action.json").read_text()); again=action.consume(self.result_path,mode="systemd",executor=self.executor); self.assertEqual(again["status"],"ALREADY_CLAIMED"); self.assertEqual(json.loads((self.session/"host-action.json").read_text()),original)
        self.session.joinpath("host-action.claim").unlink(); self.write_result(); failed=action.consume(self.result_path,mode="systemd",executor=self.executor,sync_fn=lambda: (_ for _ in ()).throw(RuntimeError("flush failed"))); self.assertEqual(failed["status"],"HOST_REBOOT_FAILED"); self.assertFalse(self.calls)
        print("T007_FAILURE_AUDIT_PRESERVED=PASS"); print("T007_SYNC_FAILURE_NO_REBOOT=PASS")
    def test_supervisor_installing_no_reboot(self):
        """The fake exits after RESET; real installer QEMU reset continuity is separately documented."""
        p,s=self.run_supervisor("reset","installing"); result=json.loads((s/"result.json").read_text()); audit=json.loads((s/"host-action.json").read_text()); self.assertEqual(result["classification"],"UNKNOWN_EXIT"); self.assertEqual(audit["status"],"NO_ACTION"); self.assertFalse((s/"host-action.claim").exists()); print("T007_SUPERVISOR_INSTALLING_NO_REBOOT=PASS"); print("T007_FAKE_RESET_LIMITATION=PASS")

    def run_supervisor(self, mode, state):
        root=Path(self.tmp.name)/mode+Path(state) if False else Path(self.tmp.name)/("integration-"+mode+"-"+state); root.mkdir(); run=root/"run"; logs=root/"logs"; run.mkdir(); logs.mkdir(); fake=root/"fake.py"; fake.write_text(t005.FAKE); fake.chmod(0o755); boot=root/"boot.py"; boot.write_text(t005.BOOT); boot.chmod(0o755); env=os.environ.copy(); env["REIMS_STATE_ROOT"]=str(root/"state"); env["REIMS_HOST_ACTION_MODE"]="dry-run"; vm="reims-0123456789abcdef"; st=ROOT/"scripts/reims-state.py"; subprocess.run([sys.executable,str(st),"configure","--vm-id",vm,"--macos","sequoia","--cpu","4","--ram-gb","8","--disk-gb","80"],env=env,check=True,capture_output=True); subprocess.run([sys.executable,str(st),"transition",state],env=env,check=True,capture_output=True); p=subprocess.run([sys.executable,str(ROOT/"scripts/reims-supervisor.py"),"run","--vm-id",vm,"--appliance-state",state,"--run-dir",str(run),"--log-root",str(logs),"--",str(boot),str(fake),str(run),mode,"0","0.15","0"],env=env,cwd=ROOT); session=next(logs.glob("*/result.json")).parent; return p,session
    def test_supervisor_reboot_integration(self):
        p,s=self.run_supervisor("reset","installed"); result=json.loads((s/"result.json").read_text()); audit=json.loads((s/"host-action.json").read_text()); self.assertEqual(p.returncode,0); self.assertEqual(result["classification"],"GUEST_REBOOT"); self.assertEqual(audit["status"],"WOULD_REBOOT"); self.assertEqual(audit["action"],"reboot"); events=[json.loads(x)["event"] for x in (s/"lifecycle.log").read_text().splitlines()]; self.assertLess(events.index("classification"),events.index("WOULD_REBOOT")); print("T007_SUPERVISOR_INTEGRATION=PASS"); print("T007_CLASSIFICATION_BEFORE_ACTION=PASS")

    def test_supervisor_reboot_consumer_failure(self):
        root=Path(self.tmp.name)/"integration-reboot-failure"; root.mkdir(); run=root/"run"; logs=root/"logs"; run.mkdir(); logs.mkdir(); fake=root/"fake.py"; fake.write_text(t005.FAKE); fake.chmod(0o755); boot=root/"boot.py"; boot.write_text(t005.BOOT); boot.chmod(0o755); bindir=root/"bin"; bindir.mkdir(); systemctl_log=root/"systemctl.argv"; systemctl=bindir/"systemctl"; systemctl.write_text("#!/bin/sh\nprintf '%s\n' \"$@\" > \"$SYSTEMCTL_LOG\"\nexit 77\n"); systemctl.chmod(0o755)
        env=os.environ.copy(); env["REIMS_STATE_ROOT"]=str(root/"state"); env["REIMS_HOST_ACTION_MODE"]="systemd"; env["SYSTEMCTL_LOG"]=str(systemctl_log); env["PATH"]=str(bindir)+os.pathsep+env["PATH"]; vm="reims-0123456789abcdef"; st=ROOT/"scripts/reims-state.py"; subprocess.run([sys.executable,str(st),"configure","--vm-id",vm,"--macos","sequoia","--cpu","4","--ram-gb","8","--disk-gb","80"],env=env,check=True,capture_output=True); subprocess.run([sys.executable,str(st),"transition","installed"],env=env,check=True,capture_output=True)
        p=subprocess.run([sys.executable,str(ROOT/"scripts/reims-supervisor.py"),"run","--vm-id",vm,"--appliance-state","installed","--run-dir",str(run),"--log-root",str(logs),"--",str(boot),str(fake),str(run),"reset","0","0.15","0"],env=env,cwd=ROOT,capture_output=True,text=True); session=next(logs.glob("*/result.json")).parent; result=json.loads((session/"result.json").read_text()); audit=json.loads((session/"host-action.json").read_text()); events=[json.loads(x)["event"] for x in (session/"lifecycle.log").read_text().splitlines()]
        self.assertEqual(p.returncode,0); self.assertEqual(result["classification"],"GUEST_REBOOT"); self.assertEqual(result["classification_reason"],"qmp_reset"); self.assertEqual(result["launcher_exit_code"],0); self.assertEqual(result["qemu_exit_code"],0); self.assertEqual(audit["status"],"HOST_REBOOT_FAILED"); self.assertIn("77",audit["error"]); self.assertEqual(systemctl_log.read_text().splitlines(),["reboot"]); self.assertIn("HOST_ACTION_CONSUMER_FAILED",events); print("T007_CONSUMER_FAILURE_FAKE_SYSTEMCTL=PASS"); print("T007_CONSUMER_FAILURE_PRESERVES_RESULT=PASS"); print("T007_CONSUMER_FAILURE_PRESERVES_RC=PASS")
if __name__ == "__main__":
    ok=unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.loadTestsFromTestCase(T007HostRebootTests)).wasSuccessful()
    if ok: print("T007_CONTROLLED_TEST_PASS")
    sys.exit(0 if ok else 1)
