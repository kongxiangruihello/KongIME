import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,workflow,jobs

class V03Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.data=patch.object(core,'DATA',Path(self.tmp.name)/'data');self.rime=patch.object(core,'RIME',Path(self.tmp.name)/'Rime');self.data.start();self.rime.start()
    def tearDown(self):self.data.stop();self.rime.stop();self.tmp.cleanup()
    def test_phrase_add_edit_delete_and_conflict(self):
        core.save_phrase({'code':'YX','text':'name@example.com'})
        with self.assertRaises(ValueError):core.save_phrase({'code':'yx','text':'overwrite'})
        core.save_phrase({'old':'yx','code':'yx','text':'new@example.com'})
        self.assertEqual(core.state()['phrases'][0]['text'],'new@example.com')
        s=core.state();s['personal']=[dict(core.normalize('地址','di zhi',100),pinned=True)];core.save(s)
        with self.assertRaises(ValueError):core.save_phrase({'code':'dizhi','text':'Test address'})
        core.save_phrase({'old':'yx','code':'yx','text':'new@example.com','delete':True});self.assertEqual(core.state()['phrases'],[])
    def test_phrase_controls_and_generation(self):
        for code,text in [('a','x'),('ab','x\ny'),('ab','x\ty'),('ab','x'*501),('a1','x')]:
            with self.assertRaises(ValueError):core.normalize_phrase({'code':code,'text':text})
        core.save_phrase({'code':'yx','text':'name@example.com'})
        core.generate(core.RIME,core.state())
        self.assertEqual((core.RIME/'kongime_phrases.txt').read_text(),'name@example.com\tyx\t1\n')
    def test_manual_migration_counts_and_preservation(self):
        old=Path(self.tmp.name)/'old';old.mkdir();s=core.state();s['phrases']=[{'code':'yx','text':'name@example.com'}];core.atomic_json(old/'state.json',s)
        result=workflow.select_directory(str(old));self.assertEqual(result['phrases'],1)
        workflow.migrate(result['id']);self.assertEqual(core.state()['phrases'],s['phrases']);self.assertTrue((core.DATA/'before-migration.json').exists());self.assertTrue((old/'state.json').exists())
    def test_migration_changed_preview_rejected(self):
        old=Path(self.tmp.name)/'old';old.mkdir();s=core.state();s['personal']=[core.normalize('测试','ce shi')];core.atomic_json(old/'state.json',s)
        r=workflow.select_directory(str(old));s['revision']+=1;core.atomic_json(old/'state.json',s)
        with self.assertRaises(ValueError):workflow.migrate(r['id'])
        self.assertFalse((core.DATA/'state.json').exists())
    def test_recover_preserves_learning_and_new_edits(self):
        core.generate(core.RIME,core.state());core.atomic_json(core.DATA/'deployment.json',{'ok':True,'revision':0,'sources':workflow.file_hashes(core.RIME,workflow.CONFIGS)})
        workflow.snapshot_good()
        (core.RIME/'qingyan.schema.yaml').write_text('broken')
        (core.RIME/'qingyan.userdb.txt').write_text('learned after backup')
        core.save_phrase({'code':'yx','text':'new@example.com'})
        with patch.object(workflow,'client',return_value=Path('/test/app')),patch.object(workflow.subprocess,'run'):
            workflow.recover()
        self.assertIn('schema:',(core.RIME/'qingyan.schema.yaml').read_text());self.assertEqual((core.RIME/'qingyan.userdb.txt').read_text(),'learned after backup');self.assertEqual(len(core.state()['phrases']),1)
    def test_job_prevents_duplicate_and_reports_failure(self):
        entered=threading.Event();finish=threading.Event()
        def work(progress):
            progress('compile');entered.set();finish.wait(3);raise ValueError('controlled failure')
        with patch.object(workflow,'deploy',side_effect=work):
            jobs.start('deploy');self.assertTrue(entered.wait(1))
            with self.assertRaises(ValueError):jobs.start('deploy')
            self.assertEqual(jobs.status()['stage'],'compile');finish.set()
            for _ in range(100):
                if not jobs.status()['running']:break
                time.sleep(.01)
            self.assertEqual(jobs.status()['stage'],'failed')

if __name__=='__main__':unittest.main()
