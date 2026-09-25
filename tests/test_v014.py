import sys,tempfile,unittest,os,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,personal_data as personal,library_tools,profile_backup
class V014Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.old=(core.DATA,core.RIME);core.DATA=self.root/'data';core.RIME=self.root/'rime'
 def tearDown(self):core.DATA,core.RIME=self.old;self.tmp.cleanup()
 def test_trash_word_and_conflict(self):
  s=core.state();row=dict(word='轻言',pinyin='qing yan',weight=100,pinned=True);personal.discard(s,'word',row);core.save(s);key=s['trash'][0]['id'];personal.restore(key)
  self.assertEqual(core.state()['personal'],[row]);self.assertEqual(core.state()['trash'],[])
  s=core.state();personal.discard(s,'word',row);core.save(s)
  with self.assertRaises(ValueError):personal.restore(s['trash'][0]['id'])
  self.assertEqual(len(core.state()['trash']),1)
 def test_library_restore_starts_disabled_and_survives_backup(self):
  library_tools.save({'name':'工作','text':'轻言\tqing yan'})
  s=core.state();personal.discard(s,'library',s['libraries'].pop());core.save(s)
  backup=profile_backup.snapshot();profile_backup.restore(backup);personal.restore(core.state()['trash'][0]['id'])
  lib=core.state()['libraries'][0];self.assertFalse(lib['enabled']);self.assertEqual(core.lib_rows(lib)[0]['word'],'轻言')
 def test_scene_keeps_new_libraries_and_undo(self):
  library_tools.save({'name':'工作','text':'轻言\tqing yan'});personal.scene({'action':'save','name':'工作'})
  s=core.state();s['libraries'][0]['enabled']=False;core.save(s)
  library_tools.save({'name':'新词库','text':'你好\tni hao'});personal.scene({'action':'apply','name':'工作'})
  self.assertTrue(all(x['enabled'] for x in core.state()['libraries']))
 def test_conflict_counts(self):
  library_tools.save({'name':'工作','text':'轻言\tqing yan\t100'})
  c=personal.conflicts([core.normalize('轻言','qing yan',200),core.normalize('轻言','qing yan',100),core.normalize('轻言','qing yin')])
  self.assertEqual((c['duplicates'],c['weight_differences'],c['pinyin_differences']),(2,1,1))
 def test_icloud_roundtrip_unique_names_and_paths(self):
  cloud=self.root/'cloud';cloud.mkdir()
  with patch.dict(os.environ,{'KONGIME_ICLOUD_ROOT':str(cloud)}):
   a=personal.icloud_save()['name'];b=personal.icloud_save()['name'];self.assertNotEqual(a,b)
   library_tools.save({'name':'新增','text':'轻言\tqing yan'});personal.icloud_restore(a);self.assertEqual(core.state()['libraries'],[])
   self.assertEqual(len(personal.icloud_status()['files']),2)
   with self.assertRaises(ValueError):personal.icloud_restore('../state.json')
 def test_invalid_extras_restore_preserves_state(self):
  before=profile_backup.snapshot();bad=json.loads(json.dumps(before));bad['manager']['state']['trash']=[{'id':'bad','kind':'word','item':{}}]
  with self.assertRaises((ValueError,KeyError)):profile_backup.restore(bad)
  self.assertEqual(profile_backup.snapshot(),before)
 def test_phrase_delete_is_recoverable(self):
  core.save_phrase({'code':'yx','text':'test@example.test'})
  core.save_phrase({'code':'yx','old':'yx','text':'test@example.test','delete':True})
  s=core.state();self.assertEqual(s['phrases'],[]);self.assertEqual(len(s['trash']),1)
  personal.restore(s['trash'][0]['id']);self.assertEqual(core.state()['phrases'][0]['code'],'yx')
 def test_full_trash_refuses_discard_without_dropping_old_records(self):
  s=core.state();row={'word':'轻言','pinyin':'qing yan','weight':100,'pinned':False}
  for _ in range(200):personal.discard(s,'word',row)
  before=[x['id'] for x in s['trash']]
  with self.assertRaises(ValueError):personal.discard(s,'word',row)
  self.assertEqual([x['id'] for x in s['trash']],before)
