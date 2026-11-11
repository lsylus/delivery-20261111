"""B13-only loopback host and source-derived assembly; no shared service mutation."""
from pathlib import Path
import os,json,tempfile,subprocess,time,secrets,shutil,sys
import cadquery as cq
from b13_workflow import ROOT,Service,current
base=Path(tempfile.mkdtemp(prefix='b13-r4-browser-',dir=ROOT/'work'));base.chmod(0o700)
out=ROOT/os.environ.get('B13_EVIDENCE_DIR','docs/evidence/B13/r4/browser-development');out.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,PATH=str(ROOT/'.tools/node/bin')+os.pathsep+os.environ.get('PATH',''))
private=ROOT/'work/b13-r4-session.json'
assert not private.exists()
service=None;gateway=None
try:
 service=Service(base/'backend',timeout=180,upload_limit=8*1024*1024)
 service.stop();cfg=json.loads(service.config.read_text());cfg['converter_config']=str(ROOT/'work/config/converters.local.json');service.config.write_text(json.dumps(cfg));service.start()
 # Only create the upload file. No project, import, frame or result is prebuilt.
 motor_path=out/'complete-motor.step'
 motor=cq.Shape.importBrep(str(ROOT/'fixtures/real-derived/b13/motor.brep'))
 cq.exporters.export(motor,str(motor_path))
 # Stable loopback transport survives a real backend process restart.
 import threading,http.server,urllib.request,urllib.error
 class Proxy(http.server.BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def relay(self):
   headers={k:v for k,v in self.headers.items() if k.lower() not in ('host','connection','content-length')}
   body=self.rfile.read(int(self.headers.get('Content-Length',0))) or None
   request=urllib.request.Request(service.url.removesuffix('/api/v1')+self.path,data=body,headers=headers,method=self.command)
   try:response=urllib.request.urlopen(request,timeout=240)
   except urllib.error.HTTPError as error:response=error
   data=response.read();self.send_response(response.code)
   for key,value in response.headers.items():
    if key.lower() not in ('content-length','transfer-encoding','connection'):self.send_header(key,value)
   self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
  do_GET=do_POST=do_PUT=do_DELETE=relay
 proxy=http.server.ThreadingHTTPServer(('127.0.0.1',0),Proxy)
 thread=threading.Thread(target=proxy.serve_forever,daemon=True);thread.start()
 cookie=secrets.token_urlsafe(32);other=secrets.token_urlsafe(32)
 sessions={cookie:{'paint':dict(owner_id='alice',session_id='a-session',module='paint',backendCredential=service.tokens['alice']),
                   'blanket':dict(owner_id='alice',session_id='a-blanket',module='blanket',backendCredential=service.tokens['blanket'])},
           other:{'paint':dict(owner_id='alice',session_id='a-other',module='paint',backendCredential=service.tokens['other_session']),
                  'blanket':dict(owner_id='alice',session_id='a-other',module='blanket',backendCredential='not-authorized')}}
 packs=base/'packages';packs.mkdir()
 for module in ('paint','blanket'):
  pack=subprocess.run(['npm','pack','--workspace',f'plugins/{module}/plugin','--pack-destination',str(base),'--json'],cwd=ROOT,env=env,capture_output=True,text=True,check=True)
  info=json.loads(pack.stdout)[0];dest=packs/module;dest.mkdir()
  subprocess.run(['tar','xzf',str(base/info['filename']),'--strip-components=1','-C',str(dest)],check=True)
 config=base/'host.json';ready=base/'ready.json'
 config.write_text(json.dumps(dict(serviceUrl='http://127.0.0.1:'+str(proxy.server_port),sessions=sessions,packages=str(packs),ready=str(ready),audit=str(out/'browser-api.jsonl'))));config.chmod(0o600)
 log=(base/'host.log').open('w');gateway=subprocess.Popen(['node','tests/e2e/isolated_host.mjs',str(config)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
 for _ in range(200):
  if ready.exists():break
  if gateway.poll() is not None:raise RuntimeError((base/'host.log').read_text())
  time.sleep(.05)
 private.write_text(json.dumps(dict(**json.loads(ready.read_text()),cookie=cookie,other_cookie=other,motor_step=str(motor_path),restart_request=str(base/'restart.request'),restart_done=str(base/'restart.done'))));private.chmod(0o600)
 (out/'browser-inputs.json').write_text(json.dumps(dict(initial_projects=0,initial_imports=0,initial_results=0,source_brep='fixtures/real-derived/b13/motor.brep',source_faces=len(motor.Faces()),input_step=str(motor_path.relative_to(ROOT))),indent=2)+'\n')
 print('B13_R4_READY',flush=True)
 while True:
  request=base/'restart.request'
  if request.exists():
   request.unlink();old_pid=service.process.pid;old_port=service.port;service.stop();service.start()
   record=dict(old_pid=old_pid,new_pid=service.process.pid,old_port=old_port,new_port=service.port,retained_data_root=str(service.data),status='pass')
   (out/'backend-restart.json').write_text(json.dumps(record,indent=2)+'\n');(base/'restart.done').write_text('done')
  time.sleep(.1)
except KeyboardInterrupt:pass
finally:
 if gateway:gateway.terminate();gateway.wait(timeout=15)
 if 'proxy' in locals():proxy.shutdown();proxy.server_close();thread.join(timeout=5)
 if service:
  logs=out/'browser-worker-logs';logs.mkdir(exist_ok=True)
  for f in (service.data/'jobs').glob('*.log'):shutil.copy2(f,logs/f.name)
  service.close()
 if 'log' in locals():log.close()
 shutil.rmtree(base)
 private.unlink(missing_ok=True)
 (out/'browser-resources.json').write_text(json.dumps(dict(status='pass',resources_created=[str(base)],resources_cleaned=[str(base)],private_session_absent=not private.exists()),indent=2)+'\n')
