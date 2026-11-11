"""B13-only loopback host and source-derived assembly; no shared service mutation."""
from pathlib import Path
import os,json,tempfile,subprocess,time,secrets,shutil,sys
import cadquery as cq
from b13_workflow import ROOT,Service,current
base=Path(tempfile.mkdtemp(prefix='b13-r2-browser-',dir=ROOT/'work'));base.chmod(0o700)
out=ROOT/os.environ.get('B13_EVIDENCE_DIR','docs/evidence/B13');out.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,PATH=str(ROOT/'.tools/node/bin')+os.pathsep+os.environ.get('PATH',''))
private=ROOT/'work/b13-r2-session.json'
assert not private.exists()
service=None;gateway=None
try:
 service=Service(base/'backend',timeout=180,upload_limit=8*1024*1024)
 service.stop();cfg=json.loads(service.config.read_text());cfg['converter_config']=str(ROOT/'work/config/converters.local.json');service.config.write_text(json.dumps(cfg));service.start()
 project=service.project('blanket')
 assembly=cq.Assembly()
 for name in ['computer-space','conical-support']:
  assembly.add(cq.Shape.importBrep(str(ROOT/f'fixtures/real-derived/b13/{name}.brep')),name=name)
 # Keep prior scoped UI scenarios and add the complete original tank for atlas UI.
 from OCP.BRep import BRep_Tool
 from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
 tank=cq.Shape.importBrep(str(ROOT/'fixtures/real-derived/b13/fuel-tank.brep'))
 assembly.add(tank,name='full-fuel-tank')
 sphere_face=max((f for f in tank.Faces() if f.geomType()=='SPHERE'),key=lambda f:f.Area())
 u0,u1,v0,v1=sphere_face._uvBounds();trim=[u0+.1,u1-.1,v0+.1,v1-.1]
 patch=cq.Face(BRepBuilderAPI_MakeFace(BRep_Tool.Surface_s(sphere_face.wrapped),*trim,1e-7).Face())
 assert patch.isValid()
 assembly.add(patch,name='fuel-tank-native-trimmed-patch')
 motor=cq.Shape.importBrep(str(ROOT/'fixtures/real-derived/b13/motor.brep'))
 assembly.add(motor,name='full-motor')
 b=tank.BoundingBox();band=tank.intersect(cq.Solid.makeBox(b.xlen+2,b.ylen+2,60,cq.Vector(b.xmin-1,b.ymin-1,760)))
 assembly.add(band,name='tank-native-band-Z760-820')
 (out/'browser-surface-scope.json').write_text(json.dumps(dict(source='fixtures/real-derived/b13/fuel-tank.brep',source_uv=[u0,u1,v0,v1],trimmed_uv=trim,scope='Complete original tank and motor imported; retained band/patch scenarios plus full hemisphere atlas UI',full_acceptance=False),indent=2)+'\n')
 step=base/'complex.step';assembly.export(str(step))
 asset=service.call('POST',f'/projects/{project}/assets',step.read_bytes(),who='blanket',expected=201,headers={'Content-Type':'application/step','X-Filename':'complex.step'})[1]
 job=service.wait(service.submit_import(project,asset,who='blanket'),'blanket');assert job['state']=='succeeded',job
 rev=current(service,project);model=service.call('GET',f'/projects/{project}/models/'+rev['model_ref']['model_id'],who='blanket')[1]
 mapping=service.call('GET','/artifacts/'+next(a for a in model['artifacts'] if a['relative_storage_path'].endswith('/mesh-map.json'))['id'],who='blanket')[1]
 refs=[f['face_ref'] for f in mapping['faces']]
 computer=cq.Shape.importBrep(str(ROOT/'fixtures/real-derived/b13/computer-space.brep'))
 bottom_face=min((f for f in computer.Faces() if f.geomType()=='PLANE' and f.normalAt().z<-.99),key=lambda f:f.Center().z)
 bottom=min((i for i,f in enumerate(refs) if f['signature']['type']=='PLANE'),key=lambda i:sum((a-b)**2 for a,b in zip(refs[i]['signature']['centroid_mm'],bottom_face.Center().toTuple())))
 cone=next(i for i,f in enumerate(refs) if f['signature']['type']=='CONE')
 sphere=max((i for i,f in enumerate(refs) if f['signature']['type']=='SPHERE'),key=lambda i:refs[i]['signature']['area_mm2'])
 motor_index=max((i for i,f in enumerate(refs) if f['signature']['type']=='CYLINDER' and abs(f['signature']['area_mm2']-140129.42456556)<1),key=lambda i:refs[i]['signature']['area_mm2'])
 band_index=next(i for i,f in enumerate(refs) if f['signature']['type']=='SPHERE' and 760<f['signature']['centroid_mm'][2]<800 and i!=sphere)
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
 private.write_text(json.dumps(dict(**json.loads(ready.read_text()),cookie=cookie,other_cookie=other,project=project,bottom_index=bottom,cone_index=cone,sphere_index=sphere,motor_index=motor_index,band_index=band_index)));private.chmod(0o600)
 (out/'browser-inputs.json').write_text(json.dumps(dict(project=project,model_ref=rev['model_ref'],source_asset_sha256=asset['sha256'],bottom_index=bottom,cone_index=cone,sphere_index=sphere,motor_index=motor_index,band_index=band_index),indent=2)+'\n')
 print('B13_READY',flush=True)
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
