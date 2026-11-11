import React,{useState} from 'react';
import {createRoot} from 'react-dom/client';
const panels:any={},navigation:any=[],pluginModule=(window as any).__SIMPLE_MODULE__||'blanket';
(window as any).__ModuleLoader__={load({factory}:any){
  factory((name:string)=>{if(name==='react')return React;throw Error('Unexpected host dependency');}).apply({slots:{
    inject(_name:string,fn:Function){fn();},register(meta:any,Component:any){
      if(meta.name==='custom.agent.workspace')panels[meta.key]=Component;
      else navigation.push({meta,Component});return()=>{};
    }}});
}};
const script=document.createElement('script');script.src=`/client/${pluginModule}.js`;
script.onload=()=>{
  function Host(){
    const [active,setActive]=useState(''),[draft,setDraft]=useState('');
    const Panel=panels[active];
    return <div style={{fontFamily:'system-ui,sans-serif',display:'flex',height:'100vh'}}>
      <aside style={{width:150,padding:16,background:'#eef2f6',boxSizing:'border-box',flexShrink:0}}>
        <strong>卫星图纸插件</strong>
        <nav aria-label="插件入口" style={{marginTop:20}}>{navigation.map(({meta,Component}:any)=><Component key={meta.id} activeTab={active} onSelectTab={setActive}/>)}</nav>
        <p style={{fontSize:12,color:'#536174',lineHeight:1.6}}>开发演示入口<br/>当前工作台保存于本机服务</p>
      </aside>
      <main style={{flex:1,minWidth:0}}>{Panel?<Panel sessionId={`simple-${pluginModule}`} useInput={(selector:any)=>selector({draft})} inputActions={{setDraft}}/>:
        <div style={{padding:40}}><h1>{pluginModule==='paint'?'喷涂图纸工作台':'多层包覆工作台'}</h1><p>点击左侧插件入口打开工作台。</p><p>导入 STEP，在三维模型中选择目标。</p></div>}</main>
    </div>;
  }
  createRoot(document.getElementById('host-root')!).render(<Host/>);
};
document.head.appendChild(script);
