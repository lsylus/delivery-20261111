/** Browser verification of the packaged client with a base-slot-only fixture. */
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import http from 'node:http';
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';

const [archive,output]=process.argv.slice(2);if(!output)throw Error('archive output required');
await fs.mkdir(output,{recursive:false});
const temp=await fs.mkdtemp(path.join(os.tmpdir(),'heater-button-browser-'));
execFileSync('tar',['-xzf',path.resolve(archive),'-C',temp]);
const reference=createRequire('/data/qmh/satellite-plugins-20261029/dsh-satellite-drawings/package.json');
const local=createRequire(new URL('../plugin/package.json',import.meta.url));
const {build}=local('esbuild');
const {chromium}=reference('playwright');
const fixture=`import React from ${JSON.stringify(reference.resolve('react'))};
import {createRoot} from ${JSON.stringify(reference.resolve('react-dom/client'))};
const root=createRoot(document.getElementById('actions'));
window.__ModuleLoader__={load(entry){
 const client=entry.factory(name=>{if(name!=='react')throw Error(name);return React;});
 const registrations=[];
 client.apply({slots:{inject(name,callback){if(name==='conversation.session.header.actions')callback();},register(entry,component){registrations.push({entry,component});}}});
 if(registrations.length!==1)throw Error('base-only registration failed');
 window.renderSession=id=>root.render(React.createElement(registrations[0].component,{sessionId:id}));
 window.renderSession('sessionA');
}};`;
const built=await build({stdin:{contents:fixture,resolveDir:temp,sourcefile:'header-fixture.jsx',loader:'jsx'},bundle:true,write:false,platform:'browser',format:'iife'});
const client=await fs.readFile(path.join(temp,'package/lib/client.js'));
const server=http.createServer((req,res)=>{
 if(req.url==='/harness.js'){res.writeHead(200,{'content-type':'text/javascript'});return res.end(built.outputFiles[0].contents);}
 if(req.url==='/client.js'){res.writeHead(200,{'content-type':'text/javascript'});return res.end(client);}
 if(req.url.startsWith('/satellite-heater/')){res.writeHead(200,{'content-type':'text/plain'});return res.end('workbench navigation target fixture');}
 res.writeHead(200,{'content-type':'text/html; charset=utf-8'});res.end('<!doctype html><html lang="zh"><title>Heater header button verification</title><body><h1>会话标题操作区 · 测试宿主</h1><div id="actions"></div><script src="/harness.js"></script><script src="/client.js"></script></body></html>');
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin='http://127.0.0.1:'+server.address().port;
let browser;const errors=[];
const summary={archive:path.resolve(archive),sha256:createHash('sha256').update(await fs.readFile(archive)).digest('hex'),host:'base-slot-only fixture with real React and packaged client; actual DSH not modified',checks:[]};
try{
 browser=await chromium.launch({headless:true,executablePath:'/data/qmh/satellite-plugins-20261029/dsh-satellite-drawings/.tools/playwright/chromium-1208/chrome-linux64/chrome',args:['--no-sandbox']});
 const context=await browser.newContext();const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 await page.goto(origin);const button=page.getByRole('button',{name:'矩形加热器出图',exact:true});await button.waitFor();
 summary.checks.push('button visible without custom.agent providers');
 for(const session of ['sessionA','sessionB','session &中文/#']){
  await page.evaluate(id=>window.renderSession(id),session);await page.evaluate(()=>new Promise(requestAnimationFrame));
  const opened=context.waitForEvent('page');await button.click();const popup=await opened;await popup.waitForLoadState('domcontentloaded');
  const url=new URL(popup.url());assert.equal(url.origin,origin);assert.equal(url.pathname,'/satellite-heater/');assert.equal(url.searchParams.get('session'),session);
  assert.equal(await popup.evaluate(()=>window.opener===null),true);await popup.close();
 }
 summary.checks.push('click opens same-origin workbench with current session and encoded special characters','new tab has no opener');
 await page.evaluate(()=>window.renderSession(undefined));await page.evaluate(()=>new Promise(requestAnimationFrame));assert.equal(await button.isDisabled(),true);
 summary.checks.push('no-session button disabled');
 await page.evaluate(()=>window.renderSession('sessionB'));await page.evaluate(()=>new Promise(requestAnimationFrame));
 await page.screenshot({path:path.join(output,'header-button-fixture.png')});assert.deepEqual(errors,[]);
 summary.checks.push('no browser script errors');summary.status='passed';
}finally{
 if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));
 await fs.writeFile(path.join(output,'summary.json'),JSON.stringify(summary,null,2)+'\n');
}
console.log(JSON.stringify(summary));
