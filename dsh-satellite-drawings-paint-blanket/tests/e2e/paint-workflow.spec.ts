import {test,expect} from '@playwright/test';
import fs from 'node:fs';
import {createHash} from 'node:crypto';
import {gzipSync} from 'node:zlib';
function record(value:any){return {result_id:value.result_id,revision_id:value.paint.revision_id,model_ref:value.paint.model_ref,status:value.paint.status,regions:value.paint.regions.length,protected_area_mm2:value.paint.regions.reduce((s:number,r:any)=>s+r.area_mm2,0),paint_sha256:createHash('sha256').update(JSON.stringify(value.paint)).digest('hex')};}
const configuration=()=>JSON.parse(fs.readFileSync('work/b09-session.json','utf8'));
async function start(page:any,context:any){const c=configuration();await context.addCookies([{name:'b07_session',value:c.cookie,url:c.origin,httpOnly:true,sameSite:'Strict'}]);await page.goto(c.origin+'/satellite-paint/?session=a-session');await expect(page.getByTestId('viewer')).toHaveAttribute('data-ready','true');return c;}
async function api(page:any,path:string){return page.evaluate(async(path:string)=>{const r=await fetch('/api/satellite-paint/service'+path);if(!r.ok)throw Error(await r.text());return r.json();},path);}
async function rect(page:any,a:number[],b:number[]){await page.getByTestId('drawing').scrollIntoViewIfNeeded();const pixels=await page.getByTestId('drawing').evaluate((svg:any,ps:number[][])=>ps.map(p=>{const q=svg.createSVGPoint();q.x=p[0];q.y=-p[1];const r=q.matrixTransform(svg.getScreenCTM());return [r.x,r.y];}),[a,b]);await page.keyboard.down('Shift');await page.mouse.move(...pixels[0]);await page.mouse.down();await page.mouse.move(...pixels[1],{steps:5});await page.mouse.up();await page.keyboard.up('Shift');}
async function edit(page:any){await page.getByRole('button',{name:'执行修改',exact:true}).click();await expect(page.getByTestId('command-preview')).toHaveCount(0);}
test('STEP selection, real regions, chat/control edits, history, persisted drawing and DWG',async({page,context})=>{
 const c=await start(page,context);const selected=await page.getByLabel('目标面').inputValue();await page.getByLabel('目标面').selectOption('');
 const canvas=page.locator('canvas'),box=await canvas.boundingBox();expect(box).not.toBeNull();
 for(const x of [.5,.65,.35,.8,.2]){for(const y of [.5,.35,.65]){await page.mouse.click(box!.x+box!.width*x,box!.y+box!.height*y);if(await page.getByLabel('目标面').inputValue())break;}if(await page.getByLabel('目标面').inputValue())break;}
 await expect(page.getByLabel('目标面')).not.toHaveValue('');await expect(page.getByTestId('selection-count')).toHaveText('已选 1 个面');
 recordSession('real-canvas-selection',{selected_index:await page.getByLabel('目标面').inputValue(),selection_count:await page.getByTestId('selection-count').innerText()});
 await page.getByLabel('目标面').selectOption(selected);
 await page.getByRole('button',{name:'生成保护区',exact:true}).click();await expect(page.getByTestId('check-state')).toHaveText('规则检查：passed');
 const initial=await api(page,`/projects/${c.project}/paint-result`);
 await page.getByLabel('接触外扩 mm').fill('4');await expect(page.getByRole('button',{name:'导出 DWG 草稿'})).toBeDisabled();await expect(page.getByRole('button',{name:'保存工程包',exact:true})).toBeDisabled();await page.getByLabel('接触外扩 mm').fill('3');
 await rect(page,[-45,25],[-35,35]);await page.getByLabel('对话修改').fill('这里补保护');await page.getByRole('button',{name:'预览对话修改'}).click();await expect(page.getByTestId('command-preview')).toContainText(initial.result_id);await expect(page.getByRole('button',{name:'导出 DWG 草稿'})).toBeDisabled();await edit(page);
 const edited=await api(page,`/projects/${c.project}/paint-result`);expect(edited.paint.revision_id).not.toBe(initial.paint.revision_id);
 const area=(r:any)=>r.paint.regions.reduce((n:number,p:any)=>n+p.area_mm2,0);expect(area(edited)-area(initial)).toBeCloseTo(100,2);
 await page.getByRole('button',{name:'撤销修改',exact:true}).click();await expect(page.getByTestId('drawing')).toHaveAttribute('data-revision',initial.paint.revision_id);
 await page.getByRole('button',{name:'重做修改',exact:true}).click();await expect(page.getByTestId('drawing')).toHaveAttribute('data-revision',edited.paint.revision_id);
 await rect(page,[-45,25],[-35,35]);await page.getByRole('button',{name:'保留喷漆',exact:true}).click();await edit(page);const excluded=await api(page,`/projects/${c.project}/paint-result`);expect(area(excluded)).toBeCloseTo(area(initial),2);
 await page.getByRole('button',{name:'撤销修改',exact:true}).click();await expect(page.getByTestId('drawing')).toHaveAttribute('data-revision',edited.paint.revision_id);
 await rect(page,[-45,25],[-35,35]);await page.getByLabel('图纸注释').fill('B09 保护区域待复核');await page.getByRole('button',{name:'放置或移动注释'}).click();await edit(page);
 await page.getByRole('button',{name:'保存工程包',exact:true}).click();await expect(page.getByRole('status')).toContainText('工程包已保存');const saved=await api(page,`/projects/${c.project}/paint-result`);
 await page.reload();await expect(page.getByTestId('viewer')).toHaveAttribute('data-ready','true');await page.getByRole('button',{name:'恢复工程包'}).click();await expect(page.getByTestId('drawing')).not.toHaveAttribute('data-revision',saved.paint.revision_id);
 const restored=await api(page,`/projects/${c.project}/paint-result`);expect(area(restored)).toBeCloseTo(area(saved),8);expect(restored.paint.drawing_document.entities.some((e:any)=>e.text==='B09 保护区域待复核')).toBeTruthy();
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'导出 DWG 草稿'}).click();const d=await download;expect(d.suggestedFilename()).toContain(restored.paint.revision_id);await d.saveAs('docs/evidence/B09/browser.dwg');expect(fs.readFileSync('docs/evidence/B09/browser.dwg').subarray(0,6).toString()).toBe('AC1032');
 await page.screenshot({path:'docs/evidence/B09/workflow.png',fullPage:true});fs.writeFileSync('docs/evidence/B09/browser-paint-result.json.gz',gzipSync(JSON.stringify(restored.paint)));fs.writeFileSync('docs/evidence/B09/browser-flow.json',JSON.stringify({status:'pass',initial:record(initial),edited:record(edited),excluded:record(excluded),saved:record(saved),restored:record(restored)},null,2));
 await context.addCookies([{name:'b07_session',value:c.other_cookie,url:c.origin,httpOnly:true,sameSite:'Strict'}]);await expect(page.getByRole('alert')).toContainText('会话已改变');await expect(page.getByTestId('viewer')).toHaveCount(0);
});
test('existing gearbox STEP plane: UI selection to editable real DWG',async({page,context})=>{
 const c=await start(page,context),candidate=JSON.parse(fs.readFileSync('docs/evidence/B09/real/candidate.json','utf8'));
 await page.getByRole('button',{name:'新建工程',exact:true}).click();await expect(page.getByTestId('viewer')).toHaveCount(0);
 await page.getByLabel('导入 STEP',{exact:true}).setInputFiles(candidate.source_path);await expect(page.getByTestId('viewer')).toHaveAttribute('data-ready','true');
 const project=await page.getByTestId('project').innerText();await page.getByLabel('目标面').selectOption(String(candidate.target_index));await page.getByRole('button',{name:'生成保护区',exact:true}).click();await expect(page.getByTestId('check-state')).toHaveText('规则检查：passed');
 const initial=await api(page,`/projects/${project}/paint-result`),model=await api(page,`/projects/${project}/models/${initial.paint.model_ref.model_id}`);expect(model.snapshot.source_manifest.files[0].sha256).toBe(candidate.source_sha256);
 const revision=await api(page,`/projects/${project}/revisions/${initial.paint.revision_id}`);expect(revision.selection[0].signature).toEqual(candidate.target.signature);
 const pts=candidate.reference_points;await rect(page,pts[0],pts[2]);await page.getByLabel('对话修改').fill('这里补保护');await page.getByRole('button',{name:'预览对话修改'}).click();await edit(page);
 const edited=await api(page,`/projects/${project}/paint-result`);expect(edited.paint.regions.length).toBeGreaterThan(0);
 await page.getByRole('button',{name:'撤销修改',exact:true}).click();await expect(page.getByTestId('drawing')).toHaveAttribute('data-revision',initial.paint.revision_id);
 await page.getByRole('button',{name:'重做修改',exact:true}).click();await expect(page.getByTestId('drawing')).toHaveAttribute('data-revision',edited.paint.revision_id);
 await page.getByRole('button',{name:'保存工程包',exact:true}).click();await expect(page.getByRole('status')).toContainText('工程包已保存');await page.reload();await expect(page.getByTestId('viewer')).toHaveAttribute('data-ready','true');
 await page.getByRole('button',{name:'恢复工程包'}).click();await expect(page.getByTestId('drawing')).not.toHaveAttribute('data-revision',edited.paint.revision_id);
 const restored=await api(page,`/projects/${project}/paint-result`);expect(restored.paint.regions.map((r:any)=>r.loops)).toEqual(edited.paint.regions.map((r:any)=>r.loops));
 const downloading=page.waitForEvent('download');await page.getByRole('button',{name:'导出 DWG 草稿'}).click();const d=await downloading;expect(d.suggestedFilename()).toContain(restored.paint.revision_id);await d.saveAs('docs/evidence/B09/real/browser.dwg');expect(fs.readFileSync('docs/evidence/B09/real/browser.dwg').subarray(0,6).toString()).toBe('AC1032');
 await page.screenshot({path:'docs/evidence/B09/real/workflow.png',fullPage:true});fs.writeFileSync('docs/evidence/B09/real/browser-paint-result.json.gz',gzipSync(JSON.stringify(restored.paint)));fs.writeFileSync('docs/evidence/B09/real/browser-flow.json',JSON.stringify({status:'pass',initial:record(initial),edited:record(edited),restored:record(restored),engineering_truth:'not_reviewed',reference_area_mm2:candidate.reference_area_mm2},null,2));
});
test('host chat draft carries current result and bounded local selection',async({page,context})=>{
 const c=await start(page,context);await page.goto(c.origin+'/host');const frame=page.frameLocator('iframe');await expect(frame.getByTestId('viewer')).toHaveAttribute('data-ready','true');
 const project=await frame.getByTestId('project').innerText(),result=await api(page,`/projects/${project}/paint-result`);
 await frame.getByRole('button',{name:'带入聊天草稿',exact:true}).click();await expect(page.getByTestId('host-draft')).toContainText(result.result_id);await expect(page.getByTestId('host-draft')).toContainText(result.paint.revision_id);
 const text=await page.getByTestId('host-draft').inputValue();await page.evaluate(()=>window.postMessage({type:'satellite-drawings:chat',request_id:'forged',selection:{}},location.origin));await expect(page.getByTestId('host-draft')).toHaveValue(text);
});

// Hold genuine server responses to exercise identity races deterministically.
// No replacement identity, model, run or geometry is manufactured by these tests.
function recordSession(name:string,details:any){fs.mkdirSync('docs/evidence/B09/r1/session',{recursive:true});fs.writeFileSync(`docs/evidence/B09/r1/session/${name}.json`,JSON.stringify({status:'pass',...details},null,2));}
async function closed(page:any){
 await expect(page.getByRole('alert')).toContainText('会话已改变');
 await expect(page.getByTestId('identity')).not.toContainText('alice');
 await expect(page.getByTestId('project')).toHaveText('');
 for(const id of ['viewer','revision','drawing','command-preview','execution-state'])await expect(page.getByTestId(id)).toHaveCount(0);
 await expect(page.locator('button:enabled')).toHaveCount(0);
 await expect(page.getByLabel('导入 STEP',{exact:true})).toBeDisabled();
 await expect(page.getByRole('status')).toHaveCount(0);
 await expect(page.getByRole('button',{name:'取消任务',exact:true})).toHaveCount(0);
}
async function cookie(context:any,c:any,other=false){await context.addCookies([{name:'b07_session',value:other?c.other_cookie:c.cookie,url:c.origin,httpOnly:true,sameSite:'Strict'}]);}
function deferred(){let done=false,complete!:()=>void;const promise=new Promise<void>(r=>complete=r);return {promise,resolve:()=>{done=true;complete();},wait:async()=>{await expect.poll(()=>done,{timeout:90000}).toBe(true);}};}

test('R1 rejects initial URL session mismatch before binding or model access',async({page,context})=>{
 const c=configuration();await cookie(context,c);const serviceRequests:string[]=[];
 page.on('request',r=>{if(r.url().includes('/service/'))serviceRequests.push(r.url());});
 await page.goto(c.origin+'/satellite-paint/?session=stale-session');await closed(page);
 expect(serviceRequests).toEqual([]);
 recordSession('initial-url-mismatch',{requested_session:'stale-session',service_requests:serviceRequests,alerts:await page.getByRole('alert').allTextContents(),viewer_count:await page.getByTestId('viewer').count(),enabled_buttons:await page.locator('button:enabled').count()});
});

for(const change of ['cookie','url'])test(`R1 rejects ${change} session change during initial model loading`,async({page,context})=>{
 const c=configuration();await cookie(context,c);const held=deferred(),release=deferred(),finished=deferred();let oldRevision='';
 await page.route('**/service/projects/*/paint-result',async route=>{
  try{const response=await route.fetch();oldRevision=(await response.json())?.paint.revision_id||c.revision;held.resolve();await release.promise;await route.fulfill({response});}catch{}finally{finished.resolve();}
 });
 try{
  await page.goto(c.origin+'/satellite-paint/?session=a-session');await held.wait();
  await expect(page.getByRole('button',{name:'新建工程',exact:true})).toBeDisabled();
  if(change==='cookie')await cookie(context,c,true);
  else await page.evaluate(()=>history.replaceState(null,'','?session=stale-session'));
  await closed(page);release.resolve();await finished.wait();await page.unrouteAll({behavior:'wait'});await closed(page);
  recordSession(`loading-${change}-change`,{old_response_revision:oldRevision,late_response_released:true,project:await page.getByTestId('project').innerText(),viewer_count:await page.getByTestId('viewer').count()});
 }finally{release.resolve();}
});

for(const operation of ['save','generate'])test(`R1 ignores late ${operation} run response after session change`,async({page,context})=>{
 const c=await start(page,context),project=await page.getByTestId('project').innerText();
 const held=deferred(),release=deferred(),finished=deferred();let heldRun:any,lateProjectReads=0,changed=false;
 const stored=await page.evaluate(()=>JSON.stringify(localStorage));
 page.on('request',r=>{if(changed&&r.url().includes('/service/projects/'))lateProjectReads++;});
 await page.route('**/service/runs/*',async route=>{
  try{let response=await route.fetch();heldRun=await response.json();for(let i=0;i<300&&!['succeeded','failed','cancelled'].includes(heldRun.state);i++){await new Promise(r=>setTimeout(r,100));response=await route.fetch();heldRun=await response.json();}held.resolve();await release.promise;await route.fulfill({response});}catch{}finally{finished.resolve();}
 });
 try{
  await page.getByRole('button',{name:operation==='save'?'保存工程包':'生成保护区',exact:true}).click();await held.wait();
  expect(heldRun.run_id||heldRun.id).toBeTruthy();expect(heldRun.state).toBe('succeeded');
  await expect(page.getByRole('button',{name:'取消任务',exact:true})).toBeVisible();
  await cookie(context,c,true);changed=true;await closed(page);
  release.resolve();await finished.wait();await page.unrouteAll({behavior:'wait'});await closed(page);
  expect(await page.evaluate(()=>JSON.stringify(localStorage))).toBe(stored);expect(lateProjectReads).toBe(0);
  recordSession(`late-${operation}-run`,{original_project:project,run_id:heldRun.run_id||heldRun.id,response_state:heldRun.state,late_response_released:true,late_project_reads:lateProjectReads,local_storage_unchanged:true,viewer_count:await page.getByTestId('viewer').count(),alerts:await page.getByRole('alert').allTextContents()});
 }finally{release.resolve();}
});
