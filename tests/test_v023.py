import sys,tempfile,unittest,subprocess,string
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,phrase_tools
class V023Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.old=core.DATA,core.RIME
  core.DATA=self.root/'data';core.RIME=self.root/'rime'
 def tearDown(self):core.DATA,core.RIME=self.old;self.tmp.cleanup()
 def organize(self,**kw):return phrase_tools.organize(dict(revision=core.state()['revision'],**kw))
 def seed(self):
  core.save_phrase({'code':'aa','text':'{W}','dynamic':True,'date_offset':1,'label':'日期','group':'工作','enabled':False})
  core.save_phrase({'code':'bb','text':'hello','group':'工作'})
  core.save_phrase({'code':'cc','text':'world','group':'生活'})
 def test_group_rename_move_export_and_undo(self):
  self.seed();before=core.state()['phrases'];self.organize(action='rename',group='工作',target='写作')
  self.assertEqual([x['code'] for x in phrase_tools.export('写作')['phrases']],['aa','bb'])
  self.assertFalse(phrase_tools.export('写作')['phrases'][0]['enabled'])
  self.organize(action='move',codes=['aa','cc'],target='')
  self.assertEqual([x['code'] for x in phrase_tools.export('')['phrases']],['aa','cc'])
  self.assertEqual(phrase_tools.export('')['phrases'][0]['date_offset'],1)
  self.assertEqual(len(phrase_tools.export()['phrases']),3)
  core.undo_change(core.change_history()[-1]['id']);core.undo_change(core.change_history()[-1]['id'])
  self.assertEqual(core.state()['phrases'],before)
 def test_group_failure_is_atomic_and_merge_explicit(self):
  self.seed();before=core.state()
  for kw in [dict(action='move',codes=['aa','missing'],target='x'),dict(action='move',codes=['aa','aa'],target='x'),dict(action='rename',group='工作',target='生活'),dict(action='rename',group='不存在',target='x'),dict(action='move',codes=['aa'],target='x\ny')]:
   with self.assertRaises(ValueError):self.organize(**kw)
   self.assertEqual(core.state(),before)
  with self.assertRaises(ValueError):phrase_tools.organize(dict(action='move',codes=['aa'],target='x',revision=before['revision']-1))
  self.organize(action='rename',group='工作',target='生活',merge=True)
  self.assertEqual(len(phrase_tools.export('生活')['phrases']),3)
 def test_real_engine_latin_collision_and_upgrade(self):
  root=core.ROOT;tool=self.root/'probe';lib=root/'branding/payload/Squirrel.app/Contents/Frameworks/librime.1.dylib'
  subprocess.run(['xcrun','clang++','-std=c++17','-O2','-I',str(root/'client/librime/src'),str(root/'tests/AbbreviationLatinSmoke.cpp'),'-o',str(tool)],check=True,capture_output=True)
  s=core.state();s['personal']=[core.normalize(c,c,100) for c in string.ascii_uppercase]+[core.normalize('A股','A gu',1000000),core.normalize('DNA','D N A',1000000)]
  s['fuzzy']=['z_zh','c_ch','s_sh'];target=self.root/'bundle';core.make_bundle(target,s)
  schema=target/'qingyan.schema.yaml';fixed=schema.read_text();start=fixed.index('      - xform/^A$/a/');end=fixed.index('      - erase/^[A-Z]$/')+len('      - erase/^[A-Z]$/')
  def probe(mode,*pairs):
   result=subprocess.run([str(tool),str(lib),str(target),mode,*pairs],capture_output=True,text=True,timeout=120)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
  # Reproduce on the production vocabulary, then upgrade the same compiled root.
  schema.write_text(fixed[:start]+'      - xlit/ABCDEFGHIJKLMNOPQRSTUVWXYZ/abcdefghijklmnopqrstuvwxyz/'+fixed[end:])
  probe('absent','nh=你好','zg=中国','bj=北京')
  schema.write_text(fixed)
  probe('present','nh=你好','zg=中国','bj=北京','sj=时间','nihao=你好',"ni'h=你好",'agu=A股','dna=DNA')
  s['settings']['abbreviation']=False;core.generate(target,s)
  probe('absent','nh=你好',"ni'h=你好")
  probe('present','nihao=你好','agu=A股','dna=DNA')
