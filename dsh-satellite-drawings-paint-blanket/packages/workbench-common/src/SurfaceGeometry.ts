import * as THREE from 'three';
// Display tessellation only; native BRep remains authoritative.
export function surfaceWorld(m:any,xy:number[]):number[]{
 const [x,y]=xy.map((v:number,i:number)=>v-(m.chart_offset_mm?.[i]||0)),r=m.radius_mm;let u:number,v:number;
 if(m.chart_kind==='gnomonic'){u=Math.atan2(y,x);v=Math.atan2(r,Math.hypot(x,y));}
 else if(m.kind==='CONE'){
  const sign=m.sine>0?1:-1,angle=Math.atan2(y*sign,x*sign),candidates:number[]=[];
  for(let k=-2;k<=2;k++){const t=m.u_origin+(angle+2*Math.PI*k)/m.sine;if(t>=m.uv_bounds[0]-1e-7&&t<=m.uv_bounds[1]+1e-7)candidates.push(t);}
  if(candidates.length!==1)throw Error('曲面图坐标逆映射不唯一');
  u=candidates[0];v=sign*Math.hypot(x,y)-r/m.sine;
 }else{u=m.u_origin+x/r;v=m.kind==='SPHERE'?y/r:y;}
 const radius=m.kind==='CONE'?r+v*m.sine:m.kind==='SPHERE'?r*Math.cos(v):r;
 const z=m.kind==='CONE'?v*m.cosine:m.kind==='SPHERE'?r*Math.sin(v):v;
 return m.origin.map((o:number,i:number)=>o+radius*Math.cos(u)*m.x_axis[i]+radius*Math.sin(u)*m.y_axis[i]+z*m.z_axis[i]);
}
export const displayPoint=(p:number[])=>new THREE.Vector3(p[0]/1000,p[2]/1000,-p[1]/1000);
export function mappedGeometry(shape:THREE.Shape,frame:any,mapping?:any){
 const source=new THREE.ShapeGeometry(shape),g=source.toNonIndexed();source.dispose();
 if(!mapping){const matrix=new THREE.Matrix4().makeBasis(displayPoint(frame.x_axis),displayPoint(frame.y_axis),displayPoint(frame.z_axis));matrix.setPosition(displayPoint(frame.origin));g.applyMatrix4(matrix);return g;}
 const input=g.getAttribute('position'),vertices:number[]=[],step=Math.max(1,mapping.radius_mm*.08);
 function triangle(a:number[],b:number[],c:number[],depth=0){
  const dist=(a:number[],b:number[])=>Math.hypot(a[0]-b[0],a[1]-b[1]);
  if(depth<8&&Math.max(dist(a,b),dist(b,c),dist(c,a))>step){
   const mid=(a:number[],b:number[])=>[(a[0]+b[0])/2,(a[1]+b[1])/2],ab=mid(a,b),bc=mid(b,c),ca=mid(c,a);
   triangle(a,ab,ca,depth+1);triangle(ab,b,bc,depth+1);triangle(ca,bc,c,depth+1);triangle(ab,bc,ca,depth+1);return;
  }
  for(const q of [a,b,c])vertices.push(...displayPoint(surfaceWorld(mapping,q)).toArray());
 }
 for(let i=0;i<input.count;i+=3)triangle([input.getX(i),input.getY(i)],[input.getX(i+1),input.getY(i+1)],[input.getX(i+2),input.getY(i+2)]);
 g.dispose();const result=new THREE.BufferGeometry();result.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));result.computeVertexNormals();return result;
}
