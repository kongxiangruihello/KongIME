import sys,tempfile,unittest,subprocess,string,json,hashlib
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,profile_backup,local_snapshots,upgrade_check,engine_check,workflow,library_tools
class V024Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.old=core.DATA,core.RIME
  core.DATA=self.root/'data';core.RIME=self.root/'rime'
 def tearDown(self):core.DATA,core.RIME=self.old;self.tmp.cleanup()
 def test_remember_preference_backup_and_generation(self):
  s=core.state();s['app_preferences']=[core.normalize_app_preference(dict(id='com.example.Writer',name='写作',mode='remember'))];core.save(s)
  backup=profile_backup.snapshot();profile_backup.restore(backup)
  self.assertEqual(core.state()['app_preferences'],s['app_preferences'])
  core.generate(core.RIME,core.state());text=(core.RIME/'squirrel.custom.yaml').read_text()
  self.assertIn('"kongime/remember_apps/com.example.Writer": true',text)
  self.assertIn('"app_options/com.example.Writer/ascii_mode": false',text)
 def test_upgrade_baseline_and_changes(self):
  core.save_phrase(dict(code='rq',text='{W}',dynamic=True));local_snapshots.on_upgrade('0.23.0')
  self.assertEqual(upgrade_check.read()['comparison'],'none')
  local_snapshots.on_upgrade('0.24.0');r=upgrade_check.read();self.assertTrue(r['ok']);self.assertEqual(r['comparison'],'same')
  core.save_phrase(dict(code='yx',text='mail'));self.assertTrue(upgrade_check.read()['changed_since'])
  r=upgrade_check.retry('0.24.0');self.assertEqual(r['comparison'],'different');self.assertTrue(r['ok'])
  self.assertEqual(next(x for x in r['categories'] if x['label']=='短语')['added'],1)
 def test_missing_library_report_preserves_data_and_backup(self):
  lib=library_tools.save(dict(name='测试',text='你好\tni hao\t100'));baseline=local_snapshots.create('before')
  path=core.DATA/'libraries'/(lib['id']+'.json');path.unlink();before=(core.DATA/'state.json').read_bytes()
  local_snapshots.on_upgrade('0.24.0');r=upgrade_check.read()
  self.assertFalse(r['ok']);self.assertIn('无法完整读取',r['errors'][0]);self.assertEqual(r['baseline'],baseline['name'])
  self.assertEqual((core.DATA/'state.json').read_bytes(),before);self.assertFalse(path.exists())
 def test_unreadable_baseline_is_not_reported_as_matching(self):
  core.save(core.state());baseline=local_snapshots.create('before');p=core.DATA/'snapshots'/baseline['name'];p.write_text('{}')
  r=upgrade_check.inspect('0.24.0',baseline=baseline['name']);self.assertTrue(r['ok']);self.assertEqual(r['comparison'],'unavailable')
 def test_engine_check_detects_regression_without_live_data_writes(self):
  s=core.state();s['personal']=[core.normalize(c,c,100) for c in string.ascii_uppercase];core.make_bundle(core.RIME,s)
  app=core.ROOT/'branding/payload/Squirrel.app'
  def compile():
   p=subprocess.run([str(app/'Contents/MacOS/rime_deployer'),'--build',str(core.RIME),str(app/'Contents/SharedSupport'),str(core.RIME/'build')],capture_output=True,text=True,timeout=120)
   self.assertEqual(p.returncode,0,p.stderr)
  compile();sentinel=core.RIME/'qingyan.userdb';sentinel.mkdir();(sentinel/'DO_NOT_OPEN').write_text('private learning sentinel')
  def hashes():return {str(p.relative_to(core.RIME)):hashlib.sha256(p.read_bytes()).hexdigest() for p in core.RIME.rglob('*') if p.is_file()}
  before=hashes();r=engine_check.run(app,True);self.assertTrue(r['ok']);self.assertEqual(before,hashes())
  schema=core.RIME/'qingyan.schema.yaml';fixed=schema.read_text();a=fixed.index('      - xform/^A$/a/');b=fixed.index('      - erase/^[A-Z]$/')+len('      - erase/^[A-Z]$/');schema.write_text(fixed[:a]+'      - xlit/ABCDEFGHIJKLMNOPQRSTUVWXYZ/abcdefghijklmnopqrstuvwxyz/'+fixed[b:]);compile()
  with self.assertRaisesRegex(ValueError,'未通过'):engine_check.run(app,True)
  s['settings']['abbreviation']=False;core.generate(core.RIME,s);compile();r=engine_check.run(app,False)
  self.assertTrue(r['ok']);self.assertTrue(all(x['skipped'] for x in r['checks'][1:]))
 def test_failed_engine_check_never_claims_deploy_success_or_reloads(self):
  app=core.ROOT/'branding/payload/Squirrel.app'
  with patch.object(workflow,'client',return_value=app),patch.object(workflow,'snapshot_good'),patch.object(workflow,'file_hashes',return_value={'compiled':'test'}),patch.object(workflow.subprocess,'run',return_value=subprocess.CompletedProcess([],0)) as run,patch.object(engine_check,'run',side_effect=ValueError('输入检查未通过')):
   with self.assertRaisesRegex(ValueError,'输入检查未通过'):workflow.deploy()
   self.assertEqual(run.call_count,1);self.assertIn('--build',run.call_args[0][0])
  self.assertFalse(json.loads((core.DATA/'deployment.json').read_text())['ok'])
