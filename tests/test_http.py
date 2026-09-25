import base64
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import urllib.request
import urllib.error
import zipfile

ROOT=Path(__file__).resolve().parents[1]
class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        env=dict(os.environ,QINGYAN_DATA=cls.tmp.name)
        code='import core,runpy;core.RIME=core.DATA/"rime";runpy.run_path("app.py",run_name="__main__")'
        cls.p=subprocess.Popen(['/usr/bin/python3','-B','-c',code,'--port','0','--no-open'],cwd=ROOT,env=env,stdout=subprocess.PIPE,text=True)
        cls.url=cls.p.stdout.readline().strip()
        cls.token=cls.request('state')['token']
    @classmethod
    def tearDownClass(cls):
        cls.p.terminate();cls.p.wait();cls.p.stdout.close();cls.tmp.cleanup()
    @classmethod
    def request(cls,path,data=None,token=True):
        req=urllib.request.Request(cls.url+'/api/'+path,data=json.dumps(data).encode() if data is not None else None)
        if data is not None:
            req.add_header('Content-Type','application/json')
            if token:req.add_header('X-Qingyan-Token',cls.token)
        with urllib.request.urlopen(req) as r:
            raw=r.read()
            return raw if r.headers.get_content_type()=='application/zip' else json.loads(raw)
    def test_v025_block_and_complete_preview(self):
        import hashlib
        original=self.request('quick-backup')
        try:
            self.request('quick-preference',dict(action='block',code='nh',word='你好'))
            profile=self.request('profile-backup');self.assertIn({'code':'nh','word':'你好','mode':'block'},profile['quick'])
            backup={'format':'kongime-complete-v1','profile':profile,'learning':{'format':'kongime-learning-v1','rows':[]}}
            backup['checksum']=hashlib.sha256(json.dumps({'profile':profile,'learning':backup['learning']},ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            preview=self.request('complete-preview',{'backup':backup});self.assertEqual(preview['learning_count'],0)
            self.assertIn('available',self.request('complete-status'))
            with self.assertRaises(urllib.error.HTTPError) as e:self.request('complete-restore',{'id':preview['id']},token=False)
            self.assertEqual(e.exception.code,403)
            self.request('quick-preference',dict(action='reset',code='nh',word='你好'))
            with self.assertRaises(urllib.error.HTTPError):self.request('complete-restore',{'id':preview['id']})
        finally:self.request('quick-restore',{'backup':original})

    def test_v024_upgrade_report_and_remember_preference(self):
        backup=self.request('backup')
        try:
            self.request('app-preference',dict(id='com.example.Editor',name='Editor',mode='remember'))
            self.assertEqual(self.request('state')['app_preferences'][-1]['mode'],'remember')
            with self.assertRaises(urllib.error.HTTPError) as e:self.request('upgrade-check',{},token=False)
            self.assertEqual(e.exception.code,403)
            self.assertTrue(self.request('upgrade-check',{})['ok'])
            self.assertIn('counts',self.request('upgrade-check'))
        finally:self.request('restore',{'backup':backup})

    def test_v023_group_export_and_organization(self):
        backup=self.request('backup')
        try:
            self.request('phrase',{'code':'vgroup','text':'group text','group':'工作'})
            revision=self.request('state')['revision']
            payload=dict(action='move',codes=['vgroup'],target='',revision=revision)
            with self.assertRaises(urllib.error.HTTPError) as e:self.request('phrase-organize',payload,token=False)
            self.assertEqual(e.exception.code,403)
            self.request('phrase-organize',payload)
            self.assertIn('vgroup',[x['code'] for x in self.request('phrases-export?group=')['phrases']])
            with self.assertRaises(urllib.error.HTTPError) as e:self.request('phrase-organize',payload)
            self.assertEqual(e.exception.code,400)
            self.assertFalse(self.request('phrases-export?group=missing')['phrases'])
        finally:self.request('restore',{'backup':backup})

    def test_v022_groups_checks_and_candidate_draft(self):
        backup=self.request('backup')
        try:
            self.request('phrase',{'code':'vgroup','text':'group text','group':'工作'})
            self.request('phrase-group',{'group':'工作','enabled':False})
            row=next(x for x in self.request('state')['phrases'] if x['code']=='vgroup')
            self.assertFalse(row['enabled'])
            self.assertTrue(self.request('phrase-check',{'code':'sh'})['warnings'])
            state=self.request('state')
            draft=self.request('phrase-candidate',{'text':'group text','code':'vgroup','comment':'','action':'edit'})
            self.assertEqual(draft['phrase']['group'],'工作');self.assertTrue(draft['editing'])
            self.assertEqual(self.request('state')['revision'],state['revision'])
            with self.assertRaises(urllib.error.HTTPError) as e:self.request('phrase-candidate',{'text':'text','code':'ab','comment':'','action':'new'},token=False)
            self.assertEqual(e.exception.code,403)
        finally:self.request('restore',{'backup':backup})

    def test_v021_phrase_transfer_and_toggle(self):
        backup=self.request('backup')
        try:
            row={'code':'vtest','text':'{W}','dynamic':True,'label':'日期','date_offset':1}
            self.request('phrase',row)
            self.request('phrase-toggle',{'code':'vtest','enabled':False})
            exported=self.request('phrases-export')
            self.assertFalse(next(x for x in exported['phrases'] if x['code']=='vtest')['enabled'])
            incoming={'format':'kongime-phrases-v1','phrases':[dict(row,text='copy {W}')]}
            p=self.request('phrases-preview',{'backup':incoming})
            self.assertEqual(p['conflicts'][0]['code'],'vtest')
            r=self.request('phrases-import',{'id':p['id'],'decisions':{'vtest':{'action':'rename','code':'vcopy'}}})
            self.assertEqual(r['added'],1)
            with self.assertRaises(urllib.error.HTTPError) as e:self.request('phrases-preview',{'backup':incoming},token=False)
            self.assertEqual(e.exception.code,403)
            self.assertIn('vcopy',[x['code'] for x in self.request('state')['phrases']])
        finally:self.request('restore',{'backup':backup})

    def test_v08_pin_unpin_preserves_word_and_weight(self):
        backup=self.request('backup')
        try:
            first={'word':'置顶测试甲','pinyin':'qin an','weight':321,'pinned':True}
            second={'word':'置顶测试乙','pinyin':'qin an','weight':654,'pinned':True}
            self.request('word',first);self.request('word',second)
            rows=self.request('words?q=qinan&scope=pinned')['rows']
            self.assertEqual([r['word'] for r in rows],['置顶测试乙'])
            second['pinned']=False;self.request('word',second)
            self.assertEqual(self.request('words?q=qinan&scope=pinned')['total'],0)
            rows=self.request('words?q=qinan')['rows']
            self.assertEqual({r['word']:r['weight'] for r in rows},{'置顶测试甲':321,'置顶测试乙':654})
            with zipfile.ZipFile(io.BytesIO(self.request('export'))) as z:
                self.assertNotIn('置顶测试',z.read('Rime/qingyan_pins.txt').decode())
        finally:self.request('restore',{'backup':backup})

    def test_full_management_flow(self):
        raw='轻言\tqing yan\t90\n清言\tqing yan\t100\n'
        p=self.request('preview',{'name':'test.txt','data':base64.b64encode(raw.encode()).decode()})
        self.assertEqual(p['count'],2)
        self.assertEqual(self.request('import',{'id':p['id']})['count'],2)
        self.request('word',{'word':'轻言','pinyin':'qing yan','weight':1000,'pinned':True})
        rows=self.request('words?q=qingyan')['rows'];self.assertEqual(rows[0]['word'],'轻言')
        self.request('settings',{'page_size':7,'learning':False})
        archive=self.request('export')
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            self.assertIn('menu/page_size: 7',z.read('Rime/default.custom.yaml').decode())
            self.assertIn('enable_user_dict: false',z.read('Rime/qingyan.schema.yaml').decode())
            self.assertEqual(z.read('Rime/qingyan_pins.txt').decode(),'轻言\tqingyan\t1\n')
        backup=self.request('backup')
        lib=self.request('state')['libraries'][0]
        self.request('library',{'id':lib['id'],'enabled':False})
        self.assertEqual(self.request('words')['total'],1)
        self.request('restore',{'backup':backup})
        self.assertEqual(self.request('words')['total'],2)
        self.assertTrue((Path(self.tmp.name)/'before-restore.json').exists())
    def test_requires_session_token(self):
        with self.assertRaises(urllib.error.HTTPError) as e:self.request('settings',{'page_size':5,'learning':True},False)
        self.assertEqual(e.exception.code,403)
    def test_renamed_scel_preview(self):
        from test_core import scel
        result=self.request('preview',{'name':'词库.txt','data':base64.b64encode(scel()).decode()})
        self.assertTrue(result['scel'])
        self.assertEqual(result['rows'][0]['word'],'轻言')
    def test_unrecognized_encoding_response(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.request('preview',{'name':'词库.txt','data':base64.b64encode(b'123456789\xa0\xff').decode()})
        error=json.load(e.exception)['error']
        self.assertIn('文件格式或编码',error)
        self.assertNotIn('codec',error)
    def test_sgpu_preview_and_export(self):
        from test_sgpu import fixture
        p=self.request('preview',{'name':'备份.bin','data':base64.b64encode(fixture()).decode()})
        self.assertTrue(p['sgpu']);self.assertEqual(p['review'],1)
        result=self.request('import',{'id':p['id']})
        self.assertEqual((result['count'],result['review']),(3,1))
        with zipfile.ZipFile(io.BytesIO(self.request('export'))) as z:
            text=z.read('Rime/qingyan_personal.dict.yaml').decode()
            self.assertIn('qing yan M D',text);self.assertNotIn('qing yan C #',text)

    def test_upgrade_resolution_restore_and_undo(self):
        backup=self.request('backup')
        try:
            from test_sgpu import fixture
            p=self.request('preview',{'name':'upgrade.bin','data':base64.b64encode(fixture()).decode()})
            # Other tests may already have imported this fixture; use its active receipt.
            existing=self.request('state')
            if not existing['imports']:
                self.request('import',{'id':p['id']})
            reviews=self.request('review')
            source=reviews[0]
            self.request('resolve',{'source':source,'decision':'replace','replacement':{'word':'修正测试','pinyin':'xiu zheng ce shi','weight':200}})
            self.assertEqual(self.request('review')[0]['decision'],'replace')
            saved=self.request('backup');self.request('restore',{'backup':saved})
            self.assertEqual(self.request('review')[0]['replacement']['word'],'修正测试')
            state=self.request('state');receipt=next(x for x in state['imports'] if not x['undone'])
            self.request('undo-import',{'id':receipt['id']})
            self.assertNotIn(receipt['library_id'],[x['id'] for x in self.request('state')['libraries']])
        finally:self.request('restore',{'backup':backup})

    def test_v03_phrase_backup_restore(self):
        backup=self.request('backup')
        try:
            self.request('phrase',{'code':'zzmail','text':'name@example.com'})
            saved=self.request('backup')
            self.request('phrase',{'old':'zzmail','code':'zzmail','text':'changed@example.com'})
            self.request('restore',{'backup':saved})
            phrase=next(x for x in self.request('state')['phrases'] if x['code']=='zzmail')
            self.assertEqual(phrase['text'],'name@example.com')
            self.assertFalse(self.request('job')['running'])
        finally:self.request('restore',{'backup':backup})

    def test_v04_preference_backup_and_reset(self):
        backup=self.request('backup')
        try:
            self.request('appearance',{'font_size':22,'layout':'stacked','theme':'dark'})
            pref={'id':'com.apple.Terminal','name':'终端','mode':'chinese'}
            self.request('app-preference',pref)
            saved=self.request('backup')
            self.request('settings',{'page_size':5,'learning':True})
            self.assertEqual(self.request('state')['appearance']['font_size'],22)
            self.request('app-preference',dict(pref,delete=True))
            self.request('restore',{'backup':saved})
            state=self.request('state');self.assertEqual(state['appearance']['theme'],'dark');self.assertEqual(state['app_preferences'][0]['mode'],'chinese')
            self.request('app-preference',dict(pref,delete=True))
            self.assertFalse(self.request('state')['app_preferences'])
        finally:self.request('restore',{'backup':backup})

    def test_v016_close_script_served(self):
        with urllib.request.urlopen(self.url+'/close-flow.js') as response:
            self.assertIn('settleSettingsClose',response.read().decode())
            self.assertIn('javascript',response.headers['Content-Type'])

    def test_v017_empty_restore_report_is_valid_json(self):
        self.assertEqual(self.request('restore-report'),{'report':None})

    def test_v017_review_restore_and_rollback(self):
        backup=self.request('profile-backup')
        changed=json.loads(json.dumps(backup))
        changed['manager']['state']['settings']['show_pinyin']=not backup['manager']['state']['settings']['show_pinyin']
        preview=self.request('restore-preview',{'backup':changed})
        self.assertGreater(preview['changes'],0)
        self.assertEqual(self.request('profile-backup'),backup)
        result=self.request('restore-confirm',{'id':preview['id']})
        self.assertTrue(result['verified'])
        report=self.request('restore-report')['report']
        self.assertTrue(report['verified']);self.assertFalse(report['changed_since'])
        rollback=self.request('restore-preview',{'source':'rollback'})
        self.assertTrue(self.request('restore-confirm',{'id':rollback['id']})['verified'])
        self.assertEqual(self.request('profile-backup')['manager']['state']['settings'],backup['manager']['state']['settings'])

if __name__=='__main__':unittest.main()
