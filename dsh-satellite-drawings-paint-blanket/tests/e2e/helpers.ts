import fs from 'node:fs';
import {expect} from '@playwright/test';
export const config=()=>JSON.parse(fs.readFileSync('work/b07-session.json','utf8'));
export async function login(context:any,who='alice'){const c=config();await context.addCookies([{name:'b07_session',value:c.cookies[who],url:c.origin,httpOnly:true,sameSite:'Strict'}]);return c;}
export async function open(page:any,context:any,module='paint',who='alice'){
  const c=await login(context,who);await page.goto(c.origin+`/satellite-${module}/`);await expect(page.getByTestId('viewer')).toHaveAttribute('data-ready','true');return c;
}
export async function screenshot(page:any,name:string){await page.screenshot({path:`docs/evidence/B07/${name}.png`,fullPage:true});}
