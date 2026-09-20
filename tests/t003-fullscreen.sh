#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
source "$ROOT/scripts/reims-fullscreen-env.sh"
unset REIMS_VGPU_FULLSCREEN
reims_resolve_fullscreen persistent
[[ "$REIMS_VGPU_FULLSCREEN" == 1 ]]; echo PERSISTENT_FULLSCREEN_DEFAULT=PASS
( REIMS_VGPU_FULLSCREEN=0; reims_resolve_fullscreen persistent; [[ "$REIMS_VGPU_FULLSCREEN" == 0 ]] ); echo PERSISTENT_FULLSCREEN_OVERRIDE_OFF=PASS
( REIMS_VGPU_FULLSCREEN=1; reims_resolve_fullscreen persistent; [[ "$REIMS_VGPU_FULLSCREEN" == 1 ]] ); echo PERSISTENT_FULLSCREEN_OVERRIDE_ON=PASS
unset REIMS_VGPU_FULLSCREEN
for mode in testing interactive capture; do reims_resolve_fullscreen "$mode"; [[ -z "${REIMS_VGPU_FULLSCREEN+x}" ]]; done
echo DEV_MODE_FULLSCREEN_DEFAULT=PASS
export REIMS_STATE_ROOT="$TMP/state-root"
python3 "$ROOT/scripts/reims-state.py" init >/dev/null
python3 "$ROOT/scripts/reims-state.py" configure --vm-id reims-0123456789abcdef --macos sequoia --cpu 4 --ram-gb 8 --disk-gb 80 >/dev/null
python3 "$ROOT/scripts/reims-state.py" transition installed >/dev/null
launch(){ env "$@" bash "$ROOT/scripts/reims-launch.sh" --dry-run; }
[[ "$(env -u REIMS_VGPU_FULLSCREEN bash "$ROOT/scripts/reims-launch.sh" --dry-run | grep '^REIMS_VGPU_FULLSCREEN=')" == REIMS_VGPU_FULLSCREEN=1 ]]; echo PRODUCT_LAUNCH_FULLSCREEN_DEFAULT=PASS
[[ "$(REIMS_VGPU_FULLSCREEN=0 bash "$ROOT/scripts/reims-launch.sh" --dry-run | grep '^REIMS_VGPU_FULLSCREEN=')" == REIMS_VGPU_FULLSCREEN=0 ]]; echo PRODUCT_LAUNCH_FULLSCREEN_OVERRIDE_OFF=PASS
[[ "$(REIMS_VGPU_FULLSCREEN=1 bash "$ROOT/scripts/reims-launch.sh" --dry-run | grep '^REIMS_VGPU_FULLSCREEN=')" == REIMS_VGPU_FULLSCREEN=1 ]]; echo PRODUCT_LAUNCH_FULLSCREEN_OVERRIDE_ON=PASS
[[ "$(REIMS_VGPU_FULLSCREEN='' bash "$ROOT/scripts/reims-launch.sh" --dry-run | grep '^REIMS_VGPU_FULLSCREEN=')" == REIMS_VGPU_FULLSCREEN= ]]; echo PRODUCT_LAUNCH_FULLSCREEN_EMPTY_PRESERVED=PASS
( unset REIMS_VGPU_FULLSCREEN; source "$ROOT/scripts/reims-vm-manager.sh"; [[ "$REIMS_VGPU_FULLSCREEN" == 1 ]] ); echo PRODUCT_MANAGER_FULLSCREEN_DEFAULT=PASS
( export REIMS_VGPU_FULLSCREEN=0; source "$ROOT/scripts/reims-vm-manager.sh"; [[ "$REIMS_VGPU_FULLSCREEN" == 0 ]] ); echo PRODUCT_MANAGER_FULLSCREEN_OVERRIDE_OFF=PASS
if grep -q reims_resolve_fullscreen "$ROOT/components/reims-vgpu/vm/boot-x86.sh"; then echo "ERROR: component still owns fullscreen product policy" >&2; exit 1; fi
if [ -e "$ROOT/components/reims-vgpu/scripts/reims-fullscreen-env.sh" ]; then echo "ERROR: component fullscreen policy helper still exists" >&2; exit 1; fi
grep -q REIMS_VGPU_FULLSCREEN "$ROOT/components/reims-vgpu/vm/boot-x86.sh"
echo COMPONENT_FULLSCREEN_POLICY_ABSENT=PASS
grep -Rqs REIMS_VGPU_FULLSCREEN "$ROOT/components/reims-vgpu/crates/reims-vgpu"
grep -RqsE 'Fullscreen::Borderless|WindowMode::Borderless' "$ROOT/components/reims-vgpu/crates/reims-vgpu"
echo NATIVE_FULLSCREEN_IMPLEMENTATION_PRESENT=PASS
echo T003_FULLSCREEN_CONTROLLED_TEST_PASS
