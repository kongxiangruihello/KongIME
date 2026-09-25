"""KongIME snapshot service. WSGI for deployment; CLI is loopback development only."""
import argparse, hashlib, hmac, json, os, re, secrets, smtplib, sqlite3, ssl, time
from email.message import EmailMessage
from contextlib import contextmanager
from pathlib import Path
from wsgiref.simple_server import make_server, WSGIRequestHandler
MAX_BYTES=32*1024*1024
class Error(Exception):
 def __init__(self,status,message):self.status=status;super().__init__(message)
def digest(value):return hashlib.sha256(value.encode()).hexdigest()
def email_address(value):
 if not isinstance(value,str) or len(value)>254 or not re.fullmatch(r'[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+',value):raise Error(400,'请输入有效邮箱')
 return value.lower()
class Service:
 def __init__(self,path,secret,send_code):
  if len(secret)<32:raise ValueError('KONGIME_AUTH_SECRET 至少 32 字符')
  self.path=str(path);self.secret=secret.encode();self.send_code=send_code
  Path(path).parent.mkdir(parents=True,exist_ok=True)
  with self.db() as db:
   db.executescript('''CREATE TABLE IF NOT EXISTS accounts(email TEXT PRIMARY KEY,revision INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS challenges(email TEXT PRIMARY KEY,hash TEXT,expires REAL,attempts INTEGER);
CREATE TABLE IF NOT EXISTS requests(email TEXT,ip TEXT,created REAL);
CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY,email TEXT,expires REAL);
CREATE TABLE IF NOT EXISTS snapshots(email TEXT,revision INTEGER,created REAL,payload TEXT,PRIMARY KEY(email,revision));''')
  os.chmod(self.path,0o600)
 @contextmanager
 def db(self):
  connection=sqlite3.connect(self.path,timeout=20)
  try:
   with connection:yield connection
  finally:connection.close()
 def code_hash(self,email,code):return hmac.new(self.secret,(email+'\0'+code).encode(),hashlib.sha256).hexdigest()
 def handle(self,method,path,data,token='',ip='unknown'):
  now=time.time()
  if method=='POST' and path=='/v1/auth/request':
   email=email_address(data.get('email'));code='%06d'%secrets.randbelow(1000000)
   with self.db() as db:
    db.execute('BEGIN IMMEDIATE');db.execute('DELETE FROM requests WHERE created<?',(now-3600,))
    recent=db.execute('SELECT count(*),max(created) FROM requests WHERE email=?',(email,)).fetchone()
    ips=db.execute('SELECT count(*) FROM requests WHERE ip=?',(ip,)).fetchone()[0]
    if recent[0]>=6 or (recent[1] and now-recent[1]<60) or ips>=30:raise Error(429,'发送过于频繁，请稍后重试')
    db.execute('INSERT INTO requests VALUES(?,?,?)',(email,ip,now))
    db.execute('INSERT OR REPLACE INTO challenges VALUES(?,?,?,0)',(email,self.code_hash(email,code),now+600))
    db.execute('DELETE FROM challenges WHERE expires<?',(now,));db.execute('DELETE FROM sessions WHERE expires<?',(now,))
   try:self.send_code(email,code)
   except Exception:
    with self.db() as db:db.execute('DELETE FROM challenges WHERE email=? AND hash=?',(email,self.code_hash(email,code)))
    raise Error(503,'验证码暂时发送失败，请稍后重试')
   return {'ok':True}
  if method=='POST' and path=='/v1/auth/verify':
   email=email_address(data.get('email'));code=data.get('code','')
   if not isinstance(code,str) or not re.fullmatch(r'\d{6}',code):raise Error(400,'请输入六位验证码')
   result=None
   with self.db() as db:
    db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT hash,expires,attempts FROM challenges WHERE email=?',(email,)).fetchone()
    if row and row[1]>now and row[2]<5:
     db.execute('UPDATE challenges SET attempts=attempts+1 WHERE email=?',(email,))
     if hmac.compare_digest(row[0],self.code_hash(email,code)):
      db.execute('DELETE FROM challenges WHERE email=?',(email,));db.execute('INSERT OR IGNORE INTO accounts(email) VALUES(?)',(email,))
      token=secrets.token_urlsafe(32);expires=now+30*86400
      db.execute('INSERT INTO sessions VALUES(?,?,?)',(digest(token),email,expires))
      result={'token':token,'email':email,'expires':expires}
   if result:return result
   raise Error(401,'验证码无效或已过期，请重新获取')
  if not token:raise Error(401,'请先登录')
  with self.db() as db:
   row=db.execute('SELECT email FROM sessions WHERE hash=? AND expires>?',(digest(token),now)).fetchone()
   if not row:raise Error(401,'登录已过期，请重新登录')
   email=row[0]
   if method=='POST' and path=='/v1/auth/logout':
    db.execute('DELETE FROM sessions WHERE hash=?',(digest(token),));return {'ok':True}
   if method=='GET' and path=='/v1/versions':
    latest=db.execute('SELECT revision FROM accounts WHERE email=?',(email,)).fetchone()[0]
    rows=db.execute('SELECT revision,created,length(CAST(payload AS BLOB)) FROM snapshots WHERE email=? ORDER BY revision DESC',(email,)).fetchall()
    return {'email':email,'latest':latest,'versions':[dict(revision=x[0],created=x[1],bytes=x[2]) for x in rows]}
   if method=='GET' and re.fullmatch(r'/v1/versions/[1-9][0-9]*',path):
    row=db.execute('SELECT payload FROM snapshots WHERE email=? AND revision=?',(email,int(path.rsplit('/',1)[1]))).fetchone()
    if not row:raise Error(404,'版本不存在或已超出保留范围')
    return json.loads(row[0])
   if method=='POST' and path=='/v1/versions':
    profile=data.get('profile');base=data.get('base_revision')
    if type(base)!=int or base<0:raise Error(400,'请先刷新云端版本')
    if not isinstance(profile,dict) or profile.get('format')!='kongime-profile-v1' or not isinstance(profile.get('manager'),dict) or not isinstance(profile.get('quick'),list) or profile.get('learning',{}).get('included') is not False:raise Error(400,'统一备份格式无效')
    payload=json.dumps(profile,ensure_ascii=False,separators=(',',':'))
    if len(payload.encode())>MAX_BYTES:raise Error(413,'统一备份最大 32 MB')
    db.execute('BEGIN IMMEDIATE')
    current=db.execute('SELECT revision FROM accounts WHERE email=?',(email,)).fetchone()[0]
    if current!=base:raise Error(409,'另一台设备已上传新版本。请刷新历史版本后确认，再上传或恢复。')
    version=current+1
    db.execute('INSERT INTO snapshots VALUES(?,?,?,?)',(email,version,now,payload));db.execute('UPDATE accounts SET revision=? WHERE email=?',(version,email))
    db.execute('DELETE FROM snapshots WHERE email=? AND revision<=?',(email,version-20))
    return {'revision':version}
  raise Error(404,'接口不存在')
 def __call__(self,environ,start_response):
  try:
   method=environ['REQUEST_METHOD'];n=int(environ.get('CONTENT_LENGTH') or 0)
   if n<0 or n>MAX_BYTES+65536:raise Error(413,'请求过大')
   raw=environ['wsgi.input'].read(n) if n else b'{}';data=json.loads(raw)
   if not isinstance(data,dict):raise Error(400,'请求格式无效')
   auth=environ.get('HTTP_AUTHORIZATION','');token=auth[7:] if auth.startswith('Bearer ') else ''
   value=self.handle(method,environ['PATH_INFO'],data,token,environ.get('REMOTE_ADDR','unknown'));status=200
  except Error as e:status=e.status;value={'error':str(e)}
  except (ValueError,TypeError,KeyError):status=400;value={'error':'请求格式无效'}
  except Exception:status=500;value={'error':'服务暂时不可用，请稍后重试'}
  body=json.dumps(value,ensure_ascii=False).encode();label={200:'OK',400:'Bad Request',401:'Unauthorized',404:'Not Found',409:'Conflict',413:'Payload Too Large',429:'Too Many Requests',503:'Service Unavailable'}.get(status,'Internal Server Error')
  start_response(str(status)+' '+label,[('Content-Type','application/json; charset=utf-8'),('Content-Length',str(len(body))),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff')]);return [body]
def smtp_sender():
 host=os.environ['KONGIME_SMTP_HOST'];user=os.environ['KONGIME_SMTP_USER'];password=os.environ['KONGIME_SMTP_PASSWORD'];sender=os.environ['KONGIME_SMTP_FROM']
 def send(email,code):
  msg=EmailMessage();msg['Subject']='KongIME 登录验证码';msg['From']=sender;msg['To']=email
  msg.set_content('你的 KongIME 验证码是 '+code+'，10 分钟内有效。若非本人操作，请忽略。')
  with smtplib.SMTP_SSL(host,int(os.environ.get('KONGIME_SMTP_PORT','465')),timeout=15,context=ssl.create_default_context()) as smtp:
   smtp.login(user,password);smtp.send_message(msg)
 return send
def create_app():return Service(os.environ['KONGIME_CLOUD_DB'],os.environ['KONGIME_AUTH_SECRET'],smtp_sender())
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--dev-mailbox',required=True);p.add_argument('--port',type=int,default=18862);args=p.parse_args()
 mailbox=Path(args.dev_mailbox);mailbox.mkdir(parents=True,exist_ok=True);os.chmod(mailbox,0o700)
 def local_send(email,code):
  path=mailbox/(digest(email)+'.json');path.write_text(json.dumps({'email':email,'code':code}));os.chmod(path,0o600)
 class Quiet(WSGIRequestHandler):
  def log_message(self,*args):pass
 app=Service(args.db,secrets.token_urlsafe(48),local_send)
 with make_server('127.0.0.1',args.port,app,handler_class=Quiet) as server:
  print('Local test service: http://127.0.0.1:'+str(server.server_port),flush=True);server.serve_forever()
