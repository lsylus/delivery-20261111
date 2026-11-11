/** Actual motor import, canvas selection, native feature cover, SVG drag and DWG exports. No UI state injection. */
import {chromium,expect as baseExpect} from '@playwright/test';
const expect=baseExpect.configure({timeout:60000});
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
const origin=process.env.FEATURE_ORIGIN||'http://127.0.0.1:18890';
const caseName=process.env.FEATURE_CASE||'motor';if(!['motor','module','cube','cylinder'].includes(caseName))throw Error('FEATURE_CASE must be motor, module, cube or cylinder');const moduleCase=caseName==='module';
const source=path.resolve(process.env.FEATURE_MOTOR_FILE||(moduleCase?'fixtures/synthetic/feature-composite/cube-cylinder-module.step':caseName==='motor'?'docs/evidence/B13/r4-review/run-01/complete-motor.step':`fixtures/synthetic/simple-v1/${caseName}.step`));
const out=path.resolve(process.env.FEATURE_OUT||(caseName==='motor'?'work/feature-composite-evidence':`work/feature-composite-${caseName}-evidence`));fs.mkdirSync(out,{recursive:true});
function artifact(name){return path.join(out,name.replace(/^motor-/,caseName+'-'));}
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
if(!fs.existsSync(source))throw Error('Motor STEP does not exist: '+source);
const resume=process.env.FEATURE_RESUME==='1';
const initialReport={status:'running',policy:'feature_composite_v1',case:caseName,manufacturing_acceptance:'not_completed',curved_interfaces:'requires_review',started_at:new Date().toISOString(),source:{path:source,bytes:fs.statSync(source).size,sha256:sha(fs.readFileSync(source))},exports:{},runs:[]};
const report=resume?JSON.parse(fs.readFileSync(artifact('workflow.json'),'utf8')):initialReport;report.status='running';report.manufacturing_acceptance='not_completed';report.curved_interfaces='requires_review';delete report.error;
function save(name,value){fs.writeFileSync(artifact(name),JSON.stringify(value,null,2));}
function progress(stage){report.stage=stage;save('workflow.json',report);console.log(stage);}
async function screenshot(locator,name,options={}){if(process.env.FEATURE_NO_SCREENSHOTS==='1')return;try{await locator.screenshot({...options,path:artifact(name),timeout:5000});}catch(error){report.screenshot_warnings=[...(report.screenshot_warnings||[]),{path:artifact(name),error:String(error)}];console.log('Diagnostic screenshot unavailable:',name);}}
const browser=await chromium.launch({headless:true,args:['--no-sandbox','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1700,height:1400}});page.setDefaultTimeout(60000);
const frame=page.frameLocator('iframe'),errors=[];page.on('pageerror',e=>errors.push(String(e)));
async function get(route){const r=await page.request.get(origin+'/api/satellite-blanket/service'+route);if(!r.ok())throw Error(`GET ${route}: ${r.status()} ${await r.text()}`);return r.json();}
async function waitViewer(){await expect(frame.locator('[data-testid=viewer][data-ready=true]')).toBeVisible({timeout:180000});}
async function operation(button,operation){
 const waiting=page.waitForRequest(r=>r.method()==='POST'&&r.url().endsWith('/operations')&&r.postDataJSON()?.operation===operation);
 await button.click({noWaitAfter:true});const req=await waiting,response=await req.response();if(!response?.ok())throw Error(`${operation} submission: ${response?.status()} ${await response?.text()}`);
 const submitted=await response.json(),deadline=Date.now()+600000;let done;
 do{done=await get('/runs/'+submitted.run_id);if(['succeeded','failed','cancelled'].includes(done.state))break;await page.waitForTimeout(500);}while(Date.now()<deadline);
 report.runs.push({operation,run_id:submitted.run_id,state:done.state});save('workflow.json',report);
 if(done.state!=='succeeded')throw Error(`${operation}: ${JSON.stringify(done.error||done.checks||done.state)}`);
 // The backend run is authoritative; the next actual control waits for its enabled state.
 return {parameters:req.postDataJSON().parameters,run:done};
}
function sameFace(a,b){return a?.instance_id===b?.instance_id&&a?.entity_id===b?.entity_id;}
async function offlineScene(model,map){
 const asset=model.artifacts.find(a=>a.format==='GLB'),r=await page.request.get(origin+'/api/satellite-blanket/service'+asset.download_url.replace('/api/v1',''));expect(r.ok()).toBe(true);const bytes=await r.body();expect(sha(bytes)).toBe(asset.sha256);
 const buffer=bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),gltf=await new GLTFLoader().parseAsync(buffer,'');
 const meshes=[];gltf.scene.traverse(o=>{if(!o.isMesh)return;const a=gltf.parser.associations.get(o);let parent=o,node=a?.nodes;while(node===undefined&&parent){node=gltf.parser.associations.get(parent)?.nodes;parent=parent.parent;}o.userData.entries=map.faces.filter(f=>f.node===node&&f.mesh===a.meshes&&f.primitive===a.primitives);o.material=new THREE.MeshBasicMaterial({side:THREE.DoubleSide});meshes.push(o);});gltf.scene.updateMatrixWorld(true);
 const box=new THREE.Box3().setFromObject(gltf.scene),center=box.getCenter(new THREE.Vector3()),size=box.getSize(new THREE.Vector3()).length();
 return {gltf,meshes,box,center,size};
}
function cameraFor(scene,width,height,spherical){const camera=new THREE.PerspectiveCamera(38,width/height,Math.max(scene.size/1000,.00001),Math.max(scene.size*100,10));camera.position.copy(scene.center).add(spherical?new THREE.Vector3().setFromSpherical(spherical):new THREE.Vector3(scene.size*.9,scene.size*.8,scene.size*1.2));camera.lookAt(scene.center);camera.updateMatrixWorld();return camera;}
function rayHit(scene,camera,ndc){const ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2(...ndc),camera);const hit=ray.intersectObjects(scene.meshes,false)[0];if(!hit)return null;const mapped=hit.object.userData.entries.find(f=>hit.faceIndex>=f.triangle_start&&hit.faceIndex<f.triangle_start+f.triangle_count);return mapped?{ref:mapped.face_ref,point:hit.point.toArray(),triangle:hit.faceIndex,ndc}:null;}
async function canvasBox(){const canvas=frame.getByLabel('真实模型三维视图');await canvas.scrollIntoViewIfNeeded();return canvas.boundingBox();}
async function clickNDC(ndc){const b=await canvasBox();await page.mouse.click(b.x+(ndc[0]+1)*b.width/2,b.y+(1-ndc[1])*b.height/2);}
function supportCandidate(scene,map,b,targets){
 const selectedBox=new THREE.Box3();for(const mesh of scene.meshes)if(mesh.userData.entries.some(e=>targets.includes(e.face_ref.instance_id)))selectedBox.union(new THREE.Box3().setFromObject(mesh));
 const all=map.faces.map(f=>f.face_ref).filter(f=>targets.includes(f.instance_id)),axes=[{axis:2,outward:[0,0,-1],gl:new THREE.Vector3(.18,-1,.18)},{axis:0,outward:[-1,0,0],gl:new THREE.Vector3(-1,.18,.18)}];
 for(const setting of axes){
  const candidates=all.filter(f=>f.signature.type==='PLANE'&&Math.abs(f.signature.normal[setting.axis])>.999).sort((a,b)=>a.signature.centroid_mm[setting.axis]-b.signature.centroid_mm[setting.axis]||b.signature.area_mm2-a.signature.area_mm2);
  for(const face of candidates){
   const axisMin=setting.axis===2?selectedBox.min.y*1000:selectedBox.min.x*1000;
   if(Math.abs(face.signature.centroid_mm[setting.axis]-axisMin)>.1)continue;
   const offset=setting.gl.clone().normalize().multiplyScalar(scene.size*Math.hypot(.9,.8,1.2)),spherical=new THREE.Spherical().setFromVector3(offset),camera=cameraFor(scene,b.width,b.height,spherical);
   for(const mesh of scene.meshes){for(const entry of mesh.userData.entries.filter(e=>sameFace(e.face_ref,face))){
    const pos=mesh.geometry.attributes.position,index=mesh.geometry.index;
    for(let t=entry.triangle_start;t<entry.triangle_start+entry.triangle_count;t++){
     const q=new THREE.Vector3();for(let k=0;k<3;k++){const i=index?index.getX(t*3+k):t*3+k;q.add(new THREE.Vector3().fromBufferAttribute(pos,i).applyMatrix4(mesh.matrixWorld));}q.multiplyScalar(1/3);const ndc=q.clone().project(camera);if(Math.abs(ndc.x)>.9||Math.abs(ndc.y)>.9)continue;
     const hit=rayHit(scene,camera,[ndc.x,ndc.y]);if(hit&&sameFace(hit.ref,face))return {face,spherical,hit,axis:setting.axis,into:setting.outward.map(v=>-v)};
    }
   }}
  }
 }
 throw Error('No visible native support plane at world z minimum or x minimum');
}
async function rotateTo(scene,spherical){const b=await canvasBox(),initial=new THREE.Spherical().setFromVector3(new THREE.Vector3(scene.size*.9,scene.size*.8,scene.size*1.2));let theta=spherical.theta-initial.theta;while(theta>Math.PI)theta-=2*Math.PI;while(theta<-Math.PI)theta+=2*Math.PI;
 const dx=-theta*b.height/(2*Math.PI),dy=-(spherical.phi-initial.phi)*b.height/(2*Math.PI),start=[b.x+b.width*.5,b.y+b.height*.5];await page.mouse.move(...start);await page.mouse.down();await page.mouse.move(start[0]+dx,start[1]+dy,{steps:30});await page.mouse.up();await page.waitForTimeout(150);return {dx,dy,initial:{theta:initial.theta,phi:initial.phi},final:{theta:spherical.theta,phi:spherical.phi}};
}
function sheetPoint(net,panel,uv){const r=panel.transform.rotation,t=panel.transform.translation,a=r[0][0]*uv[0]+r[0][1]*uv[1]+t[0],b=r[1][0]*uv[0]+r[1][1]*uv[1]+t[1],l=net.pieces.find(p=>p.id===panel.piece_id).layout,c=Math.cos(l.rotation_rad),s=Math.sin(l.rotation_rad);return [a*c-b*s+l.translation_mm[0],a*s+b*c+l.translation_mm[1]];}
function inRing(uv,ring){let inside=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const a=ring[i],b=ring[j];if((a[1]>uv[1])!==(b[1]>uv[1])&&uv[0]<(b[0]-a[0])*(uv[1]-a[1])/(b[1]-a[1])+a[0])inside=!inside;}return inside;}
function inBody(panel,uv){return inRing(uv,panel.outer_loop.points)&&!panel.holes.some(h=>inRing(uv,h.points));}
async function focusMarker(point,net,index){
 await frame.getByRole('button',{name:index===0?'聚焦定位标记':'下一个定位标记',exact:true}).click({timeout:10000});
 const svg=frame.getByTestId('blanket-drawing');await expect(svg).toHaveAttribute('data-point-editable','true',{timeout:10000});await svg.scrollIntoViewIfNeeded();const panel=net.panels.find(p=>p.key===point.panel_key),marker=frame.getByTestId('point-'+point.id);
 const hit=await marker.evaluate(e=>{const r=e.getBoundingClientRect(),hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return hit?.getAttribute('data-point-id');});
 if(hit!==point.id)throw Error('Focused marker is clipped or covered: '+point.id+' hit '+hit);
 return {svg,panel,marker};
}
async function dragAutoPoint(before){
 const net=before.net;
 for(const [index,point] of [...net.fixed_points.entries()].slice(0,1)){
  let focus;try{focus=await focusMarker(point,net,index);}catch(error){throw Error('First automatic marker focus failed: '+String(error));}
  const {svg,panel,marker}=focus,scale=await svg.evaluate(e=>Math.hypot(e.getScreenCTM().a,e.getScreenCTM().b));let wanted;
  for(const d of [Math.max(2,8/scale),Math.max(5,16/scale),Math.max(10,24/scale)]){for(const [a,b] of [[1,0],[-1,0],[0,1],[0,-1],[.707,.707],[-.707,-.707]]){const candidate=[point.uv_mm[0]+a*d,point.uv_mm[1]+b*d];if(inBody(panel,candidate)){wanted=candidate;break;}}if(wanted)break;}
  if(!wanted){console.log('point has no interior destination',point.id);continue;}
  const sheet=sheetPoint(net,panel,wanted),to=await svg.evaluate((e,p)=>{const q=new DOMPoint(...p).matrixTransform(e.getScreenCTM());return [q.x,q.y];},sheet),iframe=await page.locator('iframe').boundingBox(),box=await marker.boundingBox();
  const posted=page.waitForRequest(r=>r.method()==='POST'&&r.url().endsWith('/operations')&&r.postDataJSON()?.operation==='blanket.edit_fixed_points');
  await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(iframe.x+to[0],iframe.y+to[1],{steps:12});await page.mouse.up();const request=await posted,command=request.postDataJSON().parameters.command;
  expect(command.action).toBe('move');expect(command.id).toBe(point.id);expect(command.panel_key).toBe(point.panel_key);expect(command.uv_mm[0]).toBeCloseTo(wanted[0],3);expect(command.uv_mm[1]).toBeCloseTo(wanted[1],3);
  await expect(svg).not.toHaveAttribute('data-revision',net.revision_id,{timeout:180000});await expect(svg).toHaveAttribute('data-point-saving','false');
  const after=await get(`/projects/${report.project}/blanket-net`),changed=after.net.fixed_points.find(p=>p.id===point.id);expect(changed.uv_mm[0]).toBeCloseTo(wanted[0],3);expect(changed.uv_mm[1]).toBeCloseTo(wanted[1],3);expect(after.net.fixed_points).toHaveLength(net.fixed_points.length);
  return {after,point_id:point.id,panel_key:point.panel_key,initial_uv:point.uv_mm,requested_uv:wanted,persisted_uv:changed.uv_mm,position3d_before:point.position3d,position3d_after:changed.position3d};
 }
 throw Error('No visible automatic point has an interior material destination large enough for a real drag');
}
async function exportDWG(label,net){
 const downloaded=page.waitForEvent('download',{timeout:600000}),op=operation(frame.getByRole('button',{name:'导出并预览 DWG 草稿',exact:true}),'drawing.export');const [download]=await Promise.all([downloaded,op]);const file=artifact(`motor-${label}.dwg`);await download.saveAs(file);const bytes=fs.readFileSync(file);expect(bytes.subarray(0,6).toString()).toBe('AC1032');
 await expect(frame.getByTestId('dwg-preview')).toBeVisible({timeout:600000});await expect.poll(()=>frame.getByTestId('dwg-preview').locator('img').evaluate(e=>e.complete&&e.naturalWidth>0),{timeout:60000}).toBe(true);await screenshot(frame.getByTestId('dwg-preview'),`motor-${label}-preview.png`);
 report.exports[label]={path:file,dwg:file,bytes:bytes.length,sha256:sha(bytes),revision:net.net.revision_id,net:artifact(`motor-${label}-net.json`),product_preview_visible:true};save(`motor-${label}-net.json`,net);save('workflow.json',report);
}
try{
 progress('opening');await page.goto(origin,{waitUntil:'commit'});await page.getByRole('button',{name:'多层图纸',exact:true}).click();await expect(frame.getByRole('button',{name:'新建工程',exact:true})).toBeEnabled();
 if(!resume){
 const oldProject=await frame.getByTestId('project').textContent();await frame.getByRole('button',{name:'新建工程',exact:true}).click();await expect(frame.getByTestId('project')).not.toHaveText(oldProject);report.project=await frame.getByTestId('project').textContent();progress('importing motor');await frame.getByLabel('导入 STEP',{exact:true}).setInputFiles(source);await waitViewer();
 const project=await get('/projects/'+report.project),revision=await get(`/projects/${report.project}/revisions/${project.module_states.blanket}`),model=await get(`/projects/${report.project}/models/${revision.model_ref.model_id}`),map=await get('/artifacts/'+model.artifacts.find(a=>a.relative_storage_path.endsWith('mesh-map.json')).id),scene=await offlineScene(model,map);save('motor-import.json',{project,revision,model,map});
 const physical=[...new Set([...map.faces,...(map.unrenderable_faces||[])].map(f=>f.face_ref.instance_id))];let targets=physical;
 if(moduleCase){expect(physical).toHaveLength(3);const nodes=model.snapshot.instances,module=nodes.find(n=>n.name==='Equipment-module');expect(module,'Named equipment subgroup must exist').toBeTruthy();const pending=[module.instance_id],descendants=[];while(pending.length){const id=pending.pop();descendants.push(id);pending.push(...nodes.filter(n=>n.parent_instance_id===id).map(n=>n.instance_id));}targets=physical.filter(id=>descendants.includes(id));expect(targets).toHaveLength(2);report.module_selection={name:module.name,instance_ids:targets,source_names:nodes.filter(n=>targets.includes(n.instance_id)).map(n=>n.name),neighbor_ids:physical.filter(id=>!targets.includes(id))};expect(report.module_selection.source_names.sort()).toEqual(['Body','Terminal']);}
 else expect(physical,'This fixture is one complete native motor solid').toHaveLength(1);
 const b=await canvasBox(),initialCamera=cameraFor(scene,b.width,b.height);let targetHit;
 for(const y of [0,-.2,.2,-.4,.4]){for(const x of [0,-.2,.2,-.4,.4]){const hit=rayHit(scene,initialCamera,[x,y]);if(hit&&targets.includes(hit.ref.instance_id)){targetHit=hit;break;}}if(targetHit)break;}if(!targetHit){for(const mesh of scene.meshes){if(!mesh.userData.entries.some(e=>targets.includes(e.face_ref.instance_id)))continue;const pos=mesh.geometry.attributes.position,index=mesh.geometry.index,count=(index?index.count:pos.count)/3;for(let t=0;t<count;t+=Math.max(1,Math.floor(count/500))){const q=new THREE.Vector3();for(let k=0;k<3;k++)q.add(new THREE.Vector3().fromBufferAttribute(pos,index?index.getX(t*3+k):t*3+k).applyMatrix4(mesh.matrixWorld));q.multiplyScalar(1/3);const ndc=q.project(initialCamera);if(Math.abs(ndc.x)>.9||Math.abs(ndc.y)>.9)continue;const hit=rayHit(scene,initialCamera,[ndc.x,ndc.y]);if(hit&&targets.includes(hit.ref.instance_id)){targetHit=hit;break;}}if(targetHit)break;}}expect(targetHit).toBeTruthy();
 await frame.getByRole('button',{name:'包覆对象',exact:true}).click();await clickNDC(targetHit.ndc);await expect(frame.getByTestId('selection-count')).toContainText('包覆对象 '+targets.length);
 const support=supportCandidate(scene,map,await canvasBox(),targets);await frame.getByRole('button',{name:'定位参考面',exact:true}).click();const orbit=await rotateTo(scene,support.spherical);await clickNDC(support.hit.ndc);await expect(frame.getByTestId('installation-face')).toContainText('已选择');await waitViewer();
 report.selection={physical_instances:physical,target_instances:targets,target_click:targetHit,support_face:support.face,support_click:support.hit,orbit,glb_box:{min:scene.box.min.toArray(),max:scene.box.max.toArray()},actual_camera_basis:'Viewer3D Box3 center and diagonal'};
 progress('generating native feature cover');let generated=await operation(frame.getByRole('button',{name:'生成组合预览',exact:true}),'blanket.generate');const params=generated.parameters;expect(params.envelope_policy).toBe('feature_composite_v1');expect([...params.target_instances].sort()).toEqual([...targets].sort());expect(params.excluded_instances).toEqual([]);expect(sameFace(params.installation_face,support.face)).toBe(true);expect(params.installation_frame.origin).toEqual(support.face.signature.centroid_mm);expect(params.installation_frame.z_axis.reduce((sum,v,i)=>sum+v*support.into[i],0)).toBeGreaterThan(.999);report.selection.submitted=params;
 let cover=await get(`/projects/${report.project}/blanket-result`);expect(cover?.blanket?.feature_composite).toBeTruthy();save('motor-default-limit-cover.json',cover);
 if(moduleCase)expect(cover.blanket.manufacturing_summary?.requirements_unmet||[]).not.toContain('piece_limit_exceeded');
 if(cover.blanket.manufacturing_summary?.requirements_unmet?.includes('piece_limit_exceeded')){const count=cover.blanket.manufacturing_summary.pieces_per_layer;expect(count).toBeGreaterThan(10);report.default_limit={status:'explicit_limit_preview',limit:10,required:count,feature_count:cover.blanket.feature_composite.primitive_count};const limitedNet=await get('/projects/'+report.project+'/blanket-net');expect(limitedNet.net.pieces.length).toBe(count);await expect(frame.getByTestId('blanket-drawing')).toBeVisible();await expect(frame.getByRole('button',{name:'导出并预览 DWG 草稿',exact:true})).toBeDisabled();save('motor-default-limit-net.json',limitedNet);await screenshot(page,'motor-default-limit.png',{fullPage:true});await frame.getByText('开口与数量设置',{exact:true}).click();await frame.getByLabel('每层裁片上限',{exact:true}).fill(String(Math.min(100,Math.max(30,count))));await operation(frame.getByRole('button',{name:'生成组合预览',exact:true}),'blanket.generate');cover=await get(`/projects/${report.project}/blanket-result`);}
 expect(cover.blanket.feature_composite.primitive_count).toBeGreaterThan(caseName==='motor'||moduleCase?1:0);expect(cover.blanket.feature_composite.uncovered_source_volume_mm3).toBeLessThan(.01);save('motor-cover.json',cover);report.feature_summary=cover.blanket.feature_composite;
 progress('unfolding feature material');await operation(frame.getByRole('button',{name:'展开裁片',exact:true}),'blanket.unfold');
 }else{await expect(frame.getByTestId('project')).toHaveText(report.project);await waitViewer();if(process.env.FEATURE_REGENERATE==='1'){progress('regenerating current feature cover for resume');await operation(frame.getByRole('button',{name:'生成组合预览',exact:true}),'blanket.generate');const cover=await get(`/projects/${report.project}/blanket-result`);save('motor-cover.json',cover);report.feature_summary=cover.blanket.feature_composite;}if(process.env.FEATURE_REUNFOLD==='1'){progress('refreshing feature unfold for resume');await operation(frame.getByRole('button',{name:'展开裁片',exact:true}),'blanket.unfold');}}
 await expect(frame.getByTestId('blanket-drawing')).toBeVisible();const afterDragResume=process.env.FEATURE_AFTER_DRAG==='1',currentNet=await get(`/projects/${report.project}/blanket-net`),before=afterDragResume?JSON.parse(fs.readFileSync(report.exports.before.net,'utf8')):currentNet;expect(before.net.fixed_points.length).toBeGreaterThan(0);expect(before.net.fixed_points.every(p=>p.status==='valid')).toBe(true);expect(before.net.manufacturing_summary.pieces_per_layer).toBe(before.net.pieces.length);report.auto_point_count=before.net.fixed_points.length;progress('exporting before drag');const prior=report.exports.before;if(prior?.revision===before.net.revision_id&&fs.existsSync(prior.path)&&sha(fs.readFileSync(prior.path))===prior.sha256){console.log('Reusing the actual verified before DWG at current revision');}else await exportDWG('before',before);if(caseName==='motor'){await page.reload({waitUntil:'domcontentloaded',timeout:180000});await page.getByRole('button',{name:'多层图纸',exact:true}).click();await expect(frame.getByTestId('blanket-drawing')).toHaveAttribute('data-revision',currentNet.net.revision_id);}
 if(caseName==='motor'){
 progress('dragging automatic point');let dragged;
 if(afterDragResume){const saved=JSON.parse(fs.readFileSync(artifact('motor-dragged-point-net.json'),'utf8'));expect(saved.net.revision_id).toBe(currentNet.net.revision_id);expect(saved.net.model_ref).toEqual(before.net.model_ref);const changed=before.net.fixed_points.filter(p=>JSON.stringify(p.uv_mm)!==JSON.stringify(currentNet.net.fixed_points.find(q=>q.id===p.id)?.uv_mm));expect(changed).toHaveLength(1);const old=changed[0],point=currentNet.net.fixed_points.find(p=>p.id===old.id);dragged={after:currentNet,point_id:point.id,panel_key:point.panel_key,initial_uv:old.uv_mm,persisted_uv:point.uv_mm,position3d_before:old.position3d,position3d_after:point.position3d,resumed_persisted_drag:true};save('motor-drag-command-revision.json',await get(`/projects/${report.project}/revisions/${currentNet.net.revision_id}`));}
 else dragged=await dragAutoPoint(before);report.drag={...dragged,after:undefined};save('motor-after-net.json',dragged.after);report.point_id=dragged.point_id;save('motor-dragged-point-net.json',dragged.after);save('workflow.json',report);await screenshot(frame.getByTestId('blanket-drawing'),'motor-dragged-point.png');
 const editSummary=frame.getByText('搭接、固定点与图纸编辑',{exact:true});if(await editSummary.locator('..').getAttribute('open')===null)await editSummary.click();const positions=dragged.after.net.drawing_document.entities.flatMap(e=>e.points||[e.start,e.end,e.position].filter(Boolean)),notePosition=[Math.min(...positions.map(p=>p[0])),Math.min(...positions.map(p=>p[1]))-30],note='电机组合包络裁片；单位毫米';
 await frame.getByLabel('图纸注释',{exact:true}).fill(note);await frame.getByLabel('文字 X',{exact:true}).fill(String(notePosition[0]));await frame.getByLabel('文字 Y',{exact:true}).fill(String(notePosition[1]));await frame.getByRole('button',{name:'预览注释布局',exact:true}).click();await operation(frame.getByRole('button',{name:'执行修改',exact:true}),'drawing.edit_annotation');dragged.after=await get(`/projects/${report.project}/blanket-net`);expect(dragged.after.net.fixed_points.find(p=>p.id===dragged.point_id).uv_mm).toEqual(dragged.persisted_uv);expect(dragged.after.net.drawing_document.entities.some(e=>e.kind==='text'&&e.text===note)).toBe(true);report.annotation={text:note,position:notePosition};
 progress('exporting after drag');await exportDWG('after',dragged.after);expect(report.exports.before.sha256).not.toBe(report.exports.after.sha256);
 await page.reload({waitUntil:'domcontentloaded',timeout:180000});await page.getByRole('button',{name:'多层图纸',exact:true}).click();await expect(frame.getByTestId('blanket-drawing')).toHaveAttribute('data-revision',dragged.after.net.revision_id,{timeout:60000});const refreshed=await get(`/projects/${report.project}/blanket-net`);expect(refreshed.net.fixed_points.find(p=>p.id===dragged.point_id).uv_mm).toEqual(dragged.persisted_uv);report.refresh_preserved=true;
 progress('saving and restoring engineering');await operation(frame.getByRole('button',{name:'保存工程包',exact:true}),'engineering.save');await operation(frame.getByRole('button',{name:'恢复工程包',exact:true}),'engineering.restore');const restored=await get(`/projects/${report.project}/blanket-net`);expect(restored.net.fixed_points.map(p=>p.id)).toEqual(dragged.after.net.fixed_points.map(p=>p.id));expect(restored.net.fixed_points.find(p=>p.id===dragged.point_id).uv_mm).toEqual(dragged.persisted_uv);save('motor-restored-net.json',restored);report.restore_preserved=true;report.final_revision=restored.net.revision_id;
 }else{report.final_revision=before.net.revision_id;if(moduleCase){report.terminal_included=true;report.neighbor_unselected=true;}report.point_id=before.net.fixed_points[0].id;}
 if(caseName==='motor'){await frame.getByRole('button',{name:'复位视图',exact:true}).click();await screenshot(page,'motor-final-workbench.png',{fullPage:true});}expect(errors).toEqual([]);report.artifacts=fs.readdirSync(out).filter(name=>/^(motor|module|cube|cylinder)-.*\.(json|png)$/.test(name)&&!name.includes('-failure.')&&!(report.screenshot_warnings||[]).some(w=>w.path===artifact(name))).map(name=>{const file=artifact(name);return {path:file,sha256:sha(fs.readFileSync(file))};});report.status='passed';report.browser_errors=errors;report.completed_at=new Date().toISOString();progress('complete');console.log(JSON.stringify({status:report.status,project:report.project,point_id:report.point_id,report:artifact('workflow.json'),exports:report.exports}));
}catch(error){report.status='failed';report.error=String(error);report.browser_errors=errors;save('workflow.json',report);console.error(String(error));console.error((await frame.locator('body').innerText().catch(()=>'' )).slice(0,16000));await screenshot(page,'motor-failure.png',{fullPage:true});process.exitCode=1;}finally{await browser.close();}
