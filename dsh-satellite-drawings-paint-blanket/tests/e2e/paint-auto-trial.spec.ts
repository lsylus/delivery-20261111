import {test,expect} from '@playwright/test';
import fs from 'node:fs';

const origin=process.env.PAINT_TRIAL_URL||'http://127.0.0.1:18892';
const source=process.env.PAINT_TRIAL_STEP||'fixtures/synthetic/paint/assembly.step';
const output=process.env.PAINT_TRIAL_OUTPUT||'work/paint-auto-e2e';
const timeout=Number(process.env.PAINT_TRIAL_TIMEOUT_MS||15*60_000);
const generate=process.env.PAINT_TRIAL_GENERATE!=='0';
const reuse=process.env.PAINT_TRIAL_REUSE==='1';

test('automatic planar groups generate and export a verified DWG batch',async({page})=>{
  test.setTimeout(timeout);
  page.on('console',message=>console.log('browser:',message.type(),message.text()));
  page.on('pageerror',error=>console.log('pageerror:',error.message));
  await page.goto(origin+'/');
  await page.goto(origin+'/host');
  await page.getByRole('button',{name:'喷漆图纸',exact:true}).click();
  const app=page.frameLocator('iframe');
  if(!reuse){
    await app.getByRole('button',{name:'新建工程',exact:true}).click();
    await expect(app.getByTestId('project')).not.toHaveText('');
    await expect(app.getByLabel('导入 STEP',{exact:true})).toBeEnabled();
  }
  console.log('project:',await app.getByTestId('project').innerText());
  if(!reuse){await app.getByLabel('导入 STEP',{exact:true}).setInputFiles(source);console.log('upload selected');}
  await expect(app.getByTestId('viewer')).toHaveAttribute('data-ready','true',{timeout:Math.min(timeout-60_000,30*60_000)});
  await expect(app.getByTestId('selection-count')).toContainText('板面组');
  await expect(app.getByLabel('目标面')).toHaveCount(0);
  const selection=await app.getByTestId('selection-count').innerText();
  const viewerHeading=app.getByRole('heading',{name:/三维模型与保护/});
  await expect(viewerHeading).toContainText('绿色已选 · 金色保护');
  await expect(viewerHeading).not.toContainText('红色无效');
  const selectedCount=Number(selection.match(/已选 (\d+)/)?.[1]||0);
  const canvas=app.locator('canvas');
  await expect(canvas).toBeVisible();
  const pixels=await canvas.evaluate((value:HTMLCanvasElement)=>{
    const context=(value.getContext('webgl2')||value.getContext('webgl')) as WebGLRenderingContext|null;
    if(!context)return {nonBlank:0,width:value.width,height:value.height};
    const data=new Uint8Array(value.width*value.height*4);
    context.readPixels(0,0,value.width,value.height,context.RGBA,context.UNSIGNED_BYTE,data);
    let nonBlank=0;
    for(let i=0;i<data.length;i+=4)if(data[i+3]&&!(data[i]>235&&data[i+1]>235&&data[i+2]>235))nonBlank++;
    return {nonBlank,width:value.width,height:value.height};
  });
  expect(pixels.width*pixels.height).toBeGreaterThan(10_000);
  expect(pixels.nonBlank).toBeGreaterThan(1_000);
  const project=await app.getByTestId('project').innerText();
  const recommendations=await page.evaluate(async project=>{
    const response=await fetch(`/api/satellite-paint/service/projects/${project}/paint-recommendations`);
    if(!response.ok)throw Error(await response.text());
    return response.json();
  },project);
  const groups=recommendations?.recommendations?.groups||[];
  const diagnostics=recommendations?.recommendations?.diagnostics||[];
  const componentText=await app.getByTestId('assembly-tree').innerText();
  const summary={source,project,components:Number(componentText.match(/(\d+) 个组件/)?.[1]||0),candidates:groups.length,
    recommended:groups.filter((group:any)=>group.recommended&&group.selectable).length,
    invalid:groups.filter((group:any)=>!group.selectable).length,diagnostics,pixels,selection};
  fs.mkdirSync(output,{recursive:true});
  fs.writeFileSync(output+'/import-summary.json',JSON.stringify(summary,null,2));
  await canvas.screenshot({path:output+'/canvas.png'});
  await page.screenshot({path:output+'/workflow-import.png',fullPage:true});
  console.log('import-summary:',JSON.stringify(summary));
  if(!generate)return;
  expect(selectedCount).toBeGreaterThan(0);
  await app.getByRole('button',{name:'批量生成保护区',exact:true}).click();
  await expect(app.getByTestId('execution-state')).toContainText('已完成',{timeout:5*60_000});
  await expect(app.getByRole('button',{name:'导出批量 DWG ZIP'})).toBeEnabled();
  const download=page.waitForEvent('download');
  await app.getByRole('button',{name:'导出批量 DWG ZIP'}).click();
  const item=await download;
  await item.saveAs(output+'/paint-drawings.zip');
  await page.screenshot({path:output+'/workflow.png',fullPage:true});
  expect(fs.readFileSync(output+'/paint-drawings.zip').subarray(0,2).toString()).toBe('PK');
});
