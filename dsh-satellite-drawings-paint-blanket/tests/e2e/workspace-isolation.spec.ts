import {test,expect} from '@playwright/test';
import {open,login,config,screenshot} from './helpers';
import {start as b12start,get as b12get,config as b12config,clickSeam} from './b12-helpers';
if(process.env.B12_SCOPE!=='1'){
test('owner/session/project/module drafts are isolated; revision changes invalidate drafts',async({page,context})=>{
  const c=await open(page,context);await page.getByLabel('对话批注').fill('alice paint private');await page.reload();await expect(page.getByLabel('对话批注')).toHaveValue('alice paint private');
  const shared=c.imported.alice.project,model=c.imported.alice.revision.model_ref;
  const blanket=c.origin+'/api/satellite-blanket/service';
  expect((await page.request.put(blanket+'/sessions/a-blanket/binding',{headers:{Origin:c.origin},data:{session_id:'a-blanket',module:'blanket',project_id:shared,expected_revision:'empty'}})).status()).toBe(200);
  expect((await page.request.post(blanket+`/projects/${shared}/revisions`,{headers:{Origin:c.origin},data:{expected_revision:'empty',model_ref:model,selection:[],parameters:{},overrides:[]}})).status()).toBe(201);
  await page.goto(c.origin+'/satellite-blanket/');await expect(page.getByTestId('viewer')).toHaveAttribute('data-ready','true');await expect(page.getByLabel('对话批注')).toHaveValue('');
  await expect(page.getByTestId('project')).toHaveText(shared);
  await login(context,'other_session');
  expect((await page.request.put(c.origin+'/api/satellite-paint/service/sessions/a-other/binding',{headers:{Origin:c.origin},data:{session_id:'a-other',module:'paint',project_id:shared,expected_revision:c.imported.alice.revision.id}})).status()).toBe(200);
  await page.goto(c.origin+'/satellite-paint/');await expect(page.getByTestId('viewer')).toHaveAttribute('data-ready','true');await expect(page.getByTestId('project')).toHaveText(shared);await expect(page.getByLabel('对话批注')).toHaveValue('');
  await login(context,'bob');await page.goto(c.origin+'/satellite-paint/');await expect(page.getByTestId('viewer')).toHaveAttribute('data-ready','true');await expect(page.getByLabel('对话批注')).toHaveValue('');
  const r=await page.request.get(c.origin+'/api/satellite-paint/service/projects/'+c.imported.alice.project);expect(r.status()).toBe(404);
  await login(context);await page.goto(c.origin+'/satellite-paint/');await expect(page.getByLabel('对话批注')).toHaveValue('alice paint private');await screenshot(page,'draft-isolation');
});
test('active session change clears model, draft, selection and old iframe reference',async({page,context})=>{
  const c=await open(page,context);await page.getByTestId('drawing-face-0').click();await page.getByLabel('对话批注').fill('must not leak');
  await login(context,'other_session');await expect(page.getByRole('alert')).toContainText('会话已改变');await expect(page.getByTestId('viewer')).toHaveCount(0);await expect(page.getByTestId('selected-faces')).toHaveCount(0);
  await page.goto(c.origin+'/host');const frame=page.frameLocator('iframe');await expect(frame.getByTestId('viewer')).toHaveAttribute('data-ready','true');
  await page.evaluate(()=>{const old=document.querySelector('iframe')!.contentWindow;(window as any).oldFrame=old;});
  await login(context);await expect(frame.getByTestId('identity')).toContainText('a-session');await expect(page.getByTestId('host-draft')).toHaveValue('');
});

}else{

test('paint and blanket on same project isolate history and selection',async({page,context})=>{
 const c=await b12start(page,context),before=await b12get(page,`/projects/${c.project}`);await page.getByRole('button',{name:'撤销修改',exact:true}).click();await expect.poll(async()=>(await b12get(page,`/projects/${c.project}`)).module_states.blanket).not.toBe(before.module_states.blanket);
 expect((await b12get(page,`/projects/${c.project}`)).module_states.paint).toBe(before.module_states.paint);await page.getByRole('button',{name:'重做修改',exact:true}).click();await expect.poll(async()=>(await b12get(page,`/projects/${c.project}`)).module_states.blanket).toBe(before.module_states.blanket);
 await page.goto(c.origin+'/satellite-paint/?session=a-session');await expect(page.getByTestId('viewer')).toHaveAttribute('data-ready','true');await expect(page.getByTestId('selection-count')).toHaveText('已选 0 个面');await expect(page.getByTestId('project')).toHaveText(c.project);await expect(page.getByTestId('command-preview')).toHaveCount(0);
});
test('module switches clear host draft and local pending target',async({page,context})=>{
 const c=await b12start(page,context);await page.goto(c.origin+'/host');await page.getByRole('button',{name:'多层入口',exact:true}).click();const frame=page.frameLocator('iframe');await expect(frame.getByTestId('blanket-drawing')).toBeVisible();const n=await b12get(page,`/projects/${c.project}/blanket-net`);await clickSeam(page,frame,n.net.seams[0].id);await frame.getByRole('button',{name:'带入聊天草稿'}).click();await expect(page.getByTestId('host-draft')).toContainText(n.result_id);
 await page.getByRole('button',{name:'喷漆入口',exact:true}).click();await expect(page.getByTestId('host-draft')).toHaveValue('');await expect(frame.getByTestId('identity')).toContainText('a-session');await expect(frame.getByTestId('command-preview')).toHaveCount(0);
});
test('session change clears blanket selection, pending command and saved bundle access',async({page,context})=>{
 const c=await b12start(page,context),n=await b12get(page,`/projects/${c.project}/blanket-net`);await clickSeam(page,page,n.net.seams[0].id);await page.getByRole('button',{name:'预览增加固定点'}).click();await expect(page.getByTestId('command-preview')).toBeVisible();await context.addCookies([{name:'b07_session',value:c.other_cookie,url:c.origin}]);await expect(page.getByRole('alert')).toBeVisible();await expect(page.getByTestId('viewer')).toHaveCount(0);await expect(page.getByTestId('command-preview')).toHaveCount(0);await expect(page.getByTestId('project')).toHaveText('');
});
}
