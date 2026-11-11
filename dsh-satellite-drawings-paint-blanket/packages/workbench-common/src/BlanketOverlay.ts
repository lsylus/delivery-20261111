import {mappedGeometry,surfaceWorld} from './SurfaceGeometry';
import * as THREE from 'three';
export function blanketOverlay(loaded:any){
 const group=new THREE.Group(),cover=loaded.blanketResult?.blanket,net=loaded.blanketNet?.net,target=loaded.blanketTarget;
 const world=(p:number[])=>new THREE.Vector3(p[0]/1000,p[2]/1000,-p[1]/1000);
 for(const p of cover?.panels||[]){
  const shape=new THREE.Shape(p.outer_loop.points.map((q:number[])=>new THREE.Vector2(...q as [number,number])));
  for(const h of p.holes)shape.holes.push(new THREE.Path(h.points.map((q:number[])=>new THREE.Vector2(...q as [number,number]))));
  const g=mappedGeometry(shape,p.frame,p.surface_mapping);
  group.add(new THREE.Mesh(g,new THREE.MeshBasicMaterial({color:'#20aa92',transparent:true,opacity:.3,side:THREE.DoubleSide,depthWrite:false})));
 }
 for(const tab of net?.overlaps||[]){
  const panel=net.panels.find((p:any)=>p.key===tab.target_panel),f=panel.frame;
  const shape=new THREE.Shape(tab.receiving_uv.map((q:number[])=>new THREE.Vector2(q[0],q[1]))),g=mappedGeometry(shape,f,panel.surface_mapping);
  group.add(new THREE.Mesh(g,new THREE.MeshBasicMaterial({color:'#e5a027',transparent:true,opacity:.7,side:THREE.DoubleSide,depthTest:false})));

 }
 const edges=target?.kind==='seam'?target.edges:[];
 edges.forEach((e:any,i:number)=>{const panel=net.panels.find((p:any)=>p.key===e.panel_key),edge=net.edges[e.id],samples=panel?.surface_mapping&&edge?Array.from({length:65},(_,j)=>surfaceWorld(panel.surface_mapping,edge.uv[0].map((v:number,k:number)=>v+(edge.uv[1][k]-v)*j/64))):e.world;const g=new THREE.BufferGeometry().setFromPoints(samples.map(world)),line=new THREE.Line(g,i?new THREE.LineDashedMaterial({color:'#c026d3',depthTest:false,dashSize:.005,gapSize:.005}):new THREE.LineBasicMaterial({color:'#f97316',depthTest:false}));line.userData={kind:'seam-edge',id:e.id,panel_key:e.panel_key,mapping_ref:e.mapping_ref};line.computeLineDistances();group.add(line);});
 for(const p of net?.fixed_points||[]){const dot=new THREE.Mesh(new THREE.SphereGeometry(.0015,12,8),new THREE.MeshBasicMaterial({color:p.id===target?.id?'#ef4444':'#2734c9',depthTest:false}));dot.position.copy(world(p.position3d));group.add(dot);}
 return group;
}
