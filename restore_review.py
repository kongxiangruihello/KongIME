"""Validated, expiring restore previews with stale-state rejection and post-restore checks."""
import hashlib,json,secrets,time
import core,quick,profile_backup,personal_data,local_snapshots
PENDING={}

def fingerprint(value):
 return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def canonical(value):
 if not isinstance(value,dict) or value.get('format')!=profile_backup.FORMAT:raise ValueError('请选择配置备份文件')
 if value.get('learning',{}).get('included') is not False:raise ValueError('学习词频请使用独立恢复入口')
 s,rows=profile_backup.prepare(value['manager']);lookup=dict(rows);prefs=quick.normalize_preferences(value['quick'])
 libraries={}
 # Stable content keys, independent of regenerated UUIDs and original file hashes.
 ordered=sorted(s['libraries'],key=lambda x:(x['name'],fingerprint(lookup[x['id']])))
 for lib in ordered:
  name=lib['name'];index=1
  while name in libraries:index+=1;name=lib['name']+'（'+str(index)+'）'
  content=sorted(lookup[lib['id']],key=lambda x:(x['word'],x['pinyin']))
  libraries[name]={'词条数':len(content),'启用':lib['enabled'],'手动词库':lib['manual'],'冲突策略':lib.get('conflict_policy'),'内容校验':fingerprint(content)}
 active=core.active_rows(s,lambda lib:lookup[lib['id']])
 words={x['word']+' · '+x['pinyin']:{'初始权重':x['weight'],'置顶':bool(x.get('pinned'))} for x in active}
 phrases={x['code']:{'text':x['text'],'dynamic':bool(x.get('dynamic')),'enabled':x.get('enabled',True),'date_offset':x.get('date_offset',0),'label':x.get('label','模板'),'group':x.get('group','')} for x in s['phrases']}
 pins={x['word']+' · '+x['pinyin']:'个人置顶' for x in s['personal'] if x.get('pinned')}
 for x in prefs:
  if x['mode']=='pin':pins[x['word']+' · '+x['code']]='快捷置顶'
 settings={}
 names={'abbreviation':'简拼','page_size':'候选数量','learning':'本地候选词推荐','show_pinyin':'显示拼音','auto_save':'自动保存','ascii_punctuation':'英文标点','direct_english':'大写英文直输','recognize_addresses':'网址邮箱识别','shortcuts':'快捷键','language_hint':'中英文切换提示','pair_chinese':'中文成对标点','pair_english':'英文成对标点'}
 for key,value in s['settings'].items():settings[names.get(key,key)]=value
 settings['候选外观']=s['appearance'];settings['模糊音']=s['fuzzy']
 for x in s['app_preferences']:
  settings['应用初始语言 · '+x['id']]=x['mode']
  if x.get('disable_pairs'):settings['应用停用成对标点 · '+x['id']]=True
 return {'词库':libraries,'已启用词条与个人词语':words,'短语':phrases,'置顶':pins,'个性化设置':settings,
         '快捷排序':{x['code']+' · '+x['word']:x['mode'] for x in prefs},
         '场景':{x['name']:x['libraries'] for x in s['scenes']},
         '回收站':{x['id']:{'kind':x['kind'],'item':x['item']} for x in s['trash']},
         '个人词语设置':{x['word']+' · '+x['pinyin']:x for x in s['personal']},
         '特殊编码处理':{x['source']['word']+' · '+x['source']['pinyin']:x for x in s['resolutions']}}

def short(value):
 labels={'word':'词语','pinyin':'拼音','weight':'权重','pinned':'置顶','candidate_gap':'窗口间距','font_size':'字号','layout':'排列','theme':'外观','expand':'展开／收起','previous':'上一页','next':'下一页','pin':'置顶','kind':'类型','item':'内容','code':'编码','mode':'方式','decision':'处理','source':'原词条','replacement':'修改后'}
 def render(item):
  if item is None:return '无'
  if isinstance(item,bool):return '开启' if item else '关闭'
  if isinstance(item,dict):return '；'.join(labels.get(k,k)+'：'+render(v) for k,v in item.items() if k!='内容校验') or '无'
  if isinstance(item,list):return '、'.join(render(x) for x in item) or '无'
  return str(item)
 result=render(value)
 return result[:400]+('…' if len(result)>400 else '')

def compare(before,after):
 result=[]
 for category,old in before.items():
  new=after[category];added=sorted(new.keys()-old.keys());removed=sorted(old.keys()-new.keys());changed=sorted(k for k in old.keys()&new.keys() if old[k]!=new[k])
  samples=[]
  for kind,keys in [('新增',added),('移除',removed),('修改',changed)]:
   for key in keys:
    if len(samples)>=10:break
    before_text,after_text=short(old.get(key)),short(new.get(key))
    if category=='词库' and kind=='修改' and old[key]['内容校验']!=new[key]['内容校验']:
     after_text+='；词条内容有变化'
    samples.append({'kind':kind,'label':key[:200],'before':before_text,'after':after_text})
  result.append({'label':category,'before':len(old),'after':len(new),'added':len(added),'removed':len(removed),'changed':len(changed),'samples':samples})
 return result

def source_value(data):
 source=data.get('source','file')
 if source=='file':
  value=data['backup']
  if value.get('format')=='qingyan-backup-v1':
   value={'format':profile_backup.FORMAT,'manager':value,'quick':quick.read(core.RIME)[0],'learning':{'included':False}}
  return value
 if source=='snapshot':return local_snapshots.value(data['name'])
 if source=='icloud':return personal_data.icloud_value(data['name'])
 if source=='rollback':
  p=core.DATA/'before-profile.json'
  if not p.is_file() or p.is_symlink() or p.stat().st_size>34*1024*1024:raise ValueError('恢复前备份不可用')
  return json.loads(p.read_text())
 raise ValueError('恢复来源无效')

def preview(data):
 value=source_value(data)
 if len(json.dumps(value,ensure_ascii=False).encode())>34*1024*1024:raise ValueError('备份超过大小限制')
 target=canonical(value);before=profile_backup.snapshot();baseline=fingerprint(before)
 report=compare(canonical(before),target)
 token=secrets.token_hex(16);PENDING.clear();PENDING[token]={'value':value,'baseline':baseline,'target':target,'time':time.monotonic(),'report':report}
 return {'id':token,'categories':report,'changes':sum(x['added']+x['removed']+x['changed'] for x in report)}

def confirm(token):
 item=PENDING.pop(token,None)
 if not item or time.monotonic()-item['time']>600:raise ValueError('预览已过期，请重新预览')
 profile_backup.restore(item['value'],expected=item['baseline'])
 restored=profile_backup.snapshot();actual=canonical(restored)
 checks=[{'label':key,'expected':len(item['target'][key]),'actual':len(actual[key]),'ok':item['target'][key]==actual[key]} for key in item['target']]
 result={'ok':True,'verified':all(x['ok'] for x in checks),'checks':checks,'time':time.strftime('%Y-%m-%d %H:%M:%S'),'fingerprint':fingerprint(restored),'categories':item['report']}
 try:core.atomic_json(core.DATA/'restore-report.json',result)
 except OSError:result['warning']='恢复已完成，但核对报告未能保存；恢复前备份仍保留。'
 return result

def last_report():
 p=core.DATA/'restore-report.json'
 if not p.exists():return None
 result=json.loads(p.read_text());result['changed_since']=result.get('fingerprint')!=fingerprint(profile_backup.snapshot())
 return result
