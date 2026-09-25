import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core

U=lambda n: struct.pack('<H',n)
def scel(mask=0x44):
    offset={0x44:0x2628,0x45:0x26c4}[mask]
    data=bytearray(offset);data[:5]=b'\x40\x15\x00\x00'+bytes([mask])
    table=b''
    for i,py in enumerate(('qing','yan','zuo')):
        raw=py.encode('utf-16le');table+=U(i)+U(len(raw))+raw
    data[0x1544:0x1544+len(table)]=table
    raw='轻言'.encode('utf-16le')
    return bytes(data)+U(1)+U(4)+U(0)+U(1)+U(len(raw))+raw+U(10)+bytes(10)

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=core.DATA;self.oldr=core.RIME
        core.DATA=Path(self.tmp.name)/'data';core.RIME=Path(self.tmp.name)/'Rime'
    def tearDown(self):
        core.DATA=self.old;core.RIME=self.oldr;self.tmp.cleanup()
    def test_scel_both_versions(self):
        for mask in (0x44,0x45):self.assertEqual(core.parse_scel(scel(mask)),[{'word':'轻言','pinyin':'qing yan','weight':100}])
    def test_scel_content_detection(self):
        for filename in ('词库.txt', '词库', '词库.bin', '词库.SCEL '):
            rows, _ = core.parse_import(scel(), filename)
            self.assertEqual(rows[0]['word'], '轻言')
            self.assertTrue(core.is_scel(scel(), filename))
    def test_bomless_utf16(self):
        for encoding in ('utf-16le', 'utf-16be'):
            rows, _ = core.parse_import('轻言\tqing yan\t100\n'.encode(encoding), '词库.txt')
            self.assertEqual(rows[0]['pinyin'], 'qing yan')
    def test_binary_error_is_actionable_and_atomic(self):
        for data, name in [(b'123456789\xa0\xff', '词库.txt'),
                           (b'\xff\xfe\x00', '词库.txt'),
                           (b'\x00\x01\xff', '词库.bin')]:
            with self.assertRaises(ValueError) as error:
                core.import_library(data, name)
            self.assertNotIsInstance(error.exception, UnicodeDecodeError)
            self.assertIn('TXT', str(error.exception))
        self.assertFalse((core.DATA/'state.json').exists())
    def test_archive_gets_extraction_hint(self):
        with self.assertRaisesRegex(ValueError, '解压'):
            core.parse_import(b'PK\x03\x04abc', '词库.zip')
    def test_scel_truncation_is_atomic(self):
        for n in (1,5,11):
            with self.assertRaises(ValueError):core.import_library(scel()[:-n],'bad.scel')
        self.assertFalse((core.DATA/'state.json').exists())
    def test_unknown_scel_and_bad_index(self):
        a=bytearray(scel());a[4]=0x46
        with self.assertRaises(ValueError):core.parse_scel(a)
        a=bytearray(scel());a[0x262c:0x262e]=U(999)
        with self.assertRaises(ValueError):core.parse_scel(a)
    def test_text_dedupe_and_encodings(self):
        for encoding in ('utf-8-sig','utf-16','gb18030'):
            rows,dupes=core.parse_import('词语\t拼音\t权重\n轻言\tqing yan\t100\n轻言\tqing yan\t200'.encode(encoding),'x.txt')
            self.assertEqual(dupes,1);self.assertEqual(rows[0]['weight'],200)
    def test_invalid_text_is_not_silently_skipped(self):
        with self.assertRaises(ValueError):core.parse_import('轻言\tqing yan\n坏行'.encode(),'x.txt')
    def test_import_idempotence(self):
        core.import_library(scel(),'one.scel')
        with self.assertRaises(ValueError):core.import_library(scel(),'two.scel')
        self.assertEqual(len(core.state()['libraries']),1)
    def test_personal_override_and_library_disable(self):
        core.import_library(scel(),'one.scel');s=core.state()
        s['personal']=[{'word':'轻言','pinyin':'qing yan','weight':5,'pinned':True}]
        self.assertEqual(core.active_rows(s)[0]['weight'],5)
        s['libraries'][0]['enabled']=False
        self.assertEqual(len(core.active_rows(s)),1)
        s['personal']=[];self.assertEqual(core.active_rows(s),[])
    def test_yaml_and_pin_output(self):
        s=core.state();s['personal']=[{'word':'轻言','pinyin':'qing yan','weight':300,'pinned':True}]
        target=Path(self.tmp.name)/'out';core.generate(target,s)
        self.assertEqual((target/'qingyan_pins.txt').read_text(),'轻言\tqingyan\t1\n')
        d=(target/'qingyan.dict.yaml').read_text()
        self.assertLess(d.index('qingyan_personal'),d.index('cn_dicts/base'))
        self.assertIn('enable_user_dict: true',(target/'qingyan.schema.yaml').read_text())
    def test_apply_preserves_user_database_and_backs_up(self):
        core.RIME.mkdir();(core.RIME/'qingyan.userdb.txt').write_text('learned')
        (core.RIME/'default.custom.yaml').write_text('old config')
        r=core.apply_config()
        self.assertEqual((core.RIME/'qingyan.userdb.txt').read_text(),'learned')
        self.assertEqual((Path(r['backup'])/'default.custom.yaml').read_text(),'old config')
        self.assertTrue((core.RIME/'qingyan.schema.yaml').exists())
    def test_real_sogou_optional(self):
        f=Path('/tmp/qingyan-real.scel')
        if not f.exists():self.skipTest('external fixture unavailable')
        rows,_=core.parse_import(f.read_bytes(),'computer.scel')
        self.assertEqual(len(rows),10300)
        self.assertEqual(rows[0]['word'],'阿姆达尔定律')

if __name__=='__main__':unittest.main()
