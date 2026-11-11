import {validateSelection} from './selection-context.mjs';
export function acceptChat(event,{origin,source,current,seen}) {
  if(!source||event.source!==source||event.origin!==origin) throw Error('untrusted_message');
  const d=event.data;
  if(!d||d.type!=='satellite-drawings:chat'||typeof d.request_id!=='string'||d.request_id.length>100||seen.has(d.request_id)) throw Error('invalid_message');
  const selection=validateSelection(d.selection,current);
  seen.add(d.request_id);
  if(seen.size>1024) seen.delete(seen.values().next().value);
  return `请检查当前选中对象（${selection.module}）。\n${JSON.stringify(selection)}`;
}
// Never automatically send a message. The host's inputActions only receives a draft.
export function attachChat({window,iframe,getCurrent,setDraft,getDraft}) {
  const seen=new Set(); let disposed=false;
  let pending=Promise.resolve();
  const receive=event=>{
    if(disposed||event.origin!==window.location.origin||event.source!==iframe.contentWindow||event.data?.type!=='satellite-drawings:chat')return;
    // Serialize asynchronous authority checks; detach invalidates all pending callbacks.
    pending=pending.then(async()=>{
    try {
      if(disposed)return;
      const current=await getCurrent();
      if(disposed)return;
      const draft=acceptChat(event,{origin:window.location.origin,source:iframe.contentWindow,current,seen});
      setDraft([getDraft(),draft].filter(Boolean).join('\n\n'));
      iframe.contentWindow.postMessage({type:'satellite-drawings:chat-result',request_id:event.data.request_id,session_id:current.session_id,ok:true},window.location.origin);
    } catch { /* Untrusted messages never produce replies or side effects. */ }
    });
  };
  window.addEventListener('message',receive);
  return ()=>{disposed=true;seen.clear();window.removeEventListener('message',receive);};
}
