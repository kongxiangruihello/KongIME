"""Cloud transport; credentials stay in Keychain and never enter the WebView."""
import json, os, subprocess, time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
import core, profile_backup
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None
class Keychain:
 def __init__(self):self.cache={}
 def call(self,op,account,value=None):
  if op=='get' and account in self.cache:return self.cache[account]
  p=subprocess.run([str(core.ROOT/'credential-store')],input=json.dumps({'op':op,'account':account,'value':value}),text=True,capture_output=True,timeout=30)
  if p.returncode:raise ValueError('无法访问登录钥匙串，请解锁钥匙串后重试')
  result=json.loads(p.stdout).get('value') if op=='get' else value if op=='set' else None
  self.cache[account]=result;return result
class Client:
 def __init__(self,store=None):self.store=store or Keychain()
 def endpoint(self):
  value=os.environ.get('KONGIME_CLOUD_URL')
  if value is None:
   p=core.DATA/'cloud-connection.json';value=json.loads(p.read_text()).get('url','') if p.exists() else ''
  return self.validate_url(value) if value else ''
 def validate_url(self,value):
  if not isinstance(value,str):raise ValueError('服务地址无效')
  value=value.strip().rstrip('/');p=urlsplit(value)
  local=os.environ.get('KONGIME_CLOUD_DEV')=='1' and p.scheme=='http' and p.hostname=='127.0.0.1'
  if (p.scheme!='https' and not local) or not p.hostname or p.username or p.password or p.path or p.query or p.fragment:raise ValueError('请输入 HTTPS 服务地址，不包含路径、账号或参数')
  return value
 def configure(self,url):
  if os.environ.get('KONGIME_CLOUD_URL') is not None:raise ValueError('当前服务地址由测试环境指定')
  if self.session():raise ValueError('请先退出账号，再更换服务地址')
  core.atomic_json(core.DATA/'cloud-connection.json',{'url':self.validate_url(url) if url.strip() else ''});return {'ok':True}
 def session(self):
  url=self.endpoint()
  if not url:return None
  value=self.store.call('get',url)
  if value and value.get('expires',0)<=time.time():self.store.call('delete',url);return None
  return value
 def status(self):
  url=self.endpoint();s=self.session()
  return {'configured':bool(url),'url':url,'logged_in':bool(s),'email':s['email'] if s else '', 'test_mode':bool(url.startswith('http://127.0.0.1:'))}
 def request(self,path,data=None,authenticated=True):
  url=self.endpoint()
  if not url:raise ValueError('云服务尚未配置，仍可使用下方本地备份')
  headers={'Content-Type':'application/json'}
  if authenticated:
   s=self.session()
   if not s:raise ValueError('请先登录')
   headers['Authorization']='Bearer '+s['token']
  body=None if data is None else json.dumps(data,ensure_ascii=False).encode()
  if body and len(body)>32*1024*1024+65536:raise ValueError('统一备份最大 32 MB')
  try:
   with build_opener(NoRedirect()).open(Request(url+path,body,headers),timeout=25) as r:
    raw=r.read(32*1024*1024+65537)
    if len(raw)>32*1024*1024+65536:raise ValueError('云端文件过大')
    return json.loads(raw)
  except HTTPError as e:
   if e.code==401 and authenticated:self.store.call('delete',url)
   if e.code==409:raise ValueError('云端已有新版本，请刷新历史后检查，再决定上传或恢复。')
   if e.code==401:raise ValueError('登录或验证码已失效，请重新登录')
   if e.code==429:raise ValueError('操作过于频繁，请稍后重试')
   if e.code==404:raise ValueError('云端版本或服务接口不存在')
   raise ValueError('云服务未完成请求，请稍后重试（%s）'%e.code)
  except (URLError,TimeoutError,OSError):raise ValueError('无法连接云服务，本地词库和配置未受影响')
 def send_code(self,email):return self.request('/v1/auth/request',{'email':email},False)
 def login(self,email,code):
  result=self.request('/v1/auth/verify',{'email':email,'code':code},False)
  if not isinstance(result.get('token'),str) or not result['token'] or not isinstance(result.get('expires'),(int,float)) or not isinstance(result.get('email'),str):raise ValueError('登录响应无效')
  self.store.call('set',self.endpoint(),result);return self.status()
 def logout(self):
  # Local sign-out works offline. The remote token may remain valid until its expiry.
  message='已退出登录。'
  try:self.request('/v1/auth/logout',{})
  except ValueError:message='本机已退出登录；未能联系服务撤销会话，会话将在到期后失效。'
  self.store.call('delete',self.endpoint());return {'ok':True,'message':message}
 def versions(self):return self.request('/v1/versions')
 def upload(self,revision):
  profile_backup.recover();value=profile_backup.snapshot()
  if len(json.dumps(value,ensure_ascii=False).encode())>32*1024*1024:raise ValueError('统一备份最大 32 MB')
  return self.request('/v1/versions',{'base_revision':revision,'profile':value})
 def restore(self,revision):
  if type(revision)!=int or revision<1:raise ValueError('版本无效')
  value=self.request('/v1/versions/'+str(revision));return profile_backup.restore(value)
client=Client()
