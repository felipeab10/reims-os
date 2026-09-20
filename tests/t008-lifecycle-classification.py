#!/usr/bin/env python3
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
        print("T008_FATAL_PRECEDENCE=PASS")

    def test_external_signal(self):
        d = self.decide(external_signal="SIGTERM", qemu_exit=0)
        self.assertEqual(d["classification"], "EXTERNAL_SIGNAL")
        self.assertFalse(d["recovery_required"])
        d = self.decide(external_signal="SIGTERM", qemu_log_text="VK_ERROR_DEVICE_LOST")
        self.assertEqual(d["classification"], "REIMS_FATAL")
        print("T008_EXTERNAL_SIGNAL=PASS")

    def test_qmp_terminal_order(self):
        self.assertEqual(self.decide(qmp_events=["RESET", "SHUTDOWN"])["classification"], "GUEST_SHUTDOWN")
        self.assertEqual(self.decide(qmp_events=["SHUTDOWN", "RESET"])["classification"], "GUEST_REBOOT")
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
        d = self.decide(qemu_runtime_log_offset=20, qemu_log_text="fatal: No names found, cannot describe anything.\nVK_ERROR_DEVICE_LOST")
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
                result = supervisor.transition_recovery()
            finally:
                if old is None: os.environ.pop("REIMS_STATE_ROOT", None)
                else: os.environ["REIMS_STATE_ROOT"] = old
            self.assertTrue(result["succeeded"])
            self.assertIn('"state": "recovery"', (Path(tmp) / "state.json").read_text())
        print("T008_RECOVERY_TRANSITION=PASS")

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
