/** Actual packaged plugin, canvas clicks, native backend, unfold and DWG downloads. */
import {chromium,expect} from '@playwright/test';
import * as THREE from 'three';
import fs from 'node:fs';
const large=process.argv.includes('--large');
const port=large?18891:18890,origin=`http://127.0.0.1:${port}`;
const out=process.env.SIMPLE_OUT||'work/simple-v1-evidence';fs.mkdirSync(out,{recursive:true});
const browser=await chromium.launch({headless:true,args:['--no-sandbox','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1700,height:1400}});
page.setDefaultTimeout(60000);
const errors=[];page.on('pageerror',error=>errors.push(String(error)));
const frame=page.frameLocator('iframe');
async function get(p){const r=await page.request.get(origin+'/api/satellite-blanket/service'+p);expect(r.status()).toBe(200);return r.json();}
async function alertText(){const alerts=frame.getByRole('alert');for(let i=0;i<await alerts.count();i++){const item=alerts.nth(i);if(await item.isVisible())return (await item.textContent())?.trim()||'模型操作失败';}return '';}
async function ready({ignoreAlert=false,timeout=960000}={}){
  const deadline=Date.now()+timeout;
  while(Date.now()<deadline){
    const failure=await alertText();if(failure&&!ignoreAlert)throw Error('模型未就绪：'+failure);
    if(errors.length)throw Error('浏览器错误：'+errors.at(-1));
    const viewer=frame.locator('[data-testid=viewer][data-ready=true]');if(await viewer.count()&&await viewer.first().isVisible())return;
    await page.waitForTimeout(500);
  }
  throw Error('模型三维视图等待超时；未将未就绪状态计作验收通过');
}
async function idle(){await expect(frame.getByTestId('current-state')).not.toContainText('正在计算',{timeout:180000});}
async function createAndImport(name,path){
  const before=await frame.getByTestId('project').textContent();
  await frame.getByRole('button',{name:'新建工程',exact:true}).click();
  await expect(frame.getByTestId('project')).not.toHaveText(before);
  await expect(frame.getByLabel('导入 STEP',{exact:true})).toBeEnabled();
  const project=await frame.getByTestId('project').textContent();
  const started=Date.now();
  await frame.getByLabel('导入 STEP',{exact:true}).setInputFiles(path);
  await ready();
  const head=await get('/projects/'+project);
  const revision=await get(`/projects/${project}/revisions/${head.module_states.blanket}`);
  const model=await get(`/projects/${project}/models/${revision.model_ref.model_id}`);
  const map=await get('/artifacts/'+model.artifacts.find(a=>a.relative_storage_path.endsWith('mesh-map.json')).id);
  console.log(name,'imported',map.faces.length,'faces',Math.round((Date.now()-started)/1000),'s');
  return {project,revision,model,map,import_seconds:(Date.now()-started)/1000};
}
async function clickRelative(x,y){const canvas=frame.getByLabel('真实模型三维视图');await canvas.scrollIntoViewIfNeeded();const b=await canvas.boundingBox();await page.mouse.click(b.x+x*b.width,b.y+y*b.height);}
async function bottomPlane(dimensions){
  const canvas=frame.getByLabel('真实模型三维视图');await canvas.scrollIntoViewIfNeeded();const b=await canvas.boundingBox();
  const start={x:b.x+b.width*.5,y:b.y+b.height*.72},dy=-b.height*.22;
  await page.mouse.move(start.x,start.y);await page.mouse.down();await page.mouse.move(start.x,start.y+dy,{steps:20});await page.mouse.up();
  const [sx,sy,sz]=dimensions.map(x=>x/1000),size=Math.hypot(sx,sy,sz),center=new THREE.Vector3(0,sz/2,0);
  const offset=new THREE.Vector3(size*.9,size*.8,size*1.2),sphere=new THREE.Spherical().setFromVector3(offset);
  sphere.phi-=2*Math.PI*dy/b.height;
  const camera=new THREE.PerspectiveCamera(38,b.width/b.height,Math.max(size/1000,.00001),Math.max(size*100,10));
  camera.position.copy(center).add(new THREE.Vector3().setFromSpherical(sphere));camera.lookAt(center);camera.updateMatrixWorld();
  const point=new THREE.Vector3(0,0,0).project(camera);
  await page.mouse.click(b.x+(point.x+1)*b.width/2,b.y+(1-point.y)*b.height/2);
  await expect(frame.getByTestId('installation-face')).toContainText('已选择');
  await ready();
}
async function apply(){
  await frame.getByRole('button',{name:'执行修改',exact:true}).click();
  await expect(frame.getByTestId('command-preview')).toHaveCount(0,{timeout:180000});await idle();
}
async function runCase(name){
  const c=await createAndImport(name,`fixtures/synthetic/simple-v1/${name}.step`);
  await frame.getByRole('button',{name:'包覆对象',exact:true}).click();await clickRelative(.5,.65);
  await expect(frame.getByTestId('selection-count')).toContainText('包覆对象 1');
  if(name==='cube-cylinder'){
    await frame.getByRole('button',{name:'不包小件',exact:true}).click();await clickRelative(.5,.3);
    await expect(frame.getByTestId('selection-count')).toContainText('不包小件 1');
  }
  await frame.getByRole('button',{name:'平面安装面',exact:true}).click();
  await bottomPlane(name==='cylinder'?[80,80,80]:[100,100,name==='cube-cylinder'?140:100]);
  if(name==='cylinder')await frame.getByLabel('罩形',{exact:true}).selectOption('regular_cylinder_v1');
  await frame.getByText('开口与数量设置',{exact:true}).click();
  if(name==='cube-cylinder')await frame.getByLabel('开口形状',{exact:true}).selectOption('circle');
  await frame.getByLabel('层数',{exact:true}).fill('3');
  await frame.getByLabel(/放量体积比参考|参考.*体积比/).fill('1.01');
  await frame.getByRole('button',{name:'生成罩形与开口预览',exact:true}).click();
  await expect(frame.getByTestId('actual-dimensions')).toBeVisible({timeout:180000});await idle();
  const cover=await get(`/projects/${c.project}/blanket-result`);
  console.log(name,'cover ready');
  expect(cover.blanket.parameters.installation_frame.z_axis[2]).toBeCloseTo(1,6);
  expect(cover.blanket.regular_envelope.volume_reference_exceeded).toBe(true);
  expect(cover.blanket.manufacturing_summary.layer_count).toBe(3);
  if(name==='cube-cylinder'){
    expect(cover.blanket.parameters.excluded_instances).toHaveLength(1);
    expect(cover.blanket.panels.reduce((n,p)=>n+p.holes.length,0)).toBe(1);
    for(const d of cover.blanket.dimensions_mm)expect(d).toBeCloseTo(105,5);
  }
  await frame.getByRole('button',{name:'预览连接展开（15 mm 搭接）',exact:true}).click();await apply();
  await expect(frame.getByTestId('blanket-drawing')).toBeVisible();
  let net=await get(`/projects/${c.project}/blanket-net`);
  console.log(name,'net ready');
  expect(net.net.manufacturing_summary.total_pieces).toBe(net.net.pieces.length*3);
  expect(net.net.pieces.length).toBeLessThanOrEqual(10);
  if(name==='cylinder')expect(net.net.pieces).toHaveLength(2);
  await frame.getByText('搭接、固定点与图纸编辑',{exact:true}).click();
  const join=net.net.seams.findIndex(s=>s.kind==='join');expect(join).toBeGreaterThanOrEqual(0);
  await frame.getByRole('button',{name:`接缝 ${join+1} · join`,exact:true}).click();
  await frame.getByLabel('搭接宽度 mm',{exact:true}).fill('7');
  await frame.getByRole('button',{name:'预览搭接宽度',exact:true}).click();await apply();
  net=await get(`/projects/${c.project}/blanket-net`);expect(net.net.overlaps.some(o=>o.width_mm===7)).toBe(true);
  console.log(name,'overlap edited');
  const pointPanel=net.net.panels.find(p=>p.outer_loop.points.length===4&&!p.holes.length);
  expect(pointPanel).toBeTruthy();
  const uv=[0,1].map(k=>pointPanel.outer_loop.points.reduce((sum,p)=>sum+p[k],0)/pointPanel.outer_loop.points.length);
  await frame.getByLabel('编辑裁片',{exact:true}).selectOption(pointPanel.key);
  await frame.getByLabel('固定点 U mm',{exact:true}).fill(String(uv[0]));
  await frame.getByLabel('固定点 V mm',{exact:true}).fill(String(uv[1]));
  await frame.getByRole('button',{name:'预览增加固定点',exact:true}).click();await apply();
  net=await get(`/projects/${c.project}/blanket-net`);expect(net.net.fixed_points).toHaveLength(1);
  const pointId=net.net.fixed_points[0].id;
  console.log(name,'fixed point added');
  const all=net.net.pieces.flatMap(piece=>piece.outline_mm?.points||[]);
  await frame.getByLabel('图纸注释',{exact:true}).fill('多层包覆样例：'+name+'；单位毫米');
  await frame.getByLabel('文字 X',{exact:true}).fill('0');
  await frame.getByLabel('文字 Y',{exact:true}).fill('-20');
  await frame.getByRole('button',{name:'预览注释布局',exact:true}).click();await apply();
  net=await get(`/projects/${c.project}/blanket-net`);
  expect(net.net.drawing_document.entities.some(e=>e.kind==='text'&&e.text.includes('多层包覆样例'))).toBe(true);
  console.log(name,'Chinese annotation added');
  // Save/restore through the visible product path, then export that same net.
  await frame.getByRole('button',{name:'保存工程包',exact:true}).click();
  await expect(frame.getByRole('status').filter({hasText:'工程包已保存'})).toBeVisible({timeout:180000});
  console.log(name,'saved');
  await page.reload();await page.getByRole('button',{name:'多层图纸',exact:true}).click();
  await expect(frame.getByTestId('blanket-drawing')).toBeVisible({timeout:60000});
  console.log(name,'reloaded');
  await frame.getByRole('button',{name:'恢复工程包',exact:true}).click();await idle();
  net=await get(`/projects/${c.project}/blanket-net`);
  console.log(name,'restored');
  expect(net.net.fixed_points[0].id).toBe(pointId);
  const download=page.waitForEvent('download',{timeout:180000});
  await frame.getByRole('button',{name:'导出并预览 DWG 草稿',exact:true}).click();
  console.log(name,'export submitted');
  await(await download).saveAs(`${out}/${name}.dwg`);
  await expect(frame.getByTestId('dwg-preview')).toBeVisible({timeout:180000});
  const previewImage=frame.getByTestId('dwg-preview').locator('img');
  await expect.poll(()=>previewImage.evaluate(image=>image.complete&&image.naturalWidth>0),{timeout:60000}).toBe(true);
  await frame.getByTestId('dwg-preview').screenshot({path:`${out}/${name}-product-preview.png`});
  expect(fs.readFileSync(`${out}/${name}.dwg`).subarray(0,6).toString()).toBe('AC1032');
  await page.screenshot({path:`${out}/${name}-workbench.png`,fullPage:true});
  fs.writeFileSync(`${out}/${name}.json`,JSON.stringify({status:'passed',...c,cover,net},null,2));
  console.log(name,'PASSED',net.net.pieces.length,'pieces/layer; real DWG saved');
  await frame.getByLabel('尺寸放量系数',{exact:true}).fill('1.06');
  await expect(frame.getByRole('button',{name:'导出并预览 DWG 草稿',exact:true})).toBeDisabled();
  await frame.getByText('搭接、固定点与图纸编辑',{exact:true}).click();
  await expect(frame.getByRole('button',{name:'预览增加固定点',exact:true})).toBeDisabled();
  await frame.getByLabel('尺寸放量系数',{exact:true}).fill('1.05');
  await expect(frame.getByRole('button',{name:'导出并预览 DWG 草稿',exact:true})).toBeEnabled();
  if(name==='cylinder'){
    await frame.getByText('开口与数量设置',{exact:true}).click();
    await frame.getByLabel('每层裁片上限',{exact:true}).fill('1');
    await frame.getByRole('button',{name:'生成罩形与开口预览',exact:true}).click();await idle();
    await expect(frame.getByTestId('piece-count')).toContainText('上限 1');
    await expect(frame.getByRole('button',{name:'预览连接展开（15 mm 搭接）',exact:true})).toBeDisabled();
    await expect(frame.getByRole('button',{name:'导出并预览 DWG 草稿',exact:true})).toBeDisabled();
    const limited=await get(`/projects/${c.project}/blanket-result`);
    expect(limited.blanket.manufacturing_summary.requirements_unmet).toContain('piece_limit_exceeded');
    fs.writeFileSync(`${out}/piece-limit.json`,JSON.stringify({status:'passed',cover:limited},null,2));
    await page.screenshot({path:`${out}/piece-limit.png`,fullPage:true});
  }
  return {name,project:c.project,pieces_per_layer:net.net.pieces.length,total_pieces:net.net.pieces.length*3,dwg:`${out}/${name}.dwg`};
}
try{
  await page.goto(origin+'/');await page.getByRole('button',{name:'多层图纸',exact:true}).click();
  await expect(frame.getByRole('button',{name:'新建工程',exact:true})).toBeEnabled();
  if(large){
    const started=Date.now();
    fs.writeFileSync(`${out}/satellite.json`,JSON.stringify({status:'running',started_at:new Date().toISOString()}));
    const c=await createAndImport('satellite','work/simple-inputs/satellite-assembly.step');
    const attempts=[];let verified=null,cover=null;
    const candidates=[[.5,.5],[.5,.65],[.4,.5],[.6,.5],[.3,.5],[.7,.5],[.5,.35],[.35,.35],[.65,.35],[.35,.65],[.65,.65]];
    for(const [x,y] of candidates){
      await frame.getByRole('button',{name:'清除三维选择',exact:true}).click();await ready({ignoreAlert:true,timeout:120000});
      // A single visible plane supplies both choices. Mode changes do not move
      // the camera, so both real pointer clicks address the identical pixel.
      await frame.getByRole('button',{name:'平面安装面',exact:true}).click();await clickRelative(x,y);
      await page.waitForTimeout(300);
      if(!(await frame.getByTestId('installation-face').textContent()).includes('已选择')){attempts.push({point:[x,y],status:'no_visible_planar_face',message:await alertText()});continue;}
      await frame.getByRole('button',{name:'包覆对象',exact:true}).click();await clickRelative(x,y);
      await expect(frame.getByTestId('selection-count')).toContainText('包覆对象 1');await ready({timeout:120000});
      const submitted=page.waitForRequest(request=>request.method()==='POST'&&request.url().endsWith(`/projects/${c.project}/operations`)&&request.postDataJSON()?.operation==='blanket.generate',{timeout:15000});
      await frame.getByRole('button',{name:'生成罩形与开口预览',exact:true}).click();
      const request=await submitted,parameters=request.postDataJSON().parameters;
      expect(parameters.target_instances).toHaveLength(1);expect(parameters.excluded_instances).toHaveLength(0);
      expect(parameters.installation_face.signature.type).toBe('PLANE');
      expect(parameters.target_instances[0]).toBe(parameters.installation_face.instance_id);
      expect(c.map.faces.some(entry=>entry.face_ref.instance_id===parameters.installation_face.instance_id&&entry.face_ref.entity_id===parameters.installation_face.entity_id)).toBe(true);
      verified={point:[x,y],target_instance:parameters.target_instances[0],installation_face:parameters.installation_face,installation_frame:parameters.installation_frame};
      fs.writeFileSync(`${out}/satellite.json`,JSON.stringify({status:'passed_selection_only',scope:'import_and_direct_same_instance_planar_selection',project:c.project,bytes:fs.statSync('work/simple-inputs/satellite-assembly.step').size,faces:c.map.faces.length,unrenderable_faces:c.map.unrenderable_faces?.length||0,instances:c.model.snapshot.instances.length,import_seconds:c.import_seconds,selection:verified,attempts,native_generation:{status:'pending'},browser_errors:errors},null,2));
      const response=await request.response();
      if(!response?.ok()){attempts.push({...verified,status:'request_failed',http_status:response?.status(),message:await response?.text()});continue;}
      const submittedRun=await response.json();let run=null;
      const deadline=Date.now()+180000;
      while(Date.now()<deadline){run=await get('/runs/'+submittedRun.run_id);if(['succeeded','failed','cancelled'].includes(run.state))break;await page.waitForTimeout(1000);}
      if(!run||!['succeeded','failed','cancelled'].includes(run.state))throw Error('所选对象生成罩形等待超时；保留已验证的三维选择证据');
      if(run.state!=='succeeded'){attempts.push({...verified,status:'native_generation_failed',run_id:run.id||submittedRun.run_id,error:run.error,checks:run.checks});await page.waitForTimeout(500);continue;}
      cover=await get(`/projects/${c.project}/blanket-result`);
      if(!cover?.blanket){attempts.push({...verified,status:'native_generation_diagnostic',run_id:submittedRun.run_id,checks:run.checks});continue;}
      expect(cover.blanket.parameters.target_instances).toEqual(parameters.target_instances);
      expect(cover.blanket.parameters.installation_face).toEqual(parameters.installation_face);
      expect(cover.blanket.parameters.installation_frame).toEqual(parameters.installation_frame);
      attempts.push({...verified,status:'native_cover_generated',run_id:submittedRun.run_id});break;
    }
    expect(verified,'必须通过同一真实canvas位置选择同实例的对象和平面').toBeTruthy();
    await page.screenshot({path:`${out}/satellite-selection.png`,fullPage:true});
    const record={status:cover?'passed':'passed_selection_only',scope:'import_and_direct_same_instance_planar_selection',project:c.project,bytes:fs.statSync('work/simple-inputs/satellite-assembly.step').size,
      faces:c.map.faces.length,unrenderable_faces:c.map.unrenderable_faces?.length||0,instances:c.model.snapshot.instances.length,import_seconds:c.import_seconds,
      elapsed_seconds:(Date.now()-started)/1000,selection:verified,attempts,
      native_generation:cover?{status:'passed',result_id:cover.result_id,blanket_status:cover.blanket.status}:{status:'not_passed',limitation:'已验证同实例平面直接选择；候选组件未完成原生罩形生成，详见attempts，未将制造路径计作通过。'},browser_errors:errors};
    fs.writeFileSync(`${out}/satellite.json`,JSON.stringify(record,null,2));console.log(JSON.stringify(record));
  }else{
    const cases=process.env.SIMPLE_CASES?.split(',')||['cube','cylinder','cube-cylinder'];
    const records=[];for(const name of cases)records.push(await runCase(name));
    expect(errors).toEqual([]);
    const summaryFile=`${out}/workflow-summary.json`;
    const previous=fs.existsSync(summaryFile)?JSON.parse(fs.readFileSync(summaryFile,'utf8')).cases||[]:[];
    const combined=[...previous.filter(record=>!records.some(current=>current.name===record.name)),...records];
    fs.writeFileSync(summaryFile,JSON.stringify({status:'passed',cases:combined,browser_errors:errors},null,2));
  }
}catch(error){
  console.error(String(error));
  if(large){const f=`${out}/satellite.json`;const previous=fs.existsSync(f)?JSON.parse(fs.readFileSync(f,'utf8')):{};fs.writeFileSync(f,JSON.stringify({...previous,status:previous.status==='passed_selection_only'?'passed_selection_only':'failed',error:String(error)},null,2));}
  console.error('UI',await frame.locator('body').innerText().catch(()=>''));
  await page.screenshot({path:`${out}/${large?'satellite':'workflow'}-failure.png`,fullPage:true}).catch(()=>{});
  process.exitCode=1;
}finally{await browser.close();}
