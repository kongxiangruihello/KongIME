"""Local recoverable configuration checkpoints, independent of cloud storage."""
import hashlib,json,re,time,uuid
from pathlib import Path
import core,profile_backup

def create(reason):
 value=profile_backup.snapshot()
 encoded=json.dumps(value,ensure_ascii=False,sort_keys=True).encode()
 if len(encoded)>32*1024*1024:raise ValueError('配置快照超过 32 MB，请先导出词库后减少数据量')
 digest=hashlib.sha256(encoded).hexdigest()
 root=core.DATA/'snapshots';root.mkdir(parents=True,exist_ok=True)
 records=list_snapshots()
 if records and records[0]['digest']==digest:return records[0]
 name=time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.json'
 entry={'name':name,'time':time.strftime('%Y-%m-%d %H:%M:%S'),'reason':reason,'digest':digest,'profile':value}
 core.atomic_json(root/name,entry)
 return {k:v for k,v in entry.items() if k!='profile'}

def list_snapshots():
 root=core.DATA/'snapshots';rows=[]
 for p in sorted(root.glob('*.json'),reverse=True)[:50]:
  if p.is_symlink():continue
  try:
   entry=json.loads(p.read_text());rows.append({k:entry[k] for k in ('name','time','reason','digest')})
  except (OSError,ValueError,KeyError):continue
 return rows

def value(name):
 if not isinstance(name,str) or not re.fullmatch(r'\d{8}-\d{6}-[a-f0-9]{8}\.json',name):raise ValueError('快照标识无效')
 p=core.DATA/'snapshots'/name
 if not p.is_file() or p.is_symlink() or p.stat().st_size>34*1024*1024:raise ValueError('快照不可用')
 entry=json.loads(p.read_text());profile=entry['profile']
 digest=hashlib.sha256(json.dumps(profile,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
 if digest!=entry['digest']:raise ValueError('快照校验失败，未恢复')
 return profile

def restore(name):
 result=profile_backup.restore(value(name))
 return dict(result,message='配置快照已恢复，请保存并应用；程序版本和学习词频没有回退。')

def on_upgrade(version):
 marker=core.DATA/'snapshot-version.json'
 try:old=json.loads(marker.read_text()).get('version')
 except (OSError,ValueError):old=None
 if old==version:return
 import upgrade_check
 snapshots=list_snapshots();baseline=snapshots[0]['name'] if snapshots else None
 report=upgrade_check.inspect(version,old,baseline)
 if report['ok'] and (core.DATA/'state.json').is_file():
  try:create('升级到 '+version+' 后首次打开设置（迁移前）')
  except (OSError,ValueError) as e:
   report['backup_error']='升级快照未保存：'+str(e);core.atomic_json(core.DATA/'upgrade-check.json',report)
 core.atomic_json(marker,{'version':version})
