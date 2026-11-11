"""Independent signed-request adversarial cases; all keys/accounts are ephemeral fixtures."""
import base64,hashlib,json,secrets,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from types import SimpleNamespace
import pytest
from starlette.requests import Request
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
from thermal_drawings.api.host_auth import HostAuthenticator
from thermal_drawings.domain.errors import ServiceError
from thermal_drawings.settings import Settings

def enc(value):return base64.urlsafe_b64encode(value).decode().rstrip('=')
def wire(value):return enc(json.dumps(value,separators=(',',':')).encode())

@pytest.fixture
def host(tmp_path):
 key=Ed25519PrivateKey.generate();public=key.public_key().public_bytes(Encoding.DER,PublicFormat.SubjectPublicKeyInfo)
 kid=hashlib.sha256(public).hexdigest();registry=tmp_path/'hosts.json'
 row=dict(tenant='xingqiao-9999',user='qmh',home_hash=hashlib.sha256(b'qmh').hexdigest(),module='paint',public_key=enc(public),enabled=True)
 def store(value):registry.write_text(json.dumps(value));registry.chmod(0o600)
 store(dict(version=1,keys={kid:row}));state=dict(active=True,revoke=False,wrong_signature=False)
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*a):pass
  def do_POST(self):
   nonce=json.loads(self.rfile.read(int(self.headers['Content-Length'])))['nonce']
   if state['revoke']:
    changed=dict(row,enabled=False);store(dict(version=1,keys={kid:changed}))
   payload=wire(dict(nonce=nonce,active=state['active']))
   signature=(Ed25519PrivateKey.generate() if state['wrong_signature'] else key).sign(payload.encode())
   data=json.dumps(dict(payload=payload,signature=enc(signature))).encode()
   self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 def claims():return dict(v=1,kid=kid,tenant='xingqiao-9999',user='qmh',home_hash=row['home_hash'],module='paint',session='chat-1',method='POST',path='/api/v1/projects',body_sha256=hashlib.sha256(b'{}').hexdigest(),headers={'content-type':'application/json'},nonce=enc(secrets.token_bytes(32)),expires=int(time.time()*1000)+10000,callback_port=server.server_port)
 def request(value=None,body=b'{}',headers=None,client='127.0.0.1',path='/api/v1/projects',method='POST',signer=None,query=b''):
  payload=wire(value or claims());signature=(signer or key).sign(payload.encode())
  h={'host':'127.0.0.1','content-type':'application/json','x-drawings-host':payload+'.'+enc(signature)};h.update(headers or {})
  req=Request(dict(type='http',method=method,path=path,raw_path=path.encode(),scheme='http',query_string=query,server=('127.0.0.1',80),client=(client,1234),headers=[(k.encode(),v.encode()) for k,v in h.items()]))
  return req,body
 obj=SimpleNamespace(auth=HostAuthenticator(SimpleNamespace(host_registry=registry)),claims=claims,request=request,state=state,registry=registry,store=store,row=row,kid=kid,server=server)
 yield obj
 server.shutdown();server.server_close();thread.join()

def test_signed_valid_account_and_one_use_replay(host):
 req,body=host.request();p=host.auth.authenticate(req,body)
 assert p.owner==hashlib.sha256(b'xingqiao-9999\0qmh').hexdigest();assert p.session=='chat-1';assert p.module=='paint'
 with pytest.raises(ServiceError):host.auth.authenticate(req,body)

@pytest.mark.parametrize('field,value',[('tenant','other'),('user','other'),('module','blanket'),('home_hash','f'*64),('kid','a'*64),('session','../other'),('nonce','short'),('expires',0),('expires',99999999999999),('callback_port',80),('v',2),('method','GET'),('path','/api/v1/health'),('body_sha256','0'*64),('headers',{})])
def test_bound_claim_mismatch_denied(host,field,value):
 c=host.claims();c[field]=value
 with pytest.raises(ServiceError):host.auth.authenticate(*host.request(c))

@pytest.mark.parametrize('change',[{'body':b'{"owner":"admin"}'},{'headers':{'x-filename':'changed.step'}},{'headers':{'origin':'http://127.0.0.1'}},{'headers':{'authorization':'Bearer synthetic-development-token'}},{'headers':{'host':'evil.invalid'}},{'client':'192.0.2.4'},{'query':b'owner=admin'},{'signer':Ed25519PrivateKey.generate()}])
def test_transport_and_payload_tampering_denied(host,change):
 with pytest.raises(ServiceError):host.auth.authenticate(*host.request(**change))

@pytest.mark.parametrize('flag',['active','revoke','wrong_signature'])
def test_callback_rechecks_live_session_signature_and_enrollment(host,flag):
 host.state[flag]=False if flag=='active' else True
 with pytest.raises(ServiceError):host.auth.authenticate(*host.request())

def test_callback_unavailable_is_fail_closed(host):
 host.server.shutdown();host.server.server_close()
 with pytest.raises(ServiceError):host.auth.authenticate(*host.request())

@pytest.mark.parametrize('registry',[{'keys':{}},{'keys':[]},{'keys':None},{'keys':{'not-the-key':{}}}])
def test_unenrolled_or_malformed_registry_denied(host,registry):
 host.store(registry)
 with pytest.raises(ServiceError):host.auth.authenticate(*host.request())

def test_registry_permissions_and_no_development_fallback(host,tmp_path):
 host.registry.chmod(0o644)
 with pytest.raises(ServiceError):host.auth.authenticate(*host.request())
 host.registry.chmod(0o600)
 with pytest.raises(ValueError):Settings(data_root=tmp_path/'data',host_registry=host.registry,auth_mode='dsh-account',credentials_file=host.registry).validate()
