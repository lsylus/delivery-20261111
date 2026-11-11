import {test,expect} from '@playwright/test';
import fs from 'node:fs';
import {createHash} from 'node:crypto';
import {config,start,get,apply,record,clickSeam,evidence} from './b12-helpers';
test('actual assembly equipment: selected faces, net, chat edit, history, reopen and changed DWG',async({page,context})=>{
 const c=await start(page,context),candidate=c.candidate;
 const canvas=page.locator('canvas'),box=await canvas.boundingBox();expect(box).not.toBeNull();
 for(const x of [.5,.65,.35,.8,.2]){for(const y of [.5,.35,.65]){await page.mouse.click(box!.x+box!.width*x,box!.y+box!.height*y);if(await page.getByLabel('目标面').inputValue())break;}if(await page.getByLabel('目标面').inputValue())break;}
 await expect(page.getByLabel('目标面')).not.toHaveValue('');record('canvas-selection',{status:'pass',index:await page.getByLabel('目标面').inputValue()});
 await page.getByLabel('目标面').selectOption(String(candidate.bottom_index));await page.getByRole('button',{name:'设为安装底面',exact:true}).click();
 for(const i of candidate.face_indices.filter((i:number)=>i!==candidate.bottom_index)){await page.getByLabel('目标面').selectOption(String(i));await page.getByRole('button',{name:'加入包覆面',exact:true}).click();}
 // Exercise explicit open-face selection, then restore the selected five faces.
 await page.getByRole('button',{name:'设为整面开口',exact:true}).click();await expect(page.getByTestId('coverage-selection')).toContainText('整面开口 1');await page.getByRole('button',{name:'加入包覆面',exact:true}).click();
 await page.getByRole('button',{name:'生成罩形',exact:true}).click();await expect(page.getByTestId('baseline')).toContainText('baseline-');
 let cover=await get(page,`/projects/${c.project}/blanket-result`);expect(cover.blanket.baseline.parameters.identity.target_instances).toEqual([candidate.instance.instance_id]);
 const source=await get(page,`/projects/${c.project}/models/${cover.blanket.model_ref.model_id}`);expect(source.snapshot.source_manifest.files[0].sha256).toBe(candidate.source_sha256);
 await page.getByLabel('局部开口').check();await page.getByRole('button',{name:'预览尺寸与开口修改',exact:true}).click();await apply(page);
 await page.getByRole('button',{name:'预览真实展开',exact:true}).click();await apply(page);await expect(page.getByTestId('blanket-drawing')).toBeVisible();
 let n=await get(page,`/projects/${c.project}/blanket-net`);expect(n.net.areas.openings_mm2).toBeCloseTo(100,5);
 const seam=n.net.seams.find((s:any)=>s.kind==='join');await clickSeam(page,page,seam.id);await expect(page.getByTestId('blanket-3d')).toHaveAttribute('data-edge-count','2');await expect(page.getByTestId('target-context')).toContainText('mapping_ref');
 await page.getByLabel('对话修改').fill('这条搭接换到另一边');await page.getByRole('button',{name:'预览对话修改'}).click();await expect(page.getByTestId('command-preview')).toContainText(seam.id);await apply(page);
 let changed=await get(page,`/projects/${c.project}/blanket-net`);expect(changed.net.seams.find((s:any)=>s.id===seam.id).overlap_owner_panel).not.toBe(seam.overlap_owner_panel);
 await page.getByRole('button',{name:'撤销修改',exact:true}).click();await expect(page.getByTestId('blanket-drawing')).toHaveAttribute('data-revision',n.net.revision_id);
 await page.getByRole('button',{name:'重做修改',exact:true}).click();await expect(page.getByTestId('blanket-drawing')).toHaveAttribute('data-revision',changed.net.revision_id);
 await page.getByLabel('编辑裁片').selectOption('z+');await page.getByLabel('固定点 U mm').fill('40');await page.getByLabel('固定点 V mm').fill('40');await page.getByRole('button',{name:'预览增加固定点'}).click();await apply(page);
 n=await get(page,`/projects/${c.project}/blanket-net`);const point=n.net.fixed_points[0];await page.getByTestId(`point-${point.id}`).click();await expect(page.getByTestId('target-context')).toContainText(point.mapping_ref);
 await page.getByLabel('固定点 U mm').fill('45');await page.getByLabel('对话修改').fill('固定点移开孔洞');await page.getByRole('button',{name:'预览对话修改'}).click();await apply(page);
 await page.getByLabel('图纸注释').fill('B12 多层裁片待复核');await page.getByLabel('文字 X').fill('12');await page.getByRole('button',{name:'预览注释布局'}).click();await apply(page);
 await page.getByRole('button',{name:'保存工程包',exact:true}).click();await expect(page.getByRole('status')).toContainText('工程包已保存');n=await get(page,`/projects/${c.project}/blanket-net`);
 await page.getByRole('button',{name:'关闭工程',exact:true}).click();await expect(page.getByTestId('viewer')).toHaveCount(0);await page.getByRole('button',{name:'打开或刷新工程',exact:true}).click();await expect(page.getByTestId('blanket-drawing')).toHaveAttribute('data-revision',n.net.revision_id);
 await page.reload();await expect(page.getByTestId('viewer')).toHaveAttribute('data-ready','true');await page.getByRole('button',{name:'恢复工程包',exact:true}).click();await expect(page.getByTestId('blanket-drawing')).not.toHaveAttribute('data-revision',n.net.revision_id);
 const restored=await get(page,`/projects/${c.project}/blanket-net`);expect(restored.net.fixed_points[0].id).toBe(point.id);expect(restored.net.fixed_points[0].mapping_ref).not.toBe(point.mapping_ref);
 expect(restored.net.drawing_document.entities.some((e:any)=>e.text==='B12 多层裁片待复核'&&e.position[0]===12)).toBeTruthy();
 async function download(label:string){const wait=page.waitForEvent('download');await page.getByRole('button',{name:'导出 DWG 草稿'}).click();const d=await wait,p=`${evidence}/real/${label}.dwg`;await d.saveAs(p);expect(fs.readFileSync(p).subarray(0,6).toString()).toBe('AC1032');return {filename:d.suggestedFilename(),sha256:createHash('sha256').update(fs.readFileSync(p)).digest('hex')};}
 const first=await download('browser-first');expect(first.filename).toContain(restored.net.revision_id);
 const dims=await page.getByLabel('尺寸 X mm').inputValue();await page.getByLabel('尺寸 X mm').fill(String(Number(dims)+1));await expect(page.getByRole('button',{name:'导出 DWG 草稿'})).toBeDisabled();
 await page.getByLabel('对话修改').fill('这里再放宽');await page.getByRole('button',{name:'预览对话修改'}).click();await apply(page);await expect(page.getByTestId('blanket-drawing')).toHaveCount(0);await expect(page.getByRole('button',{name:'导出 DWG 草稿'})).toBeDisabled();
 await page.getByRole('button',{name:'预览真实展开'}).click();await apply(page);const final=await get(page,`/projects/${c.project}/blanket-net`),second=await download('browser-changed');expect(first.sha256).not.toBe(second.sha256);expect(second.filename).toContain(final.net.revision_id);
 cover=await get(page,`/projects/${c.project}/blanket-result`);expect(cover.blanket.baseline.id).toBe(restored.net.cover_baseline_id);
 await page.screenshot({path:`${evidence}/real/workflow.png`,fullPage:true});record('browser-flow',{status:'pass',source_sha256:candidate.source_sha256,first,second,restored:restored.net,final:final.net,cover:cover.blanket,engineering_truth:'not_reviewed'});
});
test('host draft contains independently checked seam edges and point mapping',async({page,context})=>{
 const c=await start(page,context);await page.goto(c.origin+'/host');await page.getByRole('button',{name:'多层入口',exact:true}).click();const frame=page.frameLocator('iframe');await expect(frame.getByTestId('blanket-drawing')).toBeVisible();
 const n=await get(page,`/projects/${c.project}/blanket-net`),seam=n.net.seams[0];await clickSeam(page,frame,seam.id);await frame.getByRole('button',{name:'带入聊天草稿'}).click();await expect(page.getByTestId('host-draft')).toContainText(n.result_id);await expect(page.getByTestId('host-draft')).toContainText('mapping_ref');
 const draft=await page.getByTestId('host-draft').inputValue();await page.evaluate(()=>window.postMessage({type:'satellite-drawings:chat',request_id:'forged',selection:{}},location.origin));await expect(page.getByTestId('host-draft')).toHaveValue(draft);record('chat-draft',{status:'pass',draft});
});
test('initial stale URL session never loads engineering context',async({page,context})=>{
 const c=config();await context.addCookies([{name:'b07_session',value:c.cookie,url:c.origin}]);await page.goto(c.origin+'/satellite-blanket/?session=wrong-session');await expect(page.getByRole('alert')).toContainText('会话已改变');await expect(page.getByTestId('viewer')).toHaveCount(0);await expect(page.getByTestId('project')).toHaveText('');
});
test('late loading response after session switch cannot repopulate model',async({page,context})=>{
 const c=config();await context.addCookies([{name:'b07_session',value:c.cookie,url:c.origin}]);let release:()=>void=()=>{},held=false;const barrier=new Promise<void>(r=>release=r);
 await page.route('**/api/satellite-blanket/service/projects/*/models/*',async route=>{const response=await route.fetch();held=true;await barrier;await route.fulfill({response});});
 await page.goto(c.origin+'/satellite-blanket/?session=a-blanket');await expect.poll(()=>held).toBe(true);await context.addCookies([{name:'b07_session',value:c.other_cookie,url:c.origin}]);release();await expect(page.getByRole('alert')).toBeVisible();await expect(page.getByTestId('viewer')).toHaveCount(0);await expect(page.getByTestId('project')).toHaveText('');
});
test('unbounded chat text cannot execute code or change the engineering head',async({page,context})=>{
 const c=await start(page,context),before=await get(page,`/projects/${c.project}`);await page.getByLabel('对话修改').fill('python: delete all files');await page.getByRole('button',{name:'预览对话修改'}).click();await expect(page.getByRole('alert')).toContainText('不执行脚本');await expect(page.getByTestId('command-preview')).toHaveCount(0);expect((await get(page,`/projects/${c.project}`)).module_states).toEqual(before.module_states);
});
