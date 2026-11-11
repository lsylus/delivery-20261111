export type PaintTargetGroup={
 id:string;
 face_refs:any[];
 recommended:boolean;
 selectable:boolean;
 opposite_group_id?:string|null;
 direction_label?:string;
 side_label?:string;
 paint_type?:string;
 topology_status?:string;
 [key:string]:any;
};

export function faceKey(ref:any){
 return ref?`${ref.instance_id}|${ref.entity_id}`:'';
}

function unique(refs:any[]){
 const seen=new Set<string>();
 return refs.filter(ref=>{const key=faceKey(ref);if(!key||seen.has(key))return false;seen.add(key);return true;});
}

export function paintTargetGroups(loaded:any):PaintTargetGroup[]{
 const supplied=loaded?.paintRecommendations?.groups;
 if(Array.isArray(supplied)&&supplied.length)return supplied.map((group:any,index:number)=>({
  ...group,
  id:String(group.id??group.group_id??`group-${index+1}`),
  face_refs:Array.isArray(group.face_refs)?group.face_refs:Array.isArray(group.target_face_refs)?group.target_face_refs:[],
  recommended:group.recommended===true,
  selectable:group.selectable!==false&&group.topology_status!=='invalid'&&group.topology_status!=='unrenderable',
  opposite_group_id:group.opposite_group_id??null,
 })).filter((group:PaintTargetGroup)=>group.face_refs.length>0);

 const persisted=loaded?.revision?.parameters?.target_face_groups;
 if(Array.isArray(persisted)&&persisted.length)return persisted.map((group:any,index:number)=>({
  ...group,
  id:String(group.id??group.group_id??`group-${index+1}`),
  face_refs:Array.isArray(group.face_refs)?group.face_refs:Array.isArray(group.target_face_refs)?group.target_face_refs:[],
  recommended:true,
  selectable:true,
  opposite_group_id:group.opposite_group_id??null,
 })).filter((group:PaintTargetGroup)=>group.face_refs.length>0);

 // Existing projects remain selectable until their model-bound recommendation
 // artifact has been generated. This fallback never invents recommendations.
 const selected=new Set((loaded?.revision?.selection||[]).map(faceKey));
 return (loaded?.map?.faces||[]).map((entry:any,index:number)=>({
  id:`legacy-face-${index+1}`,
  face_refs:[entry.face_ref],
  recommended:selected.has(faceKey(entry.face_ref)),
  selectable:true,
  opposite_group_id:null,
 }));
}

export function stableSelection(groups:PaintTargetGroup[],refs:any[]){
 const blocked=new Set(groups.filter(group=>!group.selectable).flatMap(group=>group.face_refs).map(faceKey));
 const requested=new Map(unique(refs).filter(ref=>!blocked.has(faceKey(ref))).map(ref=>[faceKey(ref),ref]));
 const ordered=groups.flatMap(group=>group.face_refs).filter(ref=>requested.delete(faceKey(ref)));
 return unique([...ordered,...requested.values()]);
}

export function recommendedSelection(groups:PaintTargetGroup[]){
 return stableSelection(groups,groups.filter(group=>group.recommended&&group.selectable).flatMap(group=>group.face_refs));
}

export function selectedGroupIds(groups:PaintTargetGroup[],refs:any[]){
 const selected=new Set(refs.map(faceKey));
 return groups.filter(group=>group.selectable&&group.face_refs.length>0&&group.face_refs.every(ref=>selected.has(faceKey(ref)))).map(group=>group.id);
}

export function togglePaintTarget(groups:PaintTargetGroup[],refs:any[],clicked:any){
 const key=faceKey(clicked),group=groups.find(candidate=>candidate.face_refs.some(ref=>faceKey(ref)===key));
 if(group&&!group.selectable)return stableSelection(groups,refs);
 const members=group?.face_refs||[clicked],selected=new Map(refs.map(ref=>[faceKey(ref),ref]));
 const remove=members.every(ref=>selected.has(faceKey(ref)));
 for(const ref of members)remove?selected.delete(faceKey(ref)):selected.set(faceKey(ref),ref);
 return stableSelection(groups,[...selected.values()]);
}

export function flipPaintTargets(groups:PaintTargetGroup[],refs:any[]){
 const byId=new Map(groups.map(group=>[group.id,group])),active=new Set(selectedGroupIds(groups,refs));
 if(![...active].some(id=>byId.get(id)?.opposite_group_id&&byId.has(byId.get(id)!.opposite_group_id!)))return stableSelection(groups,refs);
 const replaced=new Set<string>(),next:any[]=[];
 for(const id of active){
  const group=byId.get(id)!;
  for(const ref of group.face_refs)replaced.add(faceKey(ref));
  const opposite=group.opposite_group_id?byId.get(group.opposite_group_id):null;
  next.push(...(opposite?.selectable?opposite.face_refs:group.face_refs));
 }
 next.push(...refs.filter(ref=>!replaced.has(faceKey(ref))));
 return stableSelection(groups,next);
}

export function paintFaceStates(groups:PaintTargetGroup[],refs:any[]){
 const selected=new Set(refs.map(faceKey)),states:Record<string,{state:'selected';group_id:string;selectable:true}>={};
 for(const group of groups)for(const ref of group.face_refs){
  const key=faceKey(ref);
  if(group.selectable&&selected.has(key))states[key]={state:'selected',group_id:group.id,selectable:true};
 }
 return states;
}
