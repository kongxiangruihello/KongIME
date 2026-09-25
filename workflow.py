"""Installation, verified deployment and data migration for KongIME 0.2."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import time
import core

VERSION = '0.25.0'
CONFIGS = ('lua/kongime_templates.lua','kongime_templates.tsv','lua/kongime_quick.lua','qingyan.schema.yaml','qingyan.dict.yaml','qingyan_personal.dict.yaml','qingyan_pins.txt','kongime_phrases.txt','default.custom.yaml','squirrel.custom.yaml')
BUILT = ('qingyan.schema.yaml','qingyan.table.bin','qingyan.prism.bin','qingyan.reverse.bin')

def client():
    return next((p for p in (Path('/Library/Input Methods/Squirrel.app'),Path.home()/'Library/Input Methods/Squirrel.app') if p.exists()),None)

def file_hashes(root, names):
    result={}
    for name in names:
        p=root/name
        if not p.is_file():return None
        result[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    return result

def input_status():
    helper=core.ROOT/'ime-status'
    if not helper.exists():return {'enabled':None,'selected':None,'runtimes':None,'screen_count':None}
    try:
        return json.loads(subprocess.check_output([str(helper)],timeout=5))
    except (OSError,subprocess.SubprocessError,ValueError):return {'enabled':None,'selected':None,'runtimes':None,'screen_count':None}

def runtime_summary(installed, inputs):
    processes=inputs.get('runtimes')
    versions=sorted({x['version'] for x in (processes or []) if x.get('version')})
    unknown=sum(not x.get('version') for x in (processes or []))
    mismatch=bool(installed and any(v!=installed for v in versions))
    if processes is None:detail='运行版本暂无法检测'
    elif not processes:detail='未检测到运行实例，请切换到 KongIME 后刷新'
    elif unknown:detail='检测到无法识别版本的进程；旧版不支持运行版本报告'
    else:detail='正在运行：'+'、'.join(versions)
    restart=mismatch or bool(unknown and installed==VERSION)
    if restart:detail+='。请先保存其他工作，然后注销并重新登录 macOS，再刷新检查。'
    return {'running_versions':versions,'running_unknown':unknown,'runtime_detail':detail,'needs_restart':restart,'screen_count':inputs.get('screen_count')}

def status():
    s=core.state();app=client();brand=False;version=None;installed_version=None
    if app:
        try:
            info=plistlib.loads((app/'Contents/Info.plist').read_bytes())
            brand=info.get('CFBundleDisplayName')=='KongIME';version=info.get('CFBundleShortVersionString');installed_version=info.get('KongIMEVersion')
        except (OSError,ValueError):pass
    inputs=input_status()
    record={}
    try:record=json.loads((core.DATA/'deployment.json').read_text())
    except (OSError,ValueError):pass
    current=(record.get('version')==VERSION and record.get('revision')==s['revision'] and record.get('ok') is True
             and record.get('sources')==file_hashes(core.RIME,CONFIGS) and record.get('built')==file_hashes(core.RIME/'build',BUILT) and bool(record.get('built')))
    if not app:stage,label,action='missing','尚未安装输入法','install'
    elif not brand:stage,label,action='update','已安装鼠须管，可更新为 KongIME','install'
    elif not current:stage,label,action='deploy','等待部署最新词库与配置','deploy'
    elif inputs['enabled'] is False:stage,label,action='enable','配置已部署，尚未添加到系统输入法','keyboard'
    elif inputs['selected'] is False:stage,label,action='select','配置已部署，请切换到 KongIME','select'
    elif inputs['enabled'] is None:stage,label,action='unknown','配置已部署，请在下方试打确认','test'
    else:stage,label,action='ready','已部署并选中，可以试打','test'
    if record.get('ok') is False and record.get('revision')==s['revision'] and app:
        stage,label,action='failed','上次部署失败，请重试','deploy'
    runtime=runtime_summary(installed_version,inputs)
    if installed_version and installed_version!=VERSION:stage,label,action='update','已安装版本与设置版本不同，请安装对应客户端','install'
    elif runtime['needs_restart']:stage,label,action='restart','新版尚未确认接管，请注销并重新登录','restart'
    return dict(runtime,installed_version=installed_version,**{'stage':stage,'label':label,'action':action,'client_installed':bool(app),'branded':brand,'client_version':version,'manager_version':VERSION,'enabled':inputs['enabled'],'selected':inputs['selected'],'deployed':bool(current),'last_error':record.get('error'),'last_deploy':record.get('time'),'self_check':record.get('self_check'),'can_recover':(core.DATA/'last-good/record.json').is_file()})

def deploy(progress=lambda stage: None):
    app=client()
    if not app:raise ValueError('请先完成输入法安装，再部署词库')
    progress('backup')
    import local_snapshots
    local_snapshots.create('应用配置前')
    snapshot_good()
    result=core.apply_config();s=core.state()
    progress('compile')
    record={'version':VERSION,'revision':s['revision'],'ok':False,'time':time.strftime('%Y-%m-%d %H:%M:%S')}
    core.atomic_json(core.DATA/'deployment.json',record)
    try:
        run=subprocess.run([str(app/'Contents/MacOS/rime_deployer'),'--build',str(core.RIME),str(app/'Contents/SharedSupport'),str(core.RIME/'build')],capture_output=True,timeout=120)
        built=file_hashes(core.RIME/'build',BUILT)
        if run.returncode!=0 or not built:raise ValueError('词库编译未完成，请检查导入词条后重试；原学习记录仍保留')
        progress('check')
        import engine_check
        report=engine_check.run(app,s['settings']['abbreviation'])
        record.update(ok=True,self_check=report,sources=file_hashes(core.RIME,CONFIGS),built=built)
        core.atomic_json(core.DATA/'deployment.json',record)
    except (OSError,subprocess.SubprocessError,ValueError) as e:
        record['error']='部署失败：'+str(e);core.atomic_json(core.DATA/'deployment.json',record)
        raise ValueError(record['error'])
    progress('load')
    result['redeploy']=False
    try:
        subprocess.run([str(app/'Contents/MacOS/Squirrel'),'--reload'],capture_output=True,timeout=15,check=True)
        result['redeploy']=True
    except (OSError,subprocess.SubprocessError):pass
    local_snapshots.create('已成功部署的配置')
    result['compiled']=True
    result['self_check']=report
    result['message']='词库编译和拼音检查通过，'+('已请求输入法加载。' if result['redeploy'] else '请从输入法菜单重新部署后试打。')
    return result

def setup(action):
    if action=='restart':return {'message':'先保存其他应用中的工作，再从 Apple 菜单注销并重新登录。之后切换到 KongIME，点击检查状态；重新部署不能替换正在运行的旧程序。'}
    if action=='install':
        pkg=core.ROOT/'installer/安装KongIME.pkg'
        if not pkg.exists():raise ValueError('请打开下载包中的“安装KongIME.pkg”完成安装')
        subprocess.run(['/usr/bin/open',str(pkg)],check=True,timeout=10)
        return {'message':'安装程序已打开，请完成管理员授权。安装后可能需要注销并重新登录。'}
    if action=='keyboard':
        subprocess.run(['/usr/bin/open','x-apple.systempreferences:com.apple.Keyboard-Settings.extension'],check=True,timeout=10)
        return {'message':'键盘设置已打开：文本输入 → 编辑 → ＋，添加 KongIME。'}
    if action=='select':
        app=client()
        if not app:raise ValueError('尚未安装输入法')
        subprocess.run([str(app/'Contents/MacOS/Squirrel'),'--select-input-source'],check=True,timeout=15,capture_output=True)
        return {'message':'已请求切换到 KongIME，请在试打框输入 nihao。'}
    raise ValueError('未知设置操作')

def legacy_candidates():
    candidates=[];seen=set()
    direct=list(SELECTED.values())+[core.ROOT/'用户数据',core.ROOT/'data']
    if os.environ.get('KONGIME_LEGACY_DIR'):direct.insert(0,Path(os.environ['KONGIME_LEGACY_DIR']))
    # Search only known product folders, not arbitrary personal documents.
    for base in (Path.home()/'Downloads',Path.home()/'Desktop'):
        if not base.exists():continue
        for p in base.iterdir():
            if p.is_dir() and any(k in p.name.lower() for k in ('kongime','轻言','qingyan')):
                direct.extend([p/'用户数据',p/'data'])
                try:
                    for child in p.iterdir():
                        if child.is_dir() and not child.name.endswith('.app'):direct.append(child/'用户数据')
                except OSError:pass
    for p in direct:
        if p.resolve()==core.DATA.resolve() or str(p.resolve()) in seen:continue
        seen.add(str(p.resolve()));f=p/'state.json'
        try:
            value=json.loads(f.read_text())
            if not isinstance(value.get('libraries'),list) or not isinstance(value.get('personal'),list):continue
            if not value['libraries'] and not value['personal'] and not value.get('phrases'):continue
            candidates.append({'id':hashlib.sha256(str(p.resolve()).encode()).hexdigest()[:20],'path':str(p),'libraries':len(value['libraries']),'words':sum(x.get('count',0) for x in value['libraries']),'modified':time.strftime('%Y-%m-%d %H:%M',time.localtime(f.stat().st_mtime))})
        except (OSError,ValueError,TypeError):continue
    return candidates

def migrate(candidate_id):
    item=next((x for x in legacy_candidates() if x['id']==candidate_id),None)
    if not item:raise ValueError('旧版数据已变化，请刷新后重试')
    old=Path(item['path']);incoming=json.loads((old/'state.json').read_text())
    if candidate_id in SELECTED_DIGESTS and migration_digest(old,incoming)!=SELECTED_DIGESTS[candidate_id]:raise ValueError('旧目录数据已变化，请重新选择并核对数量')
    # Validate every record before writing, and only copy dictionary JSON files.
    payload=[]
    for lib in incoming['libraries']:
        if not re.fullmatch('[a-f0-9]{32}',lib['id']):raise ValueError('旧版词库标识无效')
        rows=json.loads((old/'libraries'/(lib['id']+'.json')).read_text())
        for row in rows:core.normalize(row['word'],row['pinyin'],row['weight'])
        lib['count']=len(rows)
        payload.append((lib['id'],rows))
    incoming['fuzzy']=core.normalize_fuzzy(incoming.get('fuzzy',[]))
    incoming['appearance']=core.normalize_appearance(incoming.get('appearance',{}))
    incoming['app_preferences']=[core.normalize_app_preference(x) for x in incoming.get('app_preferences',[])]
    incoming['phrases']=[core.normalize_phrase(x) for x in incoming.get('phrases',[])]
    for row in incoming['personal']:core.normalize(row['word'],row['pinyin'],row['weight'])
    if incoming['settings']['page_size'] not in (3,5,7,9):raise ValueError('旧版设置无效')
    for item in incoming.get('resolutions',[]):
        r=item['source'];core.normalize(r['word'],r['pinyin'],r['weight'])
        if item['decision'] not in ('replace','ignore','keep'):raise ValueError('旧版处理记录无效')
        if item['decision']=='replace':
            r=item['replacement'];core.normalize(r['word'],r['pinyin'],r['weight'])
            if core.needs_review(r):raise ValueError('旧版修正编码无效')
    for item in incoming.get('imports',[]):item['backup']=None
    core.atomic_json(core.DATA/'before-migration.json',core.backup_value())
    for lid,rows in payload:core.atomic_json(core.DATA/'libraries'/(lid+'.json'),rows)
    incoming.setdefault('resolutions',[]);incoming.setdefault('imports',[])
    incoming['revision']=max(core.state()['revision'],incoming.get('revision',0))+1;incoming['applied']=-1
    incoming['migrated_from']=str(old)
    core.atomic_json(core.DATA/'state.json',incoming)
    return {'message':'迁移完成：%d 个词库、%d 个个人词语、%d 个常用短语。原目录保留，请应用到输入法。' % (len(incoming['libraries']),len(incoming['personal']),len(incoming['phrases']))}


SELECTED = {}
SELECTED_DIGESTS = {}

def select_directory(path):
    parent = Path(path).expanduser().resolve()
    root = next((x for x in (parent, parent/'用户数据', parent/'data') if (x/'state.json').is_file()), None)
    if root is None: raise ValueError('该文件夹没有旧版数据，请选择包含 state.json 的“用户数据”文件夹')
    if root == core.DATA.resolve(): raise ValueError('这是当前数据目录，无需迁移')
    value = json.loads((root/'state.json').read_text())
    if not isinstance(value.get('libraries'),list) or not isinstance(value.get('personal'),list): raise ValueError('不是有效的旧版数据目录')
    total = 0
    for lib in value['libraries']:
        if not re.fullmatch('[a-f0-9]{32}',lib['id']):raise ValueError('词库标识无效')
        rows=json.loads((root/'libraries'/(lib['id']+'.json')).read_text())
        if len(rows)>core.MAX_ENTRIES:raise ValueError('词库过大')
        for r in rows:core.normalize(r['word'],r['pinyin'],r['weight'])
        total+=len(rows)
    for r in value['personal']:core.normalize(r['word'],r['pinyin'],r['weight'])
    for r in value.get('phrases',[]):core.normalize_phrase(r)
    key = hashlib.sha256(str(root).encode()).hexdigest()[:20]
    SELECTED_DIGESTS[key] = migration_digest(root, value)
    SELECTED[key] = root
    return {'id':key,'path':str(root),'libraries':len(value['libraries']),'words':total,'personal':len(value['personal']),'phrases':len(value.get('phrases',[]))}

def pick_directory():
    helper = core.ROOT/'choose-folder'
    if not helper.exists(): raise ValueError('请使用完整 Mac 应用选择文件夹，或在下方输入文件夹路径')
    result = subprocess.run([str(helper)],capture_output=True,text=True,timeout=300)
    if result.returncode == 2: return {'cancelled':True}
    if result.returncode: raise ValueError('文件夹选择未完成，请重试')
    return select_directory(result.stdout.strip())

def snapshot_good():
    try: record=json.loads((core.DATA/'deployment.json').read_text())
    except (OSError,ValueError): return
    old_configs=tuple(record.get('sources',{}))
    if not record.get('ok') or not old_configs or record['sources']!=file_hashes(core.RIME,old_configs): return
    # Copy only configuration and compiled dictionaries; never roll back learned user databases.
    names=set(CONFIGS)
    vendor=core.ROOT/'vendor/rime-ice'
    names.update(str(p.relative_to(vendor)) for p in vendor.rglob('*') if p.is_file())
    names.update('build/'+str(p.relative_to(core.RIME/'build')) for p in (core.RIME/'build').rglob('*') if p.is_file())
    import tempfile
    with tempfile.TemporaryDirectory(dir=str(core.DATA)) as tmp:
        stage=Path(tmp)/'snapshot';stage.mkdir()
        copied=[]
        for name in sorted(names):
            src=core.RIME/name
            if not src.is_file() or src.is_symlink(): continue
            dst=stage/'files'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst);copied.append(name)
        core.atomic_json(stage/'record.json',{'deployment':record,'files':copied})
        target=core.DATA/'last-good'
        if target.exists():shutil.rmtree(target)
        shutil.move(str(stage),str(target))

def recover(progress=lambda stage: None):
    app=client()
    if not app:raise ValueError('请先安装系统输入法')
    root=core.DATA/'last-good'
    if not (root/'record.json').is_file():raise ValueError('尚无可恢复的成功部署，请先完成一次部署')
    value=json.loads((root/'record.json').read_text())
    progress('backup')
    # Validate the full checkpoint before changing live configuration.
    for name in value['files']:
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('恢复记录路径无效')
        source=root/'files'/relative;dest=core.RIME/relative
        if not source.is_file() or source.is_symlink():raise ValueError('恢复文件不完整')
        if any(core.RIME.joinpath(*relative.parts[:i]).is_symlink() for i in range(len(relative.parts)+1)):raise ValueError('恢复目标含符号链接')
    import tempfile
    backup=core.DATA/'backups'/('before-recover-'+str(time.time_ns()))
    if core.RIME.exists():shutil.copytree(core.RIME,backup,symlinks=True)
    progress('restore')
    for name in value['files']:
        dest=core.RIME/name;dest.parent.mkdir(parents=True,exist_ok=True)
        fd,temp=tempfile.mkstemp(dir=str(dest.parent));os.close(fd)
        shutil.copyfile(root/'files'/name,temp);os.replace(temp,dest)
    core.atomic_json(core.DATA/'deployment.json',value['deployment'])
    progress('load')
    loaded=False
    try:
        subprocess.run([str(app/'Contents/MacOS/Squirrel'),'--reload'],capture_output=True,timeout=15,check=True);loaded=True
    except (OSError,subprocess.SubprocessError):pass
    return {'redeploy':loaded,'message':'已恢复上一次成功部署的配置。管理页中的新修改仍保留，学习记录未回退。'}


def migration_digest(root, value):
    digest=hashlib.sha256((root/'state.json').read_bytes())
    for lib in value['libraries']:
        if not re.fullmatch('[a-f0-9]{32}',lib['id']):raise ValueError('词库标识无效')
        digest.update((root/'libraries'/(lib['id']+'.json')).read_bytes())
    return digest.hexdigest()


def installed_apps():
    apps={}
    for base in (Path('/Applications'),Path.home()/'Applications',Path('/System/Applications')):
        if not base.exists():continue
        try:
            candidates=list(base.glob('*.app'))+list(base.glob('*/*.app'))
        except OSError:continue
        for path in candidates:
            try:
                info=plistlib.loads((path/'Contents/Info.plist').read_bytes())
                app_id=info.get('CFBundleIdentifier','')
                if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9.-]{1,199}',app_id):continue
                apps[app_id]={'id':app_id,'name':str(info.get('CFBundleDisplayName') or info.get('CFBundleName') or path.stem)}
            except (OSError,ValueError):continue
    return sorted(apps.values(),key=lambda x:x['name'].lower())
