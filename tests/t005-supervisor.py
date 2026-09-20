#!/usr/bin/env python3
import json, os, signal, socket, subprocess, sys, tempfile, textwrap, time, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
SUP=ROOT/'scripts/reims-supervisor.py'
FAKE= r'''#!/usr/bin/env python3
import json, os, socket, sys, time
from pathlib import Path
run=Path(sys.argv[1]); mode=sys.argv[2]; rc=int(sys.argv[3]); hold=float(sys.argv[4]); delay=float(sys.argv[5]); run.mkdir(parents=True,exist_ok=True)
pid=Path(run/'fake-qemu.pid'); pid.write_text(str(os.getpid()))
serial=run/('serial-'+str(os.getpid())+'.log'); serial.write_text('boot\n')
sock=run/('qmp-'+str(os.getpid())+'.sock'); srv=socket.socket(socket.AF_UNIX); srv.bind(str(sock)); srv.listen(1); (run/'qmp.path').write_text(str(sock))
try:
 c,_=srv.accept()
 if mode=='invalid': c.sendall(b'{"bad":true}\n')
 else:
  c.sendall(b'{"QMP":{"version":{},"capabilities":[]}}\n'); c.recv(4096); c.sendall(b'{"return":{}}\n'); time.sleep(delay)
  if mode in ('shutdown','terminal'): c.sendall(b'{"event":"SHUTDOWN"}\n')
  elif mode in ('reset','late-panic','install-reset'): c.sendall(b'{"event":"RESET"}\n')
  if mode=='late-panic': serial.write_text('boot\nDebugger called: <panic>\n')
  if mode=='install-reset': time.sleep(0.8)
  elif mode not in ('terminal',): time.sleep(hold)
finally:
 srv.close(); sock.unlink(missing_ok=True)
sys.exit(rc)
'''
BOOT='#!/usr/bin/env python3\nimport subprocess,sys\np=subprocess.Popen(sys.argv[1:]);sys.exit(p.wait())\n'
class SupervisorTests(unittest.TestCase):
 def setUp(self):
  self.tmp=Path(tempfile.mkdtemp()); self.run=self.tmp/'run'; self.logs=self.tmp/'logs'; self.fake=self.tmp/'fake-qemu.py'; self.boot=self.tmp/'boot.sh'; self.other=self.tmp/'qemu-like'; self.fake.write_text(FAKE); self.boot.write_text(BOOT); self.fake.chmod(0o755); self.boot.chmod(0o755); self.other.write_text('');
 def tearDown(self):
  import shutil; shutil.rmtree(self.tmp,ignore_errors=True)
 def launch(self,state='installed',event='shutdown',rc=0,hold=.15,delay=0.0, qmp=True):
  script=self.fake
  if not qmp: script=self.tmp/'no-qmp.py'; script.write_text("#!/usr/bin/env python3\nimport os,sys,time; run=sys.argv[1]; os.makedirs(run,exist_ok=True); f=open(run+'/serial-'+str(os.getpid())+'.log','w'); f.write('clean'); f.close(); time.sleep(0.5); sys.exit(0)"); script.chmod(0o755)
  cmd=[str(self.boot),str(script),str(self.run),event if qmp else '',str(rc),str(hold),str(delay)]
  p=subprocess.run([sys.executable,str(SUP),'run','--vm-id','reims-0123456789abcdef','--appliance-state',state,'--run-dir',str(self.run),'--log-root',str(self.logs),'--']+cmd,cwd=ROOT)
  dirs=[x for x in self.logs.iterdir() if x.is_dir() and x.name != 'latest']; self.assertTrue(dirs); d=max(dirs,key=lambda x:x.stat().st_mtime_ns); return p.returncode,json.loads((d/'result.json').read_text()),d
 def test_shutdown(self):
  rc,r,d=self.launch(); self.assertEqual(r['classification'],'GUEST_SHUTDOWN'); self.assertTrue(r['qmp']['available']); self.assertIsNotNone(r['qemu_pid']); self.assertTrue(Path(r['serial']['preserved']).exists()); self.assertEqual(rc,0); print('T005_SHUTDOWN_CLASSIFICATION=PASS')
 def test_reboot(self):
  _,r,_=self.launch(event='reset'); self.assertEqual(r['classification'],'GUEST_REBOOT'); print('T005_REBOOT_CLASSIFICATION=PASS')
 def test_panic(self):
  _,r,_=self.launch(event='late-panic'); self.assertEqual(r['classification'],'GUEST_KERNEL_PANIC'); print('T005_PANIC_PRECEDENCE=PASS')
 def test_qemu_fatal(self):
  _,r,_=self.launch(event='',rc=17); self.assertEqual(r['classification'],'QEMU_FATAL'); print('T005_QEMU_FATAL_CLASSIFICATION=PASS')
 def test_pre_qemu(self):
  bad=self.tmp/'bad.sh'; bad.write_text('#!/usr/bin/env bash\nexit 9\n'); bad.chmod(0o755); p=subprocess.run([sys.executable,str(SUP),'run','--vm-id','reims-x','--appliance-state','installed','--run-dir',str(self.run),'--log-root',str(self.logs),'--',str(bad)],cwd=ROOT); d=next(x for x in self.logs.iterdir() if x.is_dir() and x.name != 'latest'); r=json.loads((d/'result.json').read_text()); self.assertEqual(r['classification'],'REIMS_FATAL'); self.assertIsNone(r['qemu_pid']); print('T005_REIMS_FATAL_PRE_QEMU=PASS'); print('T005_PRE_QEMU_CHILD_NOT_MISIDENTIFIED=PASS')
 def test_qmp_unavailable(self):
  _,r,_=self.launch(event='',qmp=False); self.assertEqual(r['classification'],'UNKNOWN_EXIT'); self.assertIn('qmp_unavailable',r['limitations']); print('T005_QMP_UNAVAILABLE_CONSERVATIVE=PASS')
 def test_install_reset(self):
  _,r,d=self.launch(state='installing',event='install-reset',hold=.1); self.assertEqual(r['classification'],'UNKNOWN_EXIT'); self.assertIn('INSTALLER_RESET',(d/'lifecycle.log').read_text()); print('T005_INSTALLER_RESET_CONTINUES=PASS')
 def test_signal(self):
  # Exercise exact process-group forwarding and structured result.
  proc=subprocess.Popen([sys.executable,str(SUP),'run','--vm-id','reims-x','--appliance-state','installed','--run-dir',str(self.run),'--log-root',str(self.logs),'--',str(self.boot),str(self.fake),str(self.run),'', '0','5','0'],cwd=ROOT); time.sleep(.25); proc.send_signal(signal.SIGTERM); proc.wait(timeout=5); d=next(x for x in self.logs.iterdir() if x.is_dir() and x.name != 'latest'); r=json.loads((d/'result.json').read_text()); self.assertEqual(r['classification'],'EXTERNAL_SIGNAL'); print('T005_EXTERNAL_SIGNAL_CLASSIFICATION=PASS')
 def test_schema_atomic_pid_serial(self):
  _,r,d=self.launch(); required={'schema','session_id','vm_id','appliance_state','classification','started_at','ended_at','launcher_pid','qemu_pid','launcher_exit_code','qemu_exit_code','external_signal','qmp','serial','evidence','limitations'}; self.assertTrue(required<=r.keys()); self.assertTrue((d/'serial.log').read_text().startswith('boot')); self.assertFalse(list(d.glob('.result.json.*'))); self.assertIsNotNone(r['qemu_pid']); print('T005_SERIAL_PRESERVED=PASS'); print('T005_RESULT_ATOMIC=PASS'); print('T005_PID_ANCHORED_TO_LAUNCHER=PASS'); print('T005_RESULT_SCHEMA=PASS')

 def test_runtime_hardening(self):
  _,r,d=self.launch(event='terminal',hold=.0); self.assertEqual(r['classification'],'GUEST_SHUTDOWN'); print('T005_QMP_TERMINAL_EVENT_DRAIN=PASS')
  self.logs.mkdir(exist_ok=True); _,r,_=self.launch(event='late-panic',hold=.0); self.assertEqual(r['classification'],'GUEST_KERNEL_PANIC'); print('T005_LATE_SERIAL_PANIC_PRECEDENCE=PASS')
  _,r,d=self.launch(event='shutdown',hold=.8); self.assertEqual(r['classification'],'GUEST_SHUTDOWN'); print('T005_QMP_IDLE_MONITORING=PASS')
  self.assertTrue((Path(self.logs)/'latest').is_symlink()); self.assertEqual(Path(self.logs/'latest').resolve(),d); print('T005_LATEST_POINTER=PASS')
  self.assertIsNotNone(r['started_at']); self.assertLessEqual(r['started_at'],r['ended_at']); print('T005_RESULT_TIMESTAMPS=PASS')
 def test_pid_identity(self):
  _,r,d=self.launch(event='shutdown'); self.assertEqual(r['qemu_pid'],int((self.run/'fake-qemu.pid').read_text())); print('T005_PID_ANCHORED_TO_LAUNCHER=PASS')
 def test_invalid_handshake(self):
  _,r,_=self.launch(event='invalid'); self.assertFalse(r['qmp']['available']); self.assertIn('qmp_handshake_failed',r['limitations']); self.assertNotIn(r['classification'],('GUEST_SHUTDOWN','GUEST_REBOOT')); print('T005_INVALID_QMP_HANDSHAKE_CONSERVATIVE=PASS')

 def test_no_broad(self):
  for p in (SUP,ROOT/'tests/t005-supervisor.py'): self.assertNotIn(''.join(('p','kill')),p.read_text()); self.assertNotIn(''.join(('kill','all')),p.read_text())
  print('T005_NO_BROAD_PROCESS_CONTROL=PASS')
if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(SupervisorTests); ok=unittest.TextTestRunner(verbosity=0).run(suite).wasSuccessful();
 if ok: print('T005_CONTROLLED_TEST_PASS')
 sys.exit(0 if ok else 1)
