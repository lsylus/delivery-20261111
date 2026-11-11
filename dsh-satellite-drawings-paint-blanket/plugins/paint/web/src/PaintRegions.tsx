import React,{useRef,useState} from 'react';
export function PaintDrawing({document:doc,onPolygon,onRegion,region}:{document:any;onPolygon:Function;onRegion:Function;region:string}){
 const svg=useRef<SVGSVGElement>(null),start=useRef<number[]|null>(null),[box,setBox]=useState<number[][]>([]);
 if(!doc)return <p>结果没有可用图纸。</p>;
 const pts=doc.entities.flatMap((e:any)=>e.points||e.outer_loop?.points||[e.position||[0,0]]);
 const bounds=pts.reduce((b:number[],p:number[])=>[Math.min(b[0],p[0]),Math.min(b[1],p[1]),Math.max(b[2],p[0]),Math.max(b[3],p[1])],[Infinity,Infinity,-Infinity,-Infinity]);
 const minX=bounds[0],minY=bounds[1],w=bounds[2]-minX||1,h=bounds[3]-minY||1,pad=Math.max(w,h)*.06;
 const point=(e:any)=>{const p=svg.current!.createSVGPoint();p.x=e.clientX;p.y=e.clientY;const q=p.matrixTransform(svg.current!.getScreenCTM()!.inverse());return [q.x,-q.y];};
 const path=(loops:any[])=>loops.map(l=>'M'+l.points.map((p:any)=>p.join(' ')).join(' L')+' Z').join(' ');
 return <svg ref={svg} data-testid="drawing" data-revision={doc.revision_id} data-y-up="true" role="img" aria-label="真实喷漆工程图" viewBox={`${minX-pad} ${-minY-h-pad} ${w+2*pad} ${h+2*pad}`} onPointerDown={e=>{if(e.shiftKey){start.current=point(e);e.currentTarget.setPointerCapture(e.pointerId);}}} onPointerUp={e=>{if(!start.current)return;const a=start.current,b=point(e);start.current=null;const p=[a,[b[0],a[1]],b,[a[0],b[1]]];setBox(p);onPolygon(p);}}>
 <g transform="scale(1,-1)">{doc.entities.map((e:any)=>e.kind==='polyline'?<polyline key={e.id} points={[...e.points,...(e.closed?[e.points[0]]:[])].map((p:any)=>p.join(',')).join(' ')} fill="none" stroke="#34495e" strokeWidth={w/600}/>:e.kind==='hatch'?<path key={e.id} data-region={e.id} d={path([e.outer_loop,...e.holes])} fillRule="evenodd" fill={region===e.id?'#e39122':'#eab95b'} fillOpacity=".65" stroke="#8b5c0a" strokeWidth={w/800} onClick={ev=>{if(!ev.shiftKey)onRegion(e.id);}}/>:null)}
 {box.length>0&&<polygon points={box.map(p=>p.join(',')).join(' ')} fill="#38bdf8" fillOpacity=".15" stroke="#0284c7" strokeWidth={w/300} pointerEvents="none"/>}</g>
 {doc.entities.filter((e:any)=>e.kind==='text').map((e:any)=><text key={e.id} x={e.position[0]} y={-e.position[1]} fontSize={e.height_mm}>{e.text}</text>)}</svg>;
}
