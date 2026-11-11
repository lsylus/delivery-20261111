"""Private B06 + two packed plugins. No running platform/profile is modified."""
from pathlib import Path
import sys,os,json,tempfile,subprocess,time,secrets,signal,shutil,socket,hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests/runtime'))
from http_harness import Service
base=Path(tempfile.mkdtemp(prefix='b07-',dir=ROOT/'work'));base.chmod(0o700)
env=os.environ.copy();env['PATH']=str(ROOT/'.tools/node/bin')+os.pathsep+env.get('PATH','')
out=ROOT/'docs/evidence/B07';out.mkdir(exist_ok=True,parents=True)
service=None;gateway=None
try:
    service=Service(base/'backend')
    imported={}
    for who in ('alice','blanket','other_session','bob'):
        p,a,rev,run=service.imported(who)
        model=service.call('GET',f'/projects/{p}/models/{rev["model_ref"]["model_id"]}',who=who)[1]
        downloaded=[]
        artifact_dir=out/'artifacts'/who;artifact_dir.mkdir(parents=True,exist_ok=True)
        for item in model['artifacts']:
            suffix=Path(item['relative_storage_path']).name
            if suffix not in ('model.glb','mesh-map.json','snapshot.json'):continue
            payload=service.call('GET',item['download_url'].replace('/api/v1',''),who=who,raw=True)[1]
            assert hashlib.sha256(payload).hexdigest()==item['sha256'] and len(payload)==item['bytes']
            (artifact_dir/suffix).write_bytes(payload)
            downloaded.append(dict(path=str((artifact_dir/suffix).relative_to(ROOT)),sha256=item['sha256'],bytes=item['bytes']))
        imported[who]=dict(project=p,revision=rev,asset=a,model=model,downloaded=downloaded)
    sessions={};cookies={}
    for label,names in [('alice',['alice','blanket']),('other_session',['other_session','blanket']),('bob',['bob'])]:
        cookie=secrets.token_urlsafe(32);cookies[label]=cookie;sessions[cookie]={}
        for name in names:
            principal=service.principals[name]
            sessions[cookie][principal['module']]={"owner_id":principal['owner'],"session_id":principal['session'],"module":principal['module'],"backendCredential":service.tokens[name]}
    packs=base/'packages';packs.mkdir()
    package_records=[]
    for module in ('paint','blanket'):
        pack=subprocess.run(['npm','pack','--workspace',f'plugins/{module}/plugin','--pack-destination',str(base),'--json'],cwd=ROOT,env=env,capture_output=True,text=True,check=True)
        info=json.loads(pack.stdout)[0];archive=base/info['filename'];dest=packs/module;dest.mkdir()
        subprocess.run(['tar','xzf',str(archive),'--strip-components=1','-C',str(dest)],check=True)
        (out/'packages').mkdir(exist_ok=True);shutil.copyfile(archive,out/'packages'/(module+'.tgz'))
        package_records.append(dict(module=module,files=[f['path'] for f in info['files']],sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),bytes=archive.stat().st_size))
    mcp_records=[]
    for module,who in [('paint','alice'),('blanket','blanket')]:
        principal=service.principals[who]
        mcp_config=base/(module+'-mcp.json')
        mcp_config.write_text(json.dumps(dict(mode='isolated-adapter',serviceUrl=service.url.removesuffix('/api/v1'),identity=dict(owner_id=principal['owner'],session_id=principal['session'],module=module),credential=service.tokens[who])))
        mcp_config.chmod(0o600)
        mcp_env=dict(env,B07_MCP_CONTEXT_FILE=str(mcp_config))
        requests=[dict(jsonrpc='2.0',id=1,method='tools/list'),dict(jsonrpc='2.0',id=2,method='tools/call',params=dict(name=f'satellite_{module}_operation',arguments=dict(operation='engineering.save',parameters={}))),dict(jsonrpc='2.0',id=3,method='tools/call',params=dict(name=f'satellite_{module}_operation',arguments=dict(operation='drawing.export',parameters={})))]
        mcp=subprocess.run(['node',str(packs/module/'mcp/server.mjs')],input='\n'.join(json.dumps(r) for r in requests)+'\n',cwd=ROOT,env=mcp_env,capture_output=True,text=True,timeout=30,check=True)
        responses={r['id']:r for r in map(json.loads,mcp.stdout.splitlines())}
        assert responses[1]['result']['tools'][0]['name']==f'satellite_{module}_operation'
        submitted=json.loads(responses[2]['result']['content'][0]['text']);run=service.wait(submitted['run_id'],who)
        assert run['state']=='succeeded' and run['operation']=='engineering.save'
        assert '503' in responses[3]['error']['message']
        mcp_records.append(dict(module=module,status='pass',responses=responses,run=run))
    (out/'mcp.json').write_text(json.dumps(dict(status='pass',records=mcp_records),indent=2)+'\n')
    subprocess.run(['node','--input-type=module','-e',"import {build} from 'esbuild'; await build({entryPoints:['tests/e2e/host.tsx'],outfile:'work/b07-host.js',bundle:true,platform:'browser',format:'iife'});"],cwd=ROOT,env=env,check=True)
    config=base/'host.json';ready=base/'host-ready.json';audit=out/'api.jsonl'
    audit.write_text('')
    config.write_text(json.dumps(dict(serviceUrl=service.url.removesuffix('/api/v1'),sessions=sessions,packages=str(packs),ready=str(ready),audit=str(audit))));config.chmod(0o600)
    log=(base/'host.log').open('w')
    gateway=subprocess.Popen(['node','tests/e2e/isolated_host.mjs',str(config)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
    for _ in range(200):
        if ready.exists():break
        if gateway.poll() is not None:raise RuntimeError((base/'host.log').read_text())
        time.sleep(.05)
    host=json.loads(ready.read_text())
    private=ROOT/'work/b07-session.json'
    private.write_text(json.dumps(dict(**host,cookies=cookies,imported=imported,backend_pid=service.process.pid,backend_port=service.port)))
    private.chmod(0o600)
    (out/'live-inputs.json').write_text(json.dumps(dict(status='pass',host_mode='isolated-adapter',formal_host='not_configured',workspaces=host['workspaces'],inputs=imported,packages=package_records),indent=2)+'\n')
    print('B07_ISOLATED_READY',flush=True)
    while True:time.sleep(.5)
except KeyboardInterrupt:pass
finally:
    resources=[]
    if gateway:
        gateway.terminate();gateway.wait(timeout=15)
        resources.append('isolated plugin gateway')
    if service:
        resources.append('private B06 service/worker/data/credentials')
        service.close()
    log.close() if 'log' in locals() else None
    shutil.rmtree(base)
    (ROOT/'work/b07-session.json').unlink(missing_ok=True)
    (out/'resources.json').write_text(json.dumps(dict(status='pass',resources_created=resources,resources_cleaned=resources),indent=2)+'\n')
