// Uses current host's real tab registry, controller, store and SlotCore.
// The surrounding conversation/side pane rendering and backend API are fixtures.
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import http from 'node:http';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';

const [archive,output]=process.argv.slice(2);if(!output)throw Error('archive output required');
await fs.mkdir(output,{recursive:false});
const temp=await fs.mkdtemp(path.join(os.tmpdir(),'heater-sidebar-'));
execFileSync('tar',['-xzf',path.resolve(archive),'-C',temp]);
const local=createRequire(new URL('../plugin/package.json',import.meta.url));
const ref=createRequire('/data/qmh/satellite-plugins-20261029/dsh-satellite-drawings/package.json');
const {build}=local('esbuild');const {chromium}=ref('playwright');
const host='/data/lbk/codex_web/deepseek-harness2';
const moduleRoot=host+'/packages/client/ui-sidebar-right/lib/types/client';
const fixture=`
import React,{useSyncExternalStore,useState} from ${JSON.stringify(ref.resolve('react'))};
import {createRoot} from ${JSON.stringify(ref.resolve('react-dom/client'))};
import {SidebarRightTabRegistry} from '${moduleRoot}/tab-registry.js';
import {createSidebarRightController} from '${moduleRoot}/service.js';
import {createSidebarRightStore} from '${moduleRoot}/stores.js';
import {SlotCore} from '${host}/packages/client/ui-slots/lib/index.js';
const effects=[];
const ctx={effect(setup){const dispose=setup();effects.push(dispose);return dispose;}};
const tabs=new SidebarRightTabRegistry(ctx);ctx.sidebarRightTabs=tabs;
const {controller,adopt,show}=createSidebarRightController(tabs,()=>{},{autoFullscreen:()=>false,openWithFocus:(_,open)=>open(),closeWithFocus:(_,__,close)=>close()});
ctx.sidebarRight=controller;
const core=new SlotCore();
const pending=[];
ctx.slots={inject(name,callback){pending.push({name,callback});},register(options,component){return core.register(options,component);}};
const stores=new Map();let session='sessionA';
function storeOf(id){if(!stores.has(id)){const value=createSidebarRightStore(()=>({kind:'guide',title:'页面'})).create();stores.set(id,value);adopt(id,value);}return stores.get(id);}
storeOf(session);show(session);
window.snapshot=()=>({layout:stores.get(session)?.getSnapshot().bySession[session]?.layout,definitions:tabs.entries().map(x=>({id:x.id,kind:x.kind,keepMounted:x.keepMounted})),guide:tabs.guide().map(x=>({kind:x.kind,title:x.title()})),customDeclared:core.specDynamic('custom.agent.nav')!==undefined});
let setSession;
function Host(){
 const [id,setId]=useState(session);setSession=value=>{session=value;if(value)storeOf(value);show(value);setId(value);};
 const store=id?storeOf(id):storeOf('empty-fixture');
 const state=useSyncExternalStore(store.subscribe,store.getSnapshot);
 const layout=state.bySession[id]?.layout;
 const bodyEntry=core.entries('sidebar.right.pane.tab')[0];
 const action=core.entries('conversation.session.header.actions')[0];
 const pages=[...stores.entries()].flatMap(([owner,value])=>Object.values(value.getSnapshot().bySession[owner]?.layout.tabs??{}).filter(t=>t.kind==='heater-drawing').map(tab=>({owner,tab})));
 return <><header><span>当前会话：{id||'未选择'}</span><action.component sessionId={id} {...action.inject()}/></header><div className="columns"><main><h2>聊天区（测试宿主）</h2><p>工作台嵌入右侧栏，聊天保留在当前页面。</p></main><aside hidden={!layout?.expanded}><div className="strip">矩形加热器出图<button onClick={()=>controller.toggleExpanded()}>折叠侧栏</button><button onClick={()=>{const tab=Object.values(layout.tabs).find(t=>t.kind==='heater-drawing');controller.closeIn(id,tab.id);}}>关闭页签</button></div>{pages.map(({owner,tab})=><div className="body" key={owner+tab.id} hidden={owner!==id}><bodyEntry.component sessionId={owner}/></div>)}</aside></div></>;
}
window.__ModuleLoader__={load(entry){
 const client=entry.factory(name=>{if(name!=='react')throw Error(name);return React;});
 client.apply(ctx);
 core.register({name:'root',children:{'conversation.session.header.actions':{kind:'list',scope:'session'},'sidebar.right.pane.tab':{kind:'keyed',scope:'session'}}},()=>null);
 for(const item of pending)if(core.specDynamic(item.name))item.callback();
 const root=createRoot(document.getElementById('root'));root.render(<Host/>);
 window.changeSession=id=>setSession(id);
 window.openFromGuide=()=>controller.openTab(tabs.guide()[0].kind);
 window.setExpanded=value=>stores.get(session).actions.setExpanded(session,value);
}};
`;
const built=await build({stdin:{contents:fixture,resolveDir:host,sourcefile:'sidebar-fixture.jsx',loader:'jsx'},bundle:true,write:false,platform:'browser',format:'iife',alias:{react:path.dirname(ref.resolve('react')),'react-dom':path.dirname(ref.resolve('react-dom'))},plugins:[{name:'fixture-no-chrome-css',setup(build){build.onLoad({filter:/\.css$/},()=>({contents:'export default {};',loader:'js'}));}}]});
const client=await fs.readFile(path.join(temp,'package/lib/client.js'));
const requests=[];
const server=http.createServer(async(req,res)=>{
 try{
  const url=new URL(req.url,'http://localhost');
  if(url.pathname==='/harness.js'){res.setHeader('content-type','text/javascript');return res.end(built.outputFiles[0].contents);}
  if(url.pathname==='/client.js'){res.setHeader('content-type','text/javascript');return res.end(client);}
  if(url.pathname.startsWith('/api/satellite-heater/')){
   requests.push({path:url.pathname,session:req.headers['x-heater-session']});
   res.setHeader('content-type','application/json');
   return res.end(JSON.stringify(url.pathname.endsWith('/jobs')?{jobs:[]}:{ready:true,formats:['dwg','dxf','pdf']}));
  }
  if(url.pathname.startsWith('/satellite-heater/')){
   const name=url.pathname.slice('/satellite-heater/'.length)||'index.html';
   if(!['index.html','app.js','app.css','pdf.mjs','pdf.worker.mjs'].includes(name)){res.statusCode=404;return res.end();}
   res.setHeader('content-type',name.endsWith('.html')?'text/html; charset=utf-8':name.endsWith('.css')?'text/css':'text/javascript');
   return res.end(await fs.readFile(path.join(temp,'package/public',name)));
  }
  res.setHeader('content-type','text/html; charset=utf-8');res.end('<!doctype html><html lang="zh"><title>Heater sidebar verification</title><style>*{box-sizing:border-box}body{margin:0;font-family:system-ui;color:#183147}header{height:56px;display:flex;justify-content:space-between;align-items:center;padding:12px 20px;border-bottom:1px solid #ccd8e2}.columns{display:flex;height:calc(100vh - 56px)}main{flex:1;padding:24px}aside{width:62%;border-left:1px solid #ccd8e2;display:flex;flex-direction:column;min-width:0}[hidden]{display:none!important}.strip{padding:10px;background:#eaf1f5;display:flex;gap:8px;align-items:center}.body{flex:1;min-height:0}button{cursor:pointer;padding:6px 12px}</style><div id="root"></div><script src="/harness.js"></script><script src="/client.js"></script></html>');
 }catch(error){res.statusCode=500;res.end(String(error));}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin='http://127.0.0.1:'+server.address().port;
const summary={archive:path.resolve(archive),sha256:createHash('sha256').update(await fs.readFile(archive)).digest('hex'),target_dsh:'0.2.2-rc.1-102617d-dirty',host:'Actual current host SidebarRightTabRegistry, controller, store and SlotCore, real React/Chromium; fixture surrounding shell and backend API',checks:[],live_dsh_installation:'not_run'};
let browser;
try{
 browser=await chromium.launch({headless:true,executablePath:'/data/qmh/satellite-plugins-20261029/dsh-satellite-drawings/.tools/playwright/chromium-1208/chrome-linux64/chrome',args:['--no-sandbox']});
 const context=await browser.newContext({viewport:{width:1500,height:1000}});const page=await context.newPage();const errors=[];page.on('pageerror',e=>{errors.push(e.message);console.error('BROWSER:',e.message);});
 await page.goto(origin);const button=page.getByRole('button',{name:'矩形加热器出图',exact:true});await button.waitFor();
 const initial=await page.evaluate(()=>window.snapshot());assert.equal(initial.customDeclared,false);assert.equal(initial.guide[0].title,'矩形加热器出图');assert.equal(initial.definitions[0].keepMounted,true);
 await button.click();const iframe=page.locator('iframe[title="矩形加热器出图"]');await iframe.waitFor();
 await page.frameLocator('iframe').locator('#uploadButton').waitFor();
 assert.equal((await page.evaluate(()=>window.snapshot())).layout.expanded,true);assert.equal(new URL(await iframe.getAttribute('src'),origin).searchParams.get('session'),'sessionA');
 summary.checks.push('packaged client registers native sidebar page and guide entry with actual current host services, without agent-page','header button opens expanded native sidebar state');
 await button.click();assert.equal(Object.values((await page.evaluate(()=>window.snapshot())).layout.tabs).filter(t=>t.kind==='heater-drawing').length,1);
 summary.checks.push('repeated opening reuses page within pane');
 await page.frameLocator('iframe').locator('#name').fill('保留中的工作簿');await page.getByRole('button',{name:'折叠侧栏'}).click();await page.locator('aside').waitFor({state:'hidden'});await button.click();
 assert.equal(await page.frameLocator('iframe').locator('#name').inputValue(),'保留中的工作簿');
 summary.checks.push('collapse and reopen preserve iframe form');
 for(const session of ['sessionB','session &中文/#']){
  await page.evaluate(id=>window.changeSession(id),session);await button.click();
  const current=page.locator('.body:not([hidden]) iframe');await current.waitFor();
  assert.equal(new URL(await current.getAttribute('src'),origin).searchParams.get('session'),session);
 }
 await page.evaluate(()=>window.changeSession('sessionA'));await button.click();
 assert.equal(await page.locator('.body:not([hidden]) iframe').contentFrame().locator('#name').inputValue(),'保留中的工作簿');
 summary.checks.push('session switching uses isolated encoded workbench URLs and restores retained form');
 await page.getByRole('button',{name:'关闭页签'}).click();assert.equal((await page.evaluate(()=>window.snapshot())).layout.tabs&&Object.values((await page.evaluate(()=>window.snapshot())).layout.tabs).filter(t=>t.kind==='heater-drawing').length,0);
 await page.evaluate(()=>window.openFromGuide());await page.locator('.body:not([hidden]) iframe').waitFor();
 summary.checks.push('closing page removes tab; guide navigation reopens it');
 const currentFrame=page.locator('.body:not([hidden]) iframe').contentFrame();await currentFrame.locator('#uploadButton').waitFor();
 await page.screenshot({path:path.join(output,'sidebar-fixture.png')});
 await page.locator('aside').evaluate(el=>el.style.width='420px');
 assert.equal(await currentFrame.locator('#uploadButton').isVisible(),true);
 assert.equal(await currentFrame.locator('body').evaluate(el=>el.scrollWidth<=innerWidth),true);
 summary.checks.push('actual packaged workbench renders in iframe at 420px without document horizontal overflow');
 await page.evaluate(()=>window.changeSession(undefined));await page.waitForFunction(()=>document.querySelector('header button').disabled);assert.equal(await button.isDisabled(),true);
 assert.equal(context.pages().length,1);assert.equal(page.url(),origin+'/');assert.deepEqual(errors,[]);
 assert.ok(requests.some(r=>r.session==='sessionA'));assert.ok(requests.some(r=>r.session==='sessionB'));
 summary.checks.push('no browser tab or page navigation','missing-session guard','workbench requests carry owning session','no browser script errors');summary.status='passed';
}catch(error){summary.status='failed';summary.error=String(error);throw error;}
finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));await fs.writeFile(path.join(output,'summary.json'),JSON.stringify(summary,null,2)+'\n');await fs.rm(temp,{recursive:true,force:true});}
console.log(JSON.stringify(summary,null,2));
