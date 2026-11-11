import {test,expect} from '@playwright/test';
import fs from 'node:fs';
const out=process.env.B13_EVIDENCE_DIR||'docs/evidence/B13/r3/browser-development';
const config=()=>JSON.parse(fs.readFileSync('work/b13-r3-session.json','utf8'));
async function start(page:any,context:any,module='blanket'){
 const c=config();await context.addCookies([{name:'b07_session',value:c.cookie,url:c.origin}]);
 await page.goto(c.origin+'/satellite-'+module+'/?session='+(module==='blanket'?'a-blanket':'a-session'));
 await expect(page.getByTestId('viewer')).toHaveAttribute('data-ready','true');return c;
}
async function get(page:any,path:string,module='blanket'){return page.evaluate(async({path,module}:any)=>(await fetch('/api/satellite-'+module+'/service'+path)).json(),{path,module});}

test('full motor positive-clearance cover and connected net stay in the current UI revision',async({page,context})=>{
 const c=await start(page,context);
 await expect(page.getByLabel('外形策略')).toHaveValue('faceted_clearance_v1');
 await expect(page.getByLabel('候选间隙 mm')).toHaveValue('1');
 await expect(page.getByLabel('安装坐标 X 分段位置 mm')).toHaveValue('40,300,334');
 await expect(page.getByTestId('blanket-drawing')).toBeVisible();
 await expect(page.getByTestId('current-state')).toHaveText('同版本净片与图纸');
 const n=await get(page,`/projects/${c.project}/blanket-net`);
 expect(n.net.diagnostics).toHaveLength(0);expect(n.net.panels.length).toBeGreaterThan(5);
 expect(n.net.overlaps.length).toBeGreaterThan(0);expect(n.net.seams.filter((s:any)=>s.kind==='cut')).toHaveLength(0);
 expect(n.net.status).toBe('needs_review');expect(n.net.foldback.maximum_error_mm).toBeLessThan(1e-6);
 await page.getByLabel('候选间隙 mm').fill('2');
 await expect(page.getByRole('button',{name:'保存工程包',exact:true})).toBeDisabled();
 await page.getByLabel('候选间隙 mm').fill('1');
 await page.getByRole('button',{name:'保存工程包',exact:true}).click();await expect(page.getByRole('status')).toContainText('工程包已保存');
 await page.getByRole('button',{name:'恢复工程包',exact:true}).click();await expect(page.getByTestId('revision')).not.toHaveText(n.net.revision_id);
 await expect(page.getByTestId('current-state')).toHaveText('同版本净片与图纸');
 const restored=await get(page,`/projects/${c.project}/blanket-net`);expect(restored.net.overlaps).toHaveLength(n.net.overlaps.length);
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'导出 DWG 草稿',exact:true}).click();await(await download).saveAs(out+'/browser-motor-cover.dwg');
 expect(fs.readFileSync(out+'/browser-motor-cover.dwg').subarray(0,6).toString()).toBe('AC1032');
 await page.screenshot({path:out+'/browser-motor-cover.png',fullPage:false});fs.writeFileSync(out+'/browser-motor-cover.json',JSON.stringify(restored,null,2));
});

test('actual motor radial features require explicit classification and render their true surface charts',async({page,context})=>{
 const c=await start(page,context,'paint');await page.getByLabel('目标面').selectOption(String(c.motor_index));
 await page.getByRole('button',{name:'生成保护区',exact:true}).click();await expect(page.getByTestId('execution-state')).toHaveText('后端执行：已完成');
 await page.getByLabel('修订原因').fill('真实 motor 径向接口几何候选；工程分类与制造工艺待确认');
 const ids=await page.getByLabel('曲面孔口').locator('option').evaluateAll((options:any[])=>options.map(o=>o.value).filter(Boolean));expect(ids).toHaveLength(2);
 for(const id of ids){await page.getByLabel('曲面孔口').selectOption(id);await page.getByRole('button',{name:'确认曲面凸台保护',exact:true}).click();await expect(page.getByTestId('execution-state')).toHaveText('后端执行：已完成');}
 const paint=await get(page,`/projects/${c.project}/paint-result`,'paint');expect(paint.paint.regions).toHaveLength(8);
 expect(new Set(paint.paint.regions.map((r:any)=>r.surface_mapping.kind))).toEqual(new Set(['PLANE','CYLINDER']));
 expect(paint.paint.status).toBe('needs_review');expect(paint.paint.diagnostics.map((d:any)=>d.code)).toEqual(['surface_manufacturing_approval']);
 await page.getByRole('button',{name:'保存工程包',exact:true}).click();await expect(page.getByRole('status')).toContainText('工程包已保存');
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'导出 DWG 草稿',exact:true}).click();await(await download).saveAs(out+'/browser-motor-paint.dwg');
 expect(fs.readFileSync(out+'/browser-motor-paint.dwg').subarray(0,6).toString()).toBe('AC1032');
 await page.screenshot({path:out+'/browser-motor-paint.png',fullPage:false});fs.writeFileSync(out+'/browser-motor-paint.json',JSON.stringify(paint,null,2));
});

test('a foreign session cannot load the new complex manufacturing candidates',async({page,context})=>{
 const c=config();await context.addCookies([{name:'b07_session',value:c.cookie,url:c.origin}]);
 await page.goto(c.origin+'/satellite-blanket/?session=wrong-session');
 await expect(page.getByRole('alert')).toContainText('会话已改变');await expect(page.getByTestId('viewer')).toHaveCount(0);
});
