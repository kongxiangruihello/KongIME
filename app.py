import quick
import phrase_tools
import profile_backup
import cloud_client
import library_tools
import personal_data
import local_snapshots
import upgrade_check
import restore_review
import learning
import complete_backup
#!/usr/bin/env python3
"""Loopback-only management app with session-bound mutation protection."""
import argparse
import base64
import io
import json
import mimetypes
import secrets
import subprocess
import threading
import webbrowser
import zipfile
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import core
import workflow
import jobs

TOKEN = secrets.token_urlsafe(32)
PENDING = {}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def send(self, code, data, kind='application/json; charset=utf-8', filename=None):
        if isinstance(data, (dict, list)): data = json.dumps(data, ensure_ascii=False).encode()
        if isinstance(data, str): data = data.encode()
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if filename: self.send_header('Content-Disposition', 'attachment; filename="%s"' % filename)
        self.end_headers()
        self.wfile.write(data)
    def host_ok(self):
        return self.headers.get('Host') == '127.0.0.1:%d' % self.server.server_port
    def do_GET(self):
        if not self.host_ok(): return self.send(403, {'error': 'Host rejected'})
        u = urlparse(self.path)
        try:
            profile_backup.recover()
            if u.path == '/api/phrases-export':return self.send(200,phrase_tools.export(parse_qs(u.query,keep_blank_values=True).get('group',[None])[0]),filename='KongIME-phrases.json')
            if u.path == '/api/profile-backup':return self.send(200,profile_backup.snapshot(),filename='KongIME-profile.json')
            if u.path == '/api/restore-report':return self.send(200,{'report':restore_review.last_report()})
            if u.path == '/api/upgrade-check':return self.send(200,upgrade_check.read())
            if u.path == '/api/snapshots':return self.send(200,local_snapshots.list_snapshots())
            if u.path == '/api/complete-status':return self.send(200,complete_backup.status())
            if u.path == '/api/complete-download':return self.send(200,complete_backup.value(),filename='KongIME-complete.json')
            if u.path == '/api/complete-before':return self.send(200,complete_backup.value(before=True),filename='KongIME-before-restore.json')
            if u.path == '/api/learning-status':return self.send(200,learning.status())
            if u.path == '/api/learning-download':return self.send(200,learning.export_value(),filename='KongIME-learning.json')
            if u.path == '/api/diagnostics':return self.send(200,personal_data.diagnostics())
            if u.path == '/api/icloud':return self.send(200,personal_data.icloud_status())
            if u.path == '/api/library-content':return self.send(200,library_tools.content(parse_qs(u.query).get('id',[''])[0]))
            if u.path == '/api/library-export':return self.send(200,library_tools.export(parse_qs(u.query).get('id',[''])[0]),'text/plain; charset=utf-8','KongIME-dictionary.txt')
            if u.path == '/api/cloud-status':return self.send(200,cloud_client.client.status())
            if u.path == '/api/cloud-versions':return self.send(200,cloud_client.client.versions())
            if u.path == '/api/sync-status':return self.send(200,{'connected':False,'can_rollback':(core.DATA/'before-profile.json').exists(),'learning_included':False})
            if u.path == '/api/state':
                s = core.state()
                s.update({'token': TOKEN, 'installed': any(p.exists() for p in [Path('/Library/Input Methods/Squirrel.app'), Path.home() / 'Library/Input Methods/Squirrel.app']), 'ready': (core.ROOT / 'vendor/rime-ice/rime_ice.schema.yaml').exists(), 'data_path': str(core.DATA), 'rime_path': str(core.RIME)})
                return self.send(200, s)
            if u.path == '/api/quick-preferences':return self.send(200,quick.read(core.RIME)[0])
            if u.path == '/api/quick-backup':return self.send(200,{'format':'kongime-quick-v1','preferences':quick.read(core.RIME)[0]},filename='KongIME-quick-backup.json')
            if u.path == '/api/history':
                rows=[]
                for kind,entries in [('settings',core.change_history()),('quick',quick.read(core.RIME)[1])]:
                    for i,x in enumerate(entries):rows.append({'kind':kind,'id':x['id'],'time':x['time'],'label':x['label'],'can_undo':i==len(entries)-1 and (kind=='quick' or x['revision']==core.state()['revision'])})
                return self.send(200,sorted(rows,key=lambda x:x['time'],reverse=True))
            if u.path == '/api/apps': return self.send(200, workflow.installed_apps())
            if u.path == '/api/job': return self.send(200, jobs.status())
            if u.path == '/api/status': return self.send(200, workflow.status())
            if u.path == '/api/migrations': return self.send(200, workflow.legacy_candidates())
            if u.path == '/api/review': return self.send(200, core.review_rows(core.state()))
            if u.path == '/api/import-backup':
                receipt = next((x for x in core.state()['imports'] if x['id'] == parse_qs(u.query).get('id',[''])[0]), None)
                if not receipt or not receipt.get('backup'): raise ValueError('这份导入前备份不在当前设备上')
                name = Path(receipt['backup']).name
                return self.send(200, (core.DATA/'import-backups'/name).read_bytes(), 'application/json', 'KongIME-before-import.json')
            if u.path == '/api/words':
                q = parse_qs(u.query)
                result=core.search_words(core.state(), q.get('q',[''])[0], q.get('scope',['all'])[0], q.get('order',['pinyin'])[0], q.get('page',['0'])[0])
                return self.send(200, result)
            if u.path == '/api/export':
                import tempfile
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp) / 'Rime'
                    core.make_bundle(root, core.state())
                    buf = io.BytesIO()
                    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
                        for p in root.rglob('*'):
                            if p.is_file(): z.write(p, 'Rime/' + str(p.relative_to(root)))
                return self.send(200, buf.getvalue(), 'application/zip', 'Qingyan-Rime.zip')
            if u.path == '/api/backup':
                s = core.state()
                export = {'format': 'qingyan-backup-v1', 'state': s, 'libraries': {x['id']: core.lib_rows(x) for x in s['libraries']}}
                return self.send(200, json.dumps(export, ensure_ascii=False), 'application/json', 'Qingyan-backup.json')
            name = {'/': 'index.html', '/app.js': 'app.js', '/close-flow.js':'close-flow.js', '/style.css': 'style.css'}.get(u.path)
            if name:
                return self.send(200, (core.ROOT / 'web' / name).read_bytes(), mimetypes.guess_type(name)[0] + '; charset=utf-8')
            self.send(404, {'error': 'Not found'})
        except Exception as e: self.send(400, {'error': str(e)})
    def do_POST(self):
        origin = self.headers.get('Origin')
        expected = 'http://127.0.0.1:%d' % self.server.server_port
        if not self.host_ok() or self.headers.get('X-Qingyan-Token') != TOKEN or (origin and origin != expected):
            return self.send(403, {'error': '请刷新本地管理页后重试'})
        try:
            n = int(self.headers.get('Content-Length', '0'))
            limit=complete_backup.MAX_BYTES+4096 if urlparse(self.path).path=='/api/complete-preview' else 46*1024*1024
            if n <= 0 or n > limit: raise ValueError('文件超过大小限制')
            data = json.loads(self.rfile.read(n))
            path = urlparse(self.path).path
            if jobs.status()['running']: raise ValueError('正在处理配置或选择文件夹，请等待完成后再修改')
            profile_backup.recover()
            s = core.state()
            if path == '/api/phrase-group':return self.send(200,phrase_tools.group_update(data))
            if path == '/api/phrase-organize':return self.send(200,phrase_tools.organize(data))
            if path == '/api/phrase-check':return self.send(200,phrase_tools.check_code(data))
            if path == '/api/phrase-candidate':return self.send(200,phrase_tools.candidate(data))
            if path == '/api/phrases-preview':return self.send(200,phrase_tools.preview(data['backup']))
            if path == '/api/phrases-import':return self.send(200,phrase_tools.confirm(data))
            if path == '/api/phrase-toggle':return self.send(200,phrase_tools.toggle(data))
            if path == '/api/preview':
                raw = base64.b64decode(data['data'], validate=True)
                rows, duplicates = core.parse_import(raw, data['name'])
                pid = secrets.token_hex(12)
                PENDING.clear()
                PENDING[pid] = (raw, data['name'])
                return self.send(200, {'id': pid, 'count': len(rows), 'duplicates': duplicates, 'rows': rows[:8], 'scel': core.is_scel(raw, data['name']), 'sgpu': raw.startswith(b'SGPU'), 'conflicts': personal_data.conflicts(rows), 'review': sum(any(c in '0123456789#' for c in r['pinyin']) for r in rows)})
            if path == '/api/import':
                if data['id'] not in PENDING: raise ValueError('预览已过期，请重新选择文件')
                raw, name = PENDING[data['id']]
                return self.send(200, core.import_library(raw, name, data.get('policy','higher')))
            if path == '/api/library':
                lib = next((x for x in s['libraries'] if x['id'] == data['id']), None)
                if not lib: raise ValueError('词库不存在')
                if data.get('delete'): personal_data.discard(s,'library',lib);s['libraries'].remove(lib)
                else: lib['enabled'] = bool(data['enabled'])
                core.save(s)
            elif path == '/api/word':
                r = core.normalize(data['word'], data['pinyin'], data['weight'])
                r['pinned'] = bool(data.get('pinned'))
                if r['pinned'] and core.needs_review(r): raise ValueError('请先在待处理页面修正拼音')
                if r['pinned'] and any(x.get('enabled',True) and x['code'] == r['pinyin'].replace(' ', '').lower() for x in s['phrases']): raise ValueError('该拼音与常用短语缩写冲突，请先修改短语缩写')
                old = data.get('old') or {'word': r['word'], 'pinyin': r['pinyin']}
                if data.get('delete'):
                    for item in s['personal']:
                        if (item['word'],item['pinyin'])==(old['word'],old['pinyin']):personal_data.discard(s,'word',item)
                s['personal'] = [x for x in s['personal'] if (x['word'], x['pinyin']) not in ((old['word'], old['pinyin']), (r['word'], r['pinyin']))]
                if not data.get('delete'):
                    if r['pinned']:
                        for x in s['personal']:
                            if x['pinyin'].replace(' ', '').lower() == r['pinyin'].replace(' ', '').lower(): x['pinned'] = False
                    s['personal'].append(r)
                core.save(s)
            elif path == '/api/trash-restore':return self.send(200,personal_data.restore(data['id']))
            elif path == '/api/scene':return self.send(200,personal_data.scene(data))
            elif path == '/api/open-icloud':
                root=personal_data.icloud_root().parent
                root.mkdir(parents=True,exist_ok=True)
                subprocess.run(['/usr/bin/open',str(root)],check=True,timeout=10)
                return self.send(200,{'ok':True})
            elif path == '/api/restore-preview':return self.send(200,restore_review.preview(data))
            elif path == '/api/restore-confirm':return self.send(200,restore_review.confirm(data['id']))
            elif path == '/api/upgrade-check':return self.send(200,upgrade_check.retry(workflow.VERSION))
            elif path == '/api/snapshot-create':return self.send(200,local_snapshots.create('手动保存'))
            elif path == '/api/snapshot-restore':return self.send(200,local_snapshots.restore(data['name']))
            elif path == '/api/complete-preview':return self.send(200,complete_backup.preview(data['backup']))
            elif path == '/api/complete-export':return self.send(200,learning.request('complete-export'))
            elif path == '/api/complete-restore':return self.send(200,complete_backup.confirm(data['id']))
            elif path == '/api/learning-preview':
                rows=learning.validate(data['backup'])
                return self.send(200,{'count':len(rows),'rows':rows[:8]})
            elif path == '/api/learning-export':return self.send(200,learning.request('export'))
            elif path == '/api/learning-restore':return self.send(200,learning.request('restore',data['backup']))
            elif path == '/api/learning-rollback':return self.send(200,learning.request('rollback'))
            elif path == '/api/icloud-save':return self.send(200,personal_data.icloud_save())
            elif path == '/api/icloud-restore':return self.send(200,personal_data.icloud_restore(data['name']))
            elif path == '/api/manual-library':return self.send(200,library_tools.save(data))
            elif path == '/api/configuration':
                preferences=core.normalize_settings(data['settings']);appearance=core.normalize_appearance(data['appearance']);fuzzy=core.normalize_fuzzy(data['fuzzy'])
                changed = s['settings'] != preferences or s['appearance'] != appearance or s['fuzzy'] != fuzzy
                if changed:
                    s.update(settings=preferences,appearance=appearance,fuzzy=fuzzy);core.save(s)
                return self.send(200,{'ok':True,'changed':changed})
            elif path == '/api/settings':
                count = int(data['page_size'])
                if count not in (3, 5, 7, 9): raise ValueError('候选数量须为 3、5、7 或 9')
                s['settings'].update(page_size=count,learning=bool(data['learning']))
                core.save(s)
            elif path == '/api/apply':
                return self.send(200, jobs.start('deploy'))
            elif path == '/api/recover': return self.send(200, jobs.start('recover'))
            elif path == '/api/quick-preference':
                return self.send(200,quick.change(data['action'],data['code'],data['word'],root=core.RIME))
            elif path == '/api/quick-restore':
                backup=data['backup']
                if not isinstance(backup,dict) or backup.get('format')!='kongime-quick-v1':raise ValueError('请选择快捷排序备份文件')
                return self.send(200,quick.change('restore',root=core.RIME,replacement=backup.get('preferences')))
            elif path == '/api/undo-change':
                if data['kind']=='quick':return self.send(200,quick.change('undo',root=core.RIME,event=data['id']))
                return self.send(200,core.undo_change(data['id']))
            elif path == '/api/fuzzy':
                s['fuzzy']=core.normalize_fuzzy(data['fuzzy']);core.save(s)
            elif path == '/api/appearance':
                s['appearance']=core.normalize_appearance(data);core.save(s)
            elif path == '/api/app-preference':
                pref=core.normalize_app_preference(data)
                s['app_preferences']=[x for x in s['app_preferences'] if x['id']!=pref['id']]
                if not data.get('delete'):s['app_preferences'].append(pref)
                core.save(s)
            elif path == '/api/phrase-preview': return self.send(200, core.phrase_preview(data))
            elif path == '/api/phrase': return self.send(200, core.save_phrase(data))
            elif path == '/api/pick-directory': return self.send(200, jobs.start('pick'))
            elif path == '/api/inspect-directory': return self.send(200, workflow.select_directory(data['path']))
            elif path == '/api/undo-import': return self.send(200, core.undo_import(data['id']))
            elif path == '/api/resolve': return self.send(200, core.resolve_word(data))
            elif path == '/api/setup': return self.send(200, workflow.setup(data['action']))
            elif path == '/api/migrate': return self.send(200, workflow.migrate(data['id']))
            elif path == '/api/cloud-configure':return self.send(200,cloud_client.client.configure(data['url']))
            elif path == '/api/cloud-code':return self.send(200,cloud_client.client.send_code(data['email']))
            elif path == '/api/cloud-login':return self.send(200,cloud_client.client.login(data['email'],data['code']))
            elif path == '/api/cloud-logout':return self.send(200,cloud_client.client.logout())
            elif path == '/api/cloud-upload':return self.send(200,cloud_client.client.upload(data['revision']))
            elif path == '/api/cloud-restore':return self.send(200,cloud_client.client.restore(data['revision']))
            elif path == '/api/profile-restore':return self.send(200,profile_backup.restore(data['backup']))
            elif path == '/api/profile-rollback':return self.send(200,profile_backup.rollback())
            elif path == '/api/restore':
                value = data['backup']
                if value.get('format') != 'qingyan-backup-v1': raise ValueError('不是轻言备份文件')
                incoming = value['state']
                # Validate every entry and rebuild ids; never trust paths in imported backups.
                libs = []
                idmap = {}
                all_rows = []
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
                extras=personal_data.normalize_extras(incoming)
                core.atomic_json(core.DATA / 'before-restore.json', {'format': 'qingyan-backup-v1', 'state': s, 'libraries': {x['id']: core.lib_rows(x) for x in s['libraries']}})
                for lid, rows in all_rows: core.atomic_json(core.DATA / 'libraries' / (lid+'.json'), rows)
                s.update(extras)
                s.update({'fuzzy':core.normalize_fuzzy(incoming.get('fuzzy',[])), 'appearance':appearance,'app_preferences':app_preferences,'phrases':phrases, 'resolutions':resolutions, 'imports':imports, 'libraries': libs, 'personal': personal, 'settings': core.normalize_settings(settings)})
                core.save(s)
            elif path == '/api/quit':
                self.send(200, {'ok': True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            else: return self.send(404, {'error': 'Not found'})
            self.send(200, {'ok': True})
        except Exception as e: self.send(400, {'error': str(e)})

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=18761)
    parser.add_argument('--no-open', action='store_true')
    args = parser.parse_args()
    profile_backup.recover()
    local_snapshots.on_upgrade(workflow.VERSION)
    server = HTTPServer(('127.0.0.1', args.port), Handler)
    url = 'http://127.0.0.1:%d' % server.server_port
    print(url, flush=True)
    if not args.no_open: webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
