import React,{useEffect,useRef,useState} from 'react';
import {workspaceEntry} from './workspace.mjs';
import {attachChat} from './chat-bridge.mjs';
export function clientPlugin(module) {
  const entry=workspaceEntry(module);
  function Panel({sessionId,useInput,inputActions,onClose}) {
    const frame=useRef(null), live=useRef(null), [notice,setNotice]=useState('');
    const input=useInput(s=>s);live.current={sessionId,input,inputActions};
    useEffect(()=>{
      if(!sessionId||!frame.current)return;
      let alive=true;
      const getCurrent=async()=>{
        try {
          // Re-read authority and current revision from the server; iframe claims are not authority.
          const get=async p=>{const r=await fetch(`/api/satellite-${module}${p}`,{cache:'no-store',headers:{'x-satellite-session':sessionId}});if(!r.ok)throw Error('context_unavailable');return r.json();};
          const identity=await get('/context');
          if(identity.session_id!==sessionId||live.current.sessionId!==sessionId)throw Error('session_changed');
          const binding=await get(`/service/sessions/${sessionId}/binding`);
          const project=await get(`/service/projects/${binding.project_id}`);
          const head=project.module_states[module];
          const revision=await get(`/service/projects/${project.id}/revisions/${head}`);
          const model=await get(`/service/projects/${project.id}/models/${revision.model_ref.model_id}`);
          const artifact=model.artifacts.find(a=>a.relative_storage_path.endsWith('mesh-map.json'));
          const map=await get('/service'+artifact.download_url.replace('/api/v1',''));
          const result=await get(`/service/projects/${project.id}/${module==='paint'?'paint-result':'blanket-net'}`);
          if(result&&(result.paint||result.net).revision_id!==head)throw Error('result_changed');
          const finalIdentity=await get('/context');
          const finalBinding=await get(`/service/sessions/${sessionId}/binding`);
          const finalProject=await get(`/service/projects/${project.id}`);
          if(!alive||live.current.sessionId!==sessionId||finalIdentity.owner_id!==identity.owner_id||finalIdentity.session_id!==sessionId||finalBinding.project_id!==project.id||finalProject.module_states[module]!==head)throw Error('context_changed');
          return {...identity,project_id:project.id,engineering_revision:head,result_id:result?.result_id||null,net:result?.net,model_ref:revision.model_ref,face_refs:map.faces.map(f=>f.face_ref)};
        }catch{if(alive)setNotice('当前工程上下文不可用，请刷新工作台。');throw Error('context_unavailable');}
      };
      const detach=attachChat({window,iframe:frame.current,getCurrent,getDraft:()=>live.current.input?.draft||'',setDraft:value=>live.current.inputActions.setDraft(value)});
      return()=>{alive=false;detach();};
    },[sessionId]);
    return <section style={{height:'100%',display:'flex',flexDirection:'column'}}>{onClose&&<button onClick={onClose}>关闭</button>}{notice&&<p role="status">{notice}</p>}{sessionId?<iframe key={sessionId} ref={frame} title={entry.name.zh} src={`/satellite-${module}/?session=${encodeURIComponent(sessionId)}`} style={{border:0,flex:1,width:'100%'}}/>:<p>请选择当前会话。</p>}</section>;
  }
  function Entry({activeTab,onSelectTab}) {return <button aria-expanded={activeTab===entry.key} onClick={()=>onSelectTab(entry.key)}>{entry.name.zh}</button>;}
  return {inject:['slots'],apply(ctx){
    ctx.slots.inject('custom.agent.nav',()=>ctx.slots.register({name:'custom.agent.nav',id:entry.id,metadata:entry,label:Object.assign(()=>entry.name.zh,{agentWorkspace:entry})},Entry));
    ctx.slots.inject('custom.agent.workspace',()=>ctx.slots.register({name:'custom.agent.workspace',key:entry.key},Panel));
  }};
}
