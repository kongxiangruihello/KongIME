import tempfile,unittest,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,workflow
class V07Tests(unittest.TestCase):
 def test_options_validate(self):
  self.assertEqual(core.normalize_fuzzy(['n_l','n_l']),['n_l'])
  for x in ('n_l',['bad'],[True]):
   with self.assertRaises(ValueError):core.normalize_fuzzy(x)
 def test_default_and_generated_rules(self):
  with tempfile.TemporaryDirectory() as d,patch.object(core,'DATA',Path('/tmp/unused-kongime-v07')):
   s={'personal':[],'libraries':[],'settings':{'learning':False,'page_size':5},'fuzzy':['n_l','z_zh']}
   core.generate(Path(d),s);v=(Path(d)/'qingyan.schema.yaml').read_text()
   self.assertIn('derive/^n/l/',v);self.assertIn('derive/^z([^h])/zh$1/',v);self.assertNotIn('derive/ang$/an/',v)
   s['fuzzy']=[];core.generate(Path(d),s);self.assertNotIn('derive/^n/l/',(Path(d)/'qingyan.schema.yaml').read_text())
 def test_legacy_state_and_backup_migration(self):
  with tempfile.TemporaryDirectory() as d,patch.object(core,'DATA',Path(d)/'new'):
   s=core.state();self.assertEqual(s['fuzzy'],[])
   s['fuzzy']=['in_ing'];s['personal']=[core.normalize('你好','ni hao')]
   old=Path(d)/'old';core.atomic_json(old/'state.json',s)
   p=workflow.select_directory(str(old));workflow.migrate(p['id'])
   self.assertEqual(core.backup_value()['state']['fuzzy'],['in_ing'])
