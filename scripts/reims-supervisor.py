#!/usr/bin/env python3
"""Conservative QMP/serial/process supervisor for one appliance boot."""
import argparse, datetime as dt, json, os, re, signal, socket, subprocess, sys, tempfile, threading, time, uuid
from pathlib import Path

PANIC = "Debugger called: <panic>"
CLASSES = ("GUEST_SHUTDOWN", "GUEST_REBOOT", "GUEST_KERNEL_PANIC", "QEMU_FATAL", "REIMS_FATAL", "EXTERNAL_SIGNAL", "UNKNOWN_EXIT")

def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, indent=2, sort_keys=True); f.write("\n"); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
        try:
            d=os.open(path.parent, os.O_DIRECTORY); os.fsync(d); os.close(d)
        except OSError: pass
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def event(log, source, name, **extra):
    row={"timestamp":now(),"source":source,"event":name}; row.update(extra)
    with log.open("a", encoding="utf-8") as f: f.write(json.dumps(row, sort_keys=True)+"\n"); f.flush(); os.fsync(f.fileno())

def children(pid):
    try: return [int(x) for x in Path(f"/proc/{pid}/task/{pid}/children").read_text().split()]
    except (OSError, ValueError): return []
def classify(f):
    if f["panic"]: return "GUEST_KERNEL_PANIC"
    if f["external_signal"] is not None: return "EXTERNAL_SIGNAL"
    if f["launcher_exit"] is not None and not f["child_observed"] and f["launcher_exit"] != 0 and not f.get("qmp_unavailable", False): return "REIMS_FATAL"
    if f["launcher_exit"] == 0 and not f["qemu_seen"]: return "UNKNOWN_EXIT"
    if f["qemu_exit"] is not None and f["qemu_exit"] != 0: return "QEMU_FATAL"
    if f["appliance_state"] == "installed" and "RESET" in f["qmp_events"]: return "GUEST_REBOOT"
    if "SHUTDOWN" in f["qmp_events"]: return "GUEST_SHUTDOWN"
    return "UNKNOWN_EXIT"

def run(a):
    root=Path(a.log_root or os.environ.get("REIMS_LOG_ROOT", "/var/log/reims")); sid="boot-"+dt.datetime.now().strftime("%Y%m%d-%H%M%S")+"-"+uuid.uuid4().hex[:8]; out=root/sid; out.mkdir(parents=True)
    log=out/"lifecycle.log"; result=out/"result.json"; qlog=out/"qemu.log"; serial_out=out/"serial.log"
    run_dir=Path(a.run_dir); qmp_path=run_dir/"qmp.path"; before=None
    try: before=(qmp_path.stat().st_ino,qmp_path.stat().st_mtime_ns,qmp_path.read_text().strip())
    except OSError: pass
    facts={"appliance_state":a.appliance_state,"panic":False,"qemu_seen":False,"child_observed":False,"external_signal":None,"qmp_events":[],"qmp_available":False,"qmp_socket":None,"qmp_last":None,"qemu_pid":None,"qemu_exit":None,"launcher_exit":None,"serial_path":None,"serial_missing":False}
    event(log,"supervisor","session_start",session_id=sid,vm_id=a.vm_id,appliance_state=a.appliance_state)
    serial_before=set(run_dir.glob("serial-*.log"))
    child=subprocess.Popen(a.command, stdout=qlog.open("w"), stderr=subprocess.STDOUT, start_new_session=True, cwd=os.getcwd())
    event(log,"process","start",launcher_pid=child.pid)
    stop=threading.Event(); qmp_done=threading.Event(); serial_done=threading.Event()
    def on_signal(signum, _):
        if facts["external_signal"] is None:
            facts["external_signal"]=signal.Signals(signum).name; event(log,"supervisor","external_signal",signal=facts["external_signal"])
            try: os.killpg(child.pid, signum)
            except ProcessLookupError: pass
    old={s:signal.signal(s,on_signal) for s in (signal.SIGTERM,signal.SIGINT)}
    def qmp():
        deadline=time.time()+max(10,a.qmp_timeout); sock=None
        while time.time()<deadline and child.poll() is None and not stop.is_set():
            try:
                if not qmp_path.exists(): time.sleep(.02); continue
                st=(qmp_path.stat().st_ino,qmp_path.stat().st_mtime_ns,qmp_path.read_text().strip())
                if before is not None and st==before: time.sleep(.02); continue
                if not st[2]: time.sleep(.02); continue
                sock=st[2]; s=socket.socket(socket.AF_UNIX); s.settimeout(.2); s.connect(sock); facts["qmp_socket"]=sock; facts["qmp_available"]=True; event(log,"qmp","connect",socket=sock); cs=children(child.pid); facts["qemu_pid"] = cs[0] if len(cs)==1 else facts["qemu_pid"]
                reader=s.makefile("r", encoding="utf-8")
                def read():
                    while True:
                        try:
                            line=reader.readline()
                            if not line: return None
                            return json.loads(line)
                        except socket.timeout: continue
                read(); s.sendall(b'{"execute":"qmp_capabilities"}\n'); read()
                while child.poll() is None and not stop.is_set():
                    x=read()
                    if x is None: break
                    if "event" in x:
                        ev=x["event"]; facts["qmp_events"].append(ev); facts["qmp_last"]=ev; event(log,"qmp",ev,raw=x)
                        if ev=="RESET" and a.appliance_state=="installing": event(log,"qmp","INSTALLER_RESET",phase="installing")
                s.close(); return
            except (OSError, json.JSONDecodeError):
                if sock is not None: break
                time.sleep(.05)
        if not facts["qmp_available"]: event(log,"qmp","unavailable")
        qmp_done.set()
    def serial():
        known=serial_before; deadline=time.time()+max(2,a.serial_timeout)
        while child.poll() is None or time.time()<deadline:
            fresh=[p for p in run_dir.glob("serial-*.log") if p not in known]
            if len(fresh)==1:
                facts["serial_path"]=fresh[0]
                facts["qemu_seen"]=True
            elif len(fresh)>1: event(log,"serial","ambiguous",count=len(fresh))
            if facts["serial_path"] and facts["serial_path"].exists():
                text=facts["serial_path"].read_text(errors="replace")
                if PANIC in text and not facts["panic"]: facts["panic"]=True; event(log,"serial","GUEST_KERNEL_PANIC")
            if child.poll() is not None: break
            time.sleep(.03)
        if facts["serial_path"] and facts["serial_path"].exists(): serial_out.write_text(facts["serial_path"].read_text(errors="replace"), encoding="utf-8")
        elif not facts["serial_path"]: facts["serial_missing"]=True; event(log,"serial","serial_missing")
        serial_done.set()
    tq=threading.Thread(target=qmp,daemon=True); ts=threading.Thread(target=serial,daemon=True); tq.start(); ts.start()
    while child.poll() is None:
        cs=children(child.pid)
        if cs:
            facts["child_observed"]=True
        if len(cs)==1:
            facts["qemu_seen"]=True
        if len(cs)==1 and facts["qemu_pid"] is None: facts["qemu_pid"]=cs[0]; event(log,"process","qemu_child",qemu_pid=cs[0])
        elif len(cs)>1: event(log,"process","qemu_pid_ambiguous",candidates=cs)
        time.sleep(.03)
    facts["launcher_exit"]=child.returncode; event(log,"process","exit",code=child.returncode)
    stop.set(); tq.join(1); ts.join(2)
    for s,oldh in old.items(): signal.signal(s,oldh)
    if facts["qemu_pid"] is not None: facts["qemu_exit"]=child.returncode
    facts["qmp_unavailable"] = not facts["qmp_available"]
    if facts["launcher_exit"] != 0 and not facts["child_observed"] and not facts["qmp_available"]:
        facts["qmp_unavailable"] = False
    if facts["serial_path"] is None:
        fresh=[p for p in run_dir.glob("serial-*.log") if p not in serial_before]
        if len(fresh)==1:
            facts["serial_path"]=fresh[0]
            if facts["serial_path"].exists():
                serial_out.write_text(facts["serial_path"].read_text(errors="replace"), encoding="utf-8")
    if facts["serial_path"] is not None: facts["qemu_seen"]=True
    classification=classify(facts); event(log,"supervisor","classification",classification=classification)
    limitations=[]
    if not facts["qmp_available"]: limitations.append("qmp_unavailable")
    if facts["serial_missing"]: limitations.append("serial_missing")
    data={"schema":1,"session_id":sid,"vm_id":a.vm_id,"appliance_state":a.appliance_state,"classification":classification,"started_at":None,"ended_at":now(),"launcher_pid":child.pid,"qemu_pid":facts["qemu_pid"],"launcher_exit_code":facts["launcher_exit"],"qemu_exit_code":facts["qemu_exit"],"external_signal":facts["external_signal"],"qmp":{"available":facts["qmp_available"],"socket":facts["qmp_socket"],"events":facts["qmp_events"],"last_event":facts["qmp_last"]},"serial":{"source":str(facts["serial_path"]) if facts["serial_path"] else None,"preserved":str(serial_out) if serial_out.exists() else None,"panic_detected":facts["panic"]},"evidence":["qmp:"+x for x in facts["qmp_events"]],"limitations":limitations}
    atomic(result,data); latest=root/"latest"; tmp=root/(".latest-"+sid); 
    try: tmp.unlink()
    except FileNotFoundError: pass
    tmp.symlink_to(out.name); os.replace(tmp,latest)
    return 128+(-facts["launcher_exit"]) if facts["launcher_exit"]<0 else facts["launcher_exit"]
def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="mode",required=True); r=sub.add_parser("run"); r.add_argument("--vm-id",required=True); r.add_argument("--appliance-state",required=True); r.add_argument("--run-dir",required=True); r.add_argument("--log-root"); r.add_argument("--qmp-timeout",type=float,default=10); r.add_argument("--serial-timeout",type=float,default=1); r.add_argument("command",nargs=argparse.REMAINDER); a=p.parse_args();
    if a.command[:1]==["--"]: a.command=a.command[1:]
    if not a.command: p.error("run requires command after --")
    return run(a)
if __name__=="__main__": sys.exit(main())
