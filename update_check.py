"""Explicit, read-only release checks; never sends personal configuration."""
import json,re,time
from urllib.request import Request,urlopen
from urllib.error import URLError,HTTPError
import workflow
REPO='https://github.com/kongxiangruihello/KongIME'
API='https://api.github.com/repos/kongxiangruihello/KongIME/releases?per_page=100'
MAX_BYTES=2*1024*1024

def version(value):
 match=re.fullmatch(r'v?(\d{1,4})\.(\d{1,4})(?:\.(\d{1,4}))?',str(value))
 return tuple(int(x or 0) for x in match.groups()) if match else None

def select(rows,include_preview=False):
 if not isinstance(rows,list):raise ValueError('版本信息格式异常，请前往 GitHub 查看')
 candidates=[]
 for row in rows:
  if not isinstance(row,dict) or row.get('draft') or (row.get('prerelease') and not include_preview):continue
  tag=row.get('tag_name');number=version(tag)
  if not number or row.get('html_url')!=REPO+'/releases/tag/'+tag:continue
  prefix=REPO+'/releases/download/'+tag+'/'
  assets=[a for a in row.get('assets',[]) if isinstance(a,dict) and a.get('state')=='uploaded' and re.fullmatch(r'KongIME-\d+\.\d+(?:\.\d+)?-Mac\.zip',a.get('name','')) and a.get('browser_download_url')==prefix+a['name'] and a.get('size',0)>0]
  if assets:candidates.append((number,row))
 current=version(workflow.VERSION)
 if not candidates:return {'current':workflow.VERSION,'available':False,'message':'暂未找到可下载的'+('正式版或测试版' if include_preview else '正式版')+'。','url':REPO+'/releases'}
 number,row=max(candidates,key=lambda x:x[0]);new=number>current
 return {'current':workflow.VERSION,'latest':row['tag_name'],'available':new,'prerelease':bool(row.get('prerelease')),'url':row['html_url'],'message':('发现新版本：' if new else '当前版本已是所选范围内的最新版本；发布页版本：')+row['tag_name']+('（测试版）' if row.get('prerelease') else '')}

def check(include_preview=False):
 if type(include_preview) is not bool:raise ValueError('更新选项无效')
 request=Request(API,headers={'Accept':'application/vnd.github+json','User-Agent':'KongIME-update-check','X-GitHub-Api-Version':'2022-11-28'})
 try:
  with urlopen(request,timeout=12) as response:
   raw=response.read(MAX_BYTES+1)
  if len(raw)>MAX_BYTES:raise ValueError('版本信息过大，请前往 GitHub 查看')
  result=select(json.loads(raw),include_preview)
 except HTTPError as e:
  raise ValueError('GitHub 暂时无法检查（HTTP %d），请稍后重试或打开发布页。'%e.code)
 except (URLError,TimeoutError,OSError,json.JSONDecodeError):
  raise ValueError('无法连接 GitHub，请检查网络后重试，或打开发布页。')
 result['checked_at']=time.strftime('%Y-%m-%d %H:%M:%S');return result
