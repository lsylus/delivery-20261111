"""B13-only loopback host and source-derived assembly; no shared service mutation."""
from pathlib import Path
import os,json,tempfile,subprocess,time,secrets,shutil,sys
import cadquery as cq
from b13_workflow import ROOT,Service,current
base=Path(tempfile.mkdtemp(prefix='b13-r3-browser-',dir=ROOT/'work'));base.chmod(0o700)
out=ROOT/os.environ.get('B13_EVIDENCE_DIR','docs/evidence/B13/r3/browser-development');out.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,PATH=str(ROOT/'.tools/node/bin')+os.pathsep+os.environ.get('PATH',''))
private=ROOT/'work/b13-r3-session.json'
assert not private.exists()
service=None;gateway=None
try:
 service=Service(base/'backend',timeout=180,upload_limit=8*1024*1024)
 service.stop();cfg=json.loads(service.config.read_text());cfg['converter_config']=str(ROOT/'work/config/converters.local.json');service.config.write_text(json.dumps(cfg));service.start()
 project=service.project('blanket')
 from b13_workflow import import_shape
 from workflow import run,result
 from thermal_drawings.paint.surface_pipeline import boundary_id
 motor=cq.Shape.importBrep(str(ROOT/'fixtures/real-derived/b13/motor.brep'))
 rev,model,mapping=import_shape(service,project,motor,name='full-motor.step')
 refs=[f['face_ref'] for f in mapping['faces']]
 params=json.loads((ROOT/'fixtures/contracts/blanket.json').read_text());b=motor.BoundingBox()
 params.update(model_ref=rev['model_ref'],target_instances=sorted({f['instance_id'] for f in refs}),envelope_policy='faceted_clearance_v1',clearance_options=dict(clearance_mm=1.,section_cuts_mm=[40.,300.,334.]))
 params['installation_frame']['origin']=[b.xmin,b.ymin,b.zmin];params['allowance']['factors']=[1,1,1]
 run(service,project,current(service,project),'blanket.generate',params)
 cover=result(service,project)
 run(service,project,current(service,project),'blanket.unfold',dict(result_id=cover['result_id'],settings=dict(connection_plan='connected_15mm_v1')))
 motor_index=max((i for i,f in enumerate(refs) if f['signature']['type']=='CYLINDER'),key=lambda i:refs[i]['signature']['area_mm2'])
 service.bind(project,'alice')
 service.call('POST',f'/projects/{project}/revisions',dict(expected_revision='empty',model_ref=rev['model_ref'],parameters={},selection=[],overrides=[]),expected=201)
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
 config.write_text(json.dumps(dict(serviceUrl=service.url.removesuffix('/api/v1'),sessions=sessions,packages=str(packs),ready=str(ready),audit=str(out/'browser-api.jsonl'))));config.chmod(0o600)
 log=(base/'host.log').open('w');gateway=subprocess.Popen(['node','tests/e2e/isolated_host.mjs',str(config)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
 for _ in range(200):
  if ready.exists():break
  if gateway.poll() is not None:raise RuntimeError((base/'host.log').read_text())
  time.sleep(.05)
 private.write_text(json.dumps(dict(**json.loads(ready.read_text()),cookie=cookie,other_cookie=other,project=project,motor_index=motor_index)));private.chmod(0o600)
 (out/'browser-inputs.json').write_text(json.dumps(dict(project=project,model_ref=rev['model_ref'],source_brep='fixtures/real-derived/b13/motor.brep',motor_index=motor_index),indent=2)+'\n')
 print('B13_R3_READY',flush=True)
 while True:time.sleep(.5)
except KeyboardInterrupt:pass
finally:
 if gateway:gateway.terminate();gateway.wait(timeout=15)
 if service:
  logs=out/'browser-worker-logs';logs.mkdir(exist_ok=True)
  for f in (service.data/'jobs').glob('*.log'):shutil.copy2(f,logs/f.name)
  service.close()
 if 'log' in locals():log.close()
 shutil.rmtree(base)
 private.unlink(missing_ok=True)
 (out/'browser-resources.json').write_text(json.dumps(dict(status='pass',resources_created=[str(base)],resources_cleaned=[str(base)],private_session_absent=not private.exists()),indent=2)+'\n')
