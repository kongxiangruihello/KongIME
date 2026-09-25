import sys,tempfile,unittest,copy,subprocess
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,phrase_tools,profile_backup,restore_review,personal_data
class PhraseUpgradeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old=core.DATA,core.RIME
  core.DATA=Path(self.tmp.name)/'data';core.RIME=Path(self.tmp.name)/'rime';phrase_tools.PENDING.clear()
 def tearDown(self):core.DATA,core.RIME=self.old;self.tmp.cleanup()
 def test_relative_calendar_and_validation(self):
  row={'code':'rq','text':'{YYYY}-{MM}-{DD} {W} {HH}:{mm}','dynamic':True,'date_offset':1,'label':'日期'}
  self.assertEqual(core.phrase_preview(row,datetime(2024,2,28,23,12))['text'],'2024-02-29 星期四 23:12')
  self.assertEqual(core.phrase_preview(row,datetime(2026,12,31))['text'],'2027-01-01 星期五 00:00')
  for extra in [{'date_offset':367},{'date_offset':True},{'label':'bad'},{'enabled':0}]:
   with self.assertRaises(ValueError):core.normalize_phrase(dict(row,**extra))
 def test_disabled_export_restore_and_deploy(self):
  row={'code':'rq','text':'{W}','dynamic':True,'label':'日期','date_offset':1}
  core.save_phrase(row);phrase_tools.toggle({'code':'rq','enabled':False})
  self.assertFalse(phrase_tools.export()['phrases'][0]['enabled'])
  backup=profile_backup.snapshot();profile_backup.restore(backup)
  self.assertFalse(core.state()['phrases'][0]['enabled'])
  core.generate(core.RIME,core.state());self.assertEqual((core.RIME/'kongime_templates.tsv').read_text(),'')
  phrase_tools.toggle({'code':'rq','enabled':True});core.generate(core.RIME,core.state())
  self.assertIn('rq\t{W}\t1\t日期', (core.RIME/'kongime_templates.tsv').read_text())
  diff=restore_review.preview({'backup':backup});self.assertEqual(next(x for x in diff['categories'] if x['label']=='短语')['changed'],1)
  core.save_phrase(dict(core.state()['phrases'][0],old='rq',delete=True));personal_data.restore(core.state()['trash'][0]['id']);self.assertEqual(core.state()['phrases'][0]['date_offset'],1)
 def test_conflicts_all_policies_and_atomic_failure(self):
  for code in ['aa','bb','cc']:core.save_phrase({'code':code,'text':'local'})
  backup={'format':phrase_tools.FORMAT,'phrases':[{'code':c,'text':'incoming'} for c in ['aa','bb','cc','dd']]}
  p=phrase_tools.preview(backup);self.assertEqual(len(p['conflicts']),3)
  before=core.state()
  with self.assertRaises(ValueError):phrase_tools.confirm({'id':p['id'],'decisions':{'aa':{'action':'replace'},'cc':{'action':'rename','code':'dd'}}})
  self.assertEqual(core.state(),before)
  result=phrase_tools.confirm({'id':p['id'],'decisions':{'bb':{'action':'replace'},'cc':{'action':'rename','code':'ee'}}})
  self.assertEqual(result,{'added':2,'replaced':1,'kept':1})
  self.assertEqual({x['code']:x['text'] for x in core.state()['phrases']},{'aa':'local','bb':'incoming','cc':'local','dd':'incoming','ee':'incoming'})
  with self.assertRaises(ValueError):phrase_tools.confirm({'id':p['id']})
 def test_stale_preview_and_duplicate_file(self):
  backup={'format':phrase_tools.FORMAT,'phrases':[{'code':'aa','text':'one'}]}
  p=phrase_tools.preview(backup);core.save_phrase({'code':'bb','text':'two'})
  with self.assertRaises(ValueError):phrase_tools.confirm({'id':p['id']})
  backup['phrases']*=2
  with self.assertRaises(ValueError):phrase_tools.preview(backup)
 def test_disabled_pin_conflict_on_reenable(self):
  s=core.state();s['personal']=[{'word':'你好','pinyin':'ni hao','weight':100,'pinned':True}];core.save(s)
  core.save_phrase({'code':'nihao','text':'phrase','enabled':False})
  with self.assertRaises(ValueError):phrase_tools.toggle({'code':'nihao','enabled':True})
  self.assertFalse(core.state()['phrases'][0]['enabled'])

 def test_empty_transfer_is_noop(self):
  p=phrase_tools.preview(phrase_tools.export());before=core.state()
  self.assertEqual(phrase_tools.confirm({'id':p['id']}),{'added':0,'replaced':0,'kept':0})
  self.assertEqual(core.state(),before)
