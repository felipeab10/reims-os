#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
expected(){ git ls-tree HEAD -- "$1" | awk '{print $3}'; }
check(){ local path=$1 expected_sha=$2 actual; actual=$(git -C "$path" rev-parse HEAD); [[ "$actual" == "$expected_sha" ]] || { echo "ERROR: $path at $actual, expected $expected_sha" >&2; exit 1; }; [[ -z "$(git -C "$path" status --porcelain)" ]] || { echo "ERROR: dirty dependency: $path" >&2; exit 1; }; }
REIMS_VGPU_SHA=$(expected components/reims-vgpu)
QEMU_SHA=$(git -C components/reims-vgpu ls-tree HEAD vendor/qemu | awk '{print $3}')
OSX_KVM_SHA=$(expected third_party/OSX-KVM)
SERIAL_GENERATOR_SHA=$(expected third_party/osx-serial-generator)
[[ -n "$REIMS_VGPU_SHA" && -n "$QEMU_SHA" && -n "$OSX_KVM_SHA" && -n "$SERIAL_GENERATOR_SHA" ]] || exit 1
check components/reims-vgpu "$REIMS_VGPU_SHA"
check third_party/OSX-KVM "$OSX_KVM_SHA"
check third_party/osx-serial-generator "$SERIAL_GENERATOR_SHA"
check components/reims-vgpu/vendor/qemu "$QEMU_SHA"
test -f components/reims-vgpu/vendor/qemu/configure
printf "REIMS_VGPU_SHA=%s\nQEMU_SHA=%s\nOSX_KVM_SHA=%s\nSERIAL_GENERATOR_SHA=%s\n" "$REIMS_VGPU_SHA" "$QEMU_SHA" "$OSX_KVM_SHA" "$SERIAL_GENERATOR_SHA"
