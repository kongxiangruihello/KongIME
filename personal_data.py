"""Personal data protection: explicit iCloud snapshots, trash and library scenes."""
import json,os,re,time,uuid
from pathlib import Path
import core

def normalize_extras(value):
 trash=value.get('trash',[]);scenes=value.get('scenes',[])
 if not isinstance(trash,list) or len(trash)>200 or not isinstance(scenes,list) or len(scenes)>30:raise ValueError('个人数据格式或数量无效')
 result=[]
 for entry in trash:
  kind=entry['kind'];item=entry['item'];identifier=entry['id']
  if not isinstance(identifier,str) or not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('回收记录无效')
  if kind=='word':item=dict(core.normalize(item['word'],item['pinyin'],item['weight']),pinned=bool(item.get('pinned')))
  elif kind=='phrase':item=core.normalize_phrase(item)
  elif kind=='library':
   rows=[core.normalize(x['word'],x['pinyin'],x['weight']) for x in item['rows']]
   if len(rows)>core.MAX_ENTRIES:raise ValueError('回收词库过大')
   item={'name':str(item['name'])[:200],'manual':bool(item.get('manual')),'conflict_policy':item.get('conflict_policy') if item.get('conflict_policy') in ('local','incoming','higher') else None,'rows':rows}
  else:raise ValueError('回收类型无效')
  result.append({'id':identifier,'kind':kind,'item':item,'time':str(entry.get('time',''))[:40]})
 normalized=[]
 for scene in scenes:
  name=str(scene['name']).strip()
  if not name or len(name)>50 or len(scene['libraries'])>1000:raise ValueError('场景无效')
  entries=[]
  for x in scene['libraries']:
   if not isinstance(x['hash'],str) or type(x['enabled']) is not bool:raise ValueError('场景词库无效')
   entries.append({'hash':x['hash'],'enabled':x['enabled']})
  normalized.append({'name':name,'libraries':entries})
 if len({x['name'] for x in normalized})!=len(normalized) or len({x['id'] for x in result})!=len(result):raise ValueError('个人数据标识重复')
 return {'trash':result,'scenes':normalized}

def discard(s,kind,item):
 s.setdefault('trash',[])
 if len(s['trash'])>=200:raise ValueError('回收站已满，请先恢复需要的记录；本次未删除')
 if kind=='library':item={'name':item['name'],'manual':item.get('manual',False),'conflict_policy':item.get('conflict_policy'),'rows':core.lib_rows(item)}
 s['trash'].append({'id':uuid.uuid4().hex,'kind':kind,'item':dict(item),'time':time.strftime('%Y-%m-%d %H:%M:%S')})

def restore(identifier):
 s=core.state();entry=next((x for x in s.get('trash',[]) if x['id']==identifier),None)
 if not entry:raise ValueError('回收记录不存在')
 e=normalize_extras({'trash':[entry]})['trash'][0];item=e['item']
 if e['kind']=='word':
  if any((x['word'],x['pinyin'])==(item['word'],item['pinyin']) for x in s['personal']):raise ValueError('同词同拼音已存在，未覆盖现有词语')
  if item['pinned'] and (any(x.get('pinned') and x['pinyin'].replace(' ','')==item['pinyin'].replace(' ','') for x in s['personal']) or any(x['code']==item['pinyin'].replace(' ','') for x in s['phrases'])):item['pinned']=False
  s['personal'].append(item)
 elif e['kind']=='phrase':
  if any(x['code']==item['code'] for x in s['phrases']) or any(x.get('pinned') and x['pinyin'].replace(' ','')==item['code'] for x in s['personal']):raise ValueError('缩写已有词语或短语占用，未覆盖')
  s['phrases'].append(item)
 else:
  import hashlib
  lid=uuid.uuid4().hex;rows=item['rows'];core.atomic_json(core.DATA/'libraries'/(lid+'.json'),rows)
  s['libraries'].append({'id':lid,'name':item['name'],'manual':item['manual'],'conflict_policy':item.get('conflict_policy'),'enabled':False,'hash':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),'count':len(rows),'review':sum(core.needs_review(x) for x in rows)})
 s['trash']=[x for x in s['trash'] if x['id']!=identifier];core.save(s);return {'ok':True}

def scene(data):
 s=core.state();name=str(data['name']).strip();action=data['action']
 if not name or len(name)>50:raise ValueError('场景名称须为 1–50 字')
 scenes=s.setdefault('scenes',[])
 if action=='save':
  if len(scenes)>=30 and not any(x['name']==name for x in scenes):raise ValueError('最多 30 个场景')
  s['scenes']=[x for x in scenes if x['name']!=name]+[{'name':name,'libraries':[{'hash':x['hash'],'enabled':x['enabled']} for x in s['libraries']]}]
 elif action=='apply':
  selected=next((x for x in scenes if x['name']==name),None)
  if not selected:raise ValueError('场景不存在')
  selected={x['hash']:x['enabled'] for x in selected['libraries']}
  for x in s['libraries']:
   if x['hash'] in selected:x['enabled']=selected[x['hash']]
 else:raise ValueError('场景操作无效')
 core.save(s);return {'ok':True}

def conflicts(rows):
 existing=list(core.base_rows(core.state()).values());by_word={};exact={}
 for x in existing:by_word.setdefault(x['word'],set()).add(x['pinyin']);exact[(x['word'],x['pinyin'])]=x['weight']
 result={'duplicates':0,'pinyin_differences':0,'weight_differences':0,'examples':[]}
 for x in rows:
  key=(x['word'],x['pinyin']);kind=None
  if key in exact:
   result['duplicates']+=1
   if exact[key]!=x['weight']:result['weight_differences']+=1;kind='权重不同：本机 %s → 导入 %s'%(exact[key],x['weight'])
  elif x['word'] in by_word:result['pinyin_differences']+=1;kind='拼音不同：本机 '+', '.join(sorted(by_word[x['word']]))+' → 导入 '+x['pinyin']
  if kind and len(result['examples'])<20:result['examples'].append(x['word']+' · '+kind)
 return result

def icloud_root():
 # An override exists only for isolated tests. No automatic upload on startup.
 root=Path(os.environ.get('KONGIME_ICLOUD_ROOT',str(Path.home()/'Library/Mobile Documents/com~apple~CloudDocs')))
 if not root.is_dir():raise ValueError('未检测到 iCloud Drive，请先在 macOS 登录 Apple 账号并开启 iCloud Drive')
 return root/'KongIME'/'Backups'

def _icloud_status():
 try:root=icloud_root()
 except ValueError as e:return {'available':False,'message':str(e),'files':[]}
 files=sorted(root.glob('KongIME-*.json'),key=lambda p:p.name,reverse=True) if root.exists() else []
 return {'available':True,'message':'保存至 iCloud Drive / KongIME / Backups；系统负责上传，上传完成状态请在访达确认。','files':[{'name':p.name,'bytes':p.stat().st_size} for p in files[:50] if p.is_file() and not p.is_symlink()]}

def _icloud_save():
 import profile_backup
 profile_backup.recover();value=profile_backup.snapshot();encoded=json.dumps(value,ensure_ascii=False).encode()
 if len(encoded)>32*1024*1024:raise ValueError('统一备份超过 32 MB，未保存')
 root=icloud_root();root.mkdir(parents=True,exist_ok=True)
 name='KongIME-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.json'
 profile_backup.write_bytes(root/name,encoded)
 return {'ok':True,'name':name}

def icloud_value(name):
 import profile_backup
 if not isinstance(name,str) or not re.fullmatch(r'KongIME-\d{8}-\d{6}-[a-f0-9]{8}\.json',name):raise ValueError('备份名称无效')
 root=icloud_root();p=root/name
 if p.is_symlink() or not p.is_file():raise ValueError('文件尚未下载，请先在访达中下载这份 iCloud 备份')
 if p.stat().st_size>32*1024*1024:raise ValueError('备份过大')
 return json.loads(p.read_text())

def icloud_restore(name):
 import profile_backup
 return profile_backup.restore(icloud_value(name))


def icloud_status():
 try: result=_icloud_status()
 except OSError as e: result={'available':False,'message':str(e),'files':[]}
 try: record=json.loads((core.DATA/'icloud-status.json').read_text())
 except (OSError,ValueError): record={}
 result.update(last_backup=record.get('last_backup'),last_error=record.get('last_error'),auto_backup_available=False)
 return result

def icloud_save():
 try: record=json.loads((core.DATA/'icloud-status.json').read_text())
 except (OSError,ValueError): record={}
 try:
  result=_icloud_save()
 except Exception as e:
  record['last_error']=str(e);core.atomic_json(core.DATA/'icloud-status.json',record)
  raise
 record.update(last_backup=time.strftime('%Y-%m-%d %H:%M:%S'),last_error=None)
 core.atomic_json(core.DATA/'icloud-status.json',record)
 return result

def diagnostics():
 import workflow
 status=workflow.status();s=core.state();checks=[]
 checks.append({'label':'输入法版本','ok':status['branded'] and str(status.get('client_version','')).endswith(workflow.VERSION.rsplit('.',1)[0]),'detail':'设置 '+workflow.VERSION+' / 输入法 '+str(status.get('client_version') or '未安装'),'action':'installation'})
 checks.append({'label':'部署状态','ok':status['deployed'],'detail':status.get('last_error') or status['label'],'action':'deploy'})
 try:
  rows=core.active_rows(s)
  checks.append({'label':'词库加载','ok':True,'detail':str(sum(bool(x['enabled']) for x in s['libraries']))+' 个已启用导入词库，'+str(len(rows))+' 个合并词条（不含内置词库）','action':'libraries'})
 except (OSError,ValueError,KeyError) as e:checks.append({'label':'词库加载','ok':False,'detail':str(e),'action':'libraries'})
 cloud=icloud_status()
 checks.append({'label':'iCloud 目录','ok':cloud['available'],'detail':cloud['message'],'action':'icloud'})
 return {'checks':checks}
