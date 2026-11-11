/** Real offline backend and browser flow from an extracted tgz; host adapter is mocked. */
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import http from 'node:http';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';

const [archive,caseFile,out]=process.argv.slice(2);
if(!archive||!caseFile||!out)throw Error('Usage: smoke_packaged_plugin.mjs archive case.xlsx new-output');
await fs.mkdir(out,{recursive:false});
const sandbox=await fs.mkdtemp(path.join(os.tmpdir(),'heater-packaged-smoke-'));
execFileSync('tar',['-xzf',path.resolve(archive),'-C',sandbox]);
const pkg=path.join(sandbox,'package');
const home=path.join(sandbox,'profile/home');await fs.mkdir(home,{recursive:true});
const anchor=path.join(sandbox,'anchor.cjs');await fs.writeFile(anchor,'');
const toolsDir=path.join(sandbox,'node_modules/@deepseek-ai/dsh-tools');await fs.mkdir(toolsDir,{recursive:true});
await fs.writeFile(path.join(toolsDir,'package.json'),JSON.stringify({name:'@deepseek-ai/dsh-tools',type:'module',exports:'./index.mjs'}));
await fs.writeFile(path.join(toolsDir,'index.mjs'),'export const defineTool = value => value;');
const plugin=await import(pathToFileURL(path.join(pkg,'src/index.mjs')));
const sessions=new Map([['sessionA',{id:'sessionA'}],['sessionB',{id:'sessionB'}]]);
const peer={principal:{kind:'owner'},signal:new AbortController().signal};
let cleanups=[],routes=[],tools=[];
const ctx={
 get:key=>key==='profileContext'?{home,installAnchor:anchor}:undefined,
 connection:{browserPeer:peer,requestRejection:req=>req.headers.cookie==='test-owner=1'?null:401,
   admit:req=>({peer:req.headers.cookie==='test-owner=1'?peer:undefined})},
 sessions:{get:id=>sessions.get(id)},tools:{register:tool=>tools.push(tool)},
 effect:fn=>{const cleanup=fn();if(typeof cleanup==='function')cleanups.push(cleanup);},
 inject:(_names,fn)=>fn({effect:fn=>{const cleanup=fn();if(typeof cleanup==='function')cleanups.push(cleanup);},agentWorkspaces:{register:entry=>{assert.equal(entry.key,'heater-drawing');return ()=>{};}}}),
 webServer:{register:route=>{routes.push(route);return ()=>{routes=routes.filter(r=>r!==route);};}},
};
async function stopPlugin(){for(const fn of cleanups.reverse())await fn();cleanups=[];routes=[];tools=[];}
const server=http.createServer((req,res)=>{
 const route=routes.find(r=>req.url===r.path||req.url.startsWith(r.path+'/'));
 if(!route){res.writeHead(404);res.end();return;}route.handler(req,res);
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin='http://127.0.0.1:'+server.address().port;
const results={archive:path.resolve(archive),archive_sha256:createHash('sha256').update(await fs.readFile(archive)).digest('hex'),
 host_installation:'not_run',host_adapter:'mocked authenticated DSH services',backend:'real offline bundled runtime',checks:[]};
const record=name=>{results.checks.push({name,status:'passed'});console.log(name);};
const api=async(route,options={},session='sessionA')=>fetch(origin+'/api/satellite-heater'+route,{...options,
 headers:{cookie:'test-owner=1','x-heater-session':session,origin,...options.headers}});
async function waitJob(id,predicate,timeout=600000){
 const deadline=Date.now()+timeout;let current;
 do{
   const response=await api('/service/jobs/'+id);assert.equal(response.status,200);current=await response.json();
   if(predicate(current))return current;
   if(current.state==='failed'||current.state==='paused_error')throw Error(JSON.stringify(current));
   await new Promise(resolve=>setTimeout(resolve,1500));
 }while(Date.now()<deadline);throw Error('job_timeout '+JSON.stringify(current));
}
let browser;
try{
 await plugin.apply(ctx,{});record('extracted_tgz_offline_startup');
 assert.equal((await fetch(origin+'/api/satellite-heater/context')).status,401);record('unauthenticated_request_rejected');
 assert.equal((await api('/service/capabilities')).status,200);
 const invalid=await api('/service/jobs',{method:'POST',headers:{'content-type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','x-heater-name':'invalid'},body:Buffer.from('not an xlsx')});
 const invalidJob=await invalid.json();assert.equal(invalid.status,202);
 const bad=await waitJob(invalidJob.id,j=>j.state==='awaiting_resolution'||j.state==='failed');
 assert.notEqual(bad.state,'ready');assert.equal(bad.exportable,false);record('invalid_workbook_blocked_without_run');
 const require=createRequire(path.resolve('/data/qmh/satellite-plugins-20261029/dsh-satellite-drawings/package.json'));
 const {chromium}=require('playwright');
 browser=await chromium.launch({headless:true,executablePath:process.env.HEATER_TEST_CHROMIUM||'/data/qmh/satellite-plugins-20261029/dsh-satellite-drawings/.tools/playwright/chromium-1194/chrome-linux/chrome',args:['--no-sandbox']});
 const context=await browser.newContext({viewport:{width:1400,height:1100}});
 await context.addCookies([{name:'test-owner',value:'1',url:origin}]);
 const page=await context.newPage();
 const consoleErrors=[];page.on('pageerror',error=>consoleErrors.push(error.message));
 await page.goto(origin+'/satellite-heater/?session=sessionA');
 await page.getByText('后台已连接',{exact:true}).waitFor();
 await page.locator('#file').setInputFiles(path.resolve(caseFile));
 await page.locator('#name').fill('加热器图纸');
 await page.getByRole('button',{name:'上传并校验',exact:true}).click();
 await page.getByRole('button',{name:'生成 DWG 与 PDF',exact:true}).waitFor({timeout:180000});
 const listing=await (await api('/service/jobs')).json();
 const real=listing.jobs.find(j=>j.name==='加热器图纸');assert.ok(real);
 let current=await waitJob(real.id,j=>j.state==='ready');
 assert.equal(current.total_rows,3);assert.equal(current.expected_pages,3);record('browser_excel_upload_and_real_cad_preflight');
 await page.screenshot({path:path.join(out,'ready.png'),fullPage:true});
 await page.getByRole('button',{name:'生成 DWG 与 PDF',exact:true}).click();
 const firstRun=await waitJob(real.id,j=>['queued','running'].includes(j.state));
 const cancelled=await api(`/service/jobs/${real.id}/runs/${firstRun.run.id}/cancel`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({revision_hash:firstRun.revision.revision_hash})});
 assert.equal(cancelled.status,200);
 const stopped=await waitJob(real.id,j=>j.state==='cancelled');assert.equal(stopped.run.artifacts.length,0);
 assert.equal((await api(`/service/jobs/${real.id}/runs/${firstRun.run.id}/artifacts/unpublished`)).status,404);
 await page.getByRole('button',{name:'生成 DWG 与 PDF',exact:true}).waitFor({timeout:15000});
 await page.getByRole('button',{name:'生成 DWG 与 PDF',exact:true}).click();
 record('cancelled_run_unpublished_and_browser_retry_started');
 current=await waitJob(real.id,j=>j.state==='generated');
 assert.notEqual(current.run.id,firstRun.run.id);
 await page.getByText('完整出图已生成 · 待工程复核',{exact:true}).waitFor({timeout:15000});
 await page.locator('#jobs .job.active small').getByText('完整出图已生成',{exact:true}).waitFor({timeout:15000});
 assert.equal(current.run.artifacts.filter(a=>a.kind==='pdf_single').length,3);
 assert.equal(current.run.review.status,'pending');record('browser_generate_real_dwg_three_single_pdfs_merged_pdf');
 const statusTool=tools.find(t=>t.name==='heater_job_status');assert.ok(statusTool);
 const toolStatus=await statusTool.execute({job_id:real.id},{agent:{id:'sessionA',session:sessions.get('sessionA')},signal:new AbortController().signal});
 assert.equal(toolStatus.state,'generated');record('registered_tool_reads_live_session_job');
 assert.equal((await api('/service/jobs/'+real.id,{},'sessionB')).status,404);record('cross_session_job_denied');
 assert.equal((await api('/service/jobs/'+real.id+'/decisions',{method:'POST',body:'{}',headers:{'content-type':'application/json'}})).status,405);record('raw_confirmation_proxy_denied');
 const downloaded=[];
 for(const artifact of current.run.artifacts.filter(a=>['dwg','pdf_merged','pdf_single','zip','excel_actual','manifest'].includes(a.kind))){
  const route=`/service/jobs/${real.id}/runs/${current.run.id}/artifacts/${artifact.id}`;
  assert.equal((await api(route,{},'sessionB')).status,404);
  const response=await api(route);assert.equal(response.status,200);
  const bytes=Buffer.from(await response.arrayBuffer());assert.equal(createHash('sha256').update(bytes).digest('hex'),artifact.sha256);
  const filename=path.join(out,artifact.path);await fs.mkdir(path.dirname(filename),{recursive:true});await fs.writeFile(filename,bytes);
  downloaded.push({...artifact,local_path:filename});
 }
 results.artifacts=downloaded;record('all_downloaded_files_bound_to_published_hashes');
 assert.equal((await fs.readFile(path.join(out,'加热器图纸.dwg'))).subarray(0,6).toString(),'AC1032');
 await page.getByRole('button',{name:'预览／下载 加热器图纸.pdf',exact:true}).click();
 await page.waitForFunction(()=>document.getElementById('preview').dataset.page==='1'&&document.getElementById('previewStatus').textContent==='',{timeout:30000});
 const ink=await page.locator('#preview').evaluate(canvas=>{
   const pixels=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;let dark=0;
   for(let i=0;i<pixels.length;i+=4)if(pixels[i]<100&&pixels[i+1]<100&&pixels[i+2]<100)dark++;
   return dark;
 });assert.ok(ink>3000,'PDF must visibly contain drawing ink');
 await page.getByRole('button',{name:'下一页',exact:true}).click();
 await page.waitForFunction(()=>document.getElementById('preview').dataset.page==='2');
 await page.getByRole('button',{name:'上一页',exact:true}).click();
 await page.waitForFunction(()=>document.getElementById('preview').dataset.page==='1');
 const downloadPromise=page.waitForEvent('download');await page.getByRole('link',{name:'下载 PDF',exact:true}).click();
 const pdfDownload=await downloadPromise;assert.equal(pdfDownload.suggestedFilename(),'加热器图纸.pdf');
 await page.screenshot({path:path.join(out,'generated-preview.png'),fullPage:true});
 await page.setViewportSize({width:540,height:1000});await page.screenshot({path:path.join(out,'narrow.png'),fullPage:true});
 assert.deepEqual(consoleErrors,[]);record('browser_pdf_preview_and_wide_narrow_layout');
 const forged=await api('/confirm',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({job_id:real.id,action:'review',revision_hash:current.revision.revision_hash,run_id:'old-run',status:'approved',comment:'invalid'})});
 assert.equal(forged.status,409);record('stale_run_review_rejected');
 // Exercise receipt issuance and persistence; this is a test record, not an
 // engineer approval. The test deliberately records rejection.
 const reviewed=await api('/confirm',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({job_id:real.id,action:'review',revision_hash:current.revision.revision_hash,run_id:current.run.id,status:'rejected',comment:'自动化测试记录：未进行工程师正式复核'})});
 assert.equal(reviewed.status,200);const review=await reviewed.json();
 assert.equal(review.status,'rejected');assert.equal(review.manifest_sha,current.run.manifest_sha);
 assert.equal(review.artifacts.length,current.run.artifacts.length);record('host_signed_review_bound_to_run_and_artifact_hashes');
 await browser.close();browser=null;
 await stopPlugin();await plugin.apply(ctx,{});
 const restored=await (await api('/service/jobs/'+real.id)).json();assert.equal(restored.run.id,current.run.id);assert.equal(restored.state,'generated');assert.equal(restored.run.review.status,'rejected');record('backend_restart_preserves_published_run_files_and_review');
 results.status='passed';results.job_id=real.id;results.profile=home;
}finally{
 if(browser)await browser.close();await stopPlugin();await new Promise(resolve=>server.close(resolve));
 await fs.writeFile(path.join(out,'summary.json'),JSON.stringify(results,null,2)+'\n');
}
console.log(JSON.stringify({status:results.status,output:out,checks:results.checks.length}));
