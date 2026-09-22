#!/usr/bin/env python3
"""T009 — dedicated single-app Xorg session contract.

Runs the session in dry-run, which resolves the X11 environment and delegates
to scripts/reims-launch.sh --dry-run. No Xorg, no QEMU and no host action are
ever started here.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SESSION = ROOT / "scripts" / "reims-session.sh"
LAUNCHER = ROOT / "scripts" / "reims-launch.sh"
VGPU_SELECTOR = ROOT / "components" / "reims-vgpu" / "vm" / "window-system-env.sh"
VGPU_SELECTOR_TEST = ROOT / "components" / "reims-vgpu" / "vm" / "tests" / "window-system-env-test.sh"

WAYLAND_NAMES = ("WAYLAND_DISPLAY", "WAYLAND_SOCKET")


class T009SingleAppSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"
        self.guard_log = self.root / "systemctl.argv"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        guard = self.bin / "systemctl"
        guard.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$@" >> "${SYSTEMCTL_GUARD_LOG}"\nexit 99\n'
        )
        guard.chmod(0o755)
        self.configure(self.state, "installed")

    def tearDown(self):
        self.tmp.cleanup()

    def configure(self, state_root, state):
        env = os.environ.copy()
        env["REIMS_STATE_ROOT"] = str(state_root)
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/reims-state.py"), "configure",
             "--vm-id", "reims-0123456789abcdef", "--macos", "sequoia",
             "--cpu", "4", "--ram-gb", "8", "--disk-gb", "80"],
            env=env, check=True, capture_output=True,
        )
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/reims-state.py"), "transition", state],
            env=env, check=True, capture_output=True,
        )

    def session_env(self, state_root=None, **overrides):
        env = os.environ.copy()
        env["REIMS_STATE_ROOT"] = str(state_root if state_root is not None else self.state)
        env["REIMS_HOST_ACTION_MODE"] = "disabled"
        env["SYSTEMCTL_GUARD_LOG"] = str(self.guard_log)
        env["PATH"] = str(self.bin) + os.pathsep + env.get("PATH", "")
        for name in WAYLAND_NAMES:
            env.pop(name, None)
        env.pop("DISPLAY", None)
        env.pop("XAUTHORITY", None)
        env.pop("REIMS_X11_DISPLAY", None)
        env.pop("REIMS_XAUTHORITY", None)
        for key, value in overrides.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = str(value)
        return env

    def run_session(self, args=("--dry-run",), state_root=None, **overrides):
        return subprocess.run(
            ["bash", str(SESSION), *args],
            env=self.session_env(state_root, **overrides),
            cwd=ROOT, capture_output=True, text=True,
        )

    def contract(self, proc):
        fields = {}
        for line in proc.stdout.splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                fields.setdefault(key, value)
        return fields

    def guard_called(self):
        return self.guard_log.exists()

    # -- X11 environment -------------------------------------------------------
    def test_default_x11_env(self):
        proc = self.run_session()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        fields = self.contract(proc)
        self.assertEqual(fields["SESSION_TYPE"], "x11")
        self.assertEqual(fields["DISPLAY"], ":0")
        self.assertEqual(fields["WAYLAND_DISPLAY"], "<unset>")
        self.assertEqual(fields["WAYLAND_SOCKET"], "<unset>")
        self.assertEqual(fields["REIMS_VGPU_WINDOW_SYSTEM"], "x11")
        self.assertFalse(self.guard_called())
        print("T009_X11_ENV=PASS")

    def test_display_override(self):
        proc = self.run_session(REIMS_X11_DISPLAY=":7")
        self.assertEqual(self.contract(proc)["DISPLAY"], ":7")
        print("T009_DISPLAY_OVERRIDE=PASS")

    def test_xauthority_preserved(self):
        proc = self.run_session(XAUTHORITY="/run/user/1000/xauth-abc")
        self.assertEqual(self.contract(proc)["XAUTHORITY"], "/run/user/1000/xauth-abc")
        proc = self.run_session(XAUTHORITY="/run/user/1000/xauth-abc", REIMS_XAUTHORITY="/tmp/explicit-xauth")
        self.assertEqual(self.contract(proc)["XAUTHORITY"], "/tmp/explicit-xauth")
        proc = self.run_session()
        self.assertEqual(self.contract(proc)["XAUTHORITY"], "<unset>")
        print("T009_XAUTHORITY_PRESERVED=PASS")

    def test_fullscreen_contract(self):
        self.assertEqual(self.contract(self.run_session())["REIMS_VGPU_FULLSCREEN"], "1")
        self.assertEqual(self.contract(self.run_session(REIMS_VGPU_FULLSCREEN="0"))["REIMS_VGPU_FULLSCREEN"], "0")
        print("T009_FULLSCREEN_CONTRACT=PASS")

    def test_host_window_contract(self):
        self.assertEqual(self.contract(self.run_session())["REIMS_VGPU_WINDOW"], "1")
        print("T009_HOST_WINDOW_CONTRACT=PASS")

    def test_vulkan_contract(self):
        self.assertEqual(self.contract(self.run_session())["REIMS_VGPU_BACKEND"], "vulkan")
        print("T009_VULKAN_CONTRACT=PASS")

    def test_guest_import_stability_default(self):
        self.assertEqual(
            self.contract(self.run_session())["REIMS_VGPU_GUEST_IMPORT"],
            "off",
        )
        self.assertEqual(
            self.contract(self.run_session(REIMS_VGPU_GUEST_IMPORT="on"))["REIMS_VGPU_GUEST_IMPORT"],
            "on",
        )
        print("T009_GUEST_IMPORT_STABILITY_DEFAULT=PASS")

    def test_wayland_env_cleared(self):
        proc = self.run_session(WAYLAND_DISPLAY="wayland-1", WAYLAND_SOCKET="/run/user/1000/wayland-1")
        fields = self.contract(proc)
        self.assertEqual(fields["WAYLAND_DISPLAY"], "<unset>")
        self.assertEqual(fields["WAYLAND_SOCKET"], "<unset>")
        self.assertEqual(fields["DISPLAY"], ":0")
        print("T009_WAYLAND_ENV_CLEARED=PASS")
        print("T009_X11_NO_WAYLAND_ENV=PASS")

    # -- launcher chain --------------------------------------------------------
    def test_launcher_chain(self):
        self.assertIn("reims-launch.sh", SESSION.read_text())
        proc = self.run_session()
        for key in ("VM_ID", "APPLIANCE_STATE", "QEMU_REBOOT_ACTION", "RAILS_DIR"):
            self.assertIn(key, proc.stdout)
        self.assertNotIn("qemu-system", proc.stdout)
        self.assertNotIn("boot-x86.sh", proc.stdout)
        print("T009_LAUNCHER_CHAIN=PASS")

    def test_install_reboot_keeps_qemu_alive(self):
        boot = (ROOT / "components/reims-vgpu/vm/boot-x86.sh").read_text()
        self.assertIn('QEMU_REBOOT_ACTION="${QEMU_REBOOT_ACTION:-exit}"', boot)
        self.assertIn('QEMU_ARGS+=(-action reboot=reset)', boot)
        self.assertIn('QEMU_ARGS+=(-action reboot=shutdown)', boot)
        print("T009_INSTALL_REBOOT_RESET=PASS")

    def test_exit_status_preserved(self):
        ok = self.run_session()
        direct_ok = subprocess.run(["bash", str(LAUNCHER), "--dry-run"], env=self.session_env(), cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(ok.returncode, direct_ok.returncode)
        self.assertEqual(ok.returncode, 0)
        missing = self.root / "unconfigured-state"
        bad = self.run_session(state_root=missing)
        direct_bad = subprocess.run(["bash", str(LAUNCHER), "--dry-run"], env=self.session_env(missing), cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(direct_bad.returncode, 0)
        self.assertEqual(bad.returncode, direct_bad.returncode)
        print("T009_EXIT_STATUS_PRESERVED=PASS")

    def test_wm_less_x11_contract(self):
        # Full-screen in this session cannot be an EWMH request: there is no
        # window manager to answer one, so winit's Borderless hint alone would
        # leave the window at its creation size. The session must state the
        # WM-less contract, and an operator cannot switch it off — there is no
        # desktop to fall back to.
        proc = self.run_session()
        self.assertEqual(self.contract(proc)["REIMS_VGPU_X11_WMLESS"], "1")
        proc = self.run_session(REIMS_VGPU_X11_WMLESS="0")
        self.assertEqual(self.contract(proc)["REIMS_VGPU_X11_WMLESS"], "1")
        proc = self.run_session(REIMS_VGPU_X11_WMLESS="")
        self.assertEqual(self.contract(proc)["REIMS_VGPU_X11_WMLESS"], "1")
        session_text = SESSION.read_text()
        self.assertIn("REIMS_VGPU_X11_WMLESS=1", session_text)
        self.assertRegex(session_text, r"export .*REIMS_VGPU_X11_WMLESS")
        print("T009_WMLESS_X11_CONTRACT=PASS")

    def test_unknown_argument_rejected(self):
        proc = self.run_session(args=("--not-a-flag",))
        self.assertEqual(proc.returncode, 64)
        print("T009_UNKNOWN_ARGUMENT_REJECTED=PASS")

    # -- no desktop / no window manager ----------------------------------------
    def test_no_window_manager_or_desktop(self):
        text = SESSION.read_text()
        for forbidden in ("openbox", "fluxbox", "niri", "kwin", "mutter", "xfwm", "lxpanel",
                          "xdotool", "wmctrl", "gnome-session", "startplasma"):
            self.assertNotIn(forbidden, text, "session must not start " + forbidden)
        self.assertIn("REIMS_VGPU_FULLSCREEN", text)
        self.assertIn("REIMS_VGPU_X11_WMLESS", text)
        print("T009_NO_WM_DEPENDENCY=PASS")

    # -- reims-vgpu selector ---------------------------------------------------
    def run_selector(self, mode, **env):
        child = dict(env)
        child["REIMS_VGPU_WINDOW_SYSTEM"] = mode
        script = (
            "source \"" + str(VGPU_SELECTOR) + "\"\n"
            "reims_resolve_window_system || exit $?\n"
            'printf "D=%s\\n" "${DISPLAY-<unset>}"\n'
            'printf "WD=%s\\n" "${WAYLAND_DISPLAY-<unset>}"\n'
            'printf "WS=%s\\n" "${WAYLAND_SOCKET-<unset>}"\n'
        )
        return subprocess.run(["bash", "--noprofile", "--norc", "-c", script],
                              env=child, capture_output=True, text=True)

    def test_vgpu_selector(self):
        self.assertTrue(VGPU_SELECTOR.exists(), "reims-vgpu selector missing")
        proc = self.run_selector("x11", DISPLAY=":0", WAYLAND_DISPLAY="wayland-1", WAYLAND_SOCKET="/tmp/w")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("D=:0", proc.stdout)
        self.assertIn("WD=<unset>", proc.stdout)
        self.assertIn("WS=<unset>", proc.stdout)
        print("T009_VGPU_X11_SELECTOR=PASS")

        proc = self.run_selector("x11", WAYLAND_DISPLAY="wayland-1")
        self.assertEqual(proc.returncode, 64)
        self.assertIn("requires DISPLAY", proc.stderr)
        print("T009_VGPU_X11_REQUIRES_DISPLAY=PASS")

        proc = self.run_selector("auto", DISPLAY=":42", WAYLAND_DISPLAY="wayland-1")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("D=:42", proc.stdout)
        self.assertIn("WD=wayland-1", proc.stdout)
        print("T009_VGPU_AUTO_COMPAT=PASS")

        if VGPU_SELECTOR_TEST.exists():
            run = subprocess.run(["bash", str(VGPU_SELECTOR_TEST)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_host_action_never_invoked(self):
        self.run_session()
        self.assertFalse(self.guard_called())
        print("T009_NO_SYSTEMCTL=PASS")


if __name__ == "__main__":
    ok = unittest.TextTestRunner(verbosity=0).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(T009SingleAppSessionTests)
    ).wasSuccessful()
    if ok:
        print("T009_CONTROLLED_TEST_PASS")
    sys.exit(0 if ok else 1)
