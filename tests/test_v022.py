import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,phrase_tools,profile_backup,personal_data,restore_review
class PhraseGroupsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old=core.DATA,core.RIME
  core.DATA=Path(self.tmp.name)/'data';core.RIME=Path(self.tmp.name)/'rime'
 def tearDown(self):core.DATA,core.RIME=self.old;self.tmp.cleanup()
 def test_group_roundtrip_and_atomic_toggle(self):
  core.save_phrase({'code':'aa','text':'A','group':'工作'})
  core.save_phrase({'code':'bb','text':'{W}','dynamic':True,'group':'工作','enabled':False})
  core.save_phrase({'code':'cc','text':'C','group':'生活'})
  phrase_tools.group_update({'group':'工作','enabled':False})
  rows={x['code']:x for x in core.state()['phrases']};self.assertTrue(rows['cc'].get('enabled',True));self.assertFalse(rows['aa']['enabled'])
  profile_backup.restore(profile_backup.snapshot());self.assertEqual(core.state()['phrases'][0]['group'],'工作')
  self.assertEqual(phrase_tools.export()['phrases'][1]['group'],'工作')
  phrase_tools.group_update({'group':'工作','enabled':True});self.assertTrue(all(x.get('enabled',True) for x in core.state()['phrases']))
  core.save_phrase({'code':'aa','old':'aa','text':'A','group':'工作','delete':True});personal_data.restore(core.state()['trash'][0]['id'])
  self.assertEqual(next(x for x in core.state()['phrases'] if x['code']=='aa')['group'],'工作')
 def test_group_validation_and_pin_failure(self):
  for group in ['x'*31,'x\ny',123]:
   with self.assertRaises(ValueError):core.normalize_phrase({'code':'aa','text':'A','group':group})
  self.assertNotIn('group',core.normalize_phrase({'code':'aa','text':'A','group':'未分组'}))
  core.save_phrase({'code':'aa','text':'A','group':'工作','enabled':False})
  core.save_phrase({'code':'bb','text':'B','group':'工作','enabled':False})
  s=core.state();s['personal']=[{'word':'测试','pinyin':'aa','weight':10,'pinned':True}];core.save(s);before=core.state()
  with self.assertRaises(ValueError):phrase_tools.group_update({'group':'工作','enabled':True})
  self.assertEqual(core.state(),before)
 def test_common_pinyin_and_hard_conflicts(self):
  result=phrase_tools.check_code({'code':'sh'});self.assertTrue(result['examples']);self.assertTrue(result['warnings']);self.assertIsNone(result['blocking'])
  s=core.state();s['settings']['abbreviation']=False;core.save(s)
  self.assertFalse(phrase_tools.check_code({'code':'sh'})['warnings'])
  self.assertTrue(phrase_tools.check_code({'code':'shi'})['warnings'])
  self.assertFalse(phrase_tools.check_code({'code':'shi','enabled':False})['warnings'])
  core.save_phrase({'code':'shi','text':'A'})
  self.assertTrue(phrase_tools.check_code({'code':'shi'})['blocking'])
  self.assertIsNone(phrase_tools.check_code({'code':'shi','old':'shi'})['blocking'])
 def test_candidate_draft_does_not_write(self):
  core.save_phrase({'code':'rq','text':'{W}','dynamic':True,'label':'日期','group':'日期'})
  before=core.state()
  r=phrase_tools.candidate({'text':'星期二','code':'rq','comment':'日期','action':'edit'})
  self.assertTrue(r['editing']);self.assertEqual(r['phrase']['text'],'{W}');self.assertEqual(r['phrase']['group'],'日期')
  new=phrase_tools.candidate({'text':'a "quote" & <b>','code':'abc','comment':'','action':'new'})
  self.assertEqual(new['phrase']['code'],'');self.assertEqual(core.state(),before)
  with self.assertRaises(ValueError):phrase_tools.candidate({'text':'其他候选','code':'rq','comment':'qi ta','action':'edit'})
 def test_group_import_and_restore_diff(self):
  core.save_phrase({'code':'aa','text':'A','group':'工作'});backup=profile_backup.snapshot()
  p=phrase_tools.preview({'format':phrase_tools.FORMAT,'phrases':[{'code':'aa','text':'A','group':'生活'}]})
  phrase_tools.confirm({'id':p['id'],'decisions':{'aa':{'action':'replace'}}})
  self.assertEqual(core.state()['phrases'][0]['group'],'生活')
  diff=restore_review.preview({'backup':backup});self.assertEqual(next(x for x in diff['categories'] if x['label']=='短语')['changed'],1)
