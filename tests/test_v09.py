import unittest,tempfile,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import quick,core
class V09Tests(unittest.TestCase):
 def test_quick_pin_lower_and_ordered_undo(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);quick.change('pin','nihao','你好',root);quick.change('pin','nihao','拟好',root)
   prefs,h=quick.read(root);self.assertEqual([p['word'] for p in prefs],['拟好'])
   with self.assertRaises(ValueError):quick.change('undo',root=root,event=h[0]['id'])
   quick.change('undo',root=root,event=h[-1]['id']);self.assertEqual(quick.read(root)[0][0]['word'],'你好')
   quick.change('lower','nihao','你好',root);self.assertEqual(quick.read(root)[0][0]['mode'],'lower')
 def test_reject_control_characters(self):
  with tempfile.TemporaryDirectory() as d:
   for code,word in [('ABC','词'),('a\tb','词'),('ab','词\n条')]:
    with self.assertRaises(ValueError):quick.change('pin',code,word,Path(d))
 def test_settings_undo_preserves_other_records(self):
  with tempfile.TemporaryDirectory() as d,patch.object(core,'DATA',Path(d)):
   s=core.state();s['settings']['page_size']=7;core.save(s)
   s=core.state();s['phrases']=[{'code':'yx','text':'name@example.com'}];core.save(s)
   h=core.change_history()
   with self.assertRaises(ValueError):core.undo_change(h[0]['id'])
   core.undo_change(h[-1]['id']);self.assertEqual(core.state()['settings']['page_size'],7);self.assertEqual(core.state()['phrases'],[])
   core.undo_change(core.change_history()[-1]['id']);self.assertEqual(core.state()['settings']['page_size'],5)
