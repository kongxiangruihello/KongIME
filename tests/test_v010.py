import unittest,tempfile,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import quick
class V010Tests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def test_reset_and_undo(self):
  quick.change('lower','nihao','你好',self.root);quick.change('reset','nihao','你好',self.root)
  prefs,history=quick.read(self.root);self.assertEqual(prefs,[])
  quick.change('undo',root=self.root,event=history[-1]['id']);self.assertEqual(quick.read(self.root)[0][0]['mode'],'lower')
 def test_restore_replaces_and_undo_recovers(self):
  quick.change('pin','nihao','你好',self.root)
  incoming=[{'code':'zaijian','word':'再见','mode':'lower'}]
  quick.change('restore',root=self.root,replacement=incoming)
  self.assertEqual(quick.read(self.root)[0],incoming)
  quick.change('undo',root=self.root,event=quick.read(self.root)[1][-1]['id'])
  self.assertEqual(quick.read(self.root)[0],[{'code':'nihao','word':'你好','mode':'pin'}])
 def test_invalid_restore_leaves_file_unchanged(self):
  quick.change('pin','nihao','你好',self.root);path=self.root/'kongime_quick.tsv';before=path.read_bytes()
  row={'code':'nihao','word':'你好','mode':'pin'}
  for value in [None,[row,row],[row,dict(row,word='拟好')],[dict(row,mode='bad')],[dict(row,word='词\u2028条')]]:
   with self.assertRaises(ValueError):quick.change('restore',root=self.root,replacement=value)
   self.assertEqual(path.read_bytes(),before)
 def test_empty_restore_can_be_undone(self):
  quick.change('unpin','nihao','你好',self.root);quick.change('restore',root=self.root,replacement=[])
  self.assertEqual(quick.read(self.root)[0],[])
  quick.change('undo',root=self.root,event=quick.read(self.root)[1][-1]['id'])
  self.assertEqual(len(quick.read(self.root)[0]),1)
