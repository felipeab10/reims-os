#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$ROOT/scripts/reims-fullscreen-env.sh"
reims_resolve_fullscreen persistent
REIMS_VGPU_ROOT="${REIMS_VGPU_ROOT:-$ROOT/components/reims-vgpu}"
OSX_KVM="${OSX_KVM:-$ROOT/third_party/OSX-KVM}"
SERIAL_GENERATOR_ROOT="${SERIAL_GENERATOR_ROOT:-$ROOT/third_party/osx-serial-generator}"
REIMS_STATE_ROOT="${REIMS_STATE_ROOT:-/var/lib/reims}"
WORK_ROOT="$REIMS_STATE_ROOT/vms"
RAILS_DIR="$REIMS_STATE_ROOT/rails"
PERSIST_MODE="${REIMS_PERSIST_MODE:-persistent}"
SMBIOS_MODEL="${REIMS_SMBIOS_MODEL:-iMacPro1,1}"
RESERVE_CORES="${REIMS_RESERVE_CORES:-2}"; RESERVE_RAM="${REIMS_RESERVE_RAM_GB:-4}"
die(){ echo "ERRO: $*" >&2; exit 1; }
if [[ -n "${REIMS_VM_WORK_ROOT:-}" && "$REIMS_VM_WORK_ROOT" != "$WORK_ROOT" ]]; then die "REIMS_VM_WORK_ROOT must match REIMS_STATE_ROOT/vms"; fi
if [[ -n "${RAILS_DIR_OVERRIDE:-}" && "$RAILS_DIR_OVERRIDE" != "$RAILS_DIR" ]]; then die "RAILS_DIR override must match REIMS_STATE_ROOT/rails"; fi
fetch_media(){ local base=$1 installer="$base/installer"; mkdir -p "$base/run"; : > "$base/run/provision.log"; emit_progress fetch_media running; if [[ ! -f "$installer/$VERSION.dmg" || ! -f "$installer/$VERSION.chunklist" ]]; then if ! python3 "$ROOT/scripts/reims-fetch-macos.py" --action download --shortname "$VERSION" --os-type "$OS_TYPE" --outdir "$installer" --basename "$VERSION" >>"$base/run/provision.log" 2>&1; then emit_progress fetch_media failed "Falha ao baixar ou validar o instalador do macOS"; printf "ERRO: Falha ao baixar ou validar o instalador do macOS (consulte %s)\n" "$base/run/provision.log" >&2; return 1; fi; else if ! python3 "$ROOT/scripts/reims-fetch-macos.py" --verify-only "$installer/$VERSION.dmg" "$installer/$VERSION.chunklist" >>"$base/run/provision.log" 2>&1; then emit_progress fetch_media failed "Falha ao baixar ou validar o instalador do macOS"; printf "ERRO: Falha ao baixar ou validar o instalador do macOS (consulte %s)\n" "$base/run/provision.log" >&2; return 1; fi; fi; emit_progress fetch_media completed; }
need(){ command -v "$1" >/dev/null 2>&1 || missing+=("$1"); }
emit_progress(){ local phase=$1 state=$2 message=${3:-}; printf "phase=%s state=%s" "$phase" "$state"; [[ -n "$message" ]] && printf " message=%s" "$message"; printf "\n"; }
preflight(){ missing=(); for x in bash python3 cargo qemu-img dmg2img pkg-config llvm-dis spirv-val guestfish uuidgen curl make ss; do need "$x"; done; [[ -d "$OSX_KVM" ]]||missing+=(OSX-KVM); [[ -d "$SERIAL_GENERATOR_ROOT" ]]||missing+=(osx-serial-generator); [[ -r /dev/kvm ]]||missing+=(/dev/kvm); [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]||missing+=(graphical-session); hc=$(nproc); hr=$(awk '/MemTotal:/{printf "%d",$2/1024/1024}' /proc/meminfo); echo "HOST: $hc CPUs, $hr GiB RAM; reserve $RESERVE_CORES CPUs/$RESERVE_RAM GiB"; ((hc>RESERVE_CORES&&hr>RESERVE_RAM))||missing+=(host-margin); if ((${#missing[@]})); then printf 'REQUISITOS AUSENTES:\n - %s\n' "${missing[@]}"; return 1; fi; HOST_CORES=$((hc-RESERVE_CORES)); HOST_RAM=$((hr-RESERVE_RAM)); }
choose(){ local o=(ventura sonoma sequoia); select VERSION in "${o[@]}"; do [[ -n "$VERSION" ]]&&break; done; case "$VERSION" in ventura) OS_TYPE=latest;; sonoma|sequoia) OS_TYPE=default;; esac; }
resources(){ read -r -p "CPUs [$HOST_CORES]: " CORES; CORES=${CORES:-4}; read -r -p "RAM GiB [$HOST_RAM]: " RAM; RAM=${RAM:-8}; read -r -p 'Disco GiB [mínimo 70]: ' DISK; DISK=${DISK:-70}; [[ "$CORES" =~ ^[0-9]+$ && "$RAM" =~ ^[0-9]+$ && "$DISK" =~ ^[0-9]+$ ]]||die resources; ((CORES>0&&CORES<=HOST_CORES&&RAM>=2&&RAM<=HOST_RAM&&DISK>=70))||die resources; }
new_id(){ local id; while :; do id="reims-$(uuidgen | tr -d "-" | cut -c1-16)"; [[ ! -e "$WORK_ROOT/$id" && ! -e "$RAILS_DIR/$id" ]] && { VM_ID=$id; return; }; done; }
create_installing_state(){ python3 "$ROOT/scripts/reims-state.py" configure --vm-id "$VM_ID" --macos "$VERSION" --cpu "$CORES" --ram-gb "$RAM" --disk-gb "$DISK" >/dev/null; }
run_opencore_builder(){ local base=$1 sw=$2 env_file=$3 rc log; log="$base/run/provision.log"; mkdir -p "$base/run"; printf "\n=== build_opencore ===\n" >>"$log"; emit_progress build_opencore running; if [[ -n "${REIMS_T002_BUILDER:-}" ]]; then if bash "$REIMS_T002_BUILDER" >>"$log" 2>&1; then :; else rc=$?; emit_progress build_opencore failed "Falha ao configurar o OpenCore"; printf "ERRO: Falha ao configurar o OpenCore (consulte %s)\n" "$log" >&2; return "$rc"; fi; elif (cd "$sw" && source "$env_file" && bash ./generate-specific-bootdisk.sh --model "$DEVICE_MODEL" --serial "$SERIAL" --board-serial "$BOARD_SERIAL" --uuid "$UUID" --mac-address "$MAC_ADDRESS" --master-plist "$base/serial/config-auto.plist" --output-bootdisk "$base/persistent/OpenCore.qcow2") >>"$log" 2>&1; then :; else rc=$?; emit_progress build_opencore failed "Falha ao configurar o OpenCore"; printf "ERRO: Falha ao configurar o OpenCore (consulte %s)\n" "$log" >&2; return "$rc"; fi; emit_progress build_opencore completed; }
verify(){ python3 - "$1" "$2" <<'PY'
import hashlib,struct,sys
p,c=sys.argv[1:]; b=open(c,'rb').read(); H=struct.Struct('<4sIBBBxQQQ'); C=struct.Struct('<I32s'); m,hs,v,cm,sig,n,o,so=H.unpack_from(b); assert (m,hs,v,cm,sig)==(b'CNKL',36,1,1,1); f=open(p,'rb')
for i in range(n): z,w=C.unpack_from(b,o+i*C.size); assert hashlib.sha256(f.read(z)).digest()==w
assert f.read(1)==b''
PY
}
generate_opencore(){ base=$1; sw="$base/serial-work"; mkdir -p "$sw/OpenCore" "$sw/resources/OcBinaryData" "$base/serial"; cp "$SERIAL_GENERATOR_ROOT/generate-specific-bootdisk.sh" "$sw/generate-specific-bootdisk.sh"; cp "$SERIAL_GENERATOR_ROOT/opencore-image-ng.sh" "$sw/opencore-image-ng.sh"; cp -a "$OSX_KVM/OpenCore/EFI" "$sw/OpenCore/"; cp -a "$OSX_KVM/OpenCore/EFI/OC/Resources" "$sw/resources/OcBinaryData/"; (cd "$sw" && bash "$SERIAL_GENERATOR_ROOT/generate-unique-machine-values.sh" --count 1 --model "$SMBIOS_MODEL" --width 1920 --height 1080 --output-dir "$base/serial" --master-plist "$SERIAL_GENERATOR_ROOT/config-custom.plist" --create-envs --create-plists); generated=$(find "$base/serial/plists" -type f -name '*.plist' -print -quit); [[ -n "$generated" ]]||die plist; cp "$generated" "$base/serial/config-auto.plist"; python3 - "$base/serial/config-auto.plist" <<'PY'
import plistlib,sys,tempfile,os
path=sys.argv[1]; data=open(path,'rb').read(); start=data.find(b'<?xml'); assert start>=0
fd,tmp=tempfile.mkstemp(dir=os.path.dirname(path)); os.close(fd); open(tmp,'wb').write(data[start:]); p=plistlib.load(open(tmp,'rb')); p.setdefault('Misc',{}).setdefault('Boot',{}).update(ShowPicker=True,Timeout=5,PickerMode='Builtin'); p.setdefault('Misc',{}).setdefault('Security',{})['AllowSetDefault']=True; p.setdefault('UEFI',{}).setdefault('Quirks',{})['RequestBootVarRouting']=True; plistlib.dump(p,open(path,'wb'),sort_keys=False); os.unlink(tmp)
PY
env_file=$(find "$base/serial/envs" -type f -name "*.env.sh" -print -quit); [[ -n "$env_file" ]] || die identity-env; run_opencore_builder "$base" "$sw" "$env_file"; printf 'model=%s\nplist=%s\n' "$SMBIOS_MODEL" "$generated" > "$base/serial-generator.txt"; }
prepare(){ base="$WORK_ROOT/$VM_ID"; [[ ! -e "$base" ]] || die "installation exists: $base"; mkdir -p "$base" "$base/persistent" "$RAILS_DIR/$VM_ID/snapshots"; installer="$base/installer"; mkdir -p "$installer" "$base/run"; d="$installer/$VERSION.dmg"; c="$installer/$VERSION.chunklist"; m="$installer/$VERSION.img"; disk="$base/persistent/macos.qcow2"; fetch_media "$base"; [[ -f "$d"&&-f "$c" ]]||die download; [[ -f "$m" ]]||dmg2img -i "$d" "$m"; [[ ! -e "$disk" ]] || die "persistent disk already exists: $disk"; qemu-img create -f qcow2 "$disk" "${DISK}G"; qemu-img info "$disk" | grep -Fq "virtual size: ${DISK} GiB" || die "persistent disk size mismatch"; [[ ! -e "$base/persistent/OVMF_VARS.fd" ]] || die "OVMF_VARS already exists"; cp --reflink=auto "$OSX_KVM/OVMF_VARS-1920x1080.fd" "$base/persistent/OVMF_VARS.fd"; [[ ! -e "$base/persistent/OVMF_CODE.fd" ]] || die "OVMF_CODE already exists"; cp --reflink=auto "$OSX_KVM/OVMF_CODE_4M.fd" "$base/persistent/OVMF_CODE.fd"; [[ ! -e "$base/persistent/OpenCore.qcow2" ]] || die "OpenCore already exists"; generate_opencore "$base"; port=$((2222+($(printf '%s' "$VM_ID"|cksum|awk '{print $1}')%1000))); while ss -ltn 2>/dev/null|grep -q ":$port "; do port=$((port+1)); done; run="$base/run"; mkdir -p "$run"; export REIMS_VGPU_BACKEND=vulkan DISPLAY_REFRESH_HZ=60 QEMU_REBOOT_ACTION=reset SSH_PORT="$port" RUN_DIR="$run" DISKS_DIR="$base" DISK_MASTER="$disk" OPENCORE_MASTER="$base/persistent/OpenCore.qcow2" OVMF_VARS_MASTER="$base/persistent/OVMF_VARS.fd" PERSISTENT_DIR="$base/persistent" INSTALL_MEDIA="$m" RAM="${RAM}G" CPU_CORES="$CORES" CPU_THREADS="$CORES" RAILS_DIR="$RAILS_DIR"; "$REIMS_VGPU_ROOT/vm/boot-x86.sh" --persistent --device reims-vgpu-pci --rail "$VM_ID"; }
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  preflight
  echo '1) Instalar macOS'
  read -r -p 'Escolha [1]: ' q
  [[ "$q" == 1 ]] || exit 0
  choose
  resources
  new_id
  create_installing_state
  prepare
fi
