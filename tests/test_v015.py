import sys,tempfile,unittest,os,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,personal_data,profile_backup,workflow
class V015Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.old=core.DATA,core.RIME;core.DATA=self.root/'data';core.RIME=self.root/'rime'
 def tearDown(self):core.DATA,core.RIME=self.old;self.tmp.cleanup()
 def load(self,weight,policy='higher'):
  return core.import_library(('轻言\tqing yan\t'+str(weight)).encode(),'words.txt',policy)
 def test_three_policies_and_undo(self):
  for policy,expected in [('local',500),('incoming',100),('higher',500)]:
   with self.subTest(policy=policy):
    core.DATA=self.root/policy;self.load(500);receipt=self.load(100,policy)
    self.assertEqual(core.active_rows(core.state())[0]['weight'],expected)
    core.undo_import(receipt['id']);self.assertEqual(core.active_rows(core.state())[0]['weight'],500)
 def test_import_policy_survives_profile_restore(self):
  self.load(500);self.load(100,'incoming');profile_backup.restore(profile_backup.snapshot())
  self.assertEqual(core.active_rows(core.state())[0]['weight'],100)
 def test_personal_preference_and_alternate_reading_preserved(self):
  self.load(500);s=core.state();s['personal']=[dict(word='轻言',pinyin='qing yan',weight=600,pinned=True)];core.save(s)
  core.import_library('轻言\tqing yan\t100\n轻言\tqing yin\t200'.encode(),'two.txt','incoming')
  rows=core.active_rows(core.state());self.assertEqual(len(rows),2)
  self.assertEqual(next(r for r in rows if r['pinyin']=='qing yan')['weight'],600)
 def test_invalid_policy_no_writes(self):
  before=core.state()
  with self.assertRaises(ValueError):self.load(300,'unknown')
  self.assertEqual(before,core.state())
 def test_icloud_failure_retry_preserves_last_success(self):
  cloud=self.root/'cloud';cloud.mkdir()
  with patch.dict(os.environ,{'KONGIME_ICLOUD_ROOT':str(cloud)}):
   personal_data.icloud_save();success=personal_data.icloud_status()['last_backup']
   with patch('personal_data._icloud_save',side_effect=OSError('磁盘已满')):
    with self.assertRaises(OSError):personal_data.icloud_save()
   status=personal_data.icloud_status();self.assertEqual(status['last_backup'],success);self.assertIn('磁盘已满',status['last_error']);self.assertFalse(status['auto_backup_available'])
   personal_data.icloud_save();self.assertIsNone(personal_data.icloud_status()['last_error'])
 def test_diagnostics_missing_library_and_cloud(self):
  self.load(100);lib=core.state()['libraries'][0];(core.DATA/'libraries'/(lib['id']+'.json')).unlink()
  status=dict(branded=False,client_version=None,deployed=False,label='等待部署',last_error=None)
  with patch('workflow.status',return_value=status),patch.dict(os.environ,{'KONGIME_ICLOUD_ROOT':str(self.root/'missing')}):
   checks=personal_data.diagnostics()['checks'];self.assertEqual(len(checks),4);self.assertFalse(checks[2]['ok']);self.assertFalse(checks[3]['ok'])
