#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
git submodule update --init components/reims-vgpu
git submodule update --init third_party/OSX-KVM
git submodule update --init third_party/osx-serial-generator
git -C components/reims-vgpu submodule update --init vendor/qemu
"$ROOT/scripts/check-deps.sh"
