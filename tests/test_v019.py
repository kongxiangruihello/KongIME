import tempfile,unittest
from pathlib import Path
import core,profile_backup
class CandidateGapTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old=core.DATA,core.RIME
  core.DATA=Path(self.tmp.name)/'data';core.RIME=Path(self.tmp.name)/'rime'
 def tearDown(self):core.DATA,core.RIME=self.old;self.tmp.cleanup()
 def test_legacy_appearance_defaults_and_invalid_gap(self):
  self.assertEqual(core.normalize_appearance({'font_size':17})['candidate_gap'],8)
  for gap in [0,-1,100,True,'12']:
   with self.assertRaises(ValueError):core.normalize_appearance({'candidate_gap':gap})
 def test_gap_deploy_and_backup_roundtrip(self):
  s=core.state();s['appearance']=core.normalize_appearance({'candidate_gap':24});core.save(s)
  core.apply_config();self.assertIn('"kongime/candidate_gap": 24',(core.RIME/'squirrel.custom.yaml').read_text())
  saved=profile_backup.snapshot();s=core.state();s['appearance']['candidate_gap']=8;core.save(s)
  profile_backup.restore(saved);self.assertEqual(core.state()['appearance']['candidate_gap'],24)
