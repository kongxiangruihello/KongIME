"""Editable named dictionaries and plain-text export."""
import hashlib,uuid
import core

def library(identifier):
 item=next((x for x in core.state()['libraries'] if x['id']==identifier),None)
 if item is None:raise ValueError('词库不存在')
 return item

def text(rows):return ''.join('%s\t%s\t%d\n'%(r['word'],r['pinyin'],r['weight']) for r in rows)
def content(identifier):
 item=library(identifier)
 if not item.get('manual'):raise ValueError('仅手动词库支持编辑')
 return {'text':text(core.lib_rows(item))}
def export(identifier=''):return text(core.lib_rows(library(identifier)) if identifier else core.active_rows(core.state()))
def save(data):
 name=str(data.get('name','')).strip();raw=data.get('text','')
 if not name or len(name)>100 or any(ord(c)<32 for c in name):raise ValueError('请输入 1–100 字的词库名称')
 if not isinstance(raw,str) or len(raw.encode())>2*1024*1024:raise ValueError('手动词库过大')
 rows=[];seen=set()
 for line in raw.splitlines():
  if not line.strip():continue
  parts=line.split('\t')
  if len(parts) not in (2,3):raise ValueError('每行用 Tab 分隔词语、拼音和可选权重')
  row=core.normalize(parts[0],parts[1],parts[2] if len(parts)==3 else 100)
  key=(row['word'],row['pinyin'])
  if key in seen:raise ValueError('词库中有重复词条')
  seen.add(key);rows.append(row)
 if not rows or len(rows)>5000:raise ValueError('手动词库需有 1–5000 条词语')
 s=core.state();identifier=data.get('id')
 if identifier:
  item=next((x for x in s['libraries'] if x['id']==identifier and x.get('manual')),None)
  if not item:raise ValueError('可编辑词库不存在')
 else:item={'id':uuid.uuid4().hex,'enabled':True};s['libraries'].append(item)
 # Immutable content files preserve old snapshots and undo after edits.
 item['id']=uuid.uuid4().hex
 item.update(name=name,manual=True,count=len(rows),hash=hashlib.sha256(text(rows).encode()).hexdigest(),review=sum(core.needs_review(x) for x in rows))
 core.atomic_json(core.DATA/'libraries'/(item['id']+'.json'),rows);core.save(s)
 return {'ok':True,'id':item['id']}
