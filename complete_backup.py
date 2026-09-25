"""One-file personal migration, run while the native client has stopped Rime."""
import base64,json,os,re,secrets,shutil,time
from pathlib import Path
import core,learning,profile_backup,restore_review
FORMAT='kongime-complete-v1'
MAX_BYTES=64*1024*1024
PENDING={}

def validate(value):
 if not isinstance(value,dict) or value.get('format')!=FORMAT:raise ValueError('请选择 KongIME 完整迁移备份')
 if len(json.dumps(value,ensure_ascii=False).encode())>MAX_BYTES:raise ValueError('完整备份最大 64 MB')
 target=restore_review.canonical(value['profile']);learning.validate(value['learning'])
 expected=restore_review.fingerprint({'profile':value['profile'],'learning':value['learning']})
 if value.get('checksum')!=expected:raise ValueError('完整备份校验失败，文件可能不完整或已被修改')
 return target

def pack(profile,words):
 value={'format':FORMAT,'created':time.strftime('%Y-%m-%d %H:%M:%S'),'version':'0.26.0','profile':profile,'learning':words}
 value['checksum']=restore_review.fingerprint({'profile':profile,'learning':words})
 validate(value)
 return value

def available():
 try:
  import workflow,plistlib
  app=workflow.client()
  return bool(app and plistlib.loads((app/'Contents/Info.plist').read_bytes()).get('KongIMEVersion') in ('0.25.0','0.26.0'))
 except (OSError,ValueError):return False

def status():
 path=learning.root()/'complete-report.json'
 report=json.loads(path.read_text()) if path.exists() else None
 if report:report['changed_since']=report.get('fingerprint')!=restore_review.fingerprint(profile_backup.snapshot())
 return {'available':available(),'report':report,'can_rollback':(learning.root()/'complete-before.json').is_file()}

def value(before=False):
 result=json.loads((learning.root()/('complete-before.json' if before else 'complete-export.json')).read_text())
 validate(result);return result

def preview(value):
 target=validate(value);before=profile_backup.snapshot()
 report=restore_review.compare(restore_review.canonical(before),target)
 token=secrets.token_hex(16);PENDING.clear()
 PENDING[token]={'backup':value,'baseline':restore_review.fingerprint(before),'time':time.monotonic()}
 return {'id':token,'categories':report,'learning_count':len(value['learning']['rows']),'created':value.get('created','未知')}

def confirm(token):
 item=PENDING.pop(token,None)
 if not item or time.monotonic()-item['time']>600:raise ValueError('预览已过期，请重新选择完整备份')
 if item['baseline']!=restore_review.fingerprint(profile_backup.snapshot()):raise ValueError('本机配置已变化，请重新预览')
 return learning.request('complete-restore',{'backup':item['backup'],'baseline':item['baseline']})

def export_learning(tool,library,temp):
 out=temp/'complete-export.txt'
 if not (core.RIME/'qingyan.userdb').exists():return {'format':learning.FORMAT,'rows':[]}
 learning.run_tool(tool,library,core.RIME,'export',out,out)
 return learning.from_tsv(out)

def recover():
 folder=learning.root();journal=folder/'complete-transaction.json'
 if not journal.exists():return
 record=json.loads(journal.read_text());identifier=record['id']
 if not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('完整迁移恢复日志无效')
 if record.get('phase')=='committed':journal.unlink();return
 profile_backup.recover()
 # Original library files are immutable during restore; new files get fresh UUIDs.
 with profile_backup.locked():
  for key,encoded in record['files'].items():
   if key not in ('state.json','changes.json','before-profile.json','quick'):raise ValueError('完整迁移恢复路径无效')
   path=profile_backup.target(key)
   if encoded is None:path.unlink(missing_ok=True)
   else:profile_backup.write_bytes(path,base64.b64decode(encoded,validate=True))
 live=core.RIME/'qingyan.userdb';saved=folder/'complete-history'/(identifier+'.userdb')
 learning.safe_tree(live);learning.safe_tree(saved)
 if record['had_live']:
  if not saved.is_dir():raise ValueError('恢复前学习词库缺失，请保留文件并联系开发者')
  stage=folder/('recover-'+identifier+'.userdb')
  learning.safe_tree(stage)
  if stage.exists():shutil.rmtree(stage)
  shutil.copytree(saved,stage)
  if live.exists():shutil.rmtree(live)
  os.replace(stage,live)
 elif live.exists():shutil.rmtree(live)
 old=record.get('old_rollback')
 if old is None:(folder/'rollback.json').unlink(missing_ok=True)
 else:core.atomic_json(folder/'rollback.json',old)
 core.atomic_json(folder/'complete-report.json',{'verified':False,'rolled_back':True,'time':time.strftime('%Y-%m-%d %H:%M:%S'),'message':'操作未完成，已恢复操作前的配置和学习词频。'})
 journal.unlink()

def perform(operation,payload,tool,library,temp):
 folder=learning.root()
 if operation=='complete-export':
  with profile_backup.locked():profile=profile_backup.snapshot()
  backup=pack(profile,export_learning(tool,library,temp))
  core.atomic_json(folder/'complete-export.json',backup)
  return {'count':len(backup['learning']['rows'])}
 backup=payload['backup'];target=validate(backup)
 before=profile_backup.snapshot()
 if restore_review.fingerprint(before)!=payload['baseline']:raise ValueError('本机配置已变化，请重新预览')
 rows=learning.validate(backup['learning']);stage=temp/'complete-stage';stage.mkdir()
 text=temp/'complete-import.txt';out=temp/'complete-checked.txt'
 text.write_text(''.join('%s\t%s\t%d\n'%(x['word'],x['pinyin'],x['commits']) for x in rows))
 learning.run_tool(tool,library,stage,'import',text,out)
 sort=lambda values:sorted(values,key=lambda x:(x['word'],x['pinyin']))
 if sort(learning.from_tsv(out)['rows'])!=sort(rows):raise ValueError('学习词频预校验失败，未修改本机')
 before_backup=pack(before,export_learning(tool,library,temp))
 identifier=secrets.token_hex(16);live=core.RIME/'qingyan.userdb';learning.safe_tree(live)
 saved=folder/'complete-history'/(identifier+'.userdb');saved.parent.mkdir(exist_ok=True)
 if live.exists():shutil.copytree(live,saved)
 keys=('state.json','changes.json','before-profile.json','quick')
 files={k:base64.b64encode(profile_backup.target(k).read_bytes()).decode() if profile_backup.target(k).exists() else None for k in keys}
 rollback=folder/'rollback.json'
 record={'id':identifier,'phase':'pending','had_live':live.exists(),'files':files,'old_rollback':json.loads(rollback.read_text()) if rollback.exists() else None}
 core.atomic_json(folder/'complete-before.json',before_backup)
 core.atomic_json(folder/'complete-transaction.json',record)
 try:
  profile_backup.restore(backup['profile'],expected=payload['baseline'])
  learning.replace_database(stage/'qingyan.userdb')
  if restore_review.canonical(profile_backup.snapshot())!=target:raise ValueError('恢复后的配置核对不一致')
  if sort(export_learning(tool,library,temp)['rows'])!=sort(rows):raise ValueError('恢复后的学习词频核对不一致')
  report={'verified':True,'time':time.strftime('%Y-%m-%d %H:%M:%S'),'learning_count':len(rows),'fingerprint':restore_review.fingerprint(profile_backup.snapshot()),'message':'配置、词库、短语、候选偏好与学习词频校验通过；请点击应用并检查，再切换到 KongIME 试打。'}
  core.atomic_json(folder/'complete-report.json',report)
  record['phase']='committed';core.atomic_json(folder/'complete-transaction.json',record)
  (folder/'complete-transaction.json').unlink()
  return report
 except Exception:
  learning.recover_transaction();recover();raise
