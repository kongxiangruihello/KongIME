import tempfile,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,library_tools as lib,profile_backup
class V013Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old=(core.DATA,core.RIME);core.DATA=Path(self.tmp.name)/'data';core.RIME=Path(self.tmp.name)/'rime'
 def tearDown(self):core.DATA,core.RIME=self.old;self.tmp.cleanup()
 def test_manual_roundtrip_edit_undo(self):
  x=lib.save({'name':'工作','text':'轻言\tqing yan\t123'})
  self.assertEqual(core.parse_import(lib.export(x['id']).encode(),'words.txt')[0][0]['weight'],123)
  lib.save({'id':x['id'],'name':'工作','text':'轻言\tqing yan\t456'})
  core.undo_change(core.change_history()[-1]['id']);self.assertEqual(core.lib_rows(core.state()['libraries'][0])[0]['weight'],123)
 def test_invalid_library_is_not_saved(self):
  for raw in ['词语 without tabs','轻言\tqing yan\t3\n轻言\tqing yan\t5']:
   with self.assertRaises(ValueError):lib.save({'name':'词库','text':raw})
  self.assertEqual(core.state()['libraries'],[])
 def test_backup_preserves_manual_and_new_settings(self):
  lib.save({'name':'测试','text':'轻言\tqing yan'})
  s=core.state();s['settings'].update(auto_save=True,show_pinyin=False);core.save(s)
  profile_backup.restore(profile_backup.snapshot());s=core.state();self.assertTrue(s['libraries'][0]['manual']);self.assertTrue(s['settings']['auto_save']);self.assertFalse(s['settings']['show_pinyin'])
 def test_pinyin_output_switch(self):
  s=core.state();root=Path(self.tmp.name)/'generated';core.generate(root,s)
  self.assertIn('always_show_comments: true',(root/'qingyan.schema.yaml').read_text());self.assertIn('[comment]',(root/'squirrel.custom.yaml').read_text())
  s['settings']['show_pinyin']=False;core.generate(root,s);self.assertNotIn('always_show_comments: true',(root/'qingyan.schema.yaml').read_text());self.assertNotIn('[comment]',(root/'squirrel.custom.yaml').read_text())
