import React from 'react';
import {workspaceEntry as entry} from './workspace.mjs';
export const inject=['slots','sidebarRight','sidebarRightTabs'];
const sidebarId='@qmh/dsh-satellite-heater-drawing/workspace';
function Panel({sessionId,onClose}){
  return <section style={{height:'100%',minHeight:0,display:'flex',flexDirection:'column'}}>
    {onClose&&<button onClick={onClose}>关闭</button>}
    {sessionId?<iframe key={sessionId} title="矩形加热器出图" src={`/satellite-heater/?session=${encodeURIComponent(sessionId)}`} style={{border:0,flex:1,minHeight:0,width:'100%'}}/>:<p>请选择当前会话。</p>}
  </section>;
}
function Entry({activeTab,onSelectTab}){return <button aria-expanded={activeTab===entry.key} onClick={()=>onSelectTab(entry.key)}>{entry.name.zh}</button>;}
function OpenEntry({sessionId,openHeater}){
  const available=typeof sessionId==='string'&&sessionId.length>0;
  return <button type="button" disabled={!available}
    title={available?'在右侧栏打开矩形加热器出图':'请先选择会话'}
    onClick={()=>{if(available)openHeater(sessionId);}}>
    矩形加热器出图
  </button>;
}
export function apply(ctx){
  ctx.effect(()=>ctx.sidebarRightTabs.register({
    id:sidebarId,kind:entry.key,title:()=>entry.name.zh,keepMounted:true,
    guide:[{id:entry.id,order:40,title:()=>entry.name.zh,description:()=> '上传 Excel，生成和预览 DWG / PDF'}],
  }),'heater: right sidebar page');
  ctx.slots.inject('sidebar.right.pane.tab',()=>ctx.slots.register({name:'sidebar.right.pane.tab',key:sidebarId},Panel));
  ctx.slots.inject('custom.agent.nav',()=>ctx.slots.register({name:'custom.agent.nav',id:entry.id,metadata:entry,label:Object.assign(()=>entry.name.zh,{agentWorkspace:entry})},Entry));
  ctx.slots.inject('custom.agent.workspace',()=>ctx.slots.register({name:'custom.agent.workspace',key:entry.key},Panel));
  ctx.slots.inject('conversation.session.header.actions',()=>ctx.slots.register({
    name:'conversation.session.header.actions',id:'heater-drawing-open',order:40,
    inject:()=>({openHeater:sessionId=>ctx.sidebarRight.openTabIn(sessionId,entry.key)}),
  },OpenEntry));
}
