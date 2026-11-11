import {test,expect} from '@playwright/test';
import fs from 'node:fs';
const out=process.env.B13_EVIDENCE_DIR||'docs/evidence/B13';
const config=()=>JSON.parse(fs.readFileSync('work/b13-session.json','utf8'));
async function start(page:any,context:any,module='blanket'){
 const c=config();await context.addCookies([{name:'b07_session',value:c.cookie,url:c.origin}]);
 await page.goto(c.origin+'/satellite-'+module+'/?session='+(module==='blanket'?'a-blanket':'a-session'));
 await expect(page.getByTestId('viewer')).toHaveAttribute('data-ready','true');return c;
}
async function get(page:any,c:any,path:string){return page.evaluate(async(path:string)=>(await fetch('/api/satellite-blanket/service'+path)).json(),path);}
test('real concave cover and independent pieces; exact cone analysis keeps current net',async({page,context})=>{
 const c=await start(page,context);
 await page.getByLabel('目标面').selectOption(String(c.bottom_index));
 await page.getByRole('button',{name:'设为安装底面',exact:true}).click();
 await page.getByLabel('外形策略').selectOption('orthogonal_sections_v1');
 await page.getByLabel('放量系数').fill('1.01');
 await page.getByRole('button',{name:'生成罩形',exact:true}).click();
 await expect(page.getByTestId('baseline')).toContainText('baseline-');
 await page.getByRole('button',{name:'预览独立多裁片',exact:true}).click();
 await page.getByRole('button',{name:'执行修改',exact:true}).click();
 await expect(page.getByTestId('blanket-drawing')).toBeVisible();
 const net=await get(page,c,`/projects/${c.project}/blanket-net`);
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
