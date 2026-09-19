#!/usr/bin/env python3
"""Versioned persistent appliance state for Reims OS."""
import argparse, json, os, re, sys, tempfile
from pathlib import Path

SCHEMA = 1
ROOT_DEFAULT = "/var/lib/reims"
STATES = {"unconfigured", "installing", "installed", "recovery"}
MACOS = {"ventura", "sonoma", "sequoia"}
VM_RE = re.compile(r"^reims-[0-9a-f]{16}$")
FIELDS = ("schema", "configured", "vm_id", "macos", "state", "cpu", "ram_gb", "disk_gb")
TRANSITIONS = {"unconfigured": {"unconfigured", "installing"}, "installing": {"installing", "installed", "recovery"}, "installed": {"installed", "recovery"}, "recovery": {"recovery", "installing", "installed"}}

def root():
    return Path(os.environ.get("REIMS_STATE_ROOT", ROOT_DEFAULT)).expanduser()

def state_path(base=None):
    return (Path(base) if base else root()) / "state.json"

def validate_state(value):
    if not isinstance(value, dict): raise ValueError("state must be a JSON object")
    missing = [f for f in FIELDS if f not in value]
    if missing: raise ValueError("missing required field(s): " + ", ".join(missing))
    if type(value["schema"]) is not int or value["schema"] != SCHEMA: raise ValueError("unsupported schema (expected 1)")
    state = value["state"]
    if state not in STATES: raise ValueError("invalid state: " + repr(state))
    configured = value["configured"]
    if type(configured) is not bool: raise ValueError("configured must be boolean")
    if configured != (state != "unconfigured"): raise ValueError("configured contradicts state")
    if state == "unconfigured":
        if any(value[k] is not None for k in ("vm_id", "macos", "cpu", "ram_gb", "disk_gb")): raise ValueError("unconfigured fields must be null")
        return value
    if not isinstance(value["vm_id"], str) or not VM_RE.fullmatch(value["vm_id"]): raise ValueError("invalid vm_id")
    if value["macos"] not in MACOS: raise ValueError("invalid macos")
    for key in ("cpu", "ram_gb", "disk_gb"):
        if type(value[key]) is not int: raise ValueError(key + " must be an integer")
    if value["cpu"] <= 0 or value["ram_gb"] < 2 or value["disk_gb"] < 70: raise ValueError("invalid resources")
    return value

def read_state(base=None, missing_ok=False):
    path = state_path(base)
    try: raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        if missing_ok: return {"schema": 1, "configured": False, "vm_id": None, "macos": None, "state": "unconfigured", "cpu": None, "ram_gb": None, "disk_gb": None}
        raise ValueError("state.json is absent")
    try: value = json.loads(raw)
    except json.JSONDecodeError as e: raise ValueError("state.json is corrupt: " + str(e))
    return validate_state(value)

def write_state(value, base=None, fail_before_replace=False):
    value = validate_state(value); path = state_path(base); path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".state.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, indent=2, sort_keys=True); f.write("\n"); f.flush(); os.fsync(f.fileno())
        if fail_before_replace: raise OSError("simulated failure before replace")
        os.replace(name, path)
        try:
            dfd = os.open(path.parent, os.O_RDONLY); os.fsync(dfd); os.close(dfd)
        except OSError: pass
    finally:
        try: os.unlink(name)
        except FileNotFoundError: pass
    return value

def paths(value=None, base=None):
    value = value or read_state(base); base_root = Path(base) if base is not None else root(); vm = base_root / "vms" / value["vm_id"] if value["vm_id"] else None
    if vm is None: return {"VM_ROOT": None}
    persistent = vm / "persistent"
    return {"VM_ROOT": str(vm), "PERSISTENT_DIR": str(persistent), "INSTALLER_DIR": str(vm/"installer"), "RUN_DIR": str(vm/"run"), "SERIAL_DIR": str(vm/"serial"), "MACOS_DISK": str(persistent/"macos.qcow2"), "OPENCORE": str(persistent/"OpenCore.qcow2"), "OVMF_CODE": str(persistent/"OVMF_CODE.fd"), "OVMF_VARS": str(persistent/"OVMF_VARS.fd"), "RAILS_DIR": str(base_root/"rails")}

def main(argv=None):
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init"); c=sub.add_parser("configure"); c.add_argument("--vm-id",required=True); c.add_argument("--macos",required=True); c.add_argument("--cpu",type=int,required=True); c.add_argument("--ram-gb",type=int,required=True); c.add_argument("--disk-gb",type=int,required=True)
    for n in ("show","validate","status","paths"): sub.add_parser(n)
    t=sub.add_parser("transition"); t.add_argument("state", choices=sorted(STATES))
    args=p.parse_args(argv)
    try:
        if args.cmd == "init":
            path = state_path()
            if path.exists():
                current = read_state()
                if current["configured"]:
                    raise ValueError("state already contains a configured primary VM")
                print("state=unconfigured")
            else:
                write_state({"schema":1,"configured":False,"vm_id":None,"macos":None,"state":"unconfigured","cpu":None,"ram_gb":None,"disk_gb":None})
                print("state=unconfigured")
        elif args.cmd == "configure":
            path = state_path()
            if path.exists() and read_state()["configured"]:
                raise ValueError("a configured primary VM already exists")
            write_state({"schema":1,"configured":True,"vm_id":args.vm_id,"macos":args.macos,"state":"installing","cpu":args.cpu,"ram_gb":args.ram_gb,"disk_gb":args.disk_gb})
            print("state=installing")
        elif args.cmd in ("show","validate","status","paths"):
            s=read_state();
            if args.cmd == "paths": print(json.dumps(paths(s), indent=2, sort_keys=True))
            elif args.cmd == "show": print(json.dumps(s, indent=2, sort_keys=True))
            else: print("valid state=" + s["state"])
        else:
            s=read_state(); target=args.state
            if target not in TRANSITIONS[s["state"]]: raise ValueError("invalid transition: %s -> %s" % (s["state"], target))
            s=dict(s); s["state"]=target; s["configured"]=(target != "unconfigured"); write_state(s); print("state="+target)
    except (ValueError, OSError) as e: print("ERROR: "+str(e), file=sys.stderr); return 1
    return 0
if __name__ == "__main__": sys.exit(main())
