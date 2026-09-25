import sys,tempfile,unittest,json,time,uuid
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,learning,local_snapshots,profile_backup
class V016Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.old=core.DATA,core.RIME;core.DATA=self.root/'data';core.RIME=self.root/'rime'
 def tearDown(self):core.DATA,core.RIME=self.old;self.tmp.cleanup()
 def test_defaults_and_shortcut_conflicts(self):
  settings=core.normalize_settings({});self.assertTrue(settings['recognize_addresses'])
  self.assertEqual(settings['shortcuts'],core.DEFAULT_SHORTCUTS)
  with self.assertRaises(ValueError):core.normalize_settings({'shortcuts':{'pin':'Tab'}})
  with self.assertRaises(ValueError):core.normalize_settings({'shortcuts':{'expand':'minus'}})
 def test_generated_settings(self):
  s=core.state();s['settings']=core.normalize_settings({'ascii_punctuation':True,'direct_english':False,'recognize_addresses':False,'shortcuts':{'previous':'bracketleft','next':'bracketright','expand':'Control+Tab'}})
  target=self.root/'generated';core.generate(target,s);text=(target/'qingyan.schema.yaml').read_text()
  self.assertIn('accept: bracketleft',text);self.assertIn('reset: 1',text);self.assertIn('email: "^$"',text)
  self.assertIn('Control+Tab',(target/'squirrel.custom.yaml').read_text())
 def test_snapshot_rollback_and_dedup(self):
  s=core.state();core.save(s);a=local_snapshots.create('before');self.assertEqual(a,local_snapshots.create('same'))
  s=core.state();s['settings']['ascii_punctuation']=True;core.save(s)
  local_snapshots.restore(a['name']);self.assertFalse(core.state()['settings']['ascii_punctuation'])
  profile_backup.rollback();self.assertTrue(core.state()['settings']['ascii_punctuation'])
 def test_upgrade_once_and_tampering_rejected(self):
  core.save(core.state());local_snapshots.on_upgrade('0.16.0');local_snapshots.on_upgrade('0.16.0')
  rows=local_snapshots.list_snapshots();self.assertEqual(len(rows),1)
  p=core.DATA/'snapshots'/rows[0]['name'];v=json.loads(p.read_text());v['digest']='bad';p.write_text(json.dumps(v))
  with self.assertRaises(ValueError):local_snapshots.restore(rows[0]['name'])
 def test_learning_validation(self):
  good={'format':learning.FORMAT,'rows':[dict(word='公式',pinyin='gong shi',commits=7)]}
  self.assertEqual(learning.validate(good)[0]['commits'],7)
  for bad in [{'format':learning.FORMAT,'rows':good['rows']*2},{'format':learning.FORMAT,'rows':[dict(word='公式',pinyin='../x',commits=7)]}]:
   with self.assertRaises(ValueError):learning.validate(bad)
 def test_learning_transaction_rolls_back_on_failure(self):
  folder=learning.root();folder.mkdir(parents=True);live=core.RIME/'qingyan.userdb';live.mkdir();(live/'data').write_text('old')
  prepared=self.root/'prepared';prepared.mkdir();(prepared/'data').write_text('new')
  original=core.atomic_json
  def fail(path,value):
   if path.name=='rollback.json':raise OSError('disk full')
   original(path,value)
  with patch('core.atomic_json',side_effect=fail):
   with self.assertRaises(OSError):learning.replace_database(prepared)
  self.assertEqual((live/'data').read_text(),'old');self.assertFalse((folder/'transaction.json').exists())
 def test_learning_worker_real_engine(self):
  tool=core.ROOT/'client/build/learning-tool';library=core.ROOT/'branding/payload/Squirrel.app/Contents/Frameworks/librime.1.dylib'
  if not tool.exists():self.skipTest('build learning-tool first')
  folder=learning.root();folder.mkdir(parents=True)
  def run(op,rows=None):
   token=uuid.uuid4().hex;core.atomic_json(folder/'request.json',{'id':token,'created':time.time(),'operation':op,'value':{'format':learning.FORMAT,'rows':rows or []}})
   learning.worker(core.RIME,tool,library);r=json.loads((folder/'response.json').read_text());self.assertEqual(r['id'],token);self.assertNotIn('error',r,r);return r
  rows=[dict(word='公式',pinyin='gong shi',commits=7),dict(word='轻言',pinyin='qing yan',commits=12)]
  run('restore',rows);run('export');self.assertEqual(learning.export_value()['rows'],rows)
  run('restore',[dict(word='你好',pinyin='ni hao',commits=3)]);run('rollback');run('export')
  self.assertEqual(learning.export_value()['rows'],rows)

 def test_learning_interrupted_replacement_recovers(self):
  folder=learning.root();folder.mkdir(parents=True);identifier=uuid.uuid4().hex
  history=folder/'history'/(identifier+'.userdb');history.mkdir(parents=True);(history/'data').write_text('old')
  live=core.RIME/'qingyan.userdb';live.mkdir();(live/'data').write_text('new')
  core.atomic_json(folder/'transaction.json',{'id':identifier,'had_live':True,'old_rollback':None})
  learning.recover_transaction();self.assertEqual((live/'data').read_text(),'old')
  self.assertFalse((folder/'transaction.json').exists())
