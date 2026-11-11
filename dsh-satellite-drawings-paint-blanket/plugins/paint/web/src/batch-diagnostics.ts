function hint(code:string){
 if(/penetration/i.test(code))return '已检测零件穿过喷漆面；应按截面轮廓外扩 3 mm 生成不喷区，仅在截面无效时修复模型。';
 if(/footprint|projection|intersection/i.test(code))return '检查相交轮廓、接触面和投影足迹拓扑；修复后重新生成，不要按空图纸导出。';
 if(/budget|limit|exhausted/i.test(code))return '该面组扫描规模超限；先隔离或简化相关装配，必要时拆分目标后重新生成。';
 if(/topology|brep|solid|required|shell/i.test(code))return '修复或缝合列出对象的 STEP 拓扑，确认是有效实体后重新生成。';
 return '根据错误码检查列出的对象，修复模型或调整选面后重新生成。';
}

function refLabel(ref:any,group:any,targetIds:Set<string>){
 if(!ref||typeof ref!=='object')return '';
 const instance=String(ref.instance_id||ref.instance||'').trim(),entity=String(ref.entity_id||'').trim();
 if(!instance&&!entity)return '';
 const owner=targetIds.has(instance)&&group.instance_name?group.instance_name:instance;
 return [owner,entity].filter(Boolean).join(' / ');
}

export function batchDiagnosticSummary(group:any){
 if(!group)return null;
 const paint=group.paint||group.paint_result||null,diagnostics=Array.isArray(paint?.diagnostics)?paint.diagnostics:[];
 const entries=diagnostics.length?diagnostics:group.error?[{code:group.error.code||'group_generation_failed',status:'fail',observed:{message:group.error.message}}]:[];
 const counts=new Map<string,number>();
 for(const item of entries){const code=String(item?.code||'unknown_diagnostic');counts.set(code,(counts.get(code)||0)+1);}
 if(!counts.size)counts.set('drawing_unavailable',1);
 const codes=[...counts].slice(0,3).map(([code,count])=>({code,count})),codeOverflow=Math.max(0,counts.size-codes.length);
 const targetIds=new Set<string>((group.target_face_refs||[]).map((ref:any)=>String(ref.instance_id||'')));
 const labels:string[]=[];
 for(const item of entries)for(const ref of item?.source_refs||[]){const label=refLabel(ref,group,targetIds);if(label&&!labels.includes(label))labels.push(label);}
 if(!labels.length&&group.instance_name)labels.push([group.instance_name,group.direction_label||group.direction].filter(Boolean).join(' / '));
 const objects=labels.slice(0,3),objectOverflow=Math.max(0,labels.length-objects.length);
 const hints=[...new Set(codes.map(item=>hint(item.code)))].slice(0,2);
 const message=entries.map((item:any)=>item?.observed?.message||item?.message).find(Boolean)||group.error?.message||'';
 const status=group.status||paint?.status||'needs_review';
 return {
  title:status==='failed'?'当前面组生成失败':'当前面组需要复核，未生成图纸',
  codes,codeOverflow,objects,objectOverflow,hints,
  detail:String(message).slice(0,240),
 };
}
