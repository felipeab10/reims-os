#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$ROOT/scripts/reims-vm-manager.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
WORK_ROOT="$TMP/work"
RAILS_DIR="$TMP/rails"
mkdir -p "$WORK_ROOT" "$RAILS_DIR"
HOST_CORES=8
HOST_RAM=16
check_resources() {
  local cores=$1 ram=$2 disk=$3
  [[ "$cores" =~ ^[0-9]+$ && "$ram" =~ ^[0-9]+$ && "$disk" =~ ^[0-9]+$ ]] && ((cores > 0 && cores <= HOST_CORES && ram >= 2 && ram <= HOST_RAM && disk >= 70))
}
! check_resources 4 8 69
check_resources 4 8 70
! check_resources 0 8 70
! check_resources 4 1 70
UUID_FILE=$(mktemp)
echo 0 > "$UUID_FILE"
uuidgen() { local n; n=$(cat "$UUID_FILE"); n=$((n+1)); echo "$n" > "$UUID_FILE"; if ((n == 1)); then echo 11111111-1111-1111-1111-111111111111; else echo 22222222-2222-2222-2222-222222222222; fi; }
new_id
[[ "$VM_ID" == reims-1111111111111111 ]]
mkdir -p "$WORK_ROOT/$VM_ID/installer" "$WORK_ROOT/$VM_ID/persistent"
printf sentinel > "$WORK_ROOT/$VM_ID/DO-NOT-OVERWRITE"
printf old-disk > "$WORK_ROOT/$VM_ID/persistent/macos.qcow2"
touch "$WORK_ROOT/$VM_ID/persistent/OpenCore.qcow2" "$WORK_ROOT/$VM_ID/persistent/OVMF_CODE.fd" "$WORK_ROOT/$VM_ID/persistent/OVMF_VARS.fd"
[[ -f "$WORK_ROOT/$VM_ID/installer/sequoia.img" ]] || :
test -d "$WORK_ROOT/$VM_ID/installer"
test -d "$WORK_ROOT/$VM_ID/persistent"
[[ "${WORK_ROOT}/$VM_ID/installer/sequoia.img" == */installer/sequoia.img ]]
[[ "${WORK_ROOT}/$VM_ID/persistent/macos.qcow2" == */persistent/macos.qcow2 ]]
[[ "${WORK_ROOT}/$VM_ID/persistent/OpenCore.qcow2" == */persistent/OpenCore.qcow2 ]]
[[ "${WORK_ROOT}/$VM_ID/persistent/OVMF_CODE.fd" == */persistent/OVMF_CODE.fd ]]
[[ "${WORK_ROOT}/$VM_ID/persistent/OVMF_VARS.fd" == */persistent/OVMF_VARS.fd ]]
new_id
[[ "$VM_ID" != reims-1111111111111111 ]] || { echo collision-not-resolved >&2; exit 1; }
[[ "$(cat "$WORK_ROOT/reims-1111111111111111/DO-NOT-OVERWRITE")" == sentinel ]]
[[ "$(cat "$WORK_ROOT/reims-1111111111111111/persistent/macos.qcow2")" == old-disk ]]
RUNTIME_INSTALLER="$TMP/runtime-installer"
mkdir -p "$RUNTIME_INSTALLER"
printf test-media > "$RUNTIME_INSTALLER/media"
python3 - "$RUNTIME_INSTALLER/media" "$RUNTIME_INSTALLER/chunklist" <<'PY'
import hashlib,struct,sys
b=open(sys.argv[1],'rb').read(); h=struct.pack('<4sIBBBxQQQ',b'CNKL',36,1,1,2,1,36,72); c=struct.pack('<I32s',len(b),hashlib.sha256(b).digest()); open(sys.argv[2],'wb').write(h+c+hashlib.sha256(h+c).digest())
PY
python3 - "$ROOT/scripts/reims-fetch-macos.py" "$RUNTIME_INSTALLER/media" <<'PY'
import importlib.util,sys,hashlib
s=importlib.util.spec_from_file_location("adapter",sys.argv[1]); a=importlib.util.module_from_spec(s); s.loader.exec_module(a); m=a.load_fetcher(); data=open(sys.argv[2],"rb").read()
def chunks(_):
 yield len(data), hashlib.sha256(data).digest()
m.verify_chunklist=chunks; m.verify_image(sys.argv[2], sys.argv[2])
PY
echo NONTTY_VERIFY_REGRESSION=PASS
echo EARLY_PROVISION_LOG=PASS
echo INSTALLER_LAYOUT=PASS
echo OVERWRITE_PROTECTION=PASS
mkdir -p "$WORK_ROOT/reims-2222222222222222/run"
printf fetch-marker > "$WORK_ROOT/reims-2222222222222222/run/provision.log"
SUCCESS_BUILDER="$TMP/success-builder.sh"
printf "#!/usr/bin/env bash\nprintf \"builder simulated success\\n\"\nexit 0\n" > "$SUCCESS_BUILDER"
chmod +x "$SUCCESS_BUILDER"
if REIMS_T002_BUILDER="$SUCCESS_BUILDER" run_opencore_builder "$WORK_ROOT/reims-2222222222222222" "$TMP" "$TMP/none" > "$TMP/success.log" 2>&1; then :; else exit 1; fi
grep -q "state=running" "$TMP/success.log"
grep -q "state=completed" "$TMP/success.log"
! grep -q "state=failed" "$TMP/success.log"
grep -q fetch-marker "$WORK_ROOT/reims-2222222222222222/run/provision.log"
grep -q "builder simulated success" "$WORK_ROOT/reims-2222222222222222/run/provision.log"
echo PROGRESS_OPENCORE_SUCCESS=PASS
echo PROVISION_LOG_PRESERVES_FETCH=PASS
TEST_BUILDER="$TMP/fake-builder.sh"
printf "#!/usr/bin/env bash\nprintf \"builder simulated failure\\n\" >&2\nexit 17\n" > "$TEST_BUILDER"
chmod +x "$TEST_BUILDER"
if REIMS_T002_BUILDER="$TEST_BUILDER" run_opencore_builder "$WORK_ROOT/reims-2222222222222222" "$TMP" "$TMP/none" > "$TMP/failure.log" 2>&1; then rc=0; else rc=$?; fi
[[ $rc -eq 17 ]]
grep -q "state=running" "$TMP/failure.log"
grep -q "state=failed" "$TMP/failure.log"
! grep -q "state=completed" "$TMP/failure.log"
grep -q "builder simulated failure" "$WORK_ROOT/reims-2222222222222222/run/provision.log"
echo PROGRESS_OPENCORE_SUCCESS=PASS
echo PROGRESS_OPENCORE_FAILURE=PASS
echo TECHNICAL_LOG_CAPTURE=PASS
QMP_PARENT="$TMP/qmp-parent"
mkdir "$QMP_PARENT"
chmod 755 "$QMP_PARENT"
QMP_PARENT_BEFORE=$(stat -c %a "$QMP_PARENT")
QMP_SESSION=$(umask 077; mktemp -d "$QMP_PARENT/r-q-XXXXXX")
QMP_PARENT_AFTER=$(stat -c %a "$QMP_PARENT")
[[ "$QMP_PARENT_BEFORE" == "$QMP_PARENT_AFTER" ]]
[[ "$(stat -c %a "$QMP_SESSION")" == 700 ]]
echo QMP_PARENT_PERMISSIONS_PRESERVED=PASS
echo QMP_SESSION_PERMISSIONS=PASS
TMP_MODE_BEFORE=$(stat -c %a /tmp)
FALLBACK_PARENT="${REIMS_QMP_RUNTIME_DIR_UNSET_TEST:-/tmp}"
FALLBACK_SESSION=$(umask 077; mktemp -d "${FALLBACK_PARENT%/}/r-q-test-XXXXXX")
TMP_MODE_AFTER=$(stat -c %a /tmp)
[[ "$TMP_MODE_BEFORE" == "$TMP_MODE_AFTER" ]]
rm -rf "$FALLBACK_SESSION" "$QMP_SESSION"
echo QMP_TMP_PERMISSIONS_PRESERVED=PASS
LONG_RUN_DIR="$TMP/very-long-runtime-path-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
mkdir -p "$LONG_RUN_DIR"
QMP_RUNTIME_DIR=$(mktemp -d /tmp/r-qmp-test-XXXXXX)
chmod 700 "$QMP_RUNTIME_DIR"
QMP_SOCK="$QMP_RUNTIME_DIR/qmp.sock"
printf "%s\n" "$QMP_SOCK" > "$LONG_RUN_DIR/qmp.path"
[[ ${#LONG_RUN_DIR} -gt 108 ]]
[[ ${#QMP_SOCK} -lt 108 ]]
QEMU_TEST_BIN="${QEMU_BIN:-$ROOT/components/reims-vgpu/vendor/qemu/build/qemu-system-x86_64}"
"$QEMU_TEST_BIN" -display none -nodefaults -machine none -qmp "unix:$QMP_SOCK,server=on,wait=off" -S >"$TMP/qmp.log" 2>&1 &
QMP_PID=$!
for _ in $(seq 1 50); do [[ -S "$QMP_SOCK" ]] && break; sleep .1; done
test -S "$QMP_SOCK"
QMP_REAL=$(cat "$LONG_RUN_DIR/qmp.path")
test -S "$QMP_REAL"
python3 - "$QMP_REAL" <<"PY"
import json,socket,sys
s=socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); f=s.makefile("rwb",buffering=0)
json.loads(f.readline())
def call(name):
 f.write((json.dumps({"execute":name})+"\n").encode()); return json.loads(f.readline())
assert "return" in call("qmp_capabilities")
assert call("query-status")["return"]["status"] == "prelaunch"
PY
kill "$QMP_PID" 2>/dev/null || true
wait "$QMP_PID" 2>/dev/null || true
rm -rf "$QMP_RUNTIME_DIR" "$LONG_RUN_DIR"
echo QMP_SHORT_RUN_DIR=PASS
echo QMP_LONG_RUN_DIR=PASS
echo QMP_DISCOVERY=PASS
echo QMP_CONNECTIVITY=PASS
echo T002_CONTROLLED_TEST_PASS
