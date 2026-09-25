import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,profile_backup,restore_review,complete_backup,learning,update_check
class V026Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old=core.DATA,core.RIME;core.DATA=Path(self.tmp.name)/'data';core.RIME=Path(self.tmp.name)/'rime';core.save(core.state())
 def tearDown(self):core.DATA,core.RIME=self.old;self.tmp.cleanup()
 def test_app_default_compatibility_roundtrip(self):
  s=core.state();s['app_preferences']=[core.normalize_app_preference({'id':'com.tencent.xinWeChat','name':'微信','mode':'default','disable_pairs':True}),core.normalize_app_preference({'id':'com.test.editor','mode':'english'})];core.save(s);core.generate(core.RIME,s)
  config=(core.RIME/'squirrel.custom.yaml').read_text()
  self.assertIn('"kongime/pair_disabled_apps/com.tencent.xinWeChat": true',config)
  self.assertNotIn('app_options/com.tencent.xinWeChat/ascii_mode',config)
  self.assertIn('"app_options/com.test.editor/ascii_mode": true',config)
  snapshot=profile_backup.snapshot();s['app_preferences']=[];core.save(s);profile_backup.restore(snapshot)
  self.assertEqual(core.state()['app_preferences'][0]['disable_pairs'],True)
  self.assertEqual(restore_review.canonical(snapshot),restore_review.canonical(profile_backup.snapshot()))
 def test_compatibility_in_restore_diff_and_invalid_flag(self):
  s=core.state();s['app_preferences']=[{'id':'com.test.editor','mode':'default'}];core.save(s);before=restore_review.canonical(profile_backup.snapshot())
  s['app_preferences'][0]['disable_pairs']=True;core.save(s);after=restore_review.canonical(profile_backup.snapshot());self.assertNotEqual(before,after)
  with self.assertRaises(ValueError):core.normalize_app_preference({'id':'com.test.editor','mode':'default','disable_pairs':'true'})
 def test_complete_report_detects_changes(self):
  learning.root().mkdir(parents=True,exist_ok=True);core.atomic_json(learning.root()/'complete-report.json',{'verified':True,'fingerprint':restore_review.fingerprint(profile_backup.snapshot())})
  self.assertFalse(complete_backup.status()['report']['changed_since'])
  s=core.state();s['settings']['pair_chinese']=True;core.save(s);self.assertTrue(complete_backup.status()['report']['changed_since'])
 def release(self,tag='v0.27.0',preview=False):
  return {'tag_name':tag,'draft':False,'prerelease':preview,'html_url':update_check.REPO+'/releases/tag/'+tag,'assets':[{'state':'uploaded','size':50,'name':'KongIME-0.27-Mac.zip','browser_download_url':update_check.REPO+'/releases/download/'+tag+'/KongIME-0.27-Mac.zip'}]}
 def test_update_preview_opt_in_semantic_order(self):
  preview=self.release(preview=True);self.assertFalse(update_check.select([preview])['available']);self.assertTrue(update_check.select([preview],True)['available'])
  self.assertTrue(update_check.select([self.release('v0.9.0'),self.release('v0.27.0')])['available'])
  self.assertFalse(update_check.select([self.release('v0.26.0')])['available'])
 def test_update_ignores_draft_missing_assets_and_foreign_links(self):
  for kind in ('draft','foreign','missing','badtag','asset'):
   r=self.release()
   if kind=='draft':r['draft']=True
   if kind=='foreign':r['html_url']='https://example.com/download'
   if kind=='missing':r['assets']=[]
   if kind=='badtag':r['tag_name']='v0.27/../../bad'
   if kind=='asset':r['assets'][0]['browser_download_url']='https://example.com/app.zip'
   self.assertFalse(update_check.select([r],True)['available'],kind)
 def test_update_errors_and_bounded_read(self):
  from urllib.error import URLError
  with patch.object(update_check,'urlopen',side_effect=URLError('offline')):
   with self.assertRaisesRegex(ValueError,'无法连接'):update_check.check()
  with patch.object(update_check,'urlopen') as request:
   request.return_value.__enter__.return_value.read.return_value=b'x'*(update_check.MAX_BYTES+1)
   with self.assertRaisesRegex(ValueError,'过大'):update_check.check()
   self.assertEqual(request.return_value.__enter__.return_value.read.call_args.args,(update_check.MAX_BYTES+1,))
