import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core, workflow

class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.data=patch.object(core,'DATA',Path(self.tmp.name)/'data');self.rime=patch.object(core,'RIME',Path(self.tmp.name)/'Rime');self.data.start();self.rime.start()
    def tearDown(self):self.data.stop();self.rime.stop();self.tmp.cleanup()
    def test_undo_preserves_later_edits_and_snapshot(self):
        r=core.import_library('你好\tni hao\t100\n你好\tni hao\t90'.encode(),'a.txt')
        self.assertEqual(r['duplicates'],1)
        backup=json.loads((core.DATA/'import-backups'/r['backup']).read_text());self.assertEqual(backup['state']['libraries'],[])
        s=core.state();s['personal'].append(core.normalize('自定义','zi ding yi',100));core.save(s)
        core.undo_import(r['id']);self.assertEqual(len(core.state()['personal']),1);self.assertEqual(core.state()['libraries'],[])
    def special(self):
        s=core.state();r=core.normalize('特殊','te shu C #',100);s['personal'].append(r);core.save(s);return r
    def test_personal_resolution_and_undo(self):
        r=self.special();core.resolve_word({'source':r,'decision':'replace','replacement':core.normalize('特殊','te shu',200)})
        self.assertEqual([x['pinyin'] for x in core.active_rows(core.state())],['te shu'])
        core.resolve_word({'source':r,'decision':'undo'});self.assertEqual(core.review_rows(core.state())[0]['decision'],'pending')
    def test_ignore_keep_and_invalid_are_atomic(self):
        r=self.special();core.resolve_word({'source':r,'decision':'ignore'});self.assertEqual(core.active_rows(core.state()),[])
        core.resolve_word({'source':r,'decision':'keep'});self.assertEqual(len(core.active_rows(core.state())),1)
        old=core.state()
        with self.assertRaises(ValueError):core.resolve_word({'source':r,'decision':'replace','replacement':r})
        self.assertEqual(old,core.state())
    def test_status_missing_and_failed(self):
        with patch.object(workflow,'client',return_value=None),patch.object(workflow,'input_status',return_value={'enabled':None,'selected':None}):
            self.assertEqual(workflow.status()['stage'],'missing')
        app=Path(self.tmp.name)/'Squirrel.app';app.mkdir()
        core.atomic_json(core.DATA/'deployment.json',{'revision':0,'ok':False,'error':'test'})
        with patch.object(workflow,'client',return_value=app),patch.object(workflow,'input_status',return_value={'enabled':True,'selected':False}):self.assertEqual(workflow.status()['stage'],'failed')
    def test_migration_rejects_unlisted_path(self):
        with patch.object(workflow,'legacy_candidates',return_value=[]):
            with self.assertRaises(ValueError):workflow.migrate('../../state.json')

if __name__=='__main__':unittest.main()
