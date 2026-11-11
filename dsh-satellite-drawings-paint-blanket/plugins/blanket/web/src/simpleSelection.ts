// Keep assembly identities internal; the UI only exposes selection counts.
export function automaticInstallationFrame(face:any,faces:any[],instances:string[],excluded:string[],rotation=0,reverse=false){
 if(face?.signature.type!=='PLANE')throw Error('安装面必须是平面，请在三维视图重新选择');
 const dot=(a:number[],b:number[])=>a.reduce((s,v,i)=>s+v*b[i],0),origin=face.signature.centroid_mm;
 const normal=face.signature.normal,length=Math.hypot(...normal);
 if(!length)throw Error('安装面法向无效');
 const normalUnit=normal.map((v:number)=>v/length);
 const body=faces.filter(f=>instances.includes(f.instance_id)&&!excluded.includes(f.instance_id));
 let weight=0,side=0;
 for(const ref of body){const area=ref.signature.area_mm2||1;weight+=area;side+=area*dot(ref.signature.centroid_mm.map((v:number,i:number)=>v-origin[i]),normalUnit);}
 const direction=(weight&&side/weight<0?-1:1)*(reverse?-1:1),z=normalUnit.map((v:number)=>v*direction);
 const seed=Math.abs(z[0])<.9?[1,0,0]:[0,1,0],projection=dot(seed,z),raw=seed.map((v,i)=>v-projection*z[i]),scale=Math.hypot(...raw),x0=raw.map(v=>v/scale);
 const cross=(a:number[],b:number[])=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
 const y0=cross(z,x0),angle=rotation*Math.PI/180,x=x0.map((v,i)=>v*Math.cos(angle)+y0[i]*Math.sin(angle)),y=cross(z,x);
 return {origin,x_axis:x,y_axis:y,z_axis:z,units:'mm',handedness:'right'};
}


export type EquipmentScope={instanceIds:string[];moduleId:string;name:string;grouped:boolean};

function decodedEquipmentName(value:any):string{
 const decode=(hex:string)=>{try{return hex.match(/.{4}/g)!.map(code=>String.fromCharCode(parseInt(code,16))).join('');}catch{return hex;}};
 return String(value||'').replace(/_X2_([0-9a-f]+)_X0_/gi,(_,hex)=>decode(hex)).replace(/\\X2\\([0-9a-f]+)\\X0\\/gi,(_,hex)=>decode(hex)).trim();
}
function equipmentName(value:any):boolean{
 const name=decodedEquipmentName(value).replace(/\.(?:asm|step|stp)$/i,'').trim();
 if(!name||/^(?:assembly|subassembly|root|product|model|装配体|总装|整星|next\s+assembly\s+relationship|=>\[.*\])$/i.test(name))return false;
 if(/^(?:occ(?:-\d+)+|[\d_:]+|\d{6,}(?:[-_].*)?(?:asm|装配体).*|(?:asm|step|stp)(?:[-_].*)?)$/i.test(name))return false;
 return /[A-Za-z\u3400-\u9fff]{2,}/.test(name);
}

function scopeTree(snapshot:any,physicalInstanceIds:Iterable<string>){
 const nodes=new Map<string,any>((snapshot?.instances||[]).map((node:any)=>[node.instance_id,node]));
 const physical=new Set(physicalInstanceIds),children=new Map<string,string[]>();
 for(const node of nodes.values())if(node.parent_instance_id){const values=children.get(node.parent_instance_id)||[];values.push(node.instance_id);children.set(node.parent_instance_id,values);}
 function scope(id:string):EquipmentScope{
  const pending=[id],visited=new Set<string>(),instanceIds:string[]=[];
  while(pending.length){const next=pending.pop()!;if(visited.has(next))throw Error('装配层级存在循环，无法确定包覆范围');visited.add(next);if(!nodes.has(next))throw Error('装配范围已失效，请重新选择');if(physical.has(next))instanceIds.push(next);pending.push(...(children.get(next)||[]).slice().reverse());}
  if(!instanceIds.length)throw Error('所选组件没有可用的原生部件');
  const node=nodes.get(id);return {instanceIds,moduleId:id,name:decodedEquipmentName(node.name)||'所选对象',grouped:instanceIds.length>1};
 }
 return {nodes,physical,children,scope};
}

/** Source assembly names identify a selection scope, never proximity or a shared definition. */
export function parentEquipmentScope(snapshot:any,physicalInstanceIds:Iterable<string>,currentModuleId:string):EquipmentScope|null{
 const tree=scopeTree(snapshot,physicalInstanceIds);let node=tree.nodes.get(currentModuleId);const seen=new Set<string>();
 if(!node)throw Error('所选对象已失效，请重新选择');
 while(node?.parent_instance_id){
  if(seen.has(node.instance_id))throw Error('装配层级存在循环，无法确定包覆范围');seen.add(node.instance_id);
  node=tree.nodes.get(node.parent_instance_id);if(!node)throw Error('装配层级不完整，请重新选择');
  // Never grow an ordinary click into the entire imported satellite root.
  if(node.parent_instance_id&&tree.children.has(node.instance_id)&&equipmentName(node.name))return tree.scope(node.instance_id);
 }
 return null;
}

export function equipmentScope(snapshot:any,physicalInstanceIds:Iterable<string>,hitId:string):EquipmentScope{
 const ids=[...physicalInstanceIds],tree=scopeTree(snapshot,ids);
 if(!tree.physical.has(hitId)||!tree.nodes.has(hitId))throw Error('所选对象已失效，请重新选择');
 return parentEquipmentScope(snapshot,ids,hitId)||tree.scope(hitId);
}
