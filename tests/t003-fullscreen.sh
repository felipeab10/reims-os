#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$ROOT/scripts/reims-fullscreen-env.sh"

unset REIMS_VGPU_FULLSCREEN
reims_resolve_fullscreen persistent
[[ "$REIMS_VGPU_FULLSCREEN" == 1 ]]
echo PERSISTENT_FULLSCREEN_DEFAULT=PASS
( REIMS_VGPU_FULLSCREEN=0; reims_resolve_fullscreen persistent; [[ "$REIMS_VGPU_FULLSCREEN" == 0 ]] )
echo PERSISTENT_FULLSCREEN_OVERRIDE_OFF=PASS
( REIMS_VGPU_FULLSCREEN=1; reims_resolve_fullscreen persistent; [[ "$REIMS_VGPU_FULLSCREEN" == 1 ]] )
echo PERSISTENT_FULLSCREEN_OVERRIDE_ON=PASS
unset REIMS_VGPU_FULLSCREEN
for mode in testing interactive capture; do
  reims_resolve_fullscreen "$mode"
  [[ -z "${REIMS_VGPU_FULLSCREEN+x}" ]]
done
echo DEV_MODE_FULLSCREEN_DEFAULT=PASS
echo T003_FULLSCREEN_CONTROLLED_TEST_PASS
