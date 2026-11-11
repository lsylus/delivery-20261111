import {expect} from '@playwright/test';
import fs from 'node:fs';
export const evidence=process.env.B12_EVIDENCE_DIR||'docs/evidence/B12';
export const config=()=>JSON.parse(fs.readFileSync('work/b12-session.json','utf8'));
export async function start(page:any,context:any){const c=config();await context.addCookies([{name:'b07_session',value:c.cookie,url:c.origin,httpOnly:true,sameSite:'Strict'}]);await page.goto(c.origin+'/satellite-blanket/?session=a-blanket');await expect(page.getByTestId('viewer')).toHaveAttribute('data-ready','true');return c;}
export async function get(page:any,path:string,module='blanket'){const c=config(),res=await page.request.get(c.origin+`/api/satellite-${module}/service`+path);expect(res.status()).toBe(200);return res.json();}
export async function apply(page:any){await page.getByRole('button',{name:'执行修改',exact:true}).click();await expect(page.getByTestId('command-preview')).toHaveCount(0);await expect(page.getByTestId('current-state')).not.toHaveText('执行中');}
export function record(name:string,value:any){fs.writeFileSync(`${evidence}/${name}.json`,JSON.stringify(value,null,2));}

export async function clickSeam(page:any,root:any,id:string){
 const line=root.locator(`[data-seam-id="${id}"]`).first();await root.getByTestId('blanket-drawing').scrollIntoViewIfNeeded();
 const q=await line.evaluate((e:any)=>{const s=e.ownerSVGElement,p=s.createSVGPoint();p.x=.55*e.x1.baseVal.value+.45*e.x2.baseVal.value;p.y=.55*e.y1.baseVal.value+.45*e.y2.baseVal.value;const q=p.matrixTransform(e.getScreenCTM()),b=e.getBoundingClientRect();return [q.x-b.x-b.width/2,q.y-b.y-b.height/2];});const b=await line.boundingBox();if(!b)throw Error('Missing seam screen mapping');await page.mouse.click(b.x+b.width/2+q[0],b.y+b.height/2+q[1]);
}
