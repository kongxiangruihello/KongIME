import json,sys,tempfile,time,unittest,uuid,copy,subprocess
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,quick,learning,profile_backup,restore_review,complete_backup,library_tools

class V025Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.old=core.DATA,core.RIME
  core.DATA=self.root/'data';core.RIME=self.root/'rime';core.save(core.state());learning.root().mkdir(parents=True)
  self.tool=core.ROOT/'client/build/learning-tool';self.library=core.ROOT/'branding/payload/Squirrel.app/Contents/Frameworks/librime.1.dylib'
 def tearDown(self):
  core.DATA,core.RIME=self.old;self.tmp.cleanup();complete_backup.PENDING.clear()
 def run_worker(self,op,value=None,error=False):
  token=uuid.uuid4().hex;core.atomic_json(learning.root()/'request.json',{'id':token,'created':time.time(),'operation':op,'value':value})
  learning.worker(core.RIME,self.tool,self.library)
  r=json.loads((learning.root()/'response.json').read_text());self.assertEqual(r['id'],token)
  if error:self.assertIn('error',r)
  else:self.assertNotIn('error',r,r)
  return r
 def words(self,word='你好',count=5):return {'format':learning.FORMAT,'rows':[{'word':word,'pinyin':'ni hao','commits':count}]}
 def exported(self):
  self.run_worker('complete-export');return complete_backup.value()
 def restore(self,backup,error=False):
  return self.run_worker('complete-restore',{'backup':backup,'baseline':restore_review.fingerprint(profile_backup.snapshot())},error)
 def test_options_generation_and_legacy_defaults(self):
  s=core.state();self.assertTrue(s['settings']['language_hint']);self.assertFalse(s['settings']['pair_chinese'])
  s['settings'].update(pair_chinese=True,pair_english=True,language_hint=False);core.save(s)
  core.generate(core.RIME,s);text=(core.RIME/'squirrel.custom.yaml').read_text()
  self.assertIn('"kongime/pair_english": true',text);self.assertIn('"kongime/language_hint": false',text)
  with self.assertRaises(ValueError):core.normalize_settings({'pair_chinese':'yes'})
 def test_block_dedup_restore_and_backup(self):
  quick.change('pin','nh','你好',core.RIME);quick.change('block','nh','你好',core.RIME);quick.change('block','nihao','你好',core.RIME)
  prefs=quick.read(core.RIME)[0];self.assertEqual(len(prefs),1)
  backup=profile_backup.snapshot();quick.change('reset','nihao','你好',core.RIME);self.assertEqual(quick.read(core.RIME)[0],[])
  profile_backup.restore(backup);self.assertEqual(quick.read(core.RIME)[0],prefs)
  with self.assertRaises(ValueError):quick.normalize_preferences(prefs+[dict(prefs[0],code='nh')])
 def test_complete_real_roundtrip_and_before_backup(self):
  library_tools.save(dict(name='测试词库',text='你好\tni hao\t300'));core.save_phrase(dict(code='rq',text='{YYYY}年{M}月{D}日',dynamic=True))
  quick.change('block','zg','中国',core.RIME);self.run_worker('restore',self.words())
  before=self.exported();s=core.state();s['settings']['pair_chinese']=True;s['phrases']=[];core.save(s)
  self.run_worker('restore',self.words('您好',99));changed=self.exported()
  r=self.restore(before);self.assertTrue(r['verified'])
  actual=self.exported();self.assertEqual(restore_review.canonical(actual['profile']),restore_review.canonical(before['profile']));self.assertEqual(actual['learning'],before['learning'])
  rollback=complete_backup.value(before=True);self.assertEqual(rollback['learning'],changed['learning'])
  self.restore(rollback);self.assertEqual(self.exported()['learning'],changed['learning'])
 def test_bad_digest_and_invalid_learning_do_not_write(self):
  backup=self.exported();state=(core.DATA/'state.json').read_bytes();backup['learning']=self.words()
  with self.assertRaisesRegex(ValueError,'校验'):complete_backup.preview(backup)
  backup['learning']['rows'][0]['commits']=-1
  with self.assertRaises(ValueError):complete_backup.pack(backup['profile'],backup['learning'])
  self.assertEqual((core.DATA/'state.json').read_bytes(),state)
 def test_stale_and_expired_preview_rejected(self):
  value=self.exported();p=complete_backup.preview(value);quick.change('block','nh','你好',core.RIME)
  with self.assertRaisesRegex(ValueError,'已变化'):complete_backup.confirm(p['id'])
  p=complete_backup.preview(value);complete_backup.PENDING[p['id']]['time']-=601
  with self.assertRaisesRegex(ValueError,'过期'):complete_backup.confirm(p['id'])
 def test_failure_after_database_replace_rolls_back_both(self):
  self.run_worker('restore',self.words());before=self.exported()
  incoming=copy.deepcopy(before);incoming['profile']['manager']['state']['settings']['pair_english']=True
  incoming=complete_backup.pack(incoming['profile'],self.words('您好',19));original=core.atomic_json
  def fail(path,value):
   if path.name=='complete-report.json' and value.get('verified'):raise OSError('disk full')
   original(path,value)
  with patch.object(core,'atomic_json',side_effect=fail):self.restore(incoming,error=True)
  actual=self.exported();self.assertEqual(actual['profile'],before['profile']);self.assertEqual(actual['learning'],before['learning'])
  self.assertTrue(complete_backup.status()['report']['rolled_back'])
 def test_process_interruption_recovers_before_restart(self):
  self.run_worker('restore',self.words());before=self.exported();incoming=complete_backup.pack(before['profile'],self.words('您好',19));original=core.atomic_json
  def crash(path,value):
   if path.name=='complete-report.json' and value.get('verified'):raise SystemExit('crash')
   original(path,value)
  with patch.object(core,'atomic_json',side_effect=crash):
   with self.assertRaises(SystemExit):self.restore(incoming)
  self.assertTrue((learning.root()/'complete-transaction.json').exists())
  learning.worker(core.RIME,self.tool,self.library,recover_only=True)
  actual=self.exported();self.assertEqual(actual['profile'],before['profile']);self.assertEqual(actual['learning'],before['learning'])
  self.assertFalse((learning.root()/'complete-transaction.json').exists())
 def test_empty_source_database_migration(self):
  backup=self.exported();self.assertEqual(backup['learning']['rows'],[])
  self.run_worker('restore',self.words());self.restore(backup)
  self.assertEqual(self.exported()['learning']['rows'],[])
 def test_candidate_block_real_engine(self):
  core.make_bundle(core.RIME,core.state());app=core.ROOT/'branding/payload/Squirrel.app'
  subprocess.run([str(app/'Contents/MacOS/rime_deployer'),'--build',str(core.RIME),str(app/'Contents/SharedSupport'),str(core.RIME/'build')],check=True,capture_output=True,timeout=120)
  binary=self.root/'block-test'
  subprocess.run(['xcrun','clang++','-std=c++17','-I',str(core.ROOT/'client/librime/src'),str(core.ROOT/'tests/BlockCandidateSmoke.cpp'),'-o',str(binary)],check=True,capture_output=True,timeout=60)
  result=subprocess.run([str(binary),str(self.library),str(core.RIME)],capture_output=True,text=True,timeout=45)
  self.assertEqual(result.returncode,0,result.stderr)
