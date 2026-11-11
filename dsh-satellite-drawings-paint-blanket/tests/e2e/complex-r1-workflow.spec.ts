import {test,expect} from '@playwright/test';
import fs from 'node:fs';
const out=process.env.B13_EVIDENCE_DIR||'docs/evidence/B13';
const config=()=>JSON.parse(fs.readFileSync('work/b13-r1-session.json','utf8'));
async function start(page:any,context:any,module='blanket'){
 const c=config();await context.addCookies([{name:'b07_session',value:c.cookie,url:c.origin}]);
 await page.goto(c.origin+'/satellite-'+module+'/?session='+(module==='blanket'?'a-blanket':'a-session'));
 await expect(page.getByTestId('viewer')).toHaveAttribute('data-ready','true');return c;
}
async function get(page:any,c:any,path:string){return page.evaluate(async(path:string)=>(await fetch('/api/satellite-blanket/service'+path)).json(),path);}
test('real concave cover and connected 15mm plan; exact cone analysis keeps current net',async({page,context})=>{
 const c=await start(page,context);
 await page.getByLabel('目标面').selectOption(String(c.bottom_index));
 await page.getByRole('button',{name:'设为安装底面',exact:true}).click();
 await page.getByLabel('外形策略').selectOption('orthogonal_sections_v1');
 await page.getByLabel('放量系数').fill('1.01');
 await page.getByRole('button',{name:'生成罩形',exact:true}).click();
 await expect(page.getByTestId('baseline')).toContainText('baseline-');
 await page.getByRole('button',{name:'预览15mm连接方案',exact:true}).click();
 await page.getByRole('button',{name:'执行修改',exact:true}).click();
 await expect(page.getByTestId('blanket-drawing')).toBeVisible();
 const net=await get(page,c,`/projects/${c.project}/blanket-net`);
 expect(net.net.overlaps).toHaveLength(19);expect(net.net.seams.filter((s:any)=>s.kind==='fold')).toHaveLength(1);expect(net.net.status).toBe('needs_review');
 expect(net.net.pieces.length).toBeGreaterThan(5);expect(net.net.foldback.maximum_error_mm).toBeLessThan(1e-6);
 await page.getByLabel('目标面').selectOption(String(c.cone_index));
 await page.getByLabel('曲面 U 切缝 / rad').fill('6.283185307179');
 await page.getByRole('button',{name:'测量所选曲面',exact:true}).click();
 await expect(page.getByLabel('复杂几何测量')).toContainText('CONE');
 await expect(page.getByLabel('复杂几何测量')).toContainText('surface-piece-1');
 await expect(page.getByRole('img',{name:'精确曲面展开轮廓'})).toBeVisible();
 expect((await get(page,c,`/projects/${c.project}/blanket-net`)).result_id).toBe(net.result_id);
 await page.screenshot({path:out+'/browser-complex.png',fullPage:true});
 fs.writeFileSync(out+'/browser-complex.json',JSON.stringify({status:'pass',net},null,2));
});
test('actual doubly curved paint target displays measured error without manufacture approval',async({page,context})=>{
 const c=await start(page,context,'paint');
 await page.getByLabel('目标面').selectOption(String(c.sphere_index));
 await page.getByRole('button',{name:'测量所选曲面',exact:true}).click();
 await expect(page.getByLabel('复杂几何测量')).toContainText('piecewise');
 await expect(page.getByLabel('复杂几何测量')).toContainText('制造公差未批准');
 await expect(page.getByRole('img',{name:'分片误差图'})).toBeVisible();
 await page.getByLabel('目标面').selectOption(String(c.motor_index));
 await page.getByRole('button',{name:'生成保护区',exact:true}).click();
 await expect(page.getByTestId('check-state')).toContainText('needs_review');
 const choices=await page.getByLabel('曲面孔口').locator('option').evaluateAll((es:any[])=>es.map(e=>e.value).filter(Boolean));expect(choices).toHaveLength(2);
 for(const id of choices){await page.getByLabel('曲面孔口').selectOption(id);await page.getByRole('button',{name:'确认孔口3mm保护',exact:true}).click();await expect(page.getByTestId('execution-state')).toHaveText('后端执行：已完成');}
 await expect(page.getByTestId('viewer')).toHaveAttribute('data-ready','true');
 await page.getByRole('button',{name:'保存工程包',exact:true}).click();await expect(page.getByRole('status')).toContainText('工程包已保存');
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'导出 DWG 草稿',exact:true}).click();const file=await download;await file.saveAs(out+'/browser-paint.dwg');expect(fs.readFileSync(out+'/browser-paint.dwg').subarray(0,6).toString()).toBe('AC1032');
 await page.screenshot({path:out+'/browser-curved-paint.png',fullPage:true});
});
test('invalid seam parameter fails and current complex net remains unchanged',async({page,context})=>{
 const c=await start(page,context),before=await get(page,c,`/projects/${c.project}/blanket-net`);
 await page.getByLabel('目标面').selectOption(String(c.cone_index));
 await page.getByLabel('曲面 U 切缝 / rad').fill('999999');
 await page.getByRole('button',{name:'测量所选曲面',exact:true}).click();
 await expect(page.getByRole('alert')).toBeVisible();
 expect((await get(page,c,`/projects/${c.project}/blanket-net`)).result_id).toBe(before.result_id);
});
test('stale session cannot restore complex diagnostics or engineering context',async({page,context})=>{
 const c=config();await context.addCookies([{name:'b07_session',value:c.cookie,url:c.origin}]);
 await page.goto(c.origin+'/satellite-blanket/?session=wrong-session');
 await expect(page.getByRole('alert')).toContainText('会话已改变');
 await expect(page.getByTestId('viewer')).toHaveCount(0);await expect(page.getByLabel('复杂几何测量')).toHaveCount(0);
});

test('native cone and spherical band current net, points, save restore and real export',async({page,context})=>{
 const c=await start(page,context);
 for(const index of [c.cone_index,c.band_index]){
  const before=await page.getByTestId('revision').innerText();
  await page.getByLabel('目标面').selectOption(String(index));
  await page.getByLabel('曲面 U 切缝 / rad').fill('');
  await page.getByRole('button',{name:'生成所选曲面裁片候选',exact:true}).click();
  await expect(page.getByTestId('revision')).not.toHaveText(before);
  await expect(page.getByLabel('外形策略')).toHaveValue('native_surface_v1');
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'预览15mm连接方案',exact:true})).toBeEnabled();
  await page.getByRole('button',{name:'预览15mm连接方案',exact:true}).click();await page.getByRole('button',{name:'执行修改',exact:true}).click();
  await expect(page.getByTestId('blanket-drawing')).toBeVisible();
  const n=await get(page,c,`/projects/${c.project}/blanket-net`);
  expect(n.net.panels).toHaveLength(2);expect(n.net.panels[0].surface_mapping.kind).toBe(index===c.cone_index?'CONE':'SPHERE');
  if(index===c.band_index)for(const tab of n.net.overlaps){const width=tab.surface_width_measurement;expect(width.acceptance).toBe('pass');expect(Math.max(...width.native_circle_widths_mm.map((x:number)=>Math.abs(x-15)))).toBeLessThan(1e-6);expect(width.native_outside_receiving_area_mm2).toBeLessThan(1e-6);}
  expect(n.net.status).toBe('needs_review');expect(n.net.overlaps.length).toBeGreaterThan(0);expect(n.net.native_readback['folded-tabs.brep'].valid).toBe(true);
  const panel=n.net.panels[0],m=panel.surface_mapping,u=(m.uv_bounds[0]+m.uv_bounds[1])/2,v=(m.uv_bounds[2]+m.uv_bounds[3])/2,rho=m.radius_mm/m.sine+v,theta=(u-m.u_origin)*m.sine,uv=m.kind==='CONE'?[rho*Math.cos(theta),rho*Math.sin(theta)]:[m.radius_mm*(u-m.u_origin),m.radius_mm*v];
  await page.getByLabel('编辑裁片').selectOption(panel.key);await page.getByLabel('固定点 U mm').fill(String(uv[0]));await page.getByLabel('固定点 V mm').fill(String(uv[1]));
  await page.getByRole('button',{name:'预览增加固定点',exact:true}).click();await page.getByRole('button',{name:'执行修改',exact:true}).click();
  await expect(page.getByTestId('revision')).not.toHaveText(n.net.revision_id);
  await expect(page.getByTestId('viewer')).toHaveAttribute('data-ready','true');
  await expect(page.getByTestId('current-state')).toHaveText('同版本净片与图纸');
  await page.getByRole('button',{name:'保存工程包',exact:true}).click();await expect(page.getByRole('status')).toContainText('工程包已保存');
  await page.getByRole('button',{name:'恢复工程包',exact:true}).click();await expect(page.getByTestId('current-state')).toHaveText('同版本净片与图纸');
  await expect(page.getByLabel('外形策略')).toHaveValue('native_surface_v1');
  const restored=await get(page,c,`/projects/${c.project}/blanket-net`);expect(restored.net.panels[0].surface_mapping.kind).toBe(n.net.panels[0].surface_mapping.kind);expect(restored.net.fixed_points).toHaveLength(1);fs.writeFileSync(out+'/browser-native-'+index+'.json',JSON.stringify(restored,null,2));
  const download=page.waitForEvent('download');await page.getByRole('button',{name:'导出 DWG 草稿',exact:true}).click();const file=await download;const path=out+'/browser-native-'+index+'.dwg';await file.saveAs(path);expect(fs.readFileSync(path).subarray(0,6).toString()).toBe('AC1032');
  await page.screenshot({path:out+'/browser-native-'+index+'.png',fullPage:true});
 }
});
