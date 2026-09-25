import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core

class V05Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.data=patch.object(core,'DATA',Path(self.tmp.name));self.data.start()
        self.s=core.state()
        self.s['personal']=[core.normalize('你好','ni hao',200),dict(core.normalize('拟好','ni hao',300),pinned=True),core.normalize('测试','ce shi #',400)]
        core.save(self.s)
    def tearDown(self):
        self.data.stop();self.tmp.cleanup()
    def test_scopes_and_search(self):
        r=core.search_words(self.s,' NIHAO ',scope='pinned')
        self.assertEqual(r['total'],1)
        self.assertEqual(r['rows'][0]['word'],'拟好')
        self.assertEqual(r['counts'],{'all':2,'personal':2,'pinned':1,'special':0})
    def test_weight_and_page_clamping(self):
        r=core.search_words(self.s,order='weight',page=500)
        self.assertEqual([x['weight'] for x in r['rows']],[400,300,200])
        self.assertEqual(r['page'],0)
        self.assertEqual(core.search_words(self.s,'不存在',page=99)['page'],0)
    def test_resolved_special_is_replaced_without_duplicate(self):
        source=self.s['personal'][-1]
        core.resolve_word({'source':source,'decision':'replace','replacement':core.normalize('测试','ce shi',400)})
        s=core.state()
        self.assertEqual(core.search_words(s,scope='special')['total'],0)
        r=core.search_words(s,'测试',scope='personal')
        self.assertEqual(r['total'],1);self.assertEqual(r['rows'][0]['pinyin'],'ce shi')
    def test_disabled_libraries_are_excluded(self):
        self.s['libraries']=[{'id':'on','enabled':True},{'id':'off','enabled':False}]
        core.atomic_json(core.DATA/'libraries/on.json',[core.normalize('词库','ci ku')])
        core.atomic_json(core.DATA/'libraries/off.json',[core.normalize('关闭','guan bi')])
        r=core.search_words(self.s)
        self.assertEqual(r['counts']['all'],4);self.assertEqual(r['counts']['personal'],3)
    def test_invalid_filters(self):
        for kwargs in ({'scope':'bad'},{'order':'bad'},{'page':'bad'}):
            with self.assertRaises(ValueError):core.search_words(self.s,**kwargs)

if __name__=='__main__':unittest.main()
