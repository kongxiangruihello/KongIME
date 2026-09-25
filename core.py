"""Qingyan local dictionary tools. Python 3.9+, no third-party packages."""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import struct
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('QINGYAN_DATA', str(ROOT / '用户数据')))
RIME = Path.home() / 'Library/Rime'
MAX_ENTRIES = 300000

def normalize(word, pinyin, weight=100):
    word = str(word).strip()
    pinyin = re.sub(r"[\s']+", ' ', str(pinyin).replace('ü', 'v')).strip()
    pinyin = ' '.join(x if re.fullmatch('[A-Z]', x) else x.lower() for x in pinyin.split())
    if not word or len(word) > 100 or any(ord(c) < 32 for c in word):
        raise ValueError('词语为空、过长或含控制字符')
    if not re.fullmatch(r'(?:[a-zv]+|[A-Z0-9#])(?: (?:[a-zv]+|[A-Z0-9#]))*', pinyin) or len(pinyin) > 500:
        raise ValueError('拼音须为小写字母，各音节用空格分开，例如 qing yan')
    try:
        weight = int(weight)
    except (TypeError, ValueError):
        raise ValueError('初始权重须为整数')
    if not 1 <= weight <= 1000000:
        raise ValueError('初始权重须在 1–1,000,000 之间')
    return {'word': word, 'pinyin': pinyin, 'weight': weight}

class Reader:
    def __init__(self, data, start, end=None):
        self.data, self.pos, self.end = data, start, len(data) if end is None else end
    def take(self, n):
        if n < 0 or self.pos + n > self.end:
            raise ValueError('SCEL 文件被截断，未导入任何词条')
        result = self.data[self.pos:self.pos+n]
        self.pos += n
        return result
    def u16(self):
        return struct.unpack('<H', self.take(2))[0]
    def text(self, n):
        if n % 2:
            raise ValueError('SCEL 文本长度无效')
        return self.take(n).decode('utf-16le')

def parse_scel(data):
    # Public format reference: https://github.com/lewangdev/scel2txt (README).
    # Independent implementation; extension values are deliberately not treated as frequency.
    if len(data) < 0x2628 or data[:4] != b'\x40\x15\x00\x00':
        raise ValueError('不是受支持的搜狗 SCEL 细胞词库')
    offset = {0x44: 0x2628, 0x45: 0x26c4}.get(data[4])
    if offset is None or len(data) < offset:
        raise ValueError('暂不支持这个 SCEL 版本，请导出带拼音的 TXT 再导入')
    r = Reader(data, 0x1544, offset)
    table = {}
    while r.pos + 4 <= offset:
        index, n = r.u16(), r.u16()
        if n == 0:
            break
        if n > 32:
            raise ValueError('SCEL 拼音表损坏')
        py = r.text(n)
        if not re.fullmatch('[a-züv]+', py):
            raise ValueError('SCEL 拼音表含无效音节')
        table[index] = py
        if py == 'zuo':
            break
    r = Reader(data, offset)
    rows = []
    while r.pos < len(data):
        if not any(data[r.pos:r.pos+4]) and not any(data[r.pos:]):
            break
        count, size = r.u16(), r.u16()
        if count == 0 or size == 0 or size % 2 or size > 400:
            raise ValueError('SCEL 词组结构无效')
        ids = [r.u16() for _ in range(size // 2)]
        try:
            py = ' '.join(table[i] for i in ids)
        except KeyError:
            raise ValueError('SCEL 缺少拼音索引，未导入任何词条')
        for _ in range(count):
            word = r.text(r.u16())
            r.take(r.u16())
            rows.append(normalize(word, py))
            if len(rows) > MAX_ENTRIES:
                raise ValueError('单个词库最多支持 30 万词')
    if not rows:
        raise ValueError('词库中没有可导入的词条')
    return rows

def is_scel(data, filename):
    return data.startswith(b'\x40\x15\x00\x00') or filename.strip().lower().endswith('.scel')


def parse_sgpu(data):
    """SGPU v3 indexed backup. Format reference: licenses/SGPU-NOTICE.txt."""
    def fail():
        raise ValueError('SGPU 备份结构不完整或版本暂不兼容，未导入任何词条。请重新导出原始备份。')
    def uint(pos, size, limit=None):
        if pos < 0 or pos + size > (len(data) if limit is None else limit): fail()
        return int.from_bytes(data[pos:pos+size], 'little')
    if len(data) < 80 or data[:4] != b'SGPU': fail()
    if uint(16, 4) != len(data): fail()
    index, index_size, count, base, capacity, used = [uint(i, 4) for i in range(56, 80, 4)]
    if not (80 <= index <= base <= len(data)): fail()
    if index + index_size != base or base + capacity != len(data) or used > capacity: fail()
    if count == 0 or count > MAX_ENTRIES or count * 4 > index_size: fail()
    syllables = json.loads((ROOT / 'sgpu_pinyin.json').read_text())
    limit = base + used
    rows = []
    for i in range(count):
        pos = base + uint(index + 4*i, 4)
        frequency = uint(pos, 2, limit)
        size = uint(pos+9, 2, limit)
        if size == 0 or size % 2 or size > 400: fail()
        ids = [uint(pos+11+j, 2, limit) for j in range(0, size, 2)]
        if any(k >= len(syllables) for k in ids): fail()
        length = uint(pos+13+size, 2, limit)
        start = pos+15+size
        if not length or length % 2 or start+length > limit: fail()
        try:
            word = data[start:start+length].decode('utf-16le')
        except UnicodeDecodeError:
            fail()
        row = normalize(word, ' '.join(syllables[k] for k in ids), max(1, frequency))
        rows.append(row)
    return rows


def decode_text(data):
    encodings = ['utf-8-sig', 'gb18030']
    if data[:2] in (b'\xff\xfe', b'\xfe\xff'):
        encodings = ['utf-16']
    elif b'\x00' in data:
        # BOM-less UTF-16 is accepted only with aligned table separators.
        encodings = []
        for encoding, marker in [('utf-16le', b'\t\x00'), ('utf-16be', b'\x00\t')]:
            if any(data[i:i+2] == marker for i in range(0, len(data)-1, 2)):
                encodings.append(encoding)
    for encoding in encodings:
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        if not any(ord(c) < 32 and c not in '\t\r\n' for c in text):
            return text
    raise ValueError('无法识别这个词库的文件格式或编码。请提供原始 .scel 细胞词库，或从搜狗导出带拼音的 TXT；当前只支持 SGPU 格式的搜狗二进制备份。请勿只修改文件后缀。')


def parse_text(data, filename):
    text = decode_text(data)
    # Restrict Rime import to explicit word/code/weight rows; never execute YAML tags.
    if filename.endswith(('.yaml', '.yml')):
        if '\n...\n' not in text.replace('\r\n', '\n'):
            raise ValueError('Rime 词库需要以 ... 结束的文件头')
        text = text.replace('\r\n', '\n').split('\n...\n', 1)[1]
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        parts = next(csv.reader([line])) if filename.endswith('.csv') else line.split('\t')
        if parts[0].strip() in ('词语', 'word', 'text'):
            continue
        if len(parts) not in (2, 3):
            raise ValueError('第 %s 行需要“词语、拼音、可选权重”三列（TXT 用 Tab 分隔）' % number)
        try:
            rows.append(normalize(parts[0], parts[1], parts[2] if len(parts) == 3 and parts[2] else 100))
        except ValueError as e:
            raise ValueError('第 %s 行：%s' % (number, e))
        if len(rows) > MAX_ENTRIES:
            raise ValueError('单个词库最多支持 30 万词')
    if not rows:
        raise ValueError('没有找到带拼音的词条')
    return rows

def parse_import(data, filename):
    if len(data) > 32 * 1024 * 1024:
        raise ValueError('单个文件最大 32 MB')
    filename = filename.strip().lower()
    if data.startswith(b'SGPU'):
        rows = parse_sgpu(data)
    elif is_scel(data, filename):
        try:
            rows = parse_scel(data)
        except UnicodeDecodeError:
            raise ValueError('SCEL 中的文字编码无效，文件可能损坏或属于暂不支持的版本。请提供原始词库文件。') from None
    else:
        if data.startswith((b'PK\x03\x04', b'\x1f\x8b')):
            raise ValueError('这是压缩包，请先解压，再导入里面的 .scel 或带拼音的 TXT 文件。')
        if filename.endswith(('.bin', '.bak', '.dat')):
            raise ValueError('这个二进制文件不是已支持的 SGPU 备份或 SCEL 词库。请提供原始文件以核对版本，或从搜狗导出带拼音的 TXT。')
        rows = parse_text(data, filename)
    unique = {}
    for row in rows:
        key = (row['word'], row['pinyin'])
        if key not in unique or row['weight'] > unique[key]['weight']:
            unique[key] = row
    return list(unique.values()), len(rows) - len(unique)

def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=str(path.parent), prefix='.tmp-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)

def normalize_settings(value):
    count=value.get('page_size',5)
    if type(count) is not int or count not in (3,5,7,9):raise ValueError('候选数量无效')
    result={'page_size':count}
    for key,default in [('abbreviation',True),('learning',True),('show_pinyin',True),('auto_save',False),('language_hint',True),('pair_chinese',False),('pair_english',False),('ascii_punctuation',False),('direct_english',True),('recognize_addresses',True)]:
        v=value.get(key,default)
        if type(v) is not bool:raise ValueError('设置格式无效')
        result[key]=v
    result['shortcuts']=normalize_shortcuts(value.get('shortcuts',{}))
    return result

SHORTCUT_CHOICES=('Tab','Control+Tab','Control+grave','minus','equal','comma','period','bracketleft','bracketright','Control+p','Control+o','none')
DEFAULT_SHORTCUTS={'expand':'Tab','previous':'minus','next':'equal','pin':'Control+p'}
def normalize_shortcuts(value):
    if not isinstance(value,dict):raise ValueError('快捷键格式无效')
    result={k:value.get(k,v) for k,v in DEFAULT_SHORTCUTS.items()}
    for key,value in result.items():
        if value not in SHORTCUT_CHOICES:raise ValueError('不支持的快捷键')
        if key in ('expand','pin') and value not in ('Tab','Control+Tab','Control+grave','Control+p','Control+o','none'):raise ValueError('展开与置顶请使用 Tab 或组合键')
    used=[v for v in result.values() if v!='none']
    if len(used)!=len(set(used)):raise ValueError('快捷键冲突：两个操作不能使用同一个按键')
    return result

def state():
    path = DATA / 'state.json'
    if path.exists():
        value = json.loads(path.read_text())
        for key in ('resolutions', 'imports', 'phrases', 'app_preferences'): value.setdefault(key, [])
        value.setdefault('appearance', default_appearance())
        value.setdefault('fuzzy', [])
        value.setdefault('trash',[]);value.setdefault('scenes',[])
        value['settings']=normalize_settings(value['settings'])
        return value
    return {'version': 4, 'trash': [], 'scenes': [], 'fuzzy': [], 'appearance': default_appearance(), 'app_preferences': [], 'phrases': [], 'resolutions': [], 'imports': [], 'revision': 0, 'applied': -1, 'libraries': [], 'personal': [], 'settings': normalize_settings({})}

def change_history():
    p=DATA/'changes.json'
    return json.loads(p.read_text()) if p.exists() else []

def save(s):
    previous=state()
    keys=[('trash','回收站'),('scenes','词库场景'),('personal','词语与置顶'),('phrases','常用短语'),('appearance','候选外观'),('fuzzy','模糊音'),('app_preferences','应用语言'),('settings','输入习惯'),('libraries','词库'),('resolutions','编码修正')]
    labels=[label for key,label in keys if previous.get(key)!=s.get(key)]
    s['revision']=max(s['revision'],previous['revision'])+1
    history=change_history()
    if labels:
        history.append({'id':uuid.uuid4().hex,'time':time.strftime('%Y-%m-%d %H:%M:%S'),'label':'、'.join(labels),'before':previous,'revision':s['revision']})
    atomic_json(DATA/'changes.json',history[-20:])
    atomic_json(DATA / 'state.json', s)

def undo_change(event):
    history=change_history();current=state()
    if not history or history[-1]['id']!=event or history[-1]['revision']!=current['revision']:
        raise ValueError('请先撤销更新的一次设置修改')
    previous=history.pop()['before'];previous['revision']=current['revision']+1;previous['applied']=-1
    if history:history[-1]['revision']=previous['revision']
    atomic_json(DATA/'changes.json',history)
    atomic_json(DATA/'state.json',previous)
    return {'ok':True}

def lib_rows(lib):
    return json.loads((DATA / 'libraries' / (lib['id'] + '.json')).read_text())

def import_library(data, filename, policy="higher"):
    if policy not in ("local", "incoming", "higher"): raise ValueError("词库冲突策略无效")
    rows, dupes = parse_import(data, filename)
    digest = hashlib.sha256(data).hexdigest()
    s = state()
    if any(x['hash'] == digest for x in s['libraries']):
        raise ValueError('这个文件已经导入过，无需重复添加')
    backup_name = time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8] + '.json'
    atomic_json(DATA / 'import-backups' / backup_name, backup_value(s))
    existing = {row_key(r) for r in active_rows(s)}
    overlap = sum(row_key(r) in existing for r in rows)
    local = base_rows(s)
    for row in rows:
        old = local.get(row_key(row))
        if old and policy != 'incoming': row['weight'] = old['weight'] if policy == 'local' else max(old['weight'], row['weight'])
    lid = uuid.uuid4().hex
    review = sum(bool(re.search(r'[0-9#]', r['pinyin'])) for r in rows)
    lib = {'id': lid, 'name': Path(filename).name, 'count': len(rows), 'enabled': True, 'hash': digest, 'review': review, 'conflict_policy': policy}
    atomic_json(DATA / 'libraries' / (lid + '.json'), rows)
    s['libraries'].append(lib)
    s['imports'].append({'id': lid, 'library_id': lid, 'name': lib['name'], 'count': len(rows), 'read': len(rows)+dupes, 'duplicates': dupes, 'overlap': overlap, 'usable': len(rows)-review, 'review': review, 'backup': backup_name, 'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'undone': False})
    save(s)
    return dict(s['imports'][-1])

def base_rows(s, reader=None):
    reader=reader or lib_rows
    merged = {}
    for lib in s['libraries']:
        if lib['enabled']:
            for r in reader(lib):
                key = (r['word'], r['pinyin'])
                if key not in merged or lib.get('conflict_policy') in ('local', 'incoming', 'higher') or merged[key]['weight'] < r['weight']:
                    merged[key] = dict(r)
    return merged

def row_key(row):
    return row['word'], row['pinyin']

def needs_review(row):
    return bool(re.search(r'[0-9#]', row['pinyin']))

def active_rows(s, reader=None):
    merged = base_rows(s,reader)
    for r in s["personal"]:
        if needs_review(r): merged[row_key(r)] = dict(r)
    for item in s.get('resolutions', []):
        key = row_key(item['source'])
        if key not in merged: continue
        if item['decision'] == 'replace':
            merged.pop(key)
            replacement = dict(item['replacement'])
            new_key = row_key(replacement)
            if new_key not in merged or replacement['weight'] > merged[new_key]['weight']:
                merged[new_key] = replacement
        elif item['decision'] == 'ignore':
            merged.pop(key)
    for r in s['personal']:
        if not needs_review(r): merged[(r['word'], r['pinyin'])] = dict(r)
    return sorted(merged.values(), key=lambda r: (r['pinyin'], -r['weight'], r['word']))

def search_words(s, query='', scope='all', order='pinyin', page=0):
    if scope not in ('all','personal','pinned','special'): raise ValueError('词语筛选范围无效')
    if order not in ('pinyin','weight'): raise ValueError('词语排序方式无效')
    query=str(query).strip().lower()
    compact=''.join(query.split())
    rows=[r for r in active_rows(s) if query in r['word'].lower() or query in r['pinyin'].lower() or compact in r['pinyin'].replace(' ','').lower()]
    personal={row_key(r) for r in s['personal']}
    personal.update(row_key(r['replacement']) for r in s.get('resolutions',[]) if r['decision']=='replace')
    groups={'all':rows,'personal':[r for r in rows if row_key(r) in personal],
            'pinned':[r for r in rows if r.get('pinned')], 'special':[r for r in rows if needs_review(r)]}
    selected=groups[scope]
    if order=='weight': selected=sorted(selected,key=lambda r:(-r['weight'],r['pinyin'],r['word']))
    total=len(selected);page=min(max(0,int(page)),max(0,(total-1)//50))
    return {'total':total,'page':page,'rows':selected[page*50:page*50+50], 'counts':{k:len(v) for k,v in groups.items()}}

def backup_value(s=None):
    s = state() if s is None else s
    return {'format': 'qingyan-backup-v1', 'state': s, 'libraries': {x['id']: lib_rows(x) for x in s['libraries']}}

def undo_import(import_id):
    s = state()
    receipt = next((x for x in s.get('imports', []) if x['id'] == import_id), None)
    if not receipt or receipt['undone']: raise ValueError('这次导入已撤销或不存在')
    s['libraries'] = [x for x in s['libraries'] if x['id'] != receipt['library_id']]
    receipt['undone'] = True
    save(s)
    return {'ok': True, 'name': receipt['name']}

def review_rows(s):
    rows = base_rows(s)
    for r in s['personal']:
        if needs_review(r): rows[row_key(r)] = dict(r)
    resolved = {row_key(x['source']): x for x in s.get('resolutions', [])}
    result = []
    for key, r in rows.items():
        if not needs_review(r): continue
        item = resolved.get(key)
        result.append(dict(r, decision=item['decision'] if item else 'pending', replacement=item.get('replacement') if item else None))
    return sorted(result, key=lambda r: (r['word'], r['pinyin']))

def resolve_word(data):
    s = state()
    source = normalize(data['source']['word'], data['source']['pinyin'], data['source'].get('weight', 100))
    if row_key(source) not in {row_key(r) for r in review_rows(s)}: raise ValueError('待处理词条已不存在，请刷新')
    decision = data['decision']
    if decision not in ('replace', 'ignore', 'keep', 'undo'): raise ValueError('无效的处理方式')
    item = {'source': source, 'decision': decision}
    if decision == 'replace':
        v = data['replacement'];r = normalize(v['word'], v['pinyin'], v['weight'])
        if needs_review(r): raise ValueError('请改为可输入的拼音或英文字母编码，不能保留数字或 #')
        item['replacement'] = r
    s['resolutions'] = [r for r in s.get('resolutions', []) if row_key(r['source']) != row_key(source)]
    if decision != 'undo': s['resolutions'].append(item)
    save(s)
    return {'ok': True}

def default_appearance():
    return {'font_size':17, 'layout':'linear', 'theme':'auto', 'candidate_gap':8}

def normalize_appearance(value):
    size=value.get('font_size',17)
    if type(size) is not int or size not in (14,16,17,18,20,22,24):raise ValueError('请选择支持的候选字号')
    if value.get('layout','linear') not in ('linear','stacked'):raise ValueError('候选排列无效')
    if value.get('theme','auto') not in ('auto','light','dark'):raise ValueError('候选配色无效')
    gap=value.get('candidate_gap',8)
    if type(gap) is not int or gap not in (8,12,18,24):raise ValueError('请选择支持的候选窗口间距')
    return {'font_size':size,'layout':value.get('layout','linear'),'theme':value.get('theme','auto'),'candidate_gap':gap}

def normalize_app_preference(value):
    app_id=str(value.get('id',''))
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9.-]{1,199}',app_id):raise ValueError('应用标识无效')
    mode=value.get('mode')
    if mode not in ('default','chinese','english','remember'):raise ValueError('应用初始状态无效')
    if type(value.get('disable_pairs',False)) is not bool:raise ValueError('应用标点设置无效')
    result={'id':app_id,'name':str(value.get('name',app_id))[:100],'mode':mode}
    if value.get('disable_pairs'):result['disable_pairs']=True
    return result

FUZZY_RULES = {
    'z_zh': ('derive/^zh/z/', 'derive/^z([^h])/zh$1/'),
    'c_ch': ('derive/^ch/c/', 'derive/^c([^h])/ch$1/'),
    's_sh': ('derive/^sh/s/', 'derive/^s([^h])/sh$1/'),
    'n_l': ('derive/^n/l/', 'derive/^l/n/'),
    'f_h': ('derive/^f/h/', 'derive/^h/f/'),
    'an_ang': ('derive/ang$/an/', 'derive/an$/ang/'),
    'en_eng': ('derive/eng$/en/', 'derive/en$/eng/'),
    'in_ing': ('derive/ing$/in/', 'derive/in$/ing/'),
}

def normalize_fuzzy(value):
    if not isinstance(value, list) or any(not isinstance(x,str) or x not in FUZZY_RULES for x in value):
        raise ValueError('模糊音选项无效')
    return [key for key in FUZZY_RULES if key in value]

def normalize_phrase_group(value):
    if not isinstance(value,str):raise ValueError('分组名称无效')
    value=value.strip()
    if len(value)>30 or any(ord(c)<32 or ord(c)==127 for c in value):raise ValueError('分组名称最多 30 字，不能包含换行')
    return '' if value=='未分组' else value

def normalize_phrase(value):
    code = str(value.get('code', '')).strip().lower()
    text = str(value.get('text', '')).strip()
    if not re.fullmatch('[a-z]{2,20}', code): raise ValueError('缩写须为 2–20 个英文字母')
    if not text or len(text) > 500 or any(ord(c) < 32 or ord(c) == 127 for c in text):
        raise ValueError('短语须为 1–500 个字符，暂不支持换行或制表符')
    dynamic=value.get('dynamic',False)
    if type(dynamic) is not bool:raise ValueError('短语类型无效')
    if dynamic:
        remaining=re.sub(r'\{(?:YYYY|MM|M|DD|D|HH|mm|ss|W)\}', '', text)
        if '{' in remaining or '}' in remaining:raise ValueError('模板仅支持 {YYYY}、{MM}、{M}、{DD}、{D}、{HH}、{mm}、{ss}、{W}')
    enabled=value.get('enabled',True)
    if type(enabled) is not bool:raise ValueError('启用状态无效')
    extra={} if enabled else {'enabled':False}
    group=normalize_phrase_group(value.get('group',''))
    if group:extra['group']=group
    if dynamic:
        offset=value.get('date_offset',0);label=value.get('label','模板')
        if type(offset) is not int or not -366<=offset<=366:raise ValueError('日期偏移须为 -366 至 366 天')
        if label not in ('模板','日期','时间','落款'):raise ValueError('模板标签无效')
        if offset:extra['date_offset']=offset
        if label!='模板':extra['label']=label
    return dict(code=code,text=text,**({'dynamic':True} if dynamic else {}),**extra)

def phrase_preview(value, now=None):
    from datetime import datetime,timedelta
    row=normalize_phrase(value)
    if not row.get('dynamic'):return {'text':row['text']}
    now=(now or datetime.now())+timedelta(days=row.get('date_offset',0))
    values={'W':'星期'+'一二三四五六日'[now.weekday()],'YYYY':f'{now.year:04d}','MM':f'{now.month:02d}','M':str(now.month),'DD':f'{now.day:02d}','D':str(now.day),'HH':f'{now.hour:02d}','mm':f'{now.minute:02d}','ss':f'{now.second:02d}'}
    return {'text':re.sub(r'\{([A-Za-z]+)\}',lambda m:values[m[1]],row['text'])}

def full_spelling_rules():
    # Read only the bundled speller's YAML list; preserve its spelling corrections.
    source=(ROOT/'vendor/rime-ice/rime_ice.schema.yaml').read_text()
    section=source.split('\nspeller:\n',1)[1]
    section=re.split(r'\n[^ #\s][^\n]*:',section,1)[0]
    rules=[line.strip()[2:].split(' #',1)[0].strip() for line in section.splitlines() if line.startswith('    - ')]
    if not any(x.startswith('abbrev/') for x in rules):raise ValueError('基础简拼规则无法识别，请更新基础词库')
    return [x for x in rules if not x.startswith('abbrev/') and x not in ('erase/^hm$/','erase/^m$/','erase/^n$/','erase/^ng$/')]

def save_phrase(data):
    s = state(); r = normalize_phrase(data)
    old = data.get('old') or r['code']
    if not data.get('old') and any(x['code']==r['code'] for x in s['phrases']):raise ValueError('这个缩写已存在，请编辑原短语')
    if old != r['code'] and any(x['code'] == r['code'] for x in s['phrases']):
        raise ValueError('这个缩写已存在，请选择其他缩写')
    if not data.get('delete') and r.get('enabled',True) and any(x.get('pinned') and x['pinyin'].replace(' ', '').lower() == r['code'] for x in s['personal']):
        raise ValueError('这个缩写与固定首选冲突，请更换缩写或取消固定首选')
    if data.get('delete'):
        import personal_data
        for item in s['phrases']:
            if item['code']==old:personal_data.discard(s,'phrase',item)
    s['phrases'] = [x for x in s['phrases'] if x['code'] != old]
    if not data.get('delete'): s['phrases'].append(r)
    save(s)
    return {'ok': True}

def generate(target, s):
    target.mkdir(parents=True, exist_ok=True)
    (target/'lua').mkdir(exist_ok=True)
    shutil.copy2(ROOT/'runtime/kongime_quick.lua',target/'lua/kongime_quick.lua')
    shutil.copy2(ROOT/'runtime/kongime_templates.lua',target/'lua/kongime_templates.lua')
    rows = active_rows(s)
    # Preserve legacy special codes in the manager; exclude them until the user supplies usable pinyin.
    usable = [r for r in rows if not re.search(r'[0-9#]', r['pinyin'])]
    body = '\n'.join('%s\t%s\t%d' % (r['word'], r['pinyin'], r['weight']) for r in usable)
    (target / 'qingyan_personal.dict.yaml').write_text('---\nname: qingyan_personal\nversion: "1.0"\nsort: by_weight\n...\n' + body + '\n')
    (target / 'qingyan.dict.yaml').write_text('---\nname: qingyan\nversion: "1.0"\nsort: by_weight\nimport_tables:\n  - qingyan_personal\n  - cn_dicts/8105\n  - cn_dicts/base\n  - cn_dicts/ext\n...\n')
    # Inherit the verified upstream speller and punctuation; replace optional processors.
    schema = '''schema:
  schema_id: qingyan
  name: KongIME全拼
  version: "0.1.0"
  dependencies: []
switches:
  - name: ascii_mode
    states: [中, A]
  - name: ascii_punct
    states: [。，, ．，]
engine:
  processors: [ascii_composer, recognizer, key_binder, speller, punctuator, selector, navigator, express_editor]
  segmentors: [ascii_segmentor, matcher, abc_segmentor, punct_segmentor, fallback_segmentor]
  translators: [punct_translator, table_translator@qingyan_pin, table_translator@kongime_phrase, lua_translator@*kongime_templates, script_translator]
  filters: [lua_filter@*kongime_quick, uniquifier]
translator:
  dictionary: qingyan
  user_dict: qingyan
  enable_user_dict: LEARNING
  enable_sentence: true
  enable_completion: true
  spelling_hints: 0
  comment_format: ["xform/.*//"]
speller:
  __include: rime_ice.schema:/speller
  __patch:
    algebra/+:
      - xlit/ABCDEFGHIJKLMNOPQRSTUVWXYZ/abcdefghijklmnopqrstuvwxyz/
  alphabet: zyxwvutsrqponmlkjihgfedcba
  initials: zyxwvutsrqponmlkjihgfedcba
ascii_composer:
  __include: default:/ascii_composer
punctuator:
  __include: default:/punctuator
editor:
  __include: rime_ice.schema:/editor
key_binder:
  bindings:
    - {when: has_menu, accept: minus, send: Page_Up}
    - {when: has_menu, accept: equal, send: Page_Down}
recognizer:
  import_preset: default
  patterns:
    uppercase: "[A-Z][-_+.'0-9A-Za-z]*$"
'''.replace('LEARNING', str(s['settings']['learning']).lower())
    settings=normalize_settings(s['settings'])
    schema=schema.replace('  - name: ascii_punct\n', '  - name: ascii_punct\n    reset: '+str(int(settings['ascii_punctuation']))+'\n')
    bindings=''
    for action,send in [('previous','Page_Up'),('next','Page_Down')]:
        key=settings['shortcuts'][action]
        if key!='none':bindings+='    - {when: has_menu, accept: '+key+', send: '+send+'}\n'
    bindings+='    - {when: always, accept: Control+period, toggle: ascii_punct}\n'
    schema=schema.replace('    - {when: has_menu, accept: minus, send: Page_Up}\n    - {when: has_menu, accept: equal, send: Page_Down}\n',bindings)
    # Explicit settings avoid depending on future preset changes.
    pos=schema.index('recognizer:')
    schema=schema[:pos]+'''recognizer:
  patterns:
'''+('    uppercase: "[A-Z][-_+.\'0-9A-Za-z]*$"\n' if settings['direct_english'] else '    uppercase: "^$"\n')
    schema+=('    email: "^[A-Za-z][-_.0-9A-Za-z]*@.*$"\n    url: "^(www[.]|https?:|ftp[.:]|mailto:|file:).*$|^[a-z]+[.][-_0-9A-Za-z.]*$"\n' if settings['recognize_addresses'] else '    email: "^$"\n    url: "^$"\n')
    rules = [rule for key in normalize_fuzzy(s.get('fuzzy', [])) for rule in FUZZY_RULES[key]]
    schema = schema.replace('      - xlit/ABCDEFGHIJKLMNOPQRSTUVWXYZ/abcdefghijklmnopqrstuvwxyz/', '      - xlit/ABCDEFGHIJKLMNOPQRSTUVWXYZ/abcdefghijklmnopqrstuvwxyz/' + ''.join('\n      - ' + rule for rule in rules))
    if not settings['abbreviation']:
        import json
        original='  __patch:\n    algebra/+:\n      - xlit/ABCDEFGHIJKLMNOPQRSTUVWXYZ/abcdefghijklmnopqrstuvwxyz/'+''.join('\n      - '+rule for rule in rules)
        algebra=full_spelling_rules()+['xlit/ABCDEFGHIJKLMNOPQRSTUVWXYZ/abcdefghijklmnopqrstuvwxyz/']+rules
        schema=schema.replace(original,'  __patch:\n    algebra: '+json.dumps(algebra,ensure_ascii=False))
        schema=schema.replace('  enable_completion: true','  enable_completion: false')
    else:
        # Normal lowercase consonant spellings mask Rime's abbreviated initials.
        # Imported Latin letters must remain abbreviation spellings. a/e/o already
        # exist as complete Mandarin syllables, so their aliases must be normal.
        latin_rules=[('xform' if c in 'AEO' else 'abbrev')+'/^'+c+'$/'+c.lower()+'/' for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ']
        latin_rules.append('erase/^[A-Z]$/')
        schema=schema.replace('      - xlit/ABCDEFGHIJKLMNOPQRSTUVWXYZ/abcdefghijklmnopqrstuvwxyz/', '\n'.join('      - '+rule for rule in latin_rules))
    if s['settings'].get('show_pinyin',True):
        schema=schema.replace('spelling_hints: 0','spelling_hints: 99\n  always_show_comments: true').replace('  comment_format: [\"xform/.*//\"]','')
    (target / 'qingyan.schema.yaml').write_text(schema)
    pins = {}
    for r in s['personal']:
        if r.get('pinned') and not re.search(r'[0-9#]', r['pinyin']):
            pins[r['pinyin'].replace(' ', '').lower()] = r['word']
    with (target / 'qingyan.schema.yaml').open('a') as f:
        f.write("qingyan_pin:\n  dictionary: \"\"\n  user_dict: qingyan_pins\n  db_class: stabledb\n  enable_completion: false\n  enable_sentence: false\n  initial_quality: 100000\n")
    (target / 'qingyan_pins.txt').write_text('\n'.join('%s\t%s\t1' % (word, code) for code, word in pins.items()) + '\n')
    phrases = [normalize_phrase(x) for x in s.get('phrases', []) if x.get('enabled',True)]
    with (target / 'qingyan.schema.yaml').open('a') as f:
        f.write('kongime_phrase:\n  dictionary: ""\n  user_dict: kongime_phrases\n  db_class: stabledb\n  enable_completion: false\n  enable_sentence: false\n  initial_quality: 90000\n')
    (target / 'kongime_phrases.txt').write_text(''.join('%s\t%s\t1\n' % (r['text'], r['code']) for r in phrases if not r.get('dynamic')))
    (target/'kongime_templates.tsv').write_text(''.join(r['code']+'\t'+r['text']+'\t'+str(r.get('date_offset',0))+'\t'+r.get('label','模板')+'\n' for r in phrases if r.get('dynamic')))
    (target / 'default.custom.yaml').write_text('patch:\n  schema_list:\n    - schema: qingyan\n  menu/page_size: %d\n' % s['settings']['page_size'])
    appearance=normalize_appearance(s.get('appearance',{}))
    light='kongime_light' if appearance['theme']!='dark' else 'kongime_dark'
    dark='kongime_dark' if appearance['theme']!='light' else 'kongime_light'
    config = 'patch:\n'
    values={'kongime/language_hint':settings['language_hint'],'kongime/pair_chinese':settings['pair_chinese'],'kongime/pair_english':settings['pair_english'],'kongime/candidate_gap':appearance['candidate_gap'],'kongime/expand_key':settings['shortcuts']['expand'],'kongime/pin_key':settings['shortcuts']['pin'],'style/color_scheme':light,'style/color_scheme_dark':dark,
            'style/candidate_list_layout':appearance['layout'],'style/text_orientation':'horizontal',
            'style/inline_preedit':True,'style/font_face':'PingFang SC','style/font_point':appearance['font_size'],
            'style/label_font_point':max(10,appearance['font_size']-5),'style/corner_radius':8,
            'style/border_height':6,'style/border_width':9,'style/shadow_size':0,'style/show_paging':False,
            'style/candidate_format':'[label] [candidate] [comment]' if s['settings'].get('show_pinyin',True) else '[label] [candidate]'}
    # JSON scalar encoding is valid YAML and keeps names/values out of YAML syntax.
    import json
    for key,value in values.items():config+='  '+json.dumps(key)+': '+json.dumps(value,ensure_ascii=False)+'\n'
    themes={
        'kongime_light':{'name':'KongIME 浅色','back_color':'0xf6f9fa','candidate_text_color':'0x282c26','label_color':'0x838a85','hilited_candidate_back_color':'0xe8f1ed','hilited_candidate_text_color':'0x456d52','hilited_candidate_label_color':'0x456d52'},
        'kongime_dark':{'name':'KongIME 深色','back_color':'0x20251e','candidate_text_color':'0xe1e8e4','label_color':'0x8fa095','hilited_candidate_back_color':'0x2a382c','hilited_candidate_text_color':'0x709e86','hilited_candidate_label_color':'0x709e86'}}
    for name,theme in themes.items():
        config+='  "preset_color_schemes/'+name+'":\n'
        for key,value in theme.items():config+='    '+key+': '+json.dumps(value,ensure_ascii=False)+'\n'
    for pref in s.get('app_preferences',[]):
        pref=normalize_app_preference(pref)
        config+='  '+json.dumps('kongime/remember_apps/'+pref['id'])+': '+str(pref['mode']=='remember').lower()+'\n'
        config+='  '+json.dumps('kongime/pair_disabled_apps/'+pref['id'])+': '+str(pref.get('disable_pairs',False)).lower()+'\n'
        if pref['mode']!='default':config+='  '+json.dumps('app_options/'+pref['id']+'/ascii_mode')+': '+str(pref['mode']=='english').lower()+'\n'
    (target / 'squirrel.custom.yaml').write_text(config)
    return len(usable)

def make_bundle(target, s):
    vendor = ROOT / 'vendor/rime-ice'
    if not (vendor / 'rime_ice.schema.yaml').exists():
        raise ValueError('雾凇基础文件尚未就绪')
    shutil.copytree(vendor, target, dirs_exist_ok=True)
    return generate(target, s)

def apply_config():
    s = state()
    # Keep a full timestamped copy, including user dictionaries, before first writes.
    DATA.mkdir(parents=True, exist_ok=True)
    backup = None
    if RIME.exists():
        backup = DATA / 'backups' / (time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
        shutil.copytree(RIME, backup, symlinks=True)
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / 'Rime'
        count = make_bundle(target, s)
        # Existing configuration files not owned by this app are backed up, never erased.
        RIME.mkdir(parents=True, exist_ok=True)
        for source in target.rglob('*'):
            if source.is_file():
                dest = RIME / source.relative_to(target)
                if any(RIME.joinpath(*source.relative_to(target).parts[:i]).is_symlink() for i in range(len(source.relative_to(target).parts) + 1)):
                    raise ValueError('目标配置含符号链接，请在普通 Rime 文件夹中部署')
                dest.parent.mkdir(parents=True, exist_ok=True)
                fd, name = tempfile.mkstemp(dir=str(dest.parent))
                os.close(fd)
                shutil.copyfile(source, name)
                os.replace(name, dest)
    s['applied'] = s['revision']
    s['last_backup'] = str(backup) if backup else None
    atomic_json(DATA / 'state.json', s)
    return {'count': count, 'backup': str(backup) if backup else None}
