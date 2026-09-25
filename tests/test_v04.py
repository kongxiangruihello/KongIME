import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,workflow

class V04Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.data=patch.object(core,'DATA',Path(self.tmp.name)/'data');self.data.start()
    def tearDown(self):self.data.stop();self.tmp.cleanup()
    def test_old_state_loads_default_appearance(self):
        core.atomic_json(core.DATA/'state.json',{'revision':3,'applied':2,'libraries':[],'personal':[],'settings':{'page_size':9,'learning':False}})
        s=core.state();self.assertEqual(s['appearance'],core.default_appearance());self.assertEqual(s['app_preferences'],[]);self.assertEqual(s['settings']['page_size'],9)
    def test_invalid_preferences_are_rejected(self):
        for value in [{'font_size':True},{'font_size':999},{'layout':'vertical;bad'},{'theme':'x'}]:
            with self.assertRaises(ValueError):core.normalize_appearance(value)
        for value in [{'id':'com.foo/bad','mode':'english'},{'id':'com.foo','mode':'memory'}]:
            with self.assertRaises(ValueError):core.normalize_app_preference(value)
    def test_generate_appearance_and_app_options(self):
        s=core.state();s['appearance']={'font_size':24,'layout':'stacked','theme':'dark'};s['app_preferences']=[{'id':'com.apple.Terminal','name':'终端','mode':'chinese'}]
        out=Path(self.tmp.name)/'Rime';core.generate(out,s);text=(out/'squirrel.custom.yaml').read_text()
        self.assertIn('"style/font_point": 24',text);self.assertIn('"style/candidate_list_layout": "stacked"',text)
        self.assertIn('"style/color_scheme": "kongime_dark"',text);self.assertIn('"app_options/com.apple.Terminal/ascii_mode": false',text)
        self.assertNotIn('"app_options":',text)
    def test_migration_preserves_new_preferences(self):
        old=Path(self.tmp.name)/'old';s=core.state();s['appearance']={'font_size':20,'layout':'stacked','theme':'light'};s['app_preferences']=[{'id':'com.apple.Terminal','name':'终端','mode':'english'}]
        s['personal']=[core.normalize('你好','ni hao')];core.atomic_json(old/'state.json',s)
        preview=workflow.select_directory(str(old));workflow.migrate(preview['id'])
        self.assertEqual(core.state()['appearance'],dict(s['appearance'],candidate_gap=8));self.assertEqual(core.state()['app_preferences'],s['app_preferences'])

if __name__=='__main__':unittest.main()
