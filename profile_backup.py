"""Portable configuration snapshots and recoverable local restore transactions."""
import base64, fcntl, json, os, secrets, tempfile
from contextlib import contextmanager
from pathlib import Path
import core, quick, personal_data
FORMAT = 'kongime-profile-v1'

@contextmanager
def locked():
    core.RIME.mkdir(parents=True, exist_ok=True)
    with (core.RIME/'kongime_quick.lock').open('a') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield

def prepare(value):
    s=core.state()
    if value.get('format') != 'qingyan-backup-v1': raise ValueError('不是轻言备份文件')
    incoming = value['state']
    # Validate every entry and rebuild ids; never trust paths in imported backups.
    libs = []
    idmap = {}
    all_rows = []
    if len(incoming['libraries'])>1000 or len({x['id'] for x in incoming['libraries']})!=len(incoming['libraries']): raise ValueError('词库数量或标识无效')
    for lib in incoming['libraries']:
        rows = [core.normalize(r['word'], r['pinyin'], r['weight']) for r in value['libraries'][lib['id']]]
        if len(rows) > core.MAX_ENTRIES: raise ValueError('词库过大')
        lid = secrets.token_hex(16)
        idmap[lib['id']] = lid
        libs.append({'id': lid, 'name': str(lib['name'])[:200], 'hash': str(lib['hash']), 'enabled': bool(lib['enabled']), 'manual': bool(lib.get('manual',False)), 'conflict_policy': lib.get('conflict_policy') if lib.get('conflict_policy') in ('local','incoming','higher') else None, 'count': len(rows), 'review': sum(any(c in '0123456789#' for c in r['pinyin']) for r in rows)})
        all_rows.append((lid, rows))
    personal = []
    for r in incoming['personal']:
        row = core.normalize(r['word'], r['pinyin'], r['weight'])
        row['pinned'] = bool(r.get('pinned'))
        personal.append(row)
    core.normalize_fuzzy(incoming.get('fuzzy',[]))
    settings = incoming['settings']
    if settings['page_size'] not in (3,5,7,9): raise ValueError('备份设置无效')
    appearance=core.normalize_appearance(incoming.get('appearance',{}))
    app_preferences=[core.normalize_app_preference(x) for x in incoming.get('app_preferences',[])]
    phrases = [core.normalize_phrase(x) for x in incoming.get('phrases', [])]
    if len({x['code'] for x in phrases}) != len(phrases): raise ValueError('备份中有重复短语缩写')
    resolutions = []
    for item in incoming.get('resolutions', []):
        source = core.normalize(**{k:item['source'][k] for k in ('word','pinyin','weight')})
        decision = item['decision']
        if decision not in ('replace','ignore','keep'): raise ValueError('备份处理记录无效')
        out = {'source':source,'decision':decision}
        if decision == 'replace':
            r = item['replacement'];out['replacement'] = core.normalize(r['word'],r['pinyin'],r['weight'])
            if core.needs_review(out['replacement']): raise ValueError('备份修正编码无效')
        resolutions.append(out)
    imports = []
    for item in incoming.get('imports', []):
        if item.get('library_id') not in idmap: continue
        out = dict(item, id=idmap[item['library_id']], library_id=idmap[item['library_id']], backup=None)
        imports.append(out)
    s.update({'fuzzy':core.normalize_fuzzy(incoming.get('fuzzy',[])), 'appearance':appearance,'app_preferences':app_preferences,'phrases':phrases, 'resolutions':resolutions, 'imports':imports, 'libraries': libs, 'personal': personal, 'settings': core.normalize_settings(settings)})
    s.update(personal_data.normalize_extras(incoming))
    return s, all_rows

def snapshot():
    manager=core.backup_value()
    allowed=('trash','scenes','version','fuzzy','appearance','app_preferences','phrases','resolutions','imports','libraries','personal','settings')
    manager['state']={k:v for k,v in manager['state'].items() if k in allowed}
    manager['state']['imports']=[{k:v for k,v in x.items() if k in ('id','library_id','name','count','read','duplicates','overlap','usable','review','time','undone')} for x in manager['state'].get('imports',[])]
    return {'format': FORMAT, 'manager': manager, 'quick': quick.read(core.RIME)[0],
            'learning': {'included': False, 'reason': '自动学习词频尚未纳入迁移'}}

def target(key):
    if key == 'quick': return core.RIME/'kongime_quick.tsv'
    if key in ('state.json','changes.json','before-profile.json'): return core.DATA/key
    if key.startswith('libraries/') and len(key)==47 and all(c in '0123456789abcdef' for c in key[10:-5]) and key.endswith('.json'): return core.DATA/key
    raise ValueError('恢复日志路径无效')

def write_bytes(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f: f.write(value); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def recover():
    journal=core.DATA/'profile-transaction.json'
    if not journal.exists(): return
    with locked(): _recover()

def _recover():
    journal=core.DATA/'profile-transaction.json'
    if not journal.exists(): return
    records=json.loads(journal.read_text())
    decoded=[(target(k),None if v is None else base64.b64decode(v,validate=True)) for k,v in records.items()]
    for path,value in decoded:
        if value is None: path.unlink(missing_ok=True)
        else: write_bytes(path,value)
    journal.unlink()

def restore(value, expected=None):
    recover()
    if not isinstance(value,dict) or value.get('format')!=FORMAT: raise ValueError('请选择 KongIME 统一备份文件')
    if value.get('learning',{}).get('included') is not False: raise ValueError('此版本不能恢复自动学习词频')
    s,rows=prepare(value['manager'])
    prefs=quick.normalize_preferences(value['quick'])
    with locked():
        before=snapshot()
        if expected is not None:
            import hashlib
            actual=hashlib.sha256(json.dumps(before,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            if actual!=expected:raise ValueError("本机配置或快捷排序已变化，请重新预览恢复差异")
        keys=['state.json','changes.json','before-profile.json','quick']+['libraries/'+lid+'.json' for lid,_ in rows]
        records={k:base64.b64encode(target(k).read_bytes()).decode() if target(k).exists() else None for k in keys}
        journal=core.DATA/'profile-transaction.json'
        write_bytes(journal,json.dumps(records).encode())
        try:
            core.atomic_json(core.DATA/'before-profile.json',before)
            for lid,entries in rows: core.atomic_json(target('libraries/'+lid+'.json'),entries)
            s['revision']=core.state()['revision']+1; s['applied']=-1
            core.atomic_json(core.DATA/'state.json',s)
            core.atomic_json(core.DATA/'changes.json',[])
            write_bytes(target('quick'),''.join('P\t{code}\t{word}\t{mode}\n'.format(**x) for x in prefs).encode())
            journal.unlink()
        except Exception:
            _recover()
            raise
    return {'ok':True}

def rollback():
    path=core.DATA/'before-profile.json'
    if not path.exists(): raise ValueError('还没有可回退的统一恢复记录')
    return restore(json.loads(path.read_text()))
