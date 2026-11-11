import React,{useEffect,useRef,useState} from 'react';
import {Api} from './api';
import {LiveProvider,demoProvider} from './providers';
import {readDraft,writeDraft} from './state';
import {same} from '../../host-bridge/src/selection-context.mjs';
import {selectionContext,identityMatrix} from './interaction/selection';
import {execute} from './interaction/commands';
import {drawingFixture} from './fixture';
import {Viewer3D} from './Viewer3D';
import {DrawingView} from './DrawingView';
import {SelectionPanel} from './SelectionPanel';
import {ChecksPanel} from './ChecksPanel';
import type {Loaded} from './types';
function ParameterEditor({value,onChange,onValidity}:{value:any;onChange:(v:any)=>void;onValidity:(v:boolean)=>void}){
  const [text,setText]=useState(JSON.stringify(value)),[invalid,setInvalid]=useState(false);
  useEffect(()=>{setText(JSON.stringify(value));setInvalid(false);onValidity(true);},[value]);
  return <label>参数 JSON<textarea aria-label="参数 JSON" aria-invalid={invalid} value={text} onChange={e=>{setText(e.target.value);try{const p=JSON.parse(e.target.value);if(!p||Array.isArray(p)||typeof p!=='object')throw Error();setInvalid(false);onValidity(true);onChange(p);}catch{setInvalid(true);onValidity(false);}}}/>{invalid&&<small>请输入有效 JSON 对象后保存。</small>}</label>;
}
import {PaintWorkbench} from '../../../plugins/paint/web/src/PaintWorkbench';
export function Workbench({module}:{module:'paint'|'blanket'}){return module==='paint'?<PaintWorkbench/>:<BaseWorkbench module={module}/>;}
function BaseWorkbench({module}:{module:'paint'|'blanket'}){
  const [identity,setIdentity]=useState<any>(null),[loaded,setLoaded]=useState<Loaded|null>(null),[project,setProject]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[notice,setNotice]=useState(''),[draft,setDraft]=useState<any>({selection:[],annotation:'',parameters:{},revision:''}),[view,setView]=useState<'3d'|'2d'>('3d');
  const [parametersValid,setParametersValid]=useState(true);
  const provider=useRef<LiveProvider|null>(null),coords=useRef<number[][]>([]),transform=useRef(identityMatrix),history=useRef<any[]>([]),future=useRef<any[]>([]),epoch=useRef(0);
  function adopt(value:Loaded|null){setLoaded(value);history.current=[];future.current=[];coords.current=[];transform.current=identityMatrix;
    if(value){const saved=readDraft(localStorage,value.identity,value.project.id,value.revision.id);const d=saved||{selection:value.revision.selection,annotation:'',parameters:value.revision.parameters,revision:value.revision.id};
      if(d.selection?.every((ref:any)=>value.map.faces.some((f:any)=>same(f.face_ref,ref))))setDraft(d);else setDraft({selection:[],annotation:'',parameters:value.revision.parameters,revision:value.revision.id});
      window.parent.postMessage({type:'satellite-drawings:context',engineering_revision:value.revision.id},location.origin);
    }
  }
  useEffect(()=>{
    const ac=new AbortController(),my=++epoch.current,api=new Api(module,ac.signal);let timer:any;
    (async()=>{
      const id=await api.identity();const expected=new URLSearchParams(location.search).get('session');if(expected&&expected!==id.session_id)throw Error('会话已改变，请重新打开工作台');
      if(my!==epoch.current)return;setIdentity(id);const p=new LiveProvider(api,id);provider.current=p;
      const binding=await api.json(`/sessions/${id.session_id}/binding`).catch(e=>{if(String(e).includes('404'))return null;throw e;});
      if(binding?.project_id){setProject(binding.project_id);const value=await p.load(binding.project_id);if(my===epoch.current)adopt(value);}
      timer=setInterval(async()=>{try{const next=await api.identity();if(!same(next,id)){++epoch.current;ac.abort();provider.current=null;setIdentity(null);setProject('');setLoaded(null);setDraft({selection:[],annotation:'',parameters:{}});setError('会话已改变，请重新打开工作台');clearInterval(timer);}}catch(e){if(!ac.signal.aborted)setError(String(e));}},1500);
    })().catch(e=>{if(!ac.signal.aborted)setError(String(e));});
    return()=>{++epoch.current;ac.abort();clearInterval(timer);provider.current=null;};
  },[module]);
  function edit(next:any){history.current.push(draft);future.current=[];setDraft(next);if(identity&&project)writeDraft(localStorage,identity,project,next);}
  function undo(redo=false){const from=redo?future:history,to=redo?history:future;if(!from.current.length)return;to.current.push(draft);const next=from.current.pop();setDraft(next);writeDraft(localStorage,identity,project,next);}
  function select(refs:any[],origin:'2d'|'3d',points:number[][],matrix:number[]){setView(origin);coords.current=points;transform.current=matrix;edit({...draft,selection:refs});}
  async function action(fn:()=>Promise<any>){setBusy(true);setError('');const my=epoch.current;try{await fn();}catch(e){if(my===epoch.current)setError(String(e));}finally{if(my===epoch.current)setBusy(false);}}
  const dirty=!!loaded&&(!same(draft.selection,loaded.revision.selection)||!same(draft.parameters,loaded.revision.parameters)||!!draft.annotation);
  return <main><header><div><span className="eyebrow">SATELLITE DRAWINGS</span><h1>{module==='paint'?'喷漆图纸':'多层图纸'}工作台</h1></div><span className="badge" data-testid="mode">LIVE · B06 真实模型</span></header>
    <div className="identity" data-testid="identity">{identity?`${identity.owner_id} / ${identity.session_id} / ${module}`:'连接身份中…'} <span>{identity?.host_mode==='dsh-account'?'账号工作台 · 待平台验收':'隔离适配 · 正式宿主未配置'}</span></div>
    {error&&<div role="alert">{error}。未切换演示数据。{loaded&&'保留上次有效模型，当前连接未确认。'}</div>}
    <nav><button disabled={!identity||busy} onClick={()=>action(async()=>{const id=await provider.current!.create();setProject(id);adopt(null);setNotice('工程已创建，请导入 STEP。');})}>新建工程</button>
      <label className="upload">导入 STEP<input aria-label="导入 STEP" type="file" accept=".step,.stp" disabled={!project||busy} onChange={e=>{const f=e.target.files?.[0];if(f)action(async()=>adopt(await provider.current!.upload(project,f,loaded?.revision.id||'empty')));e.target.value='';}}/></label>
      <button disabled={!project||busy} onClick={()=>action(async()=>adopt(await provider.current!.load(project)))}>刷新模型</button>
      <span data-testid="project">{project||'尚未关联工程'}</span><a href={demoProvider.url} target="_blank" rel="noreferrer">查看原型示例（DEMO）</a></nav>
    {busy&&<p role="status">正在请求真实服务…</p>}{notice&&<p role="status">{notice}</p>}
    {!loaded?<div className="empty"><h2>导入装配，开始选择</h2><p>新建工程后上传 STEP，显示真实装配树与精确面引用。</p><p>模型未就绪时不会显示演示几何。</p></div>:<>
    <div className="layout"><aside><h2>装配树</h2><ul data-testid="assembly-tree">{loaded.snapshot.instances.map((i:any)=><li key={i.instance_id} style={{marginLeft:i.parent_instance_id?12:0}}>{i.name}<small>{i.instance_id}</small></li>)}</ul><SelectionPanel selected={draft.selection}/><label>对话批注<textarea aria-label="对话批注" value={draft.annotation} onChange={e=>edit({...draft,annotation:e.target.value})}/></label><button disabled={!draft.selection.length||busy||!!error} onClick={()=>{
      const selection=selectionContext(loaded,draft.selection,view,draft.annotation,coords.current,transform.current);window.parent.postMessage({type:'satellite-drawings:chat',request_id:crypto.randomUUID(),selection},location.origin);setNotice('已请求带入当前聊天草稿；请在宿主中确认。');
    }}>带入聊天草稿</button></aside>
    <section className="views"><div className="view-card"><h2>三维模型 <small>点击选面 · 拖动旋转 · 滚轮缩放</small></h2><Viewer3D loaded={loaded} selected={draft.selection} onSelect={select} onError={setError}/></div><div className="view-card"><h2>二维视图 <strong className="fixture">TEST FIXTURE · 非计算图纸</strong></h2><p>每个矩形只代表一个源面。点击联动；Shift 拖动框选可见对象。</p><DrawingView document={drawingFixture(loaded)} selected={draft.selection} onSelect={select}/></div></section>
    <aside><h2>工程草稿</h2><ParameterEditor value={draft.parameters} onChange={parameters=>edit({...draft,parameters})} onValidity={setParametersValid}/><div className="buttons"><button onClick={()=>undo()}>撤销草稿</button><button onClick={()=>undo(true)}>重做草稿</button></div>
      <button disabled={busy||!!error||!parametersValid} onClick={()=>action(async()=>{const p=provider.current!;await p.api.json(`/projects/${project}/revisions`,{method:'POST',body:JSON.stringify({expected_revision:loaded.revision.id,model_ref:loaded.revision.model_ref,parameters:draft.parameters,selection:draft.selection,overrides:loaded.revision.overrides})});adopt(await p.load(project));setNotice('已保存新的工程 revision。');})}>保存工程版本</button>
      <button disabled={busy||dirty||!!error||!parametersValid} onClick={()=>action(async()=>{const r=await execute(provider.current!.api,identity,loaded.revision,'engineering.save');await provider.current!.api.wait(r.run_id);setNotice('工程状态已由后端保存。');})}>保存工程包</button>
      <button disabled onClick={()=>{}}>导出 DWG（不可用）</button><ChecksPanel dirty={dirty} revision={loaded.revision.id}/>
    </aside></div></>}
  </main>;
}
