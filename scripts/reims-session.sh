#!/usr/bin/env bash
#
# reims-session.sh — the single graphical client of the Reims OS appliance.
#
# The dedicated Xorg session starts exactly this program (T009). It is not a
# desktop, a window manager, a panel or a shell: it establishes the X11
# contract the host window needs, then runs the normal launcher, so the
# T004-T008 lifecycle is reached through one path and one path only.
#
#   Xorg :0 -> reims-session.sh -> scripts/reims-launch.sh
#           -> reims-supervisor.py -> reims-vgpu/QEMU -> macOS fullscreen
#
# When the launcher returns, this script returns its status and nothing else
# appears. There is no desktop to fall back to and no shell is opened.
set -Eeuo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
LAUNCHER="$ROOT/scripts/reims-launch.sh"

usage() {
  cat <<'EOF'
usage: scripts/reims-session.sh [--dry-run]

Run the dedicated single-app Xorg session for the Reims appliance.

  --dry-run   print the resolved session contract and run the launcher in
              dry-run mode; never starts QEMU

Env:
  REIMS_X11_DISPLAY   X11 display to use (default :0)
  REIMS_XAUTHORITY    Xauthority file; overrides XAUTHORITY
  REIMS_VGPU_*        forwarded to the launcher unchanged
EOF
}

DRY=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "reims-session.sh: unknown argument '$1'" >&2; usage >&2; exit 64 ;;
  esac
done

# --- X11 contract -------------------------------------------------------------
# Xorg is the only graphical infrastructure in the appliance. winit 0.30 picks
# its backend from DISPLAY / WAYLAND_DISPLAY / WAYLAND_SOCKET and prefers
# Wayland when both are set, so a leftover Wayland variable would silently
# replace the dedicated X11 session. WINIT_UNIX_BACKEND does not exist in 0.30
# and is deliberately not used; the environment below is what selects X11.
export XDG_SESSION_TYPE=x11
export DISPLAY="${REIMS_X11_DISPLAY:-:0}"
unset WAYLAND_DISPLAY
unset WAYLAND_SOCKET

[ -n "$DISPLAY" ] || { echo "reims-session.sh: resolved an empty DISPLAY" >&2; exit 1; }

# XAUTHORITY is a per-login path and is never hardcoded. A value already
# exported by the session manager is preserved; REIMS_XAUTHORITY is an explicit
# override for bring-up and for tests.
if [ -n "${REIMS_XAUTHORITY:-}" ]; then
  export XAUTHORITY="$REIMS_XAUTHORITY"
elif [ -n "${XAUTHORITY:-}" ]; then
  export XAUTHORITY
fi

# --- Reims environment --------------------------------------------------------
# The session is the X11 one, and it has no window manager. Neither of those is
# operator-optional here, so the two that define the session are set rather than
# defaulted: a silent fallback would be a window that opens at its creation size
# and never fills the screen.
#
#   REIMS_VGPU_WINDOW_SYSTEM=x11  what selects the X11 backend in winit 0.30
#   REIMS_VGPU_X11_WMLESS=1       how the window takes the screen without a WM
#
# The remaining knobs keep product defaults but never overwrite an explicit
# operator value. Direct guest-RAM import is disabled for the product session
# until the reims-vgpu import path is stable on this host: with the default
# import rail, the Sequoia guest enters a kernel-panic/reboot loop after XNU
# handoff. `off` selects the copying rail and is a stability workaround, not a
# graphics-quality fix.
export REIMS_VGPU_WINDOW_SYSTEM=x11
export REIMS_VGPU_X11_WMLESS=1
: "${REIMS_VGPU_WINDOW:=1}"
: "${REIMS_VGPU_FULLSCREEN:=1}"
: "${REIMS_VGPU_BACKEND:=vulkan}"
: "${REIMS_VGPU_GUEST_IMPORT:=off}"
: "${REIMS_VGPU_SAMPLED_IDENTITY:=off}"
export REIMS_VGPU_WINDOW REIMS_VGPU_FULLSCREEN REIMS_VGPU_BACKEND \
  REIMS_VGPU_GUEST_IMPORT REIMS_VGPU_SAMPLED_IDENTITY REIMS_VGPU_X11_WMLESS

if [ "$DRY" -eq 1 ]; then
  printf 'SESSION_TYPE=%s\n' "x11"
  printf 'DISPLAY=%s\n' "$DISPLAY"
  printf 'WAYLAND_DISPLAY=%s\n' "${WAYLAND_DISPLAY-<unset>}"
  printf 'WAYLAND_SOCKET=%s\n' "${WAYLAND_SOCKET-<unset>}"
  printf 'XAUTHORITY=%s\n' "${XAUTHORITY-<unset>}"
  printf 'REIMS_VGPU_WINDOW_SYSTEM=%s\n' "$REIMS_VGPU_WINDOW_SYSTEM"
  printf 'REIMS_VGPU_X11_WMLESS=%s\n' "$REIMS_VGPU_X11_WMLESS"
  printf 'REIMS_VGPU_WINDOW=%s\n' "$REIMS_VGPU_WINDOW"
  printf 'REIMS_VGPU_FULLSCREEN=%s\n' "$REIMS_VGPU_FULLSCREEN"
  printf 'REIMS_VGPU_BACKEND=%s\n' "$REIMS_VGPU_BACKEND"
  printf 'REIMS_VGPU_GUEST_IMPORT=%s\n' "$REIMS_VGPU_GUEST_IMPORT"
  printf 'REIMS_VGPU_SAMPLED_IDENTITY=%s\n' "$REIMS_VGPU_SAMPLED_IDENTITY"
  # Prove the delegation target by running it; it starts no QEMU in dry-run.
  exec "$LAUNCHER" --dry-run
fi

exec "$LAUNCHER"
