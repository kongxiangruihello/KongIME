import sys,tempfile,unittest,subprocess,shutil
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,profile_backup,personal_data,restore_review
class V020Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old=core.DATA,core.RIME;self.root=Path(self.tmp.name)
  core.DATA=self.root/'data';core.RIME=self.root/'rime'
 def tearDown(self):core.DATA,core.RIME=self.old;self.tmp.cleanup()
 def test_templates_validation_and_preview(self):
  value={'code':'rq','text':'{YYYY}年{M}月{D}日 {HH}:{mm}:{ss}','dynamic':True}
  self.assertEqual(core.phrase_preview(value,datetime(2026,2,3,4,5,6))['text'],'2026年2月3日 04:05:06')
  for text in ['{bad}','{YYYY','{MM}}','x\ny']:
   with self.assertRaises(ValueError):core.normalize_phrase(dict(value,text=text))
  self.assertEqual(core.phrase_preview(dict(value,text='%Y $(literal)'))['text'],'%Y $(literal)')
  self.assertEqual(core.normalize_phrase({'code':'ab','text':'{YYYY}'})['text'],'{YYYY}')
 def test_template_backup_trash_and_diff(self):
  row={'code':'rq','text':'{YYYY}-{MM}-{DD}','dynamic':True};core.save_phrase(row)
  saved=profile_backup.snapshot();core.save_phrase(dict(row,old='rq',delete=True));personal_data.restore(core.state()['trash'][0]['id'])
  self.assertTrue(core.state()['phrases'][0]['dynamic']);profile_backup.restore(saved)
  self.assertTrue(core.state()['phrases'][0]['dynamic'])
  plain=profile_backup.snapshot();plain['manager']['state']['phrases'][0].pop('dynamic')
  diff=restore_review.preview({'backup':plain});self.assertEqual(next(x for x in diff['categories'] if x['label']=='短语')['changed'],1)
 def test_abbreviation_defaults_and_backup(self):
  self.assertTrue(core.normalize_settings({})['abbreviation'])
  with self.assertRaises(ValueError):core.normalize_settings({'abbreviation':'off'})
  s=core.state();s['settings']['abbreviation']=False;core.save(s);profile_backup.restore(profile_backup.snapshot());self.assertFalse(core.state()['settings']['abbreviation'])
 def test_real_engine_templates_and_abbreviation(self):
  tool=self.root/'smoke';root=core.ROOT
  subprocess.run(['xcrun','clang++','-std=c++17','-O2','-I',str(root/'client/librime/src'),str(root/'tests/TemplateSmoke.cpp'),'-o',str(tool)],check=True,capture_output=True)
  lib=root/'branding/payload/Squirrel.app/Contents/Frameworks/librime.1.dylib'
  for enabled in [True,False]:
   target=self.root/('on' if enabled else 'off');s=core.state();s['settings']['abbreviation']=enabled
   s['phrases']=[{'code':'mt','text':'{YYYY}-{MM}-{DD}','dynamic':True,'date_offset':1,'label':'日期'},{'code':'xq','text':'{W}','dynamic':True,'label':'日期'},{'code':'zz','text':'disabled phrase','enabled':False},{'code':'sj','text':'{HH}:{mm}:{ss}','dynamic':True},{'code':'rq','text':'{YYYY}-{MM}-{DD}','dynamic':True},{'code':'lk','text':'孔祥瑞 · {YYYY}-{MM}-{DD}','dynamic':True},{'code':'yl','text':'%Y $(literal)','dynamic':True},{'code':'yx','text':'name@example.com'}]
   core.make_bundle(target,s)
   (target/'qingyan.dict.yaml').write_text('---\nname: qingyan\nversion: "1.0"\nsort: by_weight\n...\n你好\tni hao\t100\n你\tni\t100\n好\thao\t100\n')
   result=subprocess.run([str(tool),str(lib),str(target),'on' if enabled else 'off'],capture_output=True,text=True,timeout=60)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
