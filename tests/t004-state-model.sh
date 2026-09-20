#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
export REIMS_STATE_ROOT="$TMP/state-root"
S="$ROOT/scripts/reims-state.py"
run(){ python3 "$S" "$@"; }
expect_launch_failure(){ local expected="$1"; if bash "$ROOT/scripts/reims-launch.sh" --dry-run >"$TMP/launch.out" 2>"$TMP/launch.err"; then return 1; fi; grep -q "$expected" "$TMP/launch.err"; ! grep -qi 'Traceback\|unbound variable' "$TMP/launch.err"; }
run init >/dev/null; run validate >/dev/null; echo STATE_INIT=PASS; echo STATE_VALIDATE=PASS
h=$(sha256sum "$REIMS_STATE_ROOT/state.json"); run init >/dev/null; [[ "$h" == "$(sha256sum "$REIMS_STATE_ROOT/state.json")" ]]; echo INIT_IDEMPOTENT=PASS
run configure --vm-id reims-0123456789abcdef --macos sequoia --cpu 8 --ram-gb 16 --disk-gb 80 >/dev/null
h=$(sha256sum "$REIMS_STATE_ROOT/state.json"); if run init >/dev/null 2>"$TMP/init.err"; then exit 1; fi; grep -q 'configured primary VM' "$TMP/init.err"; [[ "$h" == "$(sha256sum "$REIMS_STATE_ROOT/state.json")" ]]; echo INIT_DOES_NOT_OVERWRITE_CONFIGURED=PASS
printf '{bad' > "$REIMS_STATE_ROOT/state.json"; h=$(sha256sum "$REIMS_STATE_ROOT/state.json"); if run init >/dev/null 2>"$TMP/init.err"; then exit 1; fi; grep -q corrupt "$TMP/init.err"; [[ "$h" == "$(sha256sum "$REIMS_STATE_ROOT/state.json")" ]]; echo INIT_REJECTS_CORRUPT_STATE=PASS
rm -rf "$REIMS_STATE_ROOT"; mkdir -p "$REIMS_STATE_ROOT"; run configure --vm-id reims-0123456789abcdef --macos sequoia --cpu 8 --ram-gb 16 --disk-gb 80 >/dev/null
run transition installing >/dev/null; mkdir -p "$REIMS_STATE_ROOT/vms/reims-0123456789abcdef/installer"; touch "$REIMS_STATE_ROOT/vms/reims-0123456789abcdef/installer/sequoia.img"; bash "$ROOT/scripts/reims-launch.sh" --dry-run | grep -q APPLIANCE_STATE=installing; echo LAUNCH_INSTALLING_FROM_STATE=PASS
run transition installed >/dev/null; bash "$ROOT/scripts/reims-launch.sh" --dry-run | grep -q 'INSTALL_MEDIA=<absent>'; echo LAUNCH_INSTALLED_FROM_STATE=PASS
if run transition installing >"$TMP/transition.out" 2>"$TMP/transition.err"; then exit 1; fi
grep -q 'invalid transition: installed -> installing' "$TMP/transition.err"
run show | grep -q '"state": "installed"'
echo INVALID_TRANSITION_REJECTED=PASS
python3 - "$REIMS_STATE_ROOT/state.json" <<'PY2'
import json,sys
d=json.load(open(sys.argv[1])); del d["disk_gb"]; json.dump(d,open(sys.argv[1],"w"))
PY2
if run validate >"$TMP/missing.out" 2>"$TMP/missing.err"; then exit 1; fi
grep -Eq 'missing required field.*disk_gb|disk_gb.*required' "$TMP/missing.err"
echo MISSING_FIELD_REJECTED=PASS
rm -rf "$REIMS_STATE_ROOT"; mkdir -p "$REIMS_STATE_ROOT"
run configure --vm-id reims-0123456789abcdef --macos sequoia --cpu 6 --ram-gb 13 --disk-gb 91 >/dev/null
mkdir -p "$REIMS_STATE_ROOT/vms/reims-0123456789abcdef/installer"
touch "$REIMS_STATE_ROOT/vms/reims-0123456789abcdef/installer/sequoia.img"
run transition installing >/dev/null
boot="$(bash "$ROOT/scripts/reims-launch.sh" --dry-run)"
grep -q '^VM_ID=reims-0123456789abcdef$' <<<"$boot"
grep -q '^APPLIANCE_STATE=installing$' <<<"$boot"
grep -q '^CPU_CORES=6$' <<<"$boot"
grep -q '^RAM=13G$' <<<"$boot"
grep -q "^PERSISTENT_DIR=$REIMS_STATE_ROOT/vms/reims-0123456789abcdef/persistent$" <<<"$boot"
grep -q "^INSTALL_MEDIA=$REIMS_STATE_ROOT/vms/reims-0123456789abcdef/installer/sequoia.img$" <<<"$boot"
echo BOOT_RESOURCES_FROM_STATE=PASS
run transition recovery >/dev/null; expect_launch_failure 'state is recovery'; echo LAUNCH_RECOVERY_REJECTED=PASS
printf '{bad' > "$REIMS_STATE_ROOT/state.json"; expect_launch_failure 'state.json is corrupt'; echo LAUNCH_CORRUPT_STATE_REJECTED=PASS
python3 - "$REIMS_STATE_ROOT/state.json" <<'PY'
import json,sys
d={"schema":99,"configured":False,"vm_id":None,"macos":None,"state":"unconfigured","cpu":None,"ram_gb":None,"disk_gb":None}; json.dump(d,open(sys.argv[1],'w'))
PY
expect_launch_failure 'unsupported schema'; echo LAUNCH_UNKNOWN_SCHEMA_REJECTED=PASS
rm -rf "$REIMS_STATE_ROOT"; mkdir -p "$REIMS_STATE_ROOT"
run init >/dev/null; expect_launch_failure 'state is unconfigured'; echo LAUNCH_UNCONFIGURED_REJECTED=PASS
echo LAUNCH_ERRORS_CLEAN=PASS
python3 - "$S" <<'PY'
import importlib.util,sys,tempfile,os,glob
s=importlib.util.spec_from_file_location('m',sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
v={"schema":1,"configured":True,"vm_id":"reims-0123456789abcdef","macos":"sequoia","state":"installing","cpu":8,"ram_gb":16,"disk_gb":80}
for x in ('foo','reims-123','reims-G123456789abcdef','reims-0123456789abcde'):
 d=dict(v); d['vm_id']=x
 try:m.validate_state(d);raise SystemExit(1)
 except ValueError:pass
print('INVALID_VM_ID_REJECTED=PASS')
for x in ('tahoe','monterey','SEQUOIA','foo'):
 d=dict(v);d['macos']=x
 try:m.validate_state(d);raise SystemExit(1)
 except ValueError:pass
print('INVALID_MACOS_REJECTED=PASS')
for k,x in (('cpu',0),('ram_gb',1),('disk_gb',69),('cpu',True)):
 d=dict(v);d[k]=x
 try:m.validate_state(d);raise SystemExit(1)
 except ValueError:pass
print('INVALID_RESOURCES_REJECTED=PASS')
for d in ({**v,'configured':False,'state':'installed'},{**v,'configured':True,'state':'unconfigured'},{**v,'state':'unconfigured','vm_id':'reims-0123456789abcdef'}):
 try:m.validate_state(d);raise SystemExit(1)
 except ValueError:pass
print('CONFIGURED_CONSISTENCY=PASS')
b=tempfile.mkdtemp();m.write_state(v,base=b);assert all(p.startswith(b+os.sep) for p in m.paths(v,base=b).values());print('PATHS_EXPLICIT_BASE=PASS')
PY
rm -rf "$REIMS_STATE_ROOT"; mkdir -p "$REIMS_STATE_ROOT"; run configure --vm-id reims-0123456789abcdef --macos sequoia --cpu 8 --ram-gb 16 --disk-gb 80 >/dev/null
before=$(sha256sum "$REIMS_STATE_ROOT/state.json"); python3 - "$S" <<'PY'
import importlib.util,sys,glob,os
s=importlib.util.spec_from_file_location('m',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
try:m.write_state(m.read_state(),fail_before_replace=True)
except OSError:pass
assert not glob.glob(os.path.join(os.environ['REIMS_STATE_ROOT'],'.state.*.tmp'))
PY
[[ "$before" == "$(sha256sum "$REIMS_STATE_ROOT/state.json")" ]]; echo ATOMIC_WRITE_PRESERVES_PREVIOUS=PASS
TEST_ROOT="$TMP/manager-root"; mkdir -p "$TEST_ROOT"; (export REIMS_STATE_ROOT="$TEST_ROOT"; source "$ROOT/scripts/reims-vm-manager.sh"; [[ "$WORK_ROOT" == "$TEST_ROOT/vms" && "$RAILS_DIR" == "$TEST_ROOT/rails" ]]; VM_ID=reims-0123456789abcdef VERSION=sequoia CORES=8 RAM=16 DISK=80 create_installing_state)
REIMS_STATE_ROOT="$TEST_ROOT" python3 - <<'PY'
import json,os
d=json.load(open(os.path.join(os.environ['REIMS_STATE_ROOT'],'state.json'))); assert d=={"schema":1,"configured":True,"vm_id":"reims-0123456789abcdef","macos":"sequoia","state":"installing","cpu":8,"ram_gb":16,"disk_gb":80}
PY
echo MANAGER_CREATES_INSTALLING_STATE=PASS
if grep -Eq 'reims-state\.py.*transition.*installed|reims-state\.py.*installed.*transition' "$ROOT/scripts/reims-vm-manager.sh"; then echo "ERROR: manager can automatically transition to installed" >&2; exit 1; fi
echo MANAGER_DOES_NOT_AUTO_INSTALL_STATE=PASS
TEST_ROOT="$TMP/coherent-root"; rm -rf "$TEST_ROOT"; mkdir -p "$TEST_ROOT"; (export REIMS_STATE_ROOT="$TEST_ROOT"; source "$ROOT/scripts/reims-vm-manager.sh"; [[ "$WORK_ROOT" == "$TEST_ROOT/vms" && "$RAILS_DIR" == "$TEST_ROOT/rails" ]]; run configure --vm-id reims-0123456789abcdef --macos sequoia --cpu 8 --ram-gb 16 --disk-gb 80 >/dev/null; p=$(run paths); grep -q "$TEST_ROOT/vms/reims-0123456789abcdef" <<<"$p"; grep -q "$TEST_ROOT/rails" <<<"$p"); echo STATE_AND_MANAGER_PATHS_COHERENT=PASS
if (export REIMS_STATE_ROOT="$TMP/A" REIMS_VM_WORK_ROOT="$TMP/B"; source "$ROOT/scripts/reims-vm-manager.sh") 2>"$TMP/divergent.err"; then exit 1; fi; grep -q REIMS_VM_WORK_ROOT "$TMP/divergent.err"; echo DIVERGENT_VM_ROOT_REJECTED=PASS
test -f "$ROOT/third_party/OSX-KVM/fetch-macOS-v2.py"; test -f "$ROOT/third_party/osx-serial-generator/generate-specific-bootdisk.sh"; test ! -e "$ROOT/components/reims-vgpu/third_party/OSX-KVM/fetch-macOS-v2.py"; test ! -e "$ROOT/components/reims-vgpu/third_party/osx-serial-generator/generate-specific-bootdisk.sh"; echo CANONICAL_APPLIANCE_DEPS=PASS
echo T004_CONTROLLED_TEST_PASS
