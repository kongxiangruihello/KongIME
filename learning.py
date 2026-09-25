"""Explicit learning-dictionary transfer; native client pauses Rime before worker changes files."""
import json,os,re,shutil,subprocess,time,uuid,fcntl,tempfile
from pathlib import Path
import core,profile_backup
FORMAT='kongime-learning-v1'
MAX_BYTES=16*1024*1024

def validate(value):
 if not isinstance(value,dict) or value.get('format')!=FORMAT or not isinstance(value.get('rows'),list):raise ValueError('请选择 KongIME 学习词频备份')
 if len(value['rows'])>100000:raise ValueError('学习词条超过 100000 条')
 result=[];seen=set()
 for row in value['rows']:
  word=row['word'];code=row['pinyin'];count=row['commits']
  if not isinstance(word,str) or not word or len(word)>500 or any(ord(c)<32 or ord(c)==127 for c in word):raise ValueError('学习词条文字无效')
  if not isinstance(code,str) or not re.fullmatch(r'[a-z]+(?: [a-z]+)*',code) or len(code)>1000:raise ValueError('学习词条拼音无效')
  if type(count) is not int or not 0<=count<=2147483647:raise ValueError('学习词频无效')
  key=word,code
  if key in seen:raise ValueError('学习备份存在重复词条')
  seen.add(key);result.append({'word':word,'pinyin':code,'commits':count})
 return result

def from_tsv(path):
 rows=[]
 for line in path.read_text().splitlines():
  if not line or line.startswith('#'):continue
  fields=line.split('\t')
  if len(fields)!=3:raise ValueError('学习词频导出格式无效')
  rows.append({'word':fields[0],'pinyin':fields[1].strip(),'commits':int(fields[2])})
 return {'format':FORMAT,'rows':validate({'format':FORMAT,'rows':rows})}

def root():return core.RIME/'kongime-learning'
def status():
 folder=root();result={'can_rollback':(folder/'rollback.json').is_file(),'available':False}
 try:
  import workflow,plistlib
  app=workflow.client()
  result['available']=bool(app and plistlib.loads((app/'Contents/Info.plist').read_bytes()).get('KongIMEVersion')in ('0.16.0','0.17.0','0.18.0','0.19.0','0.20.0','0.21.0','0.22.0','0.23.0','0.24.0','0.25.0'))
 except (OSError,ValueError):pass
 return result

def request(operation,value=None):
 import workflow
 import complete_backup
 complete=operation in ('complete-export','complete-restore')
 if operation not in ('export','restore','rollback','complete-export','complete-restore'):raise ValueError('学习词频操作无效')
 if complete and not complete_backup.available():raise ValueError('请安装 0.25 并注销重新登录后使用完整迁移')
 if not status()['available']:raise ValueError('请先安装当前版本并注销重新登录，再使用学习词频迁移')
 if operation=='restore':value={'format':FORMAT,'rows':validate(value)}
 folder=root();folder.mkdir(parents=True,exist_ok=True)
 token=uuid.uuid4().hex
 payload={'id':token,'operation':operation,'created':time.time(),'value':value}
 encoded=json.dumps(payload,ensure_ascii=False).encode()
 if len(encoded)>(complete_backup.MAX_BYTES+4096 if complete else MAX_BYTES):raise ValueError('备份超过大小限制')
 core.atomic_json(folder/'request.json',payload)
 subprocess.run([str(workflow.client()/'Contents/MacOS/Squirrel'),'--learning'],check=True,timeout=10,capture_output=True)
 for _ in range(240 if complete else 60):
  try:
   result=json.loads((folder/'response.json').read_text())
   if result.get('id')==token:
    if result.get('error'):raise ValueError(result['error'])
    return result
  except (FileNotFoundError,json.JSONDecodeError):pass
  time.sleep(.5)
 # Revoke pending work so a delayed notification cannot restore after a timeout.
 try:
  if json.loads((folder/'request.json').read_text()).get('id')==token:(folder/'request.json').unlink()
 except FileNotFoundError:pass
 raise ValueError('输入法未在限定时间响应，请在设置中确认当前运行版本与已安装版本一致。若操作已开始，请检查学习词频状态后再重试。')

def export_value():
 value=json.loads((root()/'export.json').read_text());validate(value);return value

def safe_tree(path):
 if path.is_symlink() or (path.exists() and any(x.is_symlink() for x in path.rglob('*'))):raise ValueError('学习数据库包含符号链接，已停止操作')

def recover_transaction():
 folder=root();journal=folder/'transaction.json'
 if not journal.exists():return
 record=json.loads(journal.read_text());identifier=record['id']
 if not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('学习恢复日志无效')
 live=core.RIME/'qingyan.userdb';previous=folder/'history'/(identifier+'.userdb')
 safe_tree(live);safe_tree(previous)
 if previous.exists():
  if live.exists():shutil.rmtree(live)
  os.replace(previous,live)
 elif not record['had_live'] and live.exists():shutil.rmtree(live)
 old=record.get('old_rollback')
 if old is None:(folder/'rollback.json').unlink(missing_ok=True)
 else:core.atomic_json(folder/'rollback.json',old)
 journal.unlink()

def replace_database(prepared):
 folder=root();live=core.RIME/'qingyan.userdb';safe_tree(live);safe_tree(prepared)
 identifier=uuid.uuid4().hex;previous=folder/'history'/(identifier+'.userdb');previous.parent.mkdir(parents=True,exist_ok=True)
 rollback=folder/'rollback.json'
 old=json.loads(rollback.read_text()) if rollback.exists() else None
 record={'id':identifier,'had_live':live.exists(),'old_rollback':old}
 core.atomic_json(folder/'transaction.json',record)
 try:
  if live.exists():os.replace(live,previous)
  os.replace(prepared,live)
  core.atomic_json(rollback,{'id':identifier,'had_live':record['had_live']})
  (folder/'transaction.json').unlink()
 except Exception:
  recover_transaction();raise

def run_tool(tool,library,folder,operation,input_file,output_file):
 result=subprocess.run([str(tool),str(library),str(folder),operation,str(input_file),str(output_file)],capture_output=True,timeout=15)
 if result.returncode:raise ValueError('学习数据库被占用或导入导出失败，未继续替换；请重新启动输入法后重试')

def worker(user_dir,tool,library,recover_only=False):
 import complete_backup
 core.RIME=Path(user_dir);folder=root();folder.mkdir(parents=True,exist_ok=True)
 with (folder/'maintenance.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  recover_transaction()
  complete_backup.recover()
  if recover_only:return
  request_path=folder/'request.json'
  if not request_path.exists() or request_path.stat().st_size>complete_backup.MAX_BYTES+4096:return
  req=json.loads(request_path.read_text());token=req['id']
  if not re.fullmatch('[a-f0-9]{32}',token) or not 0<=time.time()-req['created']<35:return
  request_path.unlink()
  result={'id':token}
  try:
   op=req['operation'];live=core.RIME/'qingyan.userdb';safe_tree(live)
   with tempfile.TemporaryDirectory(dir=folder) as tmp:
    temp=Path(tmp);out=temp/'export.txt'
    if op in ('complete-export','complete-restore'):
     result.update(complete_backup.perform(op,req.get('value'),tool,library,temp))
    elif op=='export':
     value={'format':FORMAT,'rows':[]}
     if live.exists():
      run_tool(tool,library,core.RIME,'export',out,out);value=from_tsv(out)
     core.atomic_json(folder/'export.json',value);result['count']=len(value['rows'])
    elif op in ('restore','rollback'):
     stage=temp/'stage';stage.mkdir()
     if op=='restore':
      rows=validate(req['value']);text=temp/'import.txt';text.write_text(''.join('%s\t%s\t%d\n'%(x['word'],x['pinyin'],x['commits']) for x in rows))
      run_tool(tool,library,stage,'import',text,out)
      actual=from_tsv(out)['rows']
      if sorted(actual,key=lambda x:(x['word'],x['pinyin']))!=sorted(rows,key=lambda x:(x['word'],x['pinyin'])):raise ValueError('恢复后的学习词频校验不一致，未替换本机')
     else:
      previous=json.loads((folder/'rollback.json').read_text());identifier=previous['id']
      if not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('回退记录无效')
      if previous['had_live']:
       source=folder/'history'/(identifier+'.userdb');safe_tree(source);shutil.copytree(source,stage/'qingyan.userdb')
      else:
       text=temp/'empty.txt';text.write_text('');run_tool(tool,library,stage,'import',text,out)
     replace_database(stage/'qingyan.userdb');result['restored']=True
    else:raise ValueError('学习操作无效')
  except Exception as e:result['error']=str(e)
  core.atomic_json(folder/'response.json',result)

if __name__=='__main__':
 import sys
 worker(sys.argv[1],Path(sys.argv[2]),Path(sys.argv[3]),len(sys.argv)>4 and sys.argv[4]=='recover')
