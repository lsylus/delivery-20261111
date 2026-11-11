import {chromium} from '@playwright/test';
const browser=await chromium.launch({headless:true,args:['--no-sandbox','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1700,height:1400}});page.setDefaultTimeout(20000);
await page.goto('http://127.0.0.1:18890/');await page.getByRole('button',{name:'多层图纸',exact:true}).click();
const f=page.frameLocator('iframe');await f.getByTestId('current-state').waitFor();
console.log(await f.locator('body').innerText());
await page.screenshot({path:'work/simple-v1-evidence/current-state.png',fullPage:true});
await browser.close();
