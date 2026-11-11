import {test,expect} from '@playwright/test';
import {open,config,screenshot} from './helpers';
test('gateway rejects forged owner, session, cross-origin and unsafe paths',async({page,context})=>{
  const c=await open(page,context);
  const base=c.origin+'/api/satellite-paint/service';
  expect((await page.request.get(base+'/projects/'+c.imported.bob.project,{headers:{'X-Owner':'bob'}})).status()).toBe(404);
  expect((await page.request.get(base+'/sessions/b-session/binding')).status()).toBe(403);
  expect((await page.request.get(base+'/health',{headers:{Origin:'https://evil.invalid'}})).status()).toBe(403);
  expect((await page.request.get(base+'/projects%2fsecret')).status()).toBe(400);
  expect((await page.request.post(base+'/projects',{data:{name:'forged',module:'paint'}})).status()).toBe(403);
  const text=await(await page.request.get(c.origin+'/satellite-paint/app.js')).text();expect(text).not.toContain('backendCredential');expect(text).not.toContain('Bearer ');
});
// Run backend-disconnect last. This stops only this test's private B06 process.
test('real service termination exposes failure and never substitutes demo',async({page,context})=>{
  const c=await open(page,context);await screenshot(page,'before-service-failure');process.kill(c.backend_pid,'SIGTERM');
  await page.waitForTimeout(1200);await page.getByRole('button',{name:'刷新模型'}).click();await expect(page.getByRole('alert')).toContainText('502');
  await expect(page.getByTestId('mode')).toContainText('LIVE');await expect(page.getByTestId('viewer')).toHaveCount(1);await expect(page.getByRole('button',{name:'保存工程版本',exact:true})).toBeDisabled();await screenshot(page,'service-failure');
});
