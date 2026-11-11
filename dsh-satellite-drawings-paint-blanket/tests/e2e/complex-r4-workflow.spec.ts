import {test,expect} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
test.describe.configure({mode:'serial'});
const out=process.env.B13_EVIDENCE_DIR||'docs/evidence/B13/r4/browser-development';
const config=()=>JSON.parse(fs.readFileSync('work/b13-r4-session.json','utf8'));
const save=(name:string,value:any)=>{const file=out+'/'+name+'.json';fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,JSON.stringify(value,null,2));};
async function get(page:any,p:string){const r=await page.request.get(config().origin+'/api/satellite-blanket/service'+p);expect(r.status()).toBe(200);return r.json();}
async function start(page:any,context:any){const c=config();await context.addCookies([{name:'b07_session',value:c.cookie,url:c.origin}]);await page.goto(c.origin+'/satellite-blanket/?session=a-blanket');await expect(page.getByTestId('identity')).toContainText('a-blanket');return c;}
async function settled(page:any){await expect(page.getByTestId('current-state')).not.toHaveText('执行中');}
async function apply(page:any){await page.getByRole('button',{name:'执行修改',exact:true}).click();await expect(page.getByTestId('command-preview')).toHaveCount(0);await settled(page);}
async function archive(page:any,id:string,label:string){
 const run=await get(page,'/runs/'+id);expect(run.state).toBe('succeeded');const dir=out+'/blanket-http/'+label;fs.mkdirSync(dir,{recursive:true});
 for(const a of run.artifacts){const r=await page.request.get(config().origin+'/api/satellite-blanket/service/artifacts/'+a.id);expect(r.status()).toBe(200);const bytes=await r.body();expect(createHash('sha256').update(bytes).digest('hex')).toBe(a.sha256);fs.writeFileSync(dir+'/'+path.basename(a.relative_storage_path),bytes);}
 save('run-'+label,{...run});
}
test('fresh upload -> visible installation controls -> full motor connected manufacturing -> restart restore DWG',async({page,context})=>{
 const c=await start(page,context);expect(await page.getByTestId('project').textContent()).toBe('');
 await page.getByRole('button',{name:'新建工程',exact:true}).click();await expect(page.getByTestId('project')).not.toHaveText('');
 const project=(await page.getByTestId('project').textContent())!;save('browser-project',{project});
 await page.getByLabel('导入 STEP',{exact:true}).setInputFiles(c.motor_step);await expect(page.getByTestId('viewer')).toHaveAttribute('data-ready','true');
 const head=await get(page,`/projects/${project}`),rev=await get(page,`/projects/${project}/revisions/${head.module_states.blanket}`);
 expect(rev.parameters).toEqual({});expect(await get(page,`/projects/${project}/blanket-result`)).toBeNull();
 const model=await get(page,`/projects/${project}/models/${rev.model_ref.model_id}`),a=model.artifacts.find((a:any)=>a.relative_storage_path.endsWith('mesh-map.json')),map=await get(page,'/artifacts/'+a.id);expect(map.faces).toHaveLength(44);
 const refs=map.faces.map((x:any)=>x.face_ref);
 const bottoms=refs.map((f:any,i:number)=>({f,i})).filter(({f}:any)=>f.signature.type==='PLANE'&&f.signature.normal[2]<-.99);
 const bottom=bottoms.sort((a:any,b:any)=>a.f.signature.centroid_mm[2]-b.f.signature.centroid_mm[2])[0];
 const xref=refs.findIndex((f:any)=>f.instance_id===bottom.f.instance_id&&f.signature.type==='PLANE'&&f.signature.normal[0]>.99);
 expect(xref).toBeGreaterThanOrEqual(0);
 await page.getByLabel('外形策略').selectOption('faceted_clearance_v1');await page.getByLabel('目标面',{exact:true}).selectOption(String(bottom.i));await page.getByRole('button',{name:'设为安装底面',exact:true}).click();
 await page.getByLabel('安装X参考面').selectOption(String(xref));await page.getByLabel('安装原点参照').selectOption('bounds_min');
 await page.getByRole('button',{name:'核对安装坐标与分段范围'}).click();await expect(page.getByTestId('installation-range')).toBeVisible();expect(Number((await page.getByTestId('installation-range').textContent())!.match(/, ([\d.-]+)\)/)![1])).toBeCloseTo(369,3);
 expect((await get(page,`/projects/${project}`)).module_states.blanket).toBe(rev.id);
 await page.getByLabel('候选间隙 mm').fill('1');await page.getByLabel('安装坐标 X 分段位置 mm').fill('40,300,334');
 await page.screenshot({path:out+'/browser-installation-from-zero.png',fullPage:false});
 await page.getByRole('group',{name:'安装坐标 · 当前实例'}).screenshot({path:out+'/browser-installation-controls.png'});
 await page.getByRole('button',{name:'生成罩形',exact:true}).click();await expect(page.getByTestId('baseline')).toContainText('baseline-');await settled(page);
 const cover=await get(page,`/projects/${project}/blanket-result`);save('blanket-http/initial-cover',cover);await archive(page,cover.result_id,'initial-cover');
 expect(cover.blanket.panels).toHaveLength(34);expect(cover.blanket.checks.find((c:any)=>c.id==='volume_ratio').observed.ratio).toBeLessThanOrEqual(1.2);expect(cover.blanket.checks.find((c:any)=>c.id==='positive_clearance').status).toBe('pass');
 await page.getByRole('button',{name:'预览15mm连接方案',exact:true}).click();await apply(page);await expect(page.getByTestId('blanket-drawing')).toBeVisible();
 let net=await get(page,`/projects/${project}/blanket-net`);save('blanket-http/initial-net',net);await archive(page,net.result_id,'initial-native');
 expect(net.net.panels).toHaveLength(34);expect(net.net.pieces).toHaveLength(33);expect(net.net.overlaps).toHaveLength(75);expect(net.net.diagnostics).toEqual([]);expect(net.net.seams.filter((s:any)=>s.kind==='fold')).toHaveLength(1);expect(net.net.seams.filter((s:any)=>s.kind==='cut')).toHaveLength(0);expect(net.net.overlaps.every((t:any)=>t.width_mm===15)).toBeTruthy();
 const panel=net.net.panels.filter((p:any)=>p.outer_loop.points.length===4&&!p.holes.length).sort((a:any,b:any)=>Math.abs(a.outer_loop.points.reduce((s:number,v:number[],i:number,ps:number[][])=>s+v[0]*ps[(i+1)%4][1]-v[1]*ps[(i+1)%4][0],0))-Math.abs(b.outer_loop.points.reduce((s:number,v:number[],i:number,ps:number[][])=>s+v[0]*ps[(i+1)%4][1]-v[1]*ps[(i+1)%4][0],0))).pop();
 const uv=[0,1].map(k=>panel.outer_loop.points.reduce((s:number,v:number[])=>s+v[k],0)/4);
 await page.getByLabel('编辑裁片').selectOption(panel.key);await page.getByLabel('固定点 U mm').fill(String(uv[0]));await page.getByLabel('固定点 V mm').fill(String(uv[1]));await page.getByRole('button',{name:'预览增加固定点',exact:true}).click();await apply(page);
 net=await get(page,`/projects/${project}/blanket-net`);const point=net.net.fixed_points[0];await page.getByTestId('point-'+point.id).click();await page.getByLabel('固定点 U mm').fill(String(uv[0]+.25));await page.getByRole('button',{name:'预览移动固定点',exact:true}).click();await apply(page);
 net=await get(page,`/projects/${project}/blanket-net`);save('blanket-http/edited-net',net);
 await page.getByRole('button',{name:'保存工程包',exact:true}).click();await expect(page.getByRole('status')).toContainText('工程包已保存');
 // Harness controls infrastructure only: real backend exits, data persists.
 await page.goto('about:blank');fs.writeFileSync(c.restart_request,'restart');await expect.poll(()=>fs.existsSync(c.restart_done),{timeout:60000}).toBe(true);
 await page.goto(c.origin+'/satellite-blanket/?session=a-blanket');await expect(page.getByTestId('blanket-drawing')).toHaveAttribute('data-revision',net.net.revision_id);
 await page.getByRole('button',{name:'恢复工程包',exact:true}).click();await expect(page.getByTestId('blanket-drawing')).not.toHaveAttribute('data-revision',net.net.revision_id);await settled(page);
 const restored=await get(page,`/projects/${project}/blanket-net`);expect(restored.net.fixed_points[0].id).toBe(point.id);expect(restored.net.overlaps).toHaveLength(75);save('blanket-http/restored-net',restored);await archive(page,restored.result_id,'restored-native');
 const exported=page.waitForResponse(async(r:any)=>{if(!/\/runs\//.test(r.url())||r.request().method()!=='GET')return false;try{const v=await r.json();return v.operation==='drawing.export'&&v.state==='succeeded';}catch{return false;}});
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'导出 DWG 草稿',exact:true}).click();await(await download).saveAs(out+'/browser-motor-cover.dwg');const exportRun=await(await exported).json();await archive(page,exportRun.id,'export');expect(fs.readFileSync(out+'/browser-motor-cover.dwg').subarray(0,6).toString()).toBe('AC1032');
 await expect(page.getByTestId('revision')).toHaveText(restored.net.revision_id);await page.screenshot({path:out+'/browser-motor-cover.png',fullPage:false});
 save('from-zero-workflow',{status:'pass',project,imported_revision:rev.id,installation_face:bottom.f,reference_face:refs[xref],cover:cover.blanket,restored_net:restored.net,export_revision:exportRun.revision_id,backend_restart:true,initial_state:'No project, imported model or results; created and uploaded through visible UI',full_acceptance:false});
});

test('frame edits clear cuts, block old net, reject bad values and replace coordinates without replaying old points',async({page,context})=>{
 await start(page,context);await expect(page.getByTestId('blanket-drawing')).toBeVisible();const project=(await page.getByTestId('project').textContent())!,old=await get(page,`/projects/${project}/blanket-net`),cover=await get(page,`/projects/${project}/blanket-result`);
 for(const edit of [async()=>page.getByRole('button',{name:'反转安装X',exact:true}).click(),async()=>page.getByLabel('安装平面内旋转 度').fill('90'),async()=>page.getByLabel('安装原点偏移 X mm').fill('10'),async()=>page.getByLabel('安装原点参照').selectOption('face_center')]){
  await page.getByLabel('安装坐标 X 分段位置 mm').fill('40,300,334');await edit();await expect(page.getByLabel('安装坐标 X 分段位置 mm')).toHaveValue('');await expect(page.getByTestId('blanket-drawing')).toHaveCount(0);await expect(page.getByRole('button',{name:'导出 DWG 草稿',exact:true})).toBeDisabled();await expect(page.getByRole('button',{name:'预览增加固定点',exact:true})).toBeDisabled();await expect(page.getByRole('button',{name:'生成罩形',exact:true})).toBeDisabled();
 }
 for(const axis of ['X','Y','Z'])await page.getByLabel('安装X方向 '+axis,{exact:true}).fill('0');await page.getByRole('button',{name:'核对安装坐标与分段范围'}).click();await expect(page.getByRole('alert')).toContainText('invalid_installation_x_direction');
 await page.getByLabel('安装X方向 Z',{exact:true}).fill('1');await page.getByRole('button',{name:'核对安装坐标与分段范围'}).click();await expect(page.getByRole('alert')).toContainText('installation_x_parallel');
 await page.getByLabel('安装X方向 X',{exact:true}).fill('1');await page.getByLabel('安装X方向 Z',{exact:true}).fill('0');await page.getByLabel('安装原点偏移 X mm').fill('1000001');await page.getByRole('button',{name:'核对安装坐标与分段范围'}).click();await expect(page.getByRole('alert')).toBeVisible();await settled(page);
 await page.getByLabel('安装原点参照').selectOption('bounds_min');await page.getByLabel('安装原点偏移 X mm').fill('10');await page.getByLabel('安装平面内旋转 度').fill('0');await page.getByRole('button',{name:'核对安装坐标与分段范围'}).click();await expect(page.getByTestId('installation-range')).toBeVisible();expect(Number((await page.getByTestId('installation-range').textContent())!.match(/, ([\d.-]+)\)/)![1])).toBeCloseTo(359,3);
 for(const value of ['40,40','300,40','10000','0,1,2,3,4,5,6,7','1,,2']){await page.getByLabel('安装坐标 X 分段位置 mm').fill(value);await expect(page.getByRole('button',{name:'生成罩形',exact:true})).toBeDisabled();}
 expect((await get(page,`/projects/${project}/blanket-net`)).result_id).toBe(old.result_id);
 await page.getByLabel('安装坐标 X 分段位置 mm').fill('30,290,324');await page.getByRole('button',{name:'生成罩形',exact:true}).click();await settled(page);await expect(page.getByTestId('net-stale')).toBeVisible();
 expect(await get(page,`/projects/${project}/blanket-net`)).toBeNull();const changed=await get(page,`/projects/${project}/blanket-result`);expect(changed.blanket.baseline.id).not.toBe(cover.blanket.baseline.id);expect(changed.blanket.baseline.volume_mm3).toBeCloseTo(cover.blanket.baseline.volume_mm3,4);expect(changed.blanket.checks.find((c:any)=>c.id==='volume_ratio').observed.ratio).toBeLessThan(1.2);
 await page.getByRole('button',{name:'预览15mm连接方案',exact:true}).click();await apply(page);const fresh=await get(page,`/projects/${project}/blanket-net`);expect(fresh.net.fixed_points).toEqual([]);expect(fresh.net.overlaps.every((t:any)=>t.width_mm===15)).toBeTruthy();
 // Reselecting the actual bottom must invalidate the preview, even when IDs match.
 await page.getByLabel('目标面',{exact:true}).selectOption(String((await page.getByLabel('目标面').locator('option').allTextContents()).findIndex((s:string)=>s.includes(cover.blanket.parameters.installation_face.entity_id+' ·'))-1));await page.getByRole('button',{name:'设为安装底面',exact:true}).click();await expect(page.getByLabel('安装坐标 X 分段位置 mm')).toHaveValue('');await expect(page.getByTestId('blanket-drawing')).toHaveCount(0);
 save('frame-edit-invalidation',{status:'pass',original_revision:old.net.revision_id,changed_cover:changed,changed_net:fresh,old_fixed_points_not_replayed:true,bad_axes_origin_and_sections_rejected:true});
});

test('wrong or changed session cannot load or republish an installation preview',async({page,context})=>{
 const c=await start(page,context);await page.goto(c.origin+'/satellite-blanket/?session=wrong-session');await expect(page.getByRole('alert')).toContainText('会话已改变');await expect(page.getByTestId('viewer')).toHaveCount(0);
 await page.goto(c.origin+'/satellite-blanket/?session=a-blanket');await expect(page.getByTestId('viewer')).toHaveAttribute('data-ready','true');
 let release:()=>void=()=>{},held=false;const barrier=new Promise<void>(r=>release=r);
 await page.route('**/api/satellite-blanket/service/artifacts/*',async route=>{const response=await route.fetch();if((response.headers()['content-type']||'').includes('json')){held=true;await barrier;}await route.fulfill({response});});
 await page.getByRole('button',{name:'核对安装坐标与分段范围'}).click();await expect.poll(()=>held).toBe(true);
 await context.addCookies([{name:'b07_session',value:c.other_cookie,url:c.origin}]);release();await expect(page.getByRole('alert')).toContainText('会话已改变');await expect(page.getByTestId('viewer')).toHaveCount(0);await expect(page.getByTestId('installation-range')).toHaveCount(0);await expect(page.getByTestId('project')).toHaveText('');
 save('session-invalidation',{status:'pass',wrong_initial_session:true,late_installation_artifact_rejected:true});
});
