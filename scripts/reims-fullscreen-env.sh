#!/usr/bin/env bash
# Resolve the appliance fullscreen default without overwriting operator intent.
reims_resolve_fullscreen() {
  local boot_class=$1
  if [ "$boot_class" = persistent ] && [ -z "${REIMS_VGPU_FULLSCREEN+x}" ]; then
    export REIMS_VGPU_FULLSCREEN=1
  fi
}
