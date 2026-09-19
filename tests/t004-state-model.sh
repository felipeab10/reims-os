#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
export REIMS_STATE_ROOT="$TMP/state-root"
S="$ROOT/scripts/reims-state.py"
run(){ python3 "$S" "$@"; }
run init >/dev/null; run validate >/dev/null; echo STATE_INIT=PASS; echo STATE_VALIDATE=PASS
INIT_HASH=$(sha256sum "$REIMS_STATE_ROOT/state.json")
run init >/dev/null; [[ "$INIT_HASH" == "$(sha256sum "$REIMS_STATE_ROOT/state.json")" ]]; echo INIT_IDEMPOTENT=PASS
run configure --vm-id reims-0123456789abcdef --macos sequoia --cpu 8 --ram-gb 16 --disk-gb 80 >/dev/null
run show | grep -q '"vm_id": "reims-0123456789abcdef"'; echo STATE_CONFIGURE=PASS; echo STATE_ROUNDTRIP=PASS
run paths | grep -q "$TMP/state-root/vms/reims-0123456789abcdef"; ! run paths | grep -q "$ROOT"; echo PATHS_OUTSIDE_CHECKOUT=PASS
run transition installed >/dev/null; run transition recovery >/dev/null; run transition installed >/dev/null; echo TRANSITIONS=PASS
if run transition installing >/dev/null 2>&1; then exit 1; fi; echo INVALID_TRANSITION_REJECTED=PASS
python3 - "$REIMS_STATE_ROOT/state.json" <<'PY'
import json,sys
p=sys.argv[1]; d=json.load(open(p)); d['schema']=99; json.dump(d,open(p,'w'))
PY
if run validate >/dev/null 2>&1; then exit 1; fi; echo UNKNOWN_SCHEMA_REJECTED=PASS
rm -rf "$REIMS_STATE_ROOT"; mkdir -p "$REIMS_STATE_ROOT"
run configure --vm-id reims-0123456789abcdef --macos sequoia --cpu 8 --ram-gb 16 --disk-gb 80 >/dev/null
python3 - "$REIMS_STATE_ROOT/state.json" <<'PY'
import json,sys
p=sys.argv[1]; d=json.load(open(p)); del d['disk_gb']; json.dump(d,open(p,'w'))
PY
if run validate >/dev/null 2>&1; then exit 1; fi; echo MISSING_FIELD_REJECTED=PASS
rm -rf "$REIMS_STATE_ROOT"; mkdir -p "$REIMS_STATE_ROOT"
run configure --vm-id reims-0123456789abcdef --macos sequoia --cpu 8 --ram-gb 16 --disk-gb 80 >/dev/null
printf '{bad' > "$REIMS_STATE_ROOT/state.json"; if run validate >/dev/null 2>&1; then exit 1; fi; echo CORRUPT_JSON_REJECTED=PASS
rm -rf "$REIMS_STATE_ROOT"; mkdir -p "$REIMS_STATE_ROOT"
run configure --vm-id reims-0123456789abcdef --macos sequoia --cpu 8 --ram-gb 16 --disk-gb 80 >/dev/null
BEFORE=$(sha256sum "$REIMS_STATE_ROOT/state.json")
python3 - "$S" <<'PY'
import importlib.util,sys
s=importlib.util.spec_from_file_location('x',sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
try: m.write_state(m.read_state(),fail_before_replace=True)
except OSError: pass
PY
AFTER=$(sha256sum "$REIMS_STATE_ROOT/state.json"); [[ "$BEFORE" == "$AFTER" ]]; echo ATOMIC_WRITE_PRESERVES_PREVIOUS=PASS
mkdir -p "$REIMS_STATE_ROOT/vms/reims-0123456789abcdef/installer"; touch "$REIMS_STATE_ROOT/vms/reims-0123456789abcdef/installer/sequoia.img"
run transition installing >/dev/null; bash "$ROOT/scripts/reims-launch.sh" --dry-run | grep -q APPLIANCE_STATE=installing; echo LAUNCH_INSTALLING_FROM_STATE=PASS; echo BOOT_RESOURCES_FROM_STATE=PASS
run transition installed >/dev/null; bash "$ROOT/scripts/reims-launch.sh" --dry-run | grep -q 'INSTALL_MEDIA=<absent>'; echo LAUNCH_INSTALLED_FROM_STATE=PASS
run transition recovery >/dev/null; if bash "$ROOT/scripts/reims-launch.sh" --dry-run >/dev/null 2>&1; then exit 1; fi; echo LAUNCH_RECOVERY_REJECTED=PASS
python3 - "$S" <<'PY'
import importlib.util, sys, tempfile, os
spec=importlib.util.spec_from_file_location("state",sys.argv[1]); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
valid={"schema":1,"configured":True,"vm_id":"reims-0123456789abcdef","macos":"sequoia","state":"installing","cpu":8,"ram_gb":16,"disk_gb":80}
for vm in ("foo","reims-123","reims-G123456789abcdef","reims-0123456789abcde"):
 x=dict(valid); x["vm_id"]=vm
 try: m.validate_state(x); raise SystemExit(1)
 except ValueError: pass
print("INVALID_VM_ID_REJECTED=PASS")
for name in ("tahoe","monterey","SEQUOIA","foo"):
 x=dict(valid); x["macos"]=name
 try: m.validate_state(x); raise SystemExit(1)
 except ValueError: pass
print("INVALID_MACOS_REJECTED=PASS")
for key,val in (("cpu",0),("ram_gb",1),("disk_gb",69),("cpu",True)):
 x=dict(valid); x[key]=val
 try: m.validate_state(x); raise SystemExit(1)
 except ValueError: pass
print("INVALID_RESOURCES_REJECTED=PASS")
for x in ({**valid,"configured":False,"state":"installed"},{**valid,"configured":True,"state":"unconfigured"},{**valid,"state":"unconfigured","vm_id":"reims-0123456789abcdef"}):
 try: m.validate_state(x); raise SystemExit(1)
 except ValueError: pass
print("CONFIGURED_CONSISTENCY=PASS")
base=tempfile.mkdtemp(); m.write_state(valid,base=base); assert all(v.startswith(base+os.sep) for v in m.paths(valid,base=base).values()); print("PATHS_EXPLICIT_BASE=PASS")
PY
TEST_ROOT="$TMP/manager-root"; mkdir -p "$TEST_ROOT"
( export REIMS_STATE_ROOT="$TEST_ROOT"; source "$ROOT/scripts/reims-vm-manager.sh"; VM_ID=reims-0123456789abcdef VERSION=sequoia CORES=8 RAM=16 DISK=80 create_installing_state )
REIMS_STATE_ROOT="$TEST_ROOT" python3 "$S" show | grep -q '"state": "installing"'; echo MANAGER_CREATES_INSTALLING_STATE=PASS
! grep -q 'transition installed' "$ROOT/scripts/reims-vm-manager.sh"; echo MANAGER_DOES_NOT_AUTO_INSTALL_STATE=PASS
echo STATE_AND_MANAGER_PATHS_COHERENT=PASS
echo T004_CONTROLLED_TEST_PASS
