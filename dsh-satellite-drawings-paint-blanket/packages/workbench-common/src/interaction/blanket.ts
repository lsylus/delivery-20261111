import {validateSelection,same} from '../../../host-bridge/src/selection-context.mjs';
import {identityMatrix} from './selection';
export function targetContext(net:any,kind:string,id:string){
 if(kind==='seam'){const s=net.seams.find((s:any)=>s.id===id);if(!s)throw Error('请选择接缝');return {kind,id,edges:[net.edges[s.edge_a],net.edges[s.edge_b]].map((e:any)=>{const p=net.panels.find((p:any)=>p.key===e.panel);return {id:e.id,panel_key:p.key,panel_id:p.id,mapping_ref:p.mapping_ref,world:e.world};})};}
 const p=net.fixed_points.find((p:any)=>p.id===id);if(!p)throw Error('请选择固定点');return {kind:'point',id:p.id,panel_key:p.panel_key,panel_id:p.panel_id,mapping_ref:p.mapping_ref,uv_mm:p.uv_mm,position3d:p.position3d};
}
export function blanketSelection(loaded:any,target:any,annotation:string){
 const n=loaded.blanketNet,keys=target.kind==='seam'?target.edges.map((e:any)=>e.panel_key):[target.panel_key];
 const refs=n.net.panels.filter((p:any)=>keys.includes(p.key)).flatMap((p:any)=>p.source_refs).filter((r:any,i:number,a:any[])=>a.findIndex(x=>same(x,r))===i);
 const context={schema_version:1,session_id:loaded.identity.session_id,module:'blanket',project_id:loaded.project.id,model_ref:loaded.revision.model_ref,engineering_revision:loaded.revision.id,result_id:n.result_id,entity_refs:refs,view:'2d',local_coordinates:target.uv_mm?[target.uv_mm]:[],annotation,view_transform:identityMatrix,blanket_target:target};
 return validateSelection(context,{...context,net:n.net,face_refs:loaded.map.faces.map((f:any)=>f.face_ref)});
}
export function installationFrame(ref:any,faces:any[]){
 if(ref?.signature.type!=='PLANE')throw Error('请选择平面安装底面');
 const z=ref.signature.normal.map((v:number)=>-v),dot=(a:number[],b:number[])=>a.reduce((s,v,i)=>s+v*b[i],0);
 const other=faces.find(f=>f.instance_id===ref.instance_id&&f.signature.type==='PLANE'&&Math.abs(dot(f.signature.normal,z))<1e-7);
 if(!other)throw Error('找不到规则设备的正交侧面');const x=other.signature.normal,y=[z[1]*x[2]-z[2]*x[1],z[2]*x[0]-z[0]*x[2],z[0]*x[1]-z[1]*x[0]];
 return {origin:ref.signature.centroid_mm,x_axis:x,y_axis:y,z_axis:z,units:'mm',handedness:'right'};
}
export function sheetPoint(net:any,panel:any,uv:number[]){const {rotation:t,translation:v}=panel.transform,q=[t[0][0]*uv[0]+t[0][1]*uv[1]+v[0],t[1][0]*uv[0]+t[1][1]*uv[1]+v[1]],l=net.pieces.find((p:any)=>p.id===panel.piece_id).layout,c=Math.cos(l.rotation_rad),s=Math.sin(l.rotation_rad);return [q[0]*c-q[1]*s+l.translation_mm[0],q[0]*s+q[1]*c+l.translation_mm[1]];}
/** Undo the sheet layout and the complete panel transform, including reflected unfold panels. */
export function panelPoint(net:any,panel:any,sheet:number[]){
 const l=net.pieces.find((p:any)=>p.id===panel.piece_id).layout,c=Math.cos(l.rotation_rad),s=Math.sin(l.rotation_rad),x=sheet[0]-l.translation_mm[0],y=sheet[1]-l.translation_mm[1];
 const {rotation:r,translation:t}=panel.transform,u=c*x+s*y-t[0],v=-s*x+c*y-t[1],det=r[0][0]*r[1][1]-r[0][1]*r[1][0];
 if(!Number.isFinite(det)||Math.abs(det)<1e-12)throw Error('裁片坐标变换不可逆');
 return [(r[1][1]*u-r[0][1]*v)/det,(-r[1][0]*u+r[0][0]*v)/det];
}
