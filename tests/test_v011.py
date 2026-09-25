import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,quick,profile_backup as profile
class ProfileTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old=(core.DATA,core.RIME)
  core.DATA=Path(self.tmp.name)/'data';core.RIME=Path(self.tmp.name)/'rime'
  s=core.state();s['personal']=[dict(word='你好',pinyin='ni hao',weight=100,pinned=True)];core.save(s)
  quick.change('pin','nihao','你好',core.RIME)
 def tearDown(self):core.DATA,core.RIME=self.old;self.tmp.cleanup()
 def changed(self):
  v=profile.snapshot();v['manager']['state']['personal']=[];v['quick']=[];return v
 def test_roundtrip_and_rollback(self):
  before=profile.snapshot();profile.restore(self.changed());self.assertEqual(core.state()['personal'],[]);self.assertEqual(quick.read(core.RIME)[0],[])
  profile.rollback();self.assertEqual(profile.snapshot(),before);self.assertEqual(core.state()['applied'],-1)
 def test_invalid_quick_does_not_write(self):
  before=profile.snapshot();v=self.changed();v['quick']=[{'mode':'bad'}]
  with self.assertRaises(ValueError):profile.restore(v)
  self.assertEqual(profile.snapshot(),before);self.assertFalse((core.DATA/'before-profile.json').exists())
 def test_failure_rolls_back_both_stores(self):
  before={p:p.read_bytes() for root in (core.DATA,core.RIME) for p in root.rglob('*') if p.is_file()}
  original=profile.write_bytes;failed=[]
  def fail(path,value):
   if path.name=='kongime_quick.tsv' and not failed:failed.append(True);raise OSError('injected')
   return original(path,value)
  with patch.object(profile,'write_bytes',side_effect=fail):
   with self.assertRaises(OSError):profile.restore(self.changed())
  for p,value in before.items():self.assertEqual(p.read_bytes(),value)
  self.assertFalse((core.DATA/'profile-transaction.json').exists())
 def test_restart_recovers_interrupted_restore(self):
  original=profile.write_bytes
  def fail(path,value):
   if path.name=='kongime_quick.tsv':raise KeyboardInterrupt()
   return original(path,value)
  before=profile.snapshot()
  with patch.object(profile,'write_bytes',side_effect=fail):
   with self.assertRaises(KeyboardInterrupt):profile.restore(self.changed())
  self.assertTrue((core.DATA/'profile-transaction.json').exists());profile.recover();self.assertEqual(profile.snapshot(),before)
 def test_imported_library_is_remapped_and_learning_untouched(self):
  v=self.changed();v['manager']['state']['libraries']=[dict(id='../../evil',name='测试',hash='test',enabled=True)]
  v['manager']['libraries']={'../../evil':[dict(word='测试',pinyin='ce shi',weight=100)]}
  learn=core.RIME/'qingyan.userdb';learn.mkdir();(learn/'test').write_bytes(b'learning')
  profile.restore(v);self.assertEqual(core.lib_rows(core.state()['libraries'][0])[0]['word'],'测试');self.assertEqual((learn/'test').read_bytes(),b'learning')
 def test_export_excludes_device_paths(self):
  s=core.state();s['last_backup']='/private/example';core.save(s)
  self.assertNotIn('/private/example',json.dumps(profile.snapshot()));self.assertFalse(profile.snapshot()['learning']['included'])
