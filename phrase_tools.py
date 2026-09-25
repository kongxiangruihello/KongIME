"""Phrase-only transfer with explicit conflict resolution and atomic validation."""
import json,secrets,time,hashlib
import core
import re
from functools import lru_cache
PENDING={}
FORMAT='kongime-phrases-v1'
def fingerprint(s):
 return hashlib.sha256(json.dumps(s,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def export(group=None):
 if group is not None:group=core.normalize_phrase_group(group)
 return {'format':FORMAT,'phrases':[core.normalize_phrase(x) for x in core.state()['phrases'] if group is None or x.get('group','')==group]}

def organize(data):
 s=core.state()
 if data.get('revision')!=s['revision']:raise ValueError('短语列表已变化，请刷新后重试')
 target=core.normalize_phrase_group(data.get('target',''))
 if data.get('action')=='rename':
  group=core.normalize_phrase_group(data.get('group',''))
  rows=[x for x in s['phrases'] if x.get('group','')==group]
  if target!=group and any(x.get('group','')==target for x in s['phrases']) and data.get('merge') is not True:raise ValueError('目标分组已存在，请确认合并')
 elif data.get('action')=='move':
  codes=data.get('codes')
  if not isinstance(codes,list) or not codes or any(not isinstance(x,str) for x in codes) or len(set(codes))!=len(codes):raise ValueError('请选择要移动的短语')
  rows=[x for x in s['phrases'] if x['code'] in codes]
  if len(rows)!=len(codes):raise ValueError('部分短语已不存在，请刷新后重试')
 else:raise ValueError('未知分组操作')
 if not rows:raise ValueError('没有可处理的短语')
 codes={x['code'] for x in rows}
 updated=[core.normalize_phrase(dict(x,group=target)) if x['code'] in codes else x for x in s['phrases']]
 if updated!=s['phrases']:s['phrases']=updated;core.save(s)
 return {'count':len(rows),'group':target}
def validate(value):
 if not isinstance(value,dict) or value.get('format')!=FORMAT:raise ValueError('请选择 KongIME 短语导出文件')
 rows=value.get('phrases')
 if not isinstance(rows,list) or not 0<=len(rows)<=2000:raise ValueError('一次最多导入 2000 条短语')
 if len(json.dumps(value,ensure_ascii=False).encode())>2*1024*1024:raise ValueError('短语文件最大 2 MB')
 rows=[core.normalize_phrase(x) for x in rows]
 if len({x['code'] for x in rows})!=len(rows):raise ValueError('文件中有重复缩写，请先整理后导入')
 return rows
def preview(value):
 rows=validate(value);s=core.state();local={x['code']:x for x in s['phrases']}
 key=secrets.token_hex(16);PENDING.clear();PENDING[key]=(time.monotonic(),fingerprint(s),rows)
 return {'id':key,'count':len(rows),'conflicts':[{'code':x['code'],'local':local[x['code']],'incoming':x} for x in rows if x['code'] in local], 'rows':rows[:8]}
def confirm(data):
 pending=PENDING.get(data.get('id'))
 if not pending or time.monotonic()-pending[0]>900:raise ValueError('预览已过期，请重新选择短语文件')
 s=core.state()
 if fingerprint(s)!=pending[1]:raise ValueError('配置已变化，请重新预览后导入')
 local={x['code']:x for x in s['phrases']};decisions=data.get('decisions',{})
 if not isinstance(decisions,dict):raise ValueError('冲突处理无效')
 additions=[];replaced=kept=0
 reserved=set(local)|{x['code'] for x in pending[2]}
 for row in pending[2]:
  row=dict(row);code=row['code']
  if code in local:
   choice=decisions.get(code,{});action=choice.get('action','keep')
   if action=='keep':kept+=1;continue
   if action=='replace':replaced+=1
   elif action=='rename':
    row['code']=choice.get('code','');row=core.normalize_phrase(row)
    if row['code'] in reserved:raise ValueError('新缩写已存在或与本次导入重复：'+row['code'])
    reserved.add(row['code'])
   else:raise ValueError('请选择保留、替换或改名')
  additions.append(row)
 for row in additions:
  if row.get('enabled',True) and any(x.get('pinned') and x['pinyin'].replace(' ','').lower()==row['code'] for x in s['personal']):raise ValueError('缩写与个人置顶冲突：'+row['code'])
  local[row['code']]=row
 if additions:s['phrases']=list(local.values());core.save(s)
 PENDING.pop(data['id'],None)
 return {'added':len(additions)-replaced,'replaced':replaced,'kept':kept}
def toggle(data):
 s=core.state();row=next((x for x in s['phrases'] if x['code']==data['code']),None)
 if row is None:raise ValueError('短语不存在')
 return core.save_phrase(dict(row,old=row['code'],enabled=data['enabled']))

def group_update(data):
 group=core.normalize_phrase_group(data.get('group',''));enabled=data.get('enabled')
 if type(enabled) is not bool:raise ValueError('启用状态无效')
 s=core.state();rows=[x for x in s['phrases'] if x.get('group','')==group]
 if not rows:raise ValueError('这个分组还没有短语')
 pins={x['pinyin'].replace(' ','').lower() for x in s['personal'] if x.get('pinned')}
 if enabled and any(x['code'] in pins for x in rows):raise ValueError('组内有缩写与个人置顶冲突，请先单独检查')
 s['phrases']=[core.normalize_phrase(dict(x,enabled=enabled)) if x in rows else x for x in s['phrases']]
 if any(x.get('enabled',True)!=enabled for x in rows):core.save(s)
 return {'count':len(rows),'enabled':enabled}

@lru_cache(maxsize=64)
def base_matches(code,abbreviation):
 found=[]
 for name in ['8105','base']:
  path=core.ROOT/'vendor/rime-ice/cn_dicts'/(name+'.dict.yaml')
  with path.open() as source:
   for line in source:
    if line.startswith('#'):continue
    parts=line.rstrip('\n').split('\t')
    if len(parts)<2:continue
    word,pinyin=parts[:2];syllables=pinyin.split()
    if not syllables:continue
    if ''.join(syllables)!=code and not(abbreviation and ''.join(x[0] for x in syllables)==code):continue
    try:weight=int(parts[2]) if len(parts)>2 else 0
    except ValueError:weight=0
    found.append((weight,word,pinyin))
 return sorted(found,reverse=True)[:5]

def check_code(data):
 code=str(data.get('code','')).strip().lower();old=data.get('old')
 if not re.fullmatch('[a-z]{2,20}',code):return {'blocking':'缩写须为 2–20 个英文字母','warnings':[],'examples':[]}
 s=core.state()
 if any(x['code']==code and x['code']!=old for x in s['phrases']):return {'blocking':'这个缩写已用于其他短语，请改名或编辑原短语','warnings':[],'examples':[]}
 active=data.get('enabled',True) is not False
 if active and any(x.get('pinned') and x['pinyin'].replace(' ','').lower()==code for x in s['personal']):return {'blocking':'这个缩写与个人置顶冲突，请更换缩写或取消置顶','warnings':[],'examples':[]}
 abbreviation=s['settings'].get('abbreviation',True)
 matches=list(base_matches(code,abbreviation))
 for x in core.active_rows(s):
  syllables=x['pinyin'].split()
  if ''.join(syllables)==code or (abbreviation and ''.join(y[0] for y in syllables)==code):matches.append((x['weight'],x['word'],x['pinyin']))
 examples=[]
 for _,word,pinyin in sorted(matches,reverse=True):
  if word not in [x['word'] for x in examples]:examples.append({'word':word,'pinyin':pinyin})
  if len(examples)==3:break
 warnings=['这个缩写也能匹配普通拼音'+('或简拼' if abbreviation else '')+'；启用短语后，它会优先出现在候选中。'] if examples and active else []
 return {'blocking':None,'warnings':warnings,'examples':examples,'scope':'依据内置基础词库和已启用的个人词库检查；不包含全部纠错和模糊音组合。'}

def candidate(data):
 word=data.get('text','');code=data.get('code','');comment=data.get('comment','')
 if not isinstance(word,str) or not word or len(word)>500 or any(ord(c)<32 or ord(c)==127 for c in word):raise ValueError('候选内容过长或含不支持的字符，请手动添加')
 if not isinstance(code,str) or len(code)>80 or not re.fullmatch("[a-z' ]+",code):raise ValueError('候选编码无效')
 if data.get('action')=='edit':
  row=next((x for x in core.state()['phrases'] if x['code']==code and ((not x.get('dynamic') and x['text']==word) or (x.get('dynamic') and x.get('label','模板')==comment))),None)
  if not row:raise ValueError('对应短语已变化，请在列表中重新查找')
  return {'phrase':row,'editing':True}
 if data.get('action')!='new':raise ValueError('候选操作无效')
 return {'phrase':{'code':'','text':word},'editing':False}
