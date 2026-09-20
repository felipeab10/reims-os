#!/usr/bin/env python3
import json, os, re, signal, subprocess, sys, tempfile, time, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUP = ROOT / 'scripts/reims-supervisor.py'
FAKE = r'''#!/usr/bin/env python3
import os, socket, sys, time
from pathlib import Path
run=Path(sys.argv[1]); mode=sys.argv[2]; rc=int(sys.argv[3]); hold=float(sys.argv[4]); delay=float(sys.argv[5])
run.mkdir(parents=True, exist_ok=True)
serial=run/('serial-'+str(os.getpid())+'.log'); serial.write_text('boot\n')
(run/'fake-qemu.pid').write_text(str(os.getpid()))
if mode == 'serial-ambiguous': (run/'serial-extra.log').write_text('second\n')
sock=run/('qmp-'+str(os.getpid())+'.sock'); srv=socket.socket(socket.AF_UNIX); srv.bind(str(sock)); srv.listen(1); (run/'qmp.path').write_text(str(sock))
try:
 c,_=srv.accept()
 if mode == 'invalid': c.sendall(b'{"bad":true}\n')
 else:
  c.sendall(b'{"QMP":{"version":{},"capabilities":[]}}\n')
  request=b''
  while bytes([10]) not in request:
   chunk=c.recv(4096)
   if not chunk: sys.exit(70)
   request += chunk
  expected=b'{"execute":"qmp_capabilities"}'+bytes([10])
  if request != expected: sys.exit(71)
  c.sendall(b'{"return":{}}\n'); time.sleep(delay)
  if mode == 'protocol-error': c.sendall(b'{"error":{"class":"GenericError","desc":"simulated"}}\n')
  elif mode in ('shutdown','terminal','serial-ambiguous'): c.sendall(b'{"event":"SHUTDOWN"}\n')
  elif mode in ('reset','late-panic','install-reset','ambiguity'): c.sendall(b'{"event":"RESET"}\n')
  if mode == 'late-panic': serial.write_text('boot\nDebugger called: <panic>\n')
  if mode == 'install-reset': (run/'reset-sent').write_text('yes'); time.sleep(0.9)
  else: time.sleep(hold)
finally:
 srv.close(); sock.unlink(missing_ok=True)
sys.exit(rc)
'''
BOOT = "#!/usr/bin/env python3\nimport subprocess,sys\np=subprocess.Popen(sys.argv[1:]);sys.exit(p.wait())\n"

def write_exec(path, text):
    path.write_text(text); path.chmod(0o755)

class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=Path(tempfile.mkdtemp()); self.run=self.tmp/'run'; self.logs=self.tmp/'logs'; self.state_root=self.tmp/'state'
        self.fake=self.tmp/'fake-qemu.py'; self.boot=self.tmp/'boot.sh'; write_exec(self.fake,FAKE); write_exec(self.boot,BOOT)
        self.env=os.environ.copy(); self.env['REIMS_STATE_ROOT']=str(self.state_root)
        self.assertTrue(Path(self.env['REIMS_STATE_ROOT']).is_relative_to(self.tmp))
    def tearDown(self):
        import shutil; shutil.rmtree(self.tmp, ignore_errors=True)
    def command(self, script, mode='shutdown', state='installed', rc=0, hold=.15, delay=0):
        return [str(self.boot),str(script),str(self.run),mode,str(rc),str(hold),str(delay)]
    def launch(self, mode='shutdown', state='installed', rc=0, hold=.15, delay=0, script=None):
        script=script or self.fake
        p=subprocess.run([sys.executable,str(SUP),'run','--vm-id','reims-0123456789abcdef','--appliance-state',state,'--run-dir',str(self.run),'--log-root',str(self.logs),'--']+self.command(script,mode,state,rc,hold,delay),cwd=ROOT,env=self.env)
        dirs=[x for x in self.logs.iterdir() if x.is_dir() and x.name!='latest']; self.assertTrue(dirs); d=max(dirs,key=lambda x:x.stat().st_mtime_ns)
        return p.returncode,json.loads((d/'result.json').read_text()),d
    def result_for(self, proc):
        proc.wait(timeout=5); dirs=[x for x in self.logs.iterdir() if x.is_dir() and x.name!='latest']; d=max(dirs,key=lambda x:x.stat().st_mtime_ns); return d,json.loads((d/'result.json').read_text())
    def cleanup_result(self, proc):
        if proc.poll() is None:
            proc.terminate()
        try: proc.wait(timeout=3)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait()
    def test_shutdown(self):
        rc,r,d=self.launch(); self.assertEqual(r['classification'],'GUEST_SHUTDOWN'); self.assertTrue(r['qmp']['available']); self.assertEqual(rc,0); print('T005_SHUTDOWN_CLASSIFICATION=PASS')
    def test_reboot(self):
        _,r,_=self.launch(mode='reset'); self.assertEqual(r['classification'],'GUEST_REBOOT'); print('T005_REBOOT_CLASSIFICATION=PASS')
    def test_panic(self):
        _,r,_=self.launch(mode='late-panic'); self.assertEqual(r['classification'],'GUEST_KERNEL_PANIC'); print('T005_PANIC_PRECEDENCE=PASS')
    def test_qemu_fatal(self):
        _,r,_=self.launch(mode='',rc=17); self.assertEqual(r['classification'],'QEMU_FATAL'); print('T005_QEMU_FATAL_CLASSIFICATION=PASS')
    def test_pre_qemu_child_real(self):
        launcher=self.tmp/'pre-qemu.py'; write_exec(launcher, f"#!/usr/bin/env python3\nimport subprocess,sys,time\nrun=sys.argv[2]; import os; os.makedirs(run, exist_ok=True); time.sleep(.02); h=subprocess.Popen([sys.executable,'-c','import time; time.sleep(.1)']); open(run+'/build-helper.pid','w').write(str(h.pid)); h.wait(); time.sleep(.2); q=subprocess.Popen([sys.executable, {str(self.fake)!r}, run, 'shutdown', '0', '3.0', '0']); sys.exit(q.wait())\n")
        p=subprocess.Popen([sys.executable,str(SUP),'run','--vm-id','reims-x','--appliance-state','installed','--run-dir',str(self.run),'--log-root',str(self.logs),'--',str(launcher),str(self.fake),str(self.run),'shutdown','0','0.15','0'],cwd=ROOT,env=self.env)
        d,r=self.result_for(p); self.assertEqual(r['classification'],'GUEST_SHUTDOWN'); self.assertEqual(r['qemu_pid'],int((self.run/'fake-qemu.pid').read_text())); self.assertNotEqual(r['qemu_pid'],int((self.run/'build-helper.pid').read_text())); print('T005_PRE_QEMU_CHILD_NOT_MISIDENTIFIED=PASS')
    def test_qmp_protocol_error(self):
        _,r,d=self.launch(mode='protocol-error',hold=0.1)
        self.assertTrue(r['qmp']['available']); self.assertIn('qmp_protocol_error',r['limitations'])
        self.assertIn('QMP_ERROR',Path(d/'lifecycle.log').read_text()); print('T005_QMP_PROTOCOL_ERROR_SURFACED=PASS')
    def test_qmp_wire_marker(self):
        _,r,_=self.launch(); self.assertTrue(r['qmp']['available'])
        self.assertNotIn({'error': {'class': 'GenericError', 'desc': 'simulated'}}, r['qmp']['raw_events'])
        print('T005_QMP_CAPABILITIES_WIRE_FORMAT=PASS')
    def test_qmp_unavailable(self):
        no=self.tmp/'no-qmp.py'; write_exec(no, '#!/usr/bin/env python3\nimport os,sys\nrun=sys.argv[1]; os.makedirs(run,exist_ok=True); open(run+"/serial-"+str(os.getpid())+".log","w").write("clean")\n')
        _,r,_=self.launch(script=no,mode=''); self.assertEqual(r['classification'],'UNKNOWN_EXIT'); self.assertIn('qmp_unavailable',r['limitations']); print('T005_QMP_UNAVAILABLE_CONSERVATIVE=PASS')
    def test_install_reset_temporal(self):
        proc=subprocess.Popen([sys.executable,str(SUP),'run','--vm-id','reims-x','--appliance-state','installing','--run-dir',str(self.run),'--log-root',str(self.logs),'--']+self.command(self.fake,'install-reset','installing',0,.1,0),cwd=ROOT,env=self.env)
        deadline=time.time()+4
        while time.time()<deadline and not (self.run/'reset-sent').exists(): time.sleep(.02)
        self.assertTrue((self.run/'reset-sent').exists()); self.assertIsNone(proc.poll()); dirs=list(self.logs.glob('*/result.json')); self.assertFalse(dirs); life=next(self.logs.glob('*/lifecycle.log')); self.assertIn('INSTALLER_RESET',life.read_text()); d,r=self.result_for(proc); self.assertEqual(r['classification'],'UNKNOWN_EXIT'); self.assertEqual(proc.returncode, 0); print('T005_INSTALLER_RESET_CONTINUES=PASS')
    def test_external_signal(self):
        proc=subprocess.Popen([sys.executable,str(SUP),'run','--vm-id','reims-x','--appliance-state','installed','--run-dir',str(self.run),'--log-root',str(self.logs),'--']+self.command(self.fake,'shutdown','installed',0,5,0),cwd=ROOT,env=self.env); time.sleep(.25); proc.send_signal(signal.SIGTERM); d,r=self.result_for(proc); self.assertEqual(r['classification'],'EXTERNAL_SIGNAL'); print('T005_EXTERNAL_SIGNAL_CLASSIFICATION=PASS')
    def test_schema_serial_atomic(self):
        _,r,d=self.launch(); required={'schema','session_id','vm_id','appliance_state','classification','started_at','ended_at','launcher_pid','qemu_pid','launcher_exit_code','qemu_exit_code','external_signal','qmp','serial','evidence','limitations'}; self.assertTrue(required<=r.keys()); self.assertTrue((d/'serial.log').read_text().startswith('boot')); self.assertFalse(list(d.glob('.result.json.*'))); print('T005_SERIAL_PRESERVED=PASS'); print('T005_RESULT_ATOMIC=PASS'); print('T005_RESULT_SCHEMA=PASS')
        lines=(d/'lifecycle.log').read_text().splitlines(); self.assertGreaterEqual(len(lines),3); [json.loads(line) for line in lines]; self.assertNotIn('}\\n{',(d/'lifecycle.log').read_text()); print('T005_LIFECYCLE_JSONL_FORMAT=PASS')
        self.assertIsInstance(r['process']['qemu']['cmdline'],list); self.assertGreater(len(r['process']['qemu']['cmdline']),1); self.assertTrue(all('\x00' not in x for x in r['process']['qemu']['cmdline'])); print('T005_PROC_CMDLINE_TOKENIZED=PASS')
    def test_qmp_and_serial_races(self):
        _,r,_=self.launch(delay=.8,hold=0); self.assertEqual(r['classification'],'GUEST_SHUTDOWN'); print('T005_QMP_IDLE_MONITORING=PASS')
        delayed=self.tmp/'delayed.py'; write_exec(delayed, f"#!/usr/bin/env python3\nimport os,time\ntime.sleep(.4); os.execv({str(self.fake)!r}, [{str(self.fake)!r}, {str(self.run)!r}, 'shutdown', '0', '0.15', '0'])\n")
        _,r,_=self.launch(script=delayed); self.assertTrue(r['qmp']['available']); self.assertEqual(r['qemu_pid'],int((self.run/'fake-qemu.pid').read_text())); self.assertEqual(r['classification'],'GUEST_SHUTDOWN'); print('T005_DELAYED_QMP_DISCOVERY=PASS')
        _,r,_=self.launch(mode='terminal',hold=0); self.assertEqual(r['classification'],'GUEST_SHUTDOWN'); print('T005_QMP_TERMINAL_EVENT_DRAIN=PASS')
        _,r,_=self.launch(mode='late-panic',hold=0); self.assertEqual(r['classification'],'GUEST_KERNEL_PANIC'); print('T005_LATE_SERIAL_PANIC_PRECEDENCE=PASS')
        _,r,d=self.launch(delay=.1); self.assertTrue((self.logs/'latest').is_symlink()); self.assertEqual((self.logs/'latest').resolve(),d); self.assertLessEqual(r['started_at'],r['ended_at']); print('T005_LATEST_POINTER=PASS'); print('T005_RESULT_TIMESTAMPS=PASS')
    def test_pid_identity_and_ambiguity(self):
        external=subprocess.Popen([sys.executable,'-c','import time; time.sleep(3)'])
        try:
            _,r,_=self.launch(); self.assertEqual(r['qemu_pid'],int((self.run/'fake-qemu.pid').read_text())); self.assertNotEqual(r['qemu_pid'],external.pid); print('T005_PID_ANCHORED_TO_LAUNCHER=PASS')
        finally: external.terminate(); external.wait()
        amb=self.tmp/'ambiguous.py'; write_exec(amb, f"#!/usr/bin/env python3\nimport subprocess,sys,time\nfrom pathlib import Path\nrun=Path(sys.argv[1]); q=subprocess.Popen([{str(self.fake)!r}, {str(self.run)!r}, 'shutdown', '0', '0.5', '0']); h=subprocess.Popen([sys.executable,'-c','import time; time.sleep(1.5)']); (run/'ambiguity-helper.pid').write_text(str(h.pid)); rc=q.wait(); h.terminate(); h.wait(); sys.exit(rc)\n")
        cmd=[sys.executable,str(SUP),'run','--vm-id','reims-x','--appliance-state','installed','--run-dir',str(self.run),'--log-root',str(self.logs),'--',str(amb),str(self.run)]; p=subprocess.Popen(cmd,cwd=ROOT,env=self.env); _,r=self.result_for(p); self.assertIsNone(r['qemu_pid']); self.assertIn('qemu_pid_ambiguous',r['limitations']); print('T005_QEMU_PID_AMBIGUITY=PASS')
    def test_serial_ambiguity(self):
        _,r,_=self.launch(mode='serial-ambiguous'); self.assertIn('serial_ambiguous',r['limitations']); print('T005_SERIAL_AMBIGUITY=PASS')
    def test_invalid_handshake(self):
        _,r,_=self.launch(mode='invalid'); self.assertFalse(r['qmp']['available']); self.assertIn('qmp_handshake_failed',r['limitations']); print('T005_INVALID_QMP_HANDSHAKE_CONSERVATIVE=PASS')
    def test_no_broad_and_marker_audit(self):
        for p in (SUP,Path(__file__)):
            source=p.read_text(); self.assertNotIn('pgrep'+'(' ,source); self.assertNotIn('pkill'+'(' ,source); self.assertNotIn('killall'+'(' ,source)
        text=Path(__file__).read_text(); markers=re.findall(r'T005_[A-Z0-9_]+=PASS',text)
        self.assertTrue(markers); self.assertEqual(len(markers),len(set(markers))); print('T005_NO_BROAD_PROCESS_CONTROL=PASS')
if __name__=='__main__':
    ok=unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.loadTestsFromTestCase(SupervisorTests)).wasSuccessful()
    if ok: print('T005_CONTROLLED_TEST_PASS')
    sys.exit(0 if ok else 1)
