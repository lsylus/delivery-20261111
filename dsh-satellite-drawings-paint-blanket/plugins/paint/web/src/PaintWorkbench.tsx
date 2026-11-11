import React,{useEffect,useRef,useState} from 'react';
import {Api} from '../../../../packages/workbench-common/src/api';
import {LiveProvider} from '../../../../packages/workbench-common/src/providers';
import {execute} from '../../../../packages/workbench-common/src/interaction/commands';
import {Viewer3D} from '../../../../packages/workbench-common/src/Viewer3D';
import {PaintDrawing} from './PaintRegions';
import {PaintSessionApi,sessionChanged} from './PaintSessionApi';
import {selectionContext} from '../../../../packages/workbench-common/src/interaction/selection';
import {same} from '../../../../packages/host-bridge/src/selection-context.mjs';
import {flipPaintTargets,paintFaceStates,paintTargetGroups,recommendedSelection,selectedGroupIds,stableSelection,togglePaintTarget} from './paint-target-groups';
import {batchDiagnosticSummary} from './batch-diagnostics';

export function PaintWorkbench(){
 const [identity,setIdentity]=useState<any>(null),[loaded,setLoaded]=useState<any>(null),[project,setProject]=useState(''),[selected,setSelected]=useState<any[]>([]);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[runId,setRunId]=useState(''),[bundle,setBundle]=useState('');
 const [points,setPoints]=useState<number[][]>([]),[region,setRegion]=useState(''),[chat,setChat]=useState('这里补保护'),[reason,setReason]=useState('人工保护修订'),[dx,setDx]=useState(1),[dy,setDy]=useState(0);
 const [annotation,setAnnotation]=useState('保护区域待复核'),[pending,setPending]=useState<any>(null),[offset,setOffset]=useState(3);
 const provider=useRef<LiveProvider|null>(null),assertSession=useRef<(()=>void)|null>(null),epoch=useRef(0),selectionDirty=!!loaded&&!same(selected,loaded.revision.selection);
 const [rebindSource,setRebindSource]=useState('');
 const [boundary,setBoundary]=useState('');
 const [activeBatchGroup,setActiveBatchGroup]=useState('');
 const savedKey=(id:any,p:string)=>`b09-bundle:${id.owner_id}:${id.session_id}:${p}`;
 function adopt(value:any){
  const groups=paintTargetGroups(value),saved=value?.revision.selection||[];
  setBoundary('');setLoaded(value);setSelected(saved.length?stableSelection(groups,saved):recommendedSelection(groups));setPoints([]);setRegion('');setPending(null);
  setActiveBatchGroup(value?.paintBatchResult?.batch?.groups?.[0]?.group_id||'');
  if(value)setOffset(value.revision.parameters.contact_offset_mm??value.revision.parameters.protection_offset_mm??3);
 }
 useEffect(()=>{
  const ac=new AbortController(),mine=++epoch.current,expected=new URLSearchParams(location.search).get('session');
  let timer:ReturnType<typeof setInterval>|undefined,checking=false;
  function invalidate(message:string){
   if(mine!==epoch.current)return;
   ++epoch.current;ac.abort();clearInterval(timer);provider.current=null;assertSession.current=null;
   setIdentity(null);adopt(null);setProject('');setBundle('');setRunId('');setNotice('');setBusy(false);setOffset(3);setError(message);
  }
  function assertCurrent(){
   if(mine!==epoch.current||ac.signal.aborted)throw Error(sessionChanged);
   if(new URLSearchParams(location.search).get('session')!==expected){invalidate(sessionChanged);throw Error(sessionChanged);}
  }
  const onLocationChange=()=>{try{assertCurrent();}catch{}};
  window.addEventListener('popstate',onLocationChange);
  (async()=>{
   const id=await new Api('paint',ac.signal).identity();assertCurrent();
   if(expected!==null&&expected!==id.session_id){invalidate(sessionChanged);return;}
   const api=new PaintSessionApi(ac.signal,id,assertCurrent,invalidate),p=new LiveProvider(api,id);
   // Start monitoring before any binding/model fetch can suspend initialization.
   timer=setInterval(async()=>{if(checking)return;checking=true;try{await api.checkIdentity();}catch{}finally{checking=false;}},1000);
   const binding=await api.json(`/sessions/${id.session_id}/binding`).catch(e=>{if(String(e).includes('404'))return null;throw e;});
   const value=binding?await p.load(binding.project_id):null;
   await api.checkIdentity();assertCurrent();
   provider.current=p;assertSession.current=assertCurrent;setIdentity(id);
   if(binding){setProject(binding.project_id);adopt(value);setBundle(localStorage.getItem(savedKey(id,binding.project_id))||'');}
  })().catch(e=>{if(!ac.signal.aborted)invalidate(String(e));});
  return()=>{++epoch.current;ac.abort();clearInterval(timer);provider.current=null;assertSession.current=null;window.removeEventListener('popstate',onLocationChange);};
 },[]);
 async function action(fn:(p:LiveProvider,adoptCurrent:(x:any)=>void,commit:(fn:()=>void)=>Promise<void>)=>Promise<void>){
  const mine=epoch.current,p=provider.current;if(!p)return;
  const current=()=>{if(mine!==epoch.current||provider.current!==p)throw Error(sessionChanged);assertSession.current!();};
  const commit=async(fn:()=>void)=>{await (p.api as PaintSessionApi).checkIdentity();current();fn();};
  setBusy(true);setError('');
  try{await (p.api as PaintSessionApi).checkIdentity();current();await fn(p,x=>{current();adopt(x);},commit);}
  catch(e){if(mine===epoch.current)setError(String(e));}
  finally{if(mine===epoch.current){setBusy(false);setRunId('');}}
 }
 async function run(p:LiveProvider,revision:any,operation:string,parameters:any={}){
  const mine=epoch.current,r=await execute(p.api,p.identity,revision,operation,parameters);
  if(mine!==epoch.current)throw Error(sessionChanged);assertSession.current!();setRunId(r.run_id);
  const completed=await p.api.wait(r.run_id,960000);
  if(mine!==epoch.current)throw Error(sessionChanged);assertSession.current!();return completed;
 }
 const groups=paintTargetGroups(loaded),selectedIds=selectedGroupIds(groups,selected),faceStates=paintFaceStates(groups,selected);
 const recommendations=loaded?.paintRecommendations?.groups||[],batchResult=loaded?.paintBatchResult,batchGroups=batchResult?.batch?.groups||[];
 const hasGroupedTargets=recommendations.length>0||Array.isArray(loaded?.revision?.parameters?.target_face_groups)&&loaded.revision.parameters.target_face_groups.length>0;
 const activeBatch=batchGroups.find((item:any)=>item.group_id===(activeBatchGroup||batchGroups[0]?.group_id));
 const activeBatchPaint=activeBatch?.paint||activeBatch?.paint_result;
 const result=activeBatch?activeBatchPaint?{result_id:activeBatch.result_id||batchResult.result_id,paint:activeBatchPaint}:null:loaded?.paintResult;
 const activeBatchDiagnostic=activeBatch&&!activeBatchPaint?.drawing_document?batchDiagnosticSummary(activeBatch):null;
 const dirty=selectionDirty||(!!loaded&&offset!==(loaded.revision.parameters.contact_offset_mm??loaded.revision.parameters.protection_offset_mm??3));
 const batchMode=!!batchResult,valid=batchMode?!!batchResult.result_id&&!dirty:!!result?.paint?.drawing_document&&result.paint.revision_id===loaded?.revision.id&&!dirty,editable=valid&&!batchMode;
 const canFlip=groups.some(group=>selectedIds.includes(group.id)&&group.opposite_group_id&&groups.some(other=>other.id===group.opposite_group_id&&other.selectable));
 function propose(action:string){if(!editable)return;const parameters=action==='move'?{result_id:result.result_id,action,region_id:region,delta_mm:[dx,dy],reason}:{result_id:result.result_id,action,points,reason};setPending({operation:'paint.edit_regions',parameters});}
 return <main className="paint-workbench"><header><h1>喷漆图纸工作台</h1><span className="badge" data-testid="mode">LIVE · STEP</span></header>
 <p data-testid="identity">{identity?`${identity.owner_id} / ${identity.session_id}`:error?'连接已中止':'连接中'} · {identity?.host_mode==='dsh-account'?'账号工作台 · 待平台验收':'隔离测试环境'}</p>
 <p>正式 DSH 身份映射尚未验收；DWG 为待人工复核草稿。</p>
 {error&&<div role="alert">{error}。{identity?'保留上次有效结果，请刷新确认当前版本。':'连接已中止，工程与结果引用已清空。'}</div>}{notice&&<p role="status">{notice}</p>}
 <nav><button disabled={busy||!identity} onClick={()=>action(async(p,a,commit)=>{const id=await p.create();await commit(()=>{setProject(id);a(null);setBundle('');setNotice('');});})}>新建工程</button>
 <label>导入 STEP<input aria-label="导入 STEP" type="file" accept=".step,.stp" disabled={busy||!project} onChange={e=>{const f=e.target.files?.[0];if(f)action(async(p,a)=>a(await p.upload(project,f,loaded?.revision.id||'empty')));e.target.value='';}}/></label>
 <button disabled={busy||!project} onClick={()=>action(async(p,a)=>a(await p.load(project)))}>刷新模型</button><span data-testid="project">{project}</span>
 {busy&&<span>后端执行中 {runId}</span>}{runId&&<button onClick={()=>{const p=provider.current,mine=epoch.current;if(p)void p.api.json(`/runs/${runId}/cancel`,{method:'POST'}).catch(e=>{if(mine===epoch.current)setError(String(e));});}}>取消任务</button>}</nav>
 {loaded&&<section><label>重绑来源修订<input aria-label="重绑来源修订" value={rebindSource} disabled={busy} onChange={e=>setRebindSource(e.target.value)}/></label><button disabled={busy||!rebindSource} onClick={()=>action(async(p,_a,c)=>{const response=await execute(p.api,p.identity,loaded.revision,'engineering.rebind',{source_revision_id:rebindSource});const finished=await p.api.wait(response.run_id);const artifact=finished.artifacts.find((a:any)=>a.role==='revision_rebinding');const report=await p.api.json(artifact.download_url.replace('/api/v1',''));const refreshed=await p.load(project);await c(()=>{adopt(refreshed);setNotice(report.status==='valid'?'唯一映射已重放；历史保留。':'无法唯一重绑，需要重新选择；原修订和测量记录保留。');});})}>检查并重绑来源修订</button><p>本版本自动出图仅支持平面或共面板面组；曲面不会近似投影。</p></section>}
 {loaded&&<><p data-testid="revision">工程版本 {loaded.revision.id}</p><div className="layout"><aside><h2>装配与选面</h2><p data-testid="assembly-tree">装配包含 {loaded.snapshot.instances.length} 个组件；直接点击三维模型选择板面。</p>
 <p data-testid="selection-count">已选 {selectedIds.length} 个板面组 / {selected.length} 个源面</p><div className="buttons"><button disabled={busy||!groups.some(group=>group.recommended&&group.selectable)} onClick={()=>{setSelected(recommendedSelection(groups));setPending(null);}}>选择全部推荐项</button><button disabled={busy||!selected.length} onClick={()=>{setSelected([]);setPending(null);}}>清空选择</button><button disabled={busy||!canFlip} onClick={()=>{setSelected(flipPaintTargets(groups,selected));setPending(null);}}>翻面</button></div>
 <p>{hasGroupedTargets?`${recommendations.length?'系统推荐':'当前工程保存'} ${groups.filter(group=>group.recommended&&group.selectable).length} 个板面组；绿色为已选，点击模型可取消或追加。`:'当前模型没有面组推荐数据；三维点选仍可使用。'}</p><label>保护外扩 mm<input aria-label="保护外扩 mm" type="number" min="0" value={offset} onChange={e=>setOffset(Number(e.target.value))}/></label>
 <button disabled={busy||!selected.length||!Number.isFinite(offset)||offset<0} onClick={()=>action(async(p,a,commit)=>{const previous=loaded.revision,active=new Set(selectedIds),targetGroups=groups.filter(group=>active.has(group.id)).map(group=>({group_id:group.id,instance_id:group.instance_id||group.face_refs[0]?.instance_id,instance_name:group.instance_name||'',direction_label:group.direction_label||'',normal:group.normal||group.face_refs[0]?.signature?.normal||[0,0,0],side_label:group.side_label||'',paint_type:group.paint_type||group.default_paint_type||'',target_face_refs:group.face_refs})),params={schema_version:1,model_ref:previous.model_ref,target_face_refs:stableSelection(groups,selected),...(hasGroupedTargets?{target_face_groups:targetGroups}:{}),...(same(selected,previous.parameters.target_face_refs)?{curved_boundary_rules:previous.parameters.curved_boundary_rules||[]} : {}),scope_boundary:null,contact_threshold_mm:.1,contact_comparison:'lt',contact_offset_mm:offset,hole_offset_mm:offset,boss_rule:'protect',boss_additional_offset_mm:offset,rib_rule:'retain_paint',overrides:previous.overrides,rule_version:'paint-v1'};
 const revision=await p.api.json(`/projects/${project}/revisions`,{method:'POST',body:JSON.stringify({expected_revision:previous.id,model_ref:previous.model_ref,parameters:params,selection:params.target_face_refs,overrides:previous.overrides})});await run(p,revision,hasGroupedTargets?'paint.generate_batch':'paint.generate',params);a(await p.load(project));await commit(()=>setNotice(hasGroupedTargets?'批量生成完成；请逐面检查规则结果和失败项。':'后端生成完成；请检查规则结果和人工复核状态。'));})}>{hasGroupedTargets?'批量生成保护区':'生成保护区'}</button></aside>
 <section className="views"><div className="view-card"><h2>三维模型与保护 <small>绿色已选 · 金色保护</small></h2><Viewer3D loaded={{...loaded,paint:result?.paint,selectedRegion:region}} selected={selected} faceStates={faceStates} onSelect={(refs:any[])=>{if(!busy&&refs[0]){setSelected(current=>togglePaintTarget(groups,current,refs[0]));setPending(null);}}} onError={setError}/></div>
 <div className="view-card"><h2>二维工程图</h2>{batchGroups.length>1&&<label>当前图纸<select aria-label="当前图纸" value={activeBatchGroup||batchGroups[0]?.group_id} onChange={e=>{setActiveBatchGroup(e.target.value);setRegion('');setPoints([]);setPending(null);}}>{batchGroups.map((item:any)=><option key={item.group_id} value={item.group_id}>{item.direction_label||item.direction||item.side_label||item.side||item.group_id} · {item.status}</option>)}</select></label>}{result?.paint?.drawing_document?<PaintDrawing key={result.paint.revision_id+'-'+(activeBatch?.group_id||'single')} document={result.paint.drawing_document} onPolygon={(p:number[][])=>{setPoints(p);setRegion('');setPending(null);}} onRegion={(id:string)=>{setRegion(id);setPending(null);}} region={region}/>:activeBatchDiagnostic?<div role="status" data-testid="batch-diagnostic"><strong>{activeBatchDiagnostic.title}</strong><p>错误码：{activeBatchDiagnostic.codes.map((item:any)=>`${item.code}${item.count>1?` ×${item.count}`:''}`).join(' · ')}{activeBatchDiagnostic.codeOverflow?` · 另 ${activeBatchDiagnostic.codeOverflow} 类`:''}</p><p>对象：{activeBatchDiagnostic.objects.join('、')}{activeBatchDiagnostic.objectOverflow?`，另 ${activeBatchDiagnostic.objectOverflow} 个`:''}</p><p>{activeBatchDiagnostic.hints.join(' ')}</p>{activeBatchDiagnostic.detail&&<p>后端信息：{activeBatchDiagnostic.detail}</p>}</div>:<p>选定目标板面后生成真实图纸。</p>}</div></section>
 <aside><h2>{batchMode?'批量图纸':'保护区编辑'}</h2>{batchMode?<p>批量结果可逐面查看并导出；首版不在批次内编辑单个保护区。</p>:<>{result?.paint.surface_mapping&&<div><label>曲面孔口<select aria-label="曲面孔口" value={boundary} disabled={busy} onChange={e=>setBoundary(e.target.value)}><option value="">选择待确认边界</option>{result.paint.evidence[0].boundaries.map((b:any)=><option key={b.boundary_id} value={b.boundary_id}>{b.boundary_id} · {b.classification}</option>)}</select></label>{['hole','boss','rib','exclude'].map(classification=><button key={classification} disabled={busy||!editable||!boundary||!reason.trim()} onClick={()=>action(async(p,a)=>{const previous=loaded.revision,params={...previous.parameters,curved_boundary_rules:[...(previous.parameters.curved_boundary_rules||[]).filter((r:any)=>r.boundary_id!==boundary),{boundary_id:boundary,classification,reason}]};const revision=await p.api.json('/projects/'+project+'/revisions',{method:'POST',body:JSON.stringify({expected_revision:previous.id,model_ref:previous.model_ref,parameters:params,selection:previous.selection,overrides:previous.overrides})});await run(p,revision,'paint.generate',params);a(await p.load(project));})}>{classification==='hole'?'确认孔口3mm保护':classification==='boss'?'确认曲面凸台保护':classification==='rib'?'确认肋板保留喷漆':'排除此边界规则'}</button>)}</div>}<p>Shift 拖动圈画局部区域；点击阴影选区。坐标单位 mm。</p><p data-testid="region-selection">{region||`圈画 ${points.length} 个点`}</p>
 <label>修订原因<input aria-label="修订原因" value={reason} onChange={e=>setReason(e.target.value)}/></label>
 <button disabled={busy||!editable||points.length<3} onClick={()=>propose('add')}>补保护</button><button disabled={busy||!editable||points.length<3} onClick={()=>propose('exclude')}>保留喷漆</button>
 <label>移动 X<input aria-label="移动 X" type="number" value={dx} onChange={e=>setDx(Number(e.target.value))}/></label><label>移动 Y<input aria-label="移动 Y" type="number" value={dy} onChange={e=>setDy(Number(e.target.value))}/></label><button disabled={busy||!editable||!region} onClick={()=>propose('move')}>移动保护边界</button>
 <button disabled={busy||!editable} onClick={()=>action(async(_p,_a,commit)=>{await commit(()=>{const selection=selectionContext(loaded,loaded.revision.selection,'2d',chat,points);window.parent.postMessage({type:'satellite-drawings:chat',request_id:crypto.randomUUID(),selection},location.origin);setNotice('已请求带入宿主聊天草稿，请在宿主确认。');});})}>带入聊天草稿</button>
 <label>对话修改<input aria-label="对话修改" value={chat} onChange={e=>setChat(e.target.value)}/></label><button disabled={busy||!editable} onClick={()=>{if(chat==='这里补保护')propose('add');else if(chat==='这块保留喷漆')propose('exclude');else setError('请输入“这里补保护”或“这块保留喷漆”，并圈画明确区域');}}>预览对话修改</button>
 <label>图纸注释<input aria-label="图纸注释" value={annotation} onChange={e=>setAnnotation(e.target.value)}/></label><button disabled={busy||!editable||points.length<3} onClick={()=>setPending({operation:'drawing.edit_annotation',parameters:{result_id:result.result_id,annotation_id:'note',text:annotation,position:points[0]}})}>放置或移动注释</button>
 {pending&&<div data-testid="command-preview"><p>目标版本 {loaded.revision.id}；结果 {result.result_id}</p><pre>{JSON.stringify(pending.parameters,null,2)}</pre><button disabled={busy||!editable} onClick={()=>action(async(p,a)=>{const completed=await run(p,loaded.revision,pending.operation,pending.parameters);if(completed.checks.some((c:any)=>c.id==='publication'&&c.observed.current===false))throw Error('修订未成为当前结果：检查需复核或版本已改变，原结果已保留');a(await p.load(project));})}>执行修改</button><button disabled={busy} onClick={()=>setPending(null)}>放弃待执行修改</button></div>}</>}
 <div><button disabled={busy} onClick={()=>action(async(p,a)=>{await run(p,loaded.revision,'history.undo');a(await p.load(project));})}>撤销修改</button><button disabled={busy} onClick={()=>action(async(p,a)=>{await run(p,loaded.revision,'history.redo');a(await p.load(project));})}>重做修改</button></div>
 <button disabled={busy||dirty||!!pending} onClick={()=>action(async(p,_a,commit)=>{const r=await run(p,loaded.revision,'engineering.save'),id=r.artifacts.find((a:any)=>a.role==='engineering_bundle').id;await commit(()=>{setBundle(id);localStorage.setItem(savedKey(identity,project),id);setNotice('工程包已保存，包含保护修改和图纸注释。');});})}>保存工程包</button>
 <button disabled={busy||!bundle} onClick={()=>action(async(p,a)=>{await run(p,loaded.revision,'engineering.restore',{artifact_id:bundle});a(await p.load(project));})}>恢复工程包</button>
 <button disabled={busy||!valid||!!pending} onClick={()=>action(async(p,_a,commit)=>{const parameters=batchMode?{batch_result_id:batchResult.result_id,draft:true}:{result_id:result.result_id,draft:true},r=await run(p,loaded.revision,'drawing.export',parameters),a=batchMode?r.artifacts.find((item:any)=>item.filename?.toLowerCase().endsWith('.zip')||item.role==='paint_batch_zip'||item.role==='draft_bundle'):r.artifacts.find((item:any)=>item.role==='draft_dwg');if(!a)throw Error('导出结果缺少下载文件');const b=await(await p.api.request(a.download_url.replace('/api/v1',''))).blob();await commit(()=>{const url=URL.createObjectURL(b),link=document.createElement('a');link.href=url;link.download=a.filename||(batchMode?`paint-${a.revision_id}-DRAFT.zip`:`paint-${a.revision_id}-DRAFT.dwg`);link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);setNotice(batchMode?'批量 DWG 与索引 ZIP 已下载，请逐项复核失败记录。':'真实 DWG 草稿已下载，AutoCAD 与人工工艺复核尚未完成。');});})}>{batchMode?'导出批量 DWG ZIP':'导出 DWG 草稿'}</button>
 <h2>检查与复核</h2><p data-testid="execution-state">后端执行：{busy?'运行中':result||batchResult?'已完成':'未生成'}</p><p data-testid="check-state">规则检查：{batchMode?(batchResult.batch.status||'已生成批次'):(result?.paint.status||'未运行')}</p><p>人工复核：未批准</p><p>当前结果：{dirty?'有未提交选择或参数':pending?'有待执行修改':valid?'同版本':'未生成或已过期'}</p>{!batchMode&&result?.paint.checks.map((c:any)=><p key={c.id}>{c.status} · {c.reason}</p>)}</aside></div></>}
 </main>;
}
