import copy,io,json,os,sys,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
from wsgiref.simple_server import make_server,WSGIRequestHandler
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,quick,profile_backup,cloud_client
from cloud.server import Service,Error,digest
class Quiet(WSGIRequestHandler):
 def log_message(self,*args):pass
class MemoryStore:
 def __init__(self):self.values={}
 def call(self,op,account,value=None):
  if op=='get':return self.values.get(account)
  if op=='set':self.values[account]=value
  else:self.values.pop(account,None)
class CloudTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.old=(core.DATA,core.RIME)
  core.DATA=self.root/'data';core.RIME=self.root/'rime';core.save(core.state());self.mail={}
  self.service=Service(self.root/'cloud.sqlite','x'*40,lambda e,c:self.mail.update({e:c}))
 def tearDown(self):core.DATA,core.RIME=self.old;self.tmp.cleanup()
 def login(self,email='first@example.test'):
  self.service.handle('POST','/v1/auth/request',{'email':email})
  return self.service.handle('POST','/v1/auth/verify',{'email':email,'code':self.mail[email]})['token']
 def test_one_time_code_and_hashed_credentials(self):
  token=self.login();code=self.mail['first@example.test']
  with self.assertRaises(Error):self.service.handle('POST','/v1/auth/verify',{'email':'first@example.test','code':code})
  with self.service.db() as db:self.assertEqual(db.execute('SELECT hash FROM sessions').fetchone()[0],digest(token));self.assertEqual(db.execute('SELECT count(*) FROM challenges').fetchone()[0],0)
 def test_attempt_limit_and_rate_limit(self):
  self.service.handle('POST','/v1/auth/request',{'email':'first@example.test'})
  wrong='000000' if self.mail['first@example.test']!='000000' else '000001'
  for _ in range(5):
   with self.assertRaises(Error):self.service.handle('POST','/v1/auth/verify',{'email':'first@example.test','code':wrong})
  with self.assertRaises(Error):self.service.handle('POST','/v1/auth/verify',{'email':'first@example.test','code':self.mail['first@example.test']})
  with self.assertRaises(Error) as e:self.service.handle('POST','/v1/auth/request',{'email':'first@example.test'})
  self.assertEqual(e.exception.status,429)
 def test_expired_session_and_logout(self):
  token=self.login();self.service.handle('POST','/v1/auth/logout',{},token)
  with self.assertRaises(Error):self.service.handle('GET','/v1/versions',{},token)
  with self.service.db() as db:db.execute('INSERT INTO sessions VALUES(?,?,?)',(digest('expired'),'first@example.test',time.time()-1))
  with self.assertRaises(Error):self.service.handle('GET','/v1/versions',{},'expired')
 def test_account_isolation_conflict_and_history_retention(self):
  token=self.login();other=self.login('second@example.test');p=profile_backup.snapshot()
  self.service.handle('POST','/v1/versions',{'base_revision':0,'profile':p},token)
  with self.assertRaises(Error) as e:self.service.handle('POST','/v1/versions',{'base_revision':0,'profile':p},token)
  self.assertEqual(e.exception.status,409)
  self.assertEqual(self.service.handle('GET','/v1/versions',{},other)['versions'],[])
  with self.assertRaises(Error):self.service.handle('GET','/v1/versions/1',{},other)
  for revision in range(1,22):self.service.handle('POST','/v1/versions',{'base_revision':revision,'profile':p},token)
  rows=self.service.handle('GET','/v1/versions',{},token);self.assertEqual(len(rows['versions']),20);self.assertEqual(rows['latest'],22)
 def test_wsgi_rejects_bad_and_oversized_requests(self):
  def request(raw,n):
   status=[];body=self.service({'REQUEST_METHOD':'POST','PATH_INFO':'/v1/auth/request','CONTENT_LENGTH':str(n),'wsgi.input':io.BytesIO(raw)},lambda s,h:status.append(s));return status[0]
  self.assertTrue(request(b'[]',2).startswith('400'));self.assertTrue(request(b'',40*1024*1024).startswith('413'))
 def test_url_restrictions(self):
  c=cloud_client.Client(MemoryStore())
  with patch.dict(os.environ,{'KONGIME_CLOUD_DEV':'0'}):
   for url in ['http://example.test','https://user:secret@example.test','https://example.test/path','https://example.test/?secret=1']:
    with self.assertRaises(ValueError):c.validate_url(url)
  self.assertEqual(c.validate_url('https://example.test/'),'https://example.test')
 def test_two_client_roundtrip_over_http(self):
  server=make_server('127.0.0.1',0,self.service,handler_class=Quiet);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   with patch.dict(os.environ,{'KONGIME_CLOUD_URL':'http://127.0.0.1:'+str(server.server_port),'KONGIME_CLOUD_DEV':'1'}):
    a=cloud_client.Client(MemoryStore());b=cloud_client.Client(MemoryStore())
    a.send_code('first@example.test');a.login('first@example.test',self.mail['first@example.test'])
    b.store.call('set',b.endpoint(),a.session())
    s=core.state();s['personal']=[dict(word='云端测试',pinyin='yun duan ce shi',weight=100,pinned=True)];core.save(s);quick.change('pin','ceshi','测试',core.RIME)
    before=profile_backup.snapshot();self.assertEqual(a.upload(0)['revision'],1)
    core.DATA=self.root/'device-b';core.RIME=self.root/'rime-b';core.save(core.state())
    b.restore(1);self.assertEqual(profile_backup.snapshot(),before)
    b.upload(1)
    with self.assertRaises(ValueError):a.upload(1)
    self.assertNotIn('token',json.dumps(a.status()));b.logout();self.assertFalse(b.status()['logged_in'])
  finally:server.shutdown();server.server_close();thread.join()
 def test_smtp_failure_invalidates_code(self):
  self.service.send_code=lambda *args:(_ for _ in ()).throw(OSError())
  with self.assertRaises(Error):self.service.handle('POST','/v1/auth/request',{'email':'first@example.test'})
  with self.service.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM challenges').fetchone()[0],0)
