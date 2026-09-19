#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
STATE_ROOT="${REIMS_STATE_ROOT:-/var/lib/reims}"
REIMS_VGPU_ROOT="${REIMS_VGPU_ROOT:-$ROOT/components/reims-vgpu}"
export REIMS_STATE_ROOT="$STATE_ROOT"
DRY=0
[ "${1:-}" = --dry-run ] && { DRY=1; shift; }
[ "$#" -eq 0 ] || { echo "usage: scripts/reims-launch.sh [--dry-run]" >&2; exit 64; }
STATE_ERR=$(mktemp)
if ! STATE_KV="$(python3 - "$ROOT/scripts/reims-state.py" <<"PY" 2>"$STATE_ERR"
import importlib.util, sys
s=importlib.util.spec_from_file_location("reims_state",sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
v=m.read_state()
if v["state"] == "unconfigured": raise ValueError("state is unconfigured")
if v["state"] == "recovery": raise ValueError("state is recovery; recovery launcher is not implemented")
p=m.paths(v)
for k,val in {**p,"VM_ID":v["vm_id"],"MACOS":v["macos"],"CPU_CORES":v["cpu"],"RAM":v["ram_gb"],"DISK_GB":v["disk_gb"],"APPLIANCE_STATE":v["state"]}.items(): print(f"{k}={val}")
PY
)"; then
  cat "$STATE_ERR" >&2
  rm -f "$STATE_ERR"
  exit 1
fi
rm -f "$STATE_ERR"
mapfile -t KV <<< "$STATE_KV"
for item in "${KV[@]}"; do key=${item%%=*}; val=${item#*=}; printf -v "$key" "%s" "$val"; done
INSTALL_MEDIA="$INSTALLER_DIR/$MACOS.img"
if [ "$APPLIANCE_STATE" = installed ]; then INSTALL_MEDIA=""; QEMU_REBOOT_ACTION=exit; else [ -f "$INSTALL_MEDIA" ] || { echo "ERROR: installer media missing: $INSTALL_MEDIA" >&2; exit 1; }; QEMU_REBOOT_ACTION=reset; fi
export PERSISTENT_DIR RUN_DIR RAILS_DIR REIMS_VGPU_BACKEND QEMU_REBOOT_ACTION CPU_CORES CPU_THREADS="$CPU_CORES" RAM="${RAM}G" INSTALL_MEDIA
if [ "$DRY" -eq 1 ]; then
  printf "VM_ID=%s\nAPPLIANCE_STATE=%s\nMACOS=%s\nCPU_CORES=%s\nRAM=%s\nPERSISTENT_DIR=%s\nINSTALL_MEDIA=%s\nQEMU_REBOOT_ACTION=%s\nRAILS_DIR=%s\n" "$VM_ID" "$APPLIANCE_STATE" "$MACOS" "$CPU_CORES" "$RAM" "$PERSISTENT_DIR" "${INSTALL_MEDIA:-<absent>}" "$QEMU_REBOOT_ACTION" "$RAILS_DIR"
  exit 0
fi
exec "$REIMS_VGPU_ROOT/vm/boot-x86.sh" --persistent --device reims-vgpu-pci --rail "$VM_ID"
