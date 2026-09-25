"""Atomic, process-safe quick preferences shared by the client and manager."""
import json,os,sys,time,uuid,fcntl,tempfile
from pathlib import Path

def location():
 return Path(os.environ.get('KONGIME_RIME',str(Path.home()/'Library/Rime')))
def read(root=None):
 root=root or location();prefs=[];history=[]
 p=root/'kongime_quick.tsv'
 if p.exists():
  for line in p.read_text().splitlines():
   parts=line.split('\t')
   if len(parts)==4 and parts[0]=='P':prefs.append({'code':parts[1],'word':parts[2],'mode':parts[3]})
   elif line.startswith('H\t'):history.append(json.loads(line[2:]))
 return prefs,history
def validate(action,code,word):
 if action not in ('pin','unpin','lower','block','reset'):raise ValueError('无效操作')
 if not isinstance(code,str) or not code or len(code)>80 or any(c not in "abcdefghijklmnopqrstuvwxyz' " for c in code):raise ValueError('请使用中文状态下的小写拼音')
 if not isinstance(word,str) or not word or len(word)>500 or any(ord(c)<32 or c in '\x7f\x85\u2028\u2029' for c in word):raise ValueError('词语格式不支持快捷调整')

def normalize_preferences(value):
 if not isinstance(value,list) or len(value)>50000:raise ValueError('快捷排序备份格式无效')
 result=[];keys=set();pinned=set();blocked=set()
 for row in value:
  if not isinstance(row,dict):raise ValueError('快捷排序词条无效')
  mode=row.get('mode');code=row.get('code');word=row.get('word')
  if mode not in ('pin','unpin','lower','block'):raise ValueError('快捷排序模式无效')
  validate(mode,code,word)
  if (code,word) in keys or (mode=='pin' and code in pinned):raise ValueError('备份中有重复词条或同编码重复置顶')
  keys.add((code,word))
  if mode=='block':
   if word in blocked:raise ValueError('备份中有重复屏蔽词语')
   blocked.add(word)
  if mode=='pin':pinned.add(code)
  result.append({'code':code,'word':word,'mode':mode})
 return result

def change(action,code='',word='',root=None,event=None,replacement=None):
 root=root or location();root.mkdir(parents=True,exist_ok=True)
 if action=='restore':replacement=normalize_preferences(replacement)
 elif action!='undo':validate(action,code,word)
 with (root/'kongime_quick.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);prefs,history=read(root)
  if action=='undo':
   if not history or history[-1]['id']!=event:raise ValueError('请先撤销更新的一次快捷调整')
   prefs=history.pop()['before']
  else:
   before=[dict(x) for x in prefs]
   if action=='restore':
    prefs=replacement;label='恢复快捷排序备份'
   else:
    prefs=[x for x in prefs if not(x['code']==code and (x['word']==word or (action=='pin' and x['mode']=='pin'))) and not(action=='block' and x['word']==word and x['mode']=='block')]
    if action!='reset':prefs.append({'code':code,'word':word,'mode':action})
    label={'pin':'置顶','unpin':'取消置顶','lower':'降低优先级','block':'屏蔽候选词','reset':'恢复默认排序'}[action]+' · '+word
   history.append({'id':uuid.uuid4().hex,'time':time.strftime('%Y-%m-%d %H:%M:%S'),'label':label,'before':before})
   history=history[-30:]
  text=''.join('P\t{code}\t{word}\t{mode}\n'.format(**x) for x in prefs)+''.join('H\t'+json.dumps(x,ensure_ascii=False)+'\n' for x in history)
  fd,name=tempfile.mkstemp(dir=root)
  try:
   with os.fdopen(fd,'w') as f:f.write(text)
   os.replace(name,root/'kongime_quick.tsv')
  finally:
   if os.path.exists(name):os.unlink(name)
 return {'ok':True}
if __name__=='__main__':
 try:change(*sys.argv[1:4]);print('ok')
 except Exception as e:print(str(e),file=sys.stderr);sys.exit(1)
