import os,struct,json,tempfile,unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core

def fixture():
    table=json.loads((core.ROOT/'sgpu_pinyin.json').read_text())
    records=[]
    for word,codes,freq in [('轻言','qing yan',0),('轻言','qing yan',70),('轻言MD','qing yan M D',13),('轻言C#','qing yan C #',2)]:
        ids=b''.join(struct.pack('<H',table.index(p)) for p in codes.split())
        raw=word.encode('utf-16le')
        records.append(struct.pack('<H',freq)+bytes(7)+struct.pack('<H',len(ids))+ids+struct.pack('<HH',len(ids)+len(raw)+4,len(raw))+raw)
    offsets=[];body=b''
    for record in records:offsets.append(len(body));body+=record
    index=140;size=len(records)*4;base=index+size
    result=bytearray(base+len(body));result[:4]=b'SGPU'
    struct.pack_into('<I',result,16,len(result))
    struct.pack_into('<6I',result,56,index,size,len(records),base,len(body),len(body))
    for i,off in enumerate(offsets):struct.pack_into('<I',result,index+i*4,off)
    result[base:]=body
    return bytes(result)

class SGPUTests(unittest.TestCase):
    def test_content_detection_frequency_and_mixed(self):
        rows,dupes=core.parse_import(fixture(),'renamed.txt')
        self.assertEqual(dupes,1);self.assertEqual(len(rows),3)
        self.assertEqual(rows[0]['weight'],70)
        self.assertEqual(rows[1]['pinyin'],'qing yan M D')
        self.assertEqual(rows[2]['pinyin'],'qing yan C #')
    def test_zero_frequency_floor(self):
        self.assertEqual(core.parse_sgpu(fixture())[0]['weight'],1)
    def test_rejects_truncated_or_invalid_index(self):
        for data in (fixture()[:-1],fixture()[:40]):
            with self.assertRaises(ValueError):core.parse_sgpu(data)
        data=bytearray(fixture());struct.pack_into('<I',data,140,0xffffffff)
        with self.assertRaises(ValueError):core.parse_sgpu(data)
    def test_invalid_syllable_is_rejected(self):
        data=bytearray(fixture());base=struct.unpack_from('<I',data,68)[0]
        struct.pack_into('<H',data,base+11,65535)
        with self.assertRaises(ValueError):core.parse_sgpu(data)
    def test_special_codes_preserved_but_not_deployed(self):
        s=core.state();s.update(libraries=[],personal=core.parse_import(fixture(),'x.bin')[0])
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);core.generate(path,s)
            generated=(path/'qingyan_personal.dict.yaml').read_text()
            self.assertIn('qing yan M D',generated);self.assertNotIn('qing yan C #',generated)
            self.assertIn('abbrev/^C$/c/',(path/'qingyan.schema.yaml').read_text())
    def test_user_fixture_optional(self):
        name=os.environ.get('QINGYAN_SGPU_FIXTURE')
        if not name:self.skipTest('private fixture not provided')
        rows,dupes=core.parse_import(Path(name).read_bytes(),name)
        self.assertEqual((len(rows),dupes),(56356,2323))
        self.assertEqual(sum(any(c in '0123456789#' for c in r['pinyin']) for r in rows),47)

if __name__=='__main__':unittest.main()
