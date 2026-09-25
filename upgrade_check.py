"""Local upgrade inventory; differences from older snapshots are not assumed to be data loss."""
import json,time
import core,local_snapshots,profile_backup

def inspect(version,previous=None,baseline=None):
 report={'version':version,'previous':previous,'time':time.strftime('%Y-%m-%d %H:%M:%S'),'errors':[],'counts':{},'baseline':baseline,'categories':[],'comparison':'none'}
 try:
  s=core.state();report['revision']=s['revision']
  report['counts']={'词库':len(s['libraries']),'个人词语':len(s['personal']),'短语':len(s['phrases']),'应用语言规则':len(s['app_preferences'])}
  for lib in s['libraries']:
   try:
    rows=core.lib_rows(lib)
    if len(rows)!=lib['count']:raise ValueError('词条数量不一致')
    for row in rows:core.normalize(row['word'],row['pinyin'],row['weight'])
   except (OSError,ValueError,KeyError,TypeError):report['errors'].append('词库“'+str(lib.get('name','未命名'))+'”无法完整读取，请从备份检查恢复')
  if not report['errors']:
   import restore_review
   current=restore_review.canonical(profile_backup.snapshot())
   if baseline:
    try:
     old=restore_review.canonical(local_snapshots.value(baseline))
     report['categories']=[{k:v for k,v in x.items() if k!='samples'} for x in restore_review.compare(old,current)]
     report['comparison']='different' if any(x['added']+x['removed']+x['changed'] for x in report['categories']) else 'same'
    except (OSError,ValueError,KeyError,TypeError):report['comparison']='unavailable'
 except (OSError,ValueError,KeyError,TypeError) as e:report['errors'].append('个人配置无法完整读取：'+str(e))
 report['ok']=not report['errors']
 core.atomic_json(core.DATA/'upgrade-check.json',report)
 return report

def read():
 try:report=json.loads((core.DATA/'upgrade-check.json').read_text())
 except (OSError,ValueError):return None
 try:report['changed_since']=core.state()['revision']!=report.get('revision')
 except (OSError,ValueError,KeyError):report['changed_since']=True
 return report

def retry(version):
 old=read() or {}
 return inspect(version,old.get('previous'),old.get('baseline'))
