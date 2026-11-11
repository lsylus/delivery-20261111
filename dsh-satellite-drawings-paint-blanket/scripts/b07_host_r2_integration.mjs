// Real deployed DSH services and Gateway, synthetic account repository/credentials,
// real packed plugin entrypoints and real Python HTTP backend. Never contacts 9999.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {spawn,spawnSync} from 'node:child_process';
import {createHash,randomBytes} from 'node:crypto';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {chromium,expect} from '@playwright/test';
const root=path.resolve(import.meta.dirname,'..');
const runtime='/data/lbk/codex_web/deepseek-harness-no-history';
const requireHost=createRequire(runtime+'/apps/cli/package.json');
const hostImport=async name=>import(pathToFileURL(requireHost.resolve(name)).href);
const {Context}=await hostImport('@deepseek-ai/cordis');
const {default:WebServer}=await hostImport('@deepseek-ai/dsh-host-webserver');
const Connection=await import(pathToFileURL(runtime+'/packages/client/connection/lib/index.js'));
const {SessionStore}=await hostImport('@deepseek-ai/dsh-session');
const {ToolsService}=await hostImport('@deepseek-ai/dsh-tools');
const {createGateway}=await import(pathToFileURL(runtime+'/packages/custom/auth/src/server/gateway.ts'));
const work=await fs.mkdtemp('/data/qmh/b07-host-r2-e2e-');
const out=root+'/work/host-r2';await fs.mkdir(out,{recursive:true});
const backendRoot=work+'/backend',python=root+'/.venv-host/bin/python';
const run=(args)=>{const p=spawnSync(python,args,{cwd:root,encoding:'utf8'});if(p.status!==0)throw Error(p.stderr||p.stdout);return p.stdout;};
run(['scripts/host_backend.py','--root',backendRoot,'init']);
await build({entryPoints:[root+'/tests/e2e/host-r2.tsx'],outfile:out+'/host-ui.js',bundle:true,platform:'browser',format:'iife'});
const log=await fs.open(out+'/backend.log','w');
const backend=spawn(python,['scripts/serve_host.py','--config',backendRoot+'/config.json','--ready-file',work+'/ready.json','--port','0'],{cwd:root,stdio:['ignore',log.fd,log.fd]});
const hosts=[],records=[];let gateway;
async function check(name,fn){await fn();records.push({name,status:'pass'});console.log('PASS',name);}
try{
  for(let i=0;i<200;i++){try{await fs.access(work+'/ready.json');break;}catch{await new Promise(r=>setTimeout(r,100));}}
  const ready=JSON.parse(await fs.readFile(work+'/ready.json','utf8')),serviceUrl=`http://127.0.0.1:${ready.port}`;
  async function createAccount(user){
    const hash=createHash('sha256').update(user).digest('hex'),home=work+'/users/'+hash+'/home';
    await fs.mkdir(home,{recursive:true,mode:0o700});
    await fs.writeFile(home+'/private-plugin-context.json',JSON.stringify({userId:user,home,harnessRoot:runtime}),{mode:0o600});
    const ctx=new Context();hosts.push(ctx);
    ctx.provide('profileContext',{name:'web',home,dir:home+'/profiles/web',installAnchor:runtime+'/apps/cli/package.json',cwd:work,startedBundles:[],overlays:[]});
    const creds=new Map();ctx.provide('credentials',{async modifyRecord(k,fn){const v=await fn(creds.get(k));if(v)creds.set(k,v);return creds.get(k);}});
    ctx.provide('systemPrompt',{tools(){return()=>{};}});
    await ctx.plugin(WebServer,{host:'127.0.0.1',port:0}).await();
    await ctx.plugin(Connection).await();await ctx.plugin(SessionStore).await();await ctx.plugin(ToolsService).await();
    const sessions=[],sessionScopes=[];
    for(let i=0;i<2;i++){const fiber=ctx.inject(['sessions'],c=>{sessions.push(c.sessions.create(`${user}-chat-${i}`,{meta:{cwd:work}}));});await fiber.await();sessionScopes.push(fiber);}
    const origin=ctx.webServer.getOrigin();
    ctx.webServer.register({kind:'exact',path:'/',handler:(req,res)=>{if(ctx.connection.authorizeIndex(req,res)){res.end('isolated real DSH host');}}});
    for(const module of ['paint','blanket'])ctx.webServer.register({kind:'exact',path:'/client/'+module+'.js',handler:async(req,res)=>{if(ctx.connection.requestRejection(req)){res.writeHead(401);return res.end();}res.setHeader('content-type','application/javascript');res.end(await fs.readFile(out+`/unpacked/${module}/package/lib/client.js`));}});
    ctx.webServer.register({kind:'exact',path:'/host-ui.js',handler:async(req,res)=>{res.setHeader('content-type','application/javascript');res.end(await fs.readFile(out+'/host-ui.js'));}});
    ctx.webServer.register({kind:'exact',path:'/host',handler:(req,res)=>{res.setHeader('content-type','text/html; charset=utf-8');res.end('<div id="host-root"></div><script src="/host-ui.js"></script>');}});
    const launch=ctx.connection.authenticatedUrl(origin+'/');
    const response=await fetch(launch,{redirect:'manual'});assert.equal(response.status,303);
    const cookie=response.headers.get('set-cookie').split(';')[0];
    const plugins=[];
    for(const module of ['paint','blanket']){
      const plugin=await import(pathToFileURL(out+`/unpacked/${module}/package/lib/index.mjs`));
      const fiber=ctx.plugin(plugin,{serviceUrl,tenant:'xingqiao-9999'});await fiber.await();plugins.push(fiber);
      const infoResponse=await fetch(origin+`/api/satellite-${module}/host-info`,{headers:{cookie}});
      assert.equal(infoResponse.status,200,'plugin must register in actual DSH');
      const info=await infoResponse.json(),file=work+`/${user}-${module}-public.json`;
      await fs.writeFile(file,JSON.stringify(info));run(['scripts/host_backend.py','--root',backendRoot,'enroll','--public-info',file,'--user',user]);
    }
    return {ctx,origin,cookie,sessions,sessionScopes,plugins};
  }
  const alice=await createAccount('qmh'),bob=await createAccount('other-test-account');
  const browserTokens=new Map([[randomBytes(24).toString('hex'),'qmh'],[randomBytes(24).toString('hex'),'other-test-account']]);
  const tokenFor=user=>[...browserTokens].find(([,v])=>v===user)[0];
  const accountMap=new Map([['qmh',alice],['other-test-account',bob]]);
  const config={allowedHosts:[],secureCookies:false,allowRegistration:false};
  const unexpected=async()=>{throw Error('No account writes in test fixture');};
  const store={resolveSession:async token=>browserTokens.get(token)||null,isAdmin:async()=>false,close:unexpected,createUser:unexpected,authenticate:unexpected,listUsers:unexpected,setPassword:unexpected,changePassword:unexpected,createSession:unexpected,deleteSession:async token=>browserTokens.delete(token)};
  gateway=await createGateway(config,store,'',{get:async user=>accountMap.get(user),close:async()=>{}});
  await gateway.listen({host:'127.0.0.1',port:0});const origin=`http://127.0.0.1:${gateway.server.address().port}`;config.allowedHosts.push(new URL(origin).host);
  const api=async(module,route,{user='qmh',session=alice.sessions[0].id,method='GET',body,headers={}}={})=>fetch(origin+`/api/satellite-${module}`+route,{method,redirect:'manual',headers:{cookie:'dsh-user-session='+tokenFor(user),'x-satellite-session':session,...(method!=='GET'?{origin,'content-type':'application/json'}:{}),...headers},body:body===undefined?undefined:typeof body==='string'||Buffer.isBuffer(body)?body:JSON.stringify(body)});
  let project;
  await check('real DSH Node22 packed plugins + gateway account context',async()=>{
    const result=await api('paint','/context');assert.equal(result.status,200);const v=await result.json();
    assert.equal(v.session_id,alice.sessions[0].id);assert.equal(v.host_mode,'dsh-account');assert.notEqual(v.owner_id,alice.ctx.connection.browserPeer.id);
    const health=await api('paint','/service/health');assert.equal(health.status,200,await health.text());
  });
  await check('anonymous, cross-origin and unknown or foreign live session denied',async()=>{
    assert.equal((await fetch(origin+'/api/satellite-paint/context')).status,401);
    assert.equal((await api('paint','/context',{headers:{origin:'http://evil.invalid'}})).status,403);
    assert.equal((await api('paint','/context',{session:'invented'})).status,401);
    assert.equal((await api('paint','/context',{session:bob.sessions[0].id})).status,401);
  });
  await check('TEST project create, binding and cross-owner rejection',async()=>{
    assert.equal((await api('paint','/service/projects',{method:'POST',body:{name:'production',module:'paint'}})).status,422);
    const response=await api('paint','/service/projects',{method:'POST',body:{name:'TEST-qmh-host-r2',module:'paint'}});assert.equal(response.status,201,await response.clone().text());project=await response.json();
    const b={session_id:alice.sessions[0].id,module:'paint',project_id:project.id,expected_revision:'empty'};
    assert.equal((await api('paint',`/service/sessions/${b.session_id}/binding`,{method:'PUT',body:b})).status,200);
    assert.equal((await api('paint','/service/projects/'+project.id,{user:'other-test-account',session:bob.sessions[0].id})).status,404);
  });
  let model,revision,runId,assetId;
  await check('actual STEP import, GLB/mesh-map reads and other-session artifact denial',async()=>{
    const step=await fs.readFile(root+'/fixtures/synthetic/assembly-tree.step');
    const upload=await api('paint',`/service/projects/${project.id}/assets`,{method:'POST',body:step,headers:{'content-type':'application/step','x-filename':'assembly-tree.step'}});
    assert.equal(upload.status,201,await upload.clone().text());const asset=await upload.json();assetId=asset.id;
    const imported=await api('paint',`/service/projects/${project.id}/imports`,{method:'POST',body:{asset_id:asset.id,main_file:asset.filename,format_options:{},expected_revision:'empty',idempotency_key:'host-r2-import'}});
    assert.equal(imported.status,202,await imported.clone().text());runId=(await imported.json()).run_id;
    let run;for(let i=0;i<400;i++){run=await (await api('paint','/service/runs/'+runId)).json();if(['succeeded','failed'].includes(run.state))break;await new Promise(r=>setTimeout(r,100));}
    assert.equal(run.state,'succeeded',JSON.stringify(run.error));
    const p=await (await api('paint','/service/projects/'+project.id)).json();revision=await (await api('paint',`/service/projects/${project.id}/revisions/${p.module_states.paint}`)).json();
    model=await (await api('paint',`/service/projects/${project.id}/models/${revision.model_ref.model_id}`)).json();
    for(const artifact of model.artifacts){const route='/service'+artifact.download_url.replace('/api/v1','');assert.equal((await api('paint',route)).status,200);assert.equal((await api('paint',route,{session:alice.sessions[1].id})).status,403);}
    assert.equal((await api('blanket','/service/runs/'+runId)).status,404);
  });
  const execContext={agent:{id:alice.sessions[0].id,session:alice.sessions[0]},signal:new AbortController().signal};
  const native=async(module,name,args)=>alice.ctx.tools.get(`satellite_${module}_${name}`).execute(args,execContext);
  async function nativeWait(module,id){for(let i=0;i<500;i++){const v=await native(module,'run',{run_id:id,action:'status'});if(['succeeded','failed','cancelled'].includes(v.state)){assert.equal(v.state,'succeeded',JSON.stringify(v.error));return v;}await new Promise(r=>setTimeout(r,100));}throw Error('native job timeout');}
  await check('both registered native operation/run tools save and restore exact session-bound engineering',async()=>{
    for(const module of ['paint','blanket']){
      const status=await native(module,'host_status',{});assert.equal(status.module,module);assert.equal(status.user,'qmh');
      if(module==='blanket'){
        const b={session_id:alice.sessions[0].id,module,project_id:project.id,expected_revision:'empty'};
        assert.equal((await api(module,`/service/sessions/${b.session_id}/binding`,{method:'PUT',body:b})).status,200);
        const response=await api(module,`/service/projects/${project.id}/imports`,{method:'POST',body:{asset_id:assetId,main_file:'assembly-tree.step',format_options:{},expected_revision:'empty',idempotency_key:'host-r2-blanket-import'}});
        // Use the already uploaded project asset, not a second file copy.
        if(response.status!==202)throw Error(await response.text());await nativeWait(module,(await response.json()).run_id);
      }
      const saved=await nativeWait(module,(await native(module,'operation',{operation:'engineering.save',parameters:{}})).run_id);
      const bundle=saved.artifacts.find(a=>a.role==='engineering_bundle');assert.ok(bundle);
      await nativeWait(module,(await native(module,'operation',{operation:'engineering.restore',parameters:{artifact_id:bundle.id}})).run_id);
      const other=module==='paint'?'blanket':'paint';
      await assert.rejects(native(other,'run',{run_id:saved.id,action:'status'}));
    }
    await assert.rejects(alice.ctx.tools.get('satellite_paint_host_status').execute({}, {agent:{id:bob.sessions[0].id,session:bob.sessions[0]},signal:new AbortController().signal}));
    const aborted=new AbortController();aborted.abort();await assert.rejects(alice.ctx.tools.get('satellite_paint_host_status').execute({}, {...execContext,signal:aborted.signal}));
  });
  await check('packed browser UI through actual gateway: both modules STEP, view, save/restore, paint drawing and host draft',async()=>{
    const browser=await chromium.launch({headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
    let browserPage;
    try{
      const context=await browser.newContext({viewport:{width:1600,height:1100}});
      await context.addCookies([{name:'dsh-user-session',value:tokenFor('qmh'),url:origin,httpOnly:true,sameSite:'Strict'}]);
      const page=await context.newPage();browserPage=page;page.setDefaultTimeout(45000);
      for(const module of ['paint','blanket']){
        await page.goto(origin+`/satellite-${module}/?session=${alice.sessions[1].id}`);
        await expect(page.getByTestId('identity')).toContainText('qmh-chat-1');
        await page.getByRole('button',{name:'新建工程',exact:true}).click();
        await expect(page.getByTestId('project')).not.toHaveText('');
        await page.getByLabel('导入 STEP',{exact:true}).setInputFiles(root+'/fixtures/synthetic/box-100.step');
        await expect(page.getByTestId('viewer')).toHaveAttribute('data-ready','true',{timeout:60000});
        if(module==='paint')await expect(page.getByTestId('assembly-tree')).toBeVisible();
        {
          const projectId=await page.getByTestId('project').innerText();
          const get=async route=>(await api(module,'/service'+route,{session:alice.sessions[1].id})).json();
          const p=await get('/projects/'+projectId),rev=await get(`/projects/${projectId}/revisions/${p.module_states[module]}`),m=await get(`/projects/${projectId}/models/${rev.model_ref.model_id}`);
          const map=await get(m.artifacts.find(a=>a.relative_storage_path.endsWith('mesh-map.json')).download_url.replace('/api/v1',''));
          if(module==='paint'){
          const index=map.faces.findIndex(f=>f.face_ref.signature.normal?.[2]>.9);assert.ok(index>=0);
          await page.getByLabel('目标面',{exact:true}).selectOption(String(index));
          await page.getByRole('button',{name:'生成保护区',exact:true}).click();
          await expect(page.getByTestId('drawing')).toBeVisible({timeout:60000});
          }else{
            const bottom=map.faces.findIndex(f=>f.face_ref.signature.normal?.[2]<-.9);assert.ok(bottom>=0);
            await page.getByLabel('目标面',{exact:true}).selectOption(String(bottom));
            await page.getByRole('button',{name:'设为安装底面',exact:true}).click();
            for(let i=0;i<map.faces.length;i++)if(i!==bottom){await page.getByLabel('目标面',{exact:true}).selectOption(String(i));await page.getByRole('button',{name:'加入包覆面',exact:true}).click();}
            await page.getByRole('button',{name:'生成罩形',exact:true}).click();await expect(page.getByTestId('baseline')).toContainText('baseline-',{timeout:60000});
            await page.getByRole('button',{name:'预览真实展开',exact:true}).click();
            await page.getByRole('button',{name:'执行修改',exact:true}).click();
            await expect(page.getByTestId('blanket-drawing')).toBeVisible({timeout:60000});
          }
        }
        await page.getByRole('button',{name:'保存工程包',exact:true}).click();
        await expect(page.getByRole('status')).toContainText('工程包已保存');
        await page.reload();await expect(page.getByTestId('viewer')).toHaveAttribute('data-ready','true');
        await page.getByRole('button',{name:'恢复工程包',exact:true}).click();
        await expect(page.getByRole('button',{name:'恢复工程包',exact:true})).toBeEnabled();
        await expect(page.getByRole('alert')).toHaveCount(0);
        await page.screenshot({path:out+`/browser-${module}.png`,fullPage:true});
      }
      await page.goto(origin+'/host?session='+alice.sessions[1].id);
      const frame=page.frameLocator('iframe');await expect(frame.getByTestId('drawing')).toBeVisible();
      await frame.getByRole('button',{name:'带入聊天草稿',exact:true}).click();
      await expect(page.getByTestId('host-draft')).not.toHaveValue('');
      const draft=await page.getByTestId('host-draft').inputValue();assert.ok(draft.includes(alice.sessions[1].id));
      await page.evaluate(()=>window.postMessage({type:'satellite-drawings:chat',request_id:'forged',selection:{}},location.origin));
      await expect(page.getByTestId('host-draft')).toHaveValue(draft);
      await page.getByRole('button',{name:'多层入口',exact:true}).click();
      await expect(frame.getByRole('heading',{name:'多层图纸工作台',exact:true})).toBeVisible();
      await expect(page.getByTestId('host-draft')).toHaveValue('');
      await expect(frame.getByTestId('blanket-drawing')).toBeVisible();
      await page.screenshot({path:out+'/browser-host-slots.png',fullPage:true});
      await page.goto(origin+'/satellite-paint/?session=not-a-live-session');await expect(page.getByRole('alert')).toBeVisible();await expect(page.getByTestId('viewer')).toHaveCount(0);
    }catch(e){if(browserPage){await browserPage.screenshot({path:out+'/browser-failure.png',fullPage:true});await fs.writeFile(out+'/browser-failure.txt',await browserPage.locator('body').innerText());}throw e;}finally{await browser.close();}
  });
  await check('project read-only and revoked membership enforced on direct and indirect routes',async()=>{
    run(['scripts/host_backend.py','--root',backendRoot,'project-access','--project',project.id,'--owner',project.owner_id,'--access','read']);
    assert.equal((await api('paint','/service/projects/'+project.id)).status,200);
    assert.equal((await api('paint',`/service/runs/${runId}/cancel`,{method:'POST',body:{}})).status,403);
    run(['scripts/host_backend.py','--root',backendRoot,'project-access','--project',project.id,'--owner',project.owner_id,'--access','deny']);
    assert.equal((await api('paint','/service/runs/'+runId)).status,403);
    assert.equal((await api('paint','/service/projects/'+project.id)).status,403);
    run(['scripts/host_backend.py','--root',backendRoot,'project-access','--project',project.id,'--owner',project.owner_id,'--access','write']);
  });
  await check('plugin unload drops authority; reload retains enrolled key and actual tools',async()=>{
    const previous=await native('paint','host_status',{});
    await alice.plugins[0].dispose();
    assert.equal(alice.ctx.tools.get('satellite_paint_operation'),undefined);
    assert.equal((await api('paint','/context')).status,404);
    const plugin=await import(pathToFileURL(out+'/unpacked/paint/package/lib/index.mjs'));
    const fiber=alice.ctx.plugin(plugin,{serviceUrl,tenant:'xingqiao-9999'});await fiber.await();alice.plugins[0]=fiber;
    assert.equal((await native('paint','host_status',{})).kid,previous.kid);
    assert.equal((await api('paint','/service/health')).status,200);
  });
  await check('account logout revokes subsequent proxy traffic',async()=>{
    const key=tokenFor('other-test-account');browserTokens.delete(key);
    const result=await fetch(origin+'/api/satellite-paint/context',{headers:{cookie:'dsh-user-session='+key,'x-satellite-session':bob.sessions[0].id}});assert.equal(result.status,401);
  });
  await check('disposed live session cannot be revived by frontend session id',async()=>{
    await alice.sessionScopes[1].dispose();assert.equal((await api('paint','/context',{session:alice.sessions[1].id})).status,401);
  });
  await check('new backend outage returns error without demo fallback',async()=>{
    backend.kill('SIGTERM');await new Promise(resolve=>backend.once('exit',resolve));
    assert.equal((await api('paint','/service/health')).status,502);
  });
}catch(e){console.error('Integration failure:',e);throw e;}finally{
  await gateway?.close();for(const ctx of hosts.reverse())await ctx.fiber.dispose();
  if(backend.exitCode===null&&backend.signalCode===null){backend.kill('SIGTERM');await new Promise(resolve=>backend.once('exit',resolve));}
  await log.close();
  await fs.writeFile(out+'/integration.json',JSON.stringify({node:process.version,dsh:'0.2.2-rc.1',scope:'real deployed DSH services/gateway; synthetic account store and isolated data, not live 9999',records,work,all_resources_stopped:true},null,2)+'\n');
}
