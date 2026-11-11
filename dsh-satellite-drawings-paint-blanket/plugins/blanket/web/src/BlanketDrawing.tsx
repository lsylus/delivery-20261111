import React,{useRef,useState} from 'react';
import {sheetPoint,panelPoint} from '../../../../packages/workbench-common/src/interaction/blanket';
type Drag={id:string;panel:any;pointerId:number;start:[number,number];offset:number[];uv:number[];moved:boolean};
export function BlanketDrawing({net,target,onTarget,onPointMove,disabled=false}:{net:any;target:any;onTarget:Function;onPointMove?:(id:string,panelKey:string,uv:number[])=>Promise<boolean>;disabled?:boolean}){
 const [zoom,setZoom]=useState(1),[pan,setPan]=useState([0,0]),[preview,setPreview]=useState<{id:string;uv:number[]}|null>(null),[saving,setSaving]=useState(false);
 const drag=useRef<Drag|null>(null),svg=useRef<SVGSVGElement|null>(null);
 const doc=net.drawing_document,points=doc.entities.flatMap((e:any)=>e.points||[e.start,e.end,e.position].filter(Boolean));
 const xs=points.map((p:any)=>p[0]),ys=points.map((p:any)=>p[1]),x=Math.min(...xs)-15,y=Math.min(...ys)-15,w=Math.max(...xs)-x+15,h=Math.max(...ys)-y+15;
 const panels=Object.fromEntries(net.panels.map((p:any)=>[p.key,p]));
 const vw=w/zoom,vh=h/zoom,locked=disabled||saving;
 function pointerUV(e:React.PointerEvent,panel:any){const matrix=svg.current?.getScreenCTM();if(!matrix)throw Error('无法读取裁片视图坐标');const q=new DOMPoint(e.clientX,e.clientY).matrixTransform(matrix.inverse());return panelPoint(net,panel,[q.x,q.y]);}
 function start(e:React.PointerEvent<SVGCircleElement>,point:any){if(e.button!==0||locked||!onPointMove)return;e.preventDefault();e.stopPropagation();const panel=panels[point.panel_key],uv=pointerUV(e,panel);drag.current={id:point.id,panel,pointerId:e.pointerId,start:[e.clientX,e.clientY],offset:uv.map((v,i)=>v-point.uv_mm[i]),uv:[...point.uv_mm],moved:false};e.currentTarget.setPointerCapture(e.pointerId);onTarget('point',point.id);}
 function move(e:React.PointerEvent<SVGCircleElement>){const d=drag.current;if(!d||e.pointerId!==d.pointerId)return;e.preventDefault();e.stopPropagation();if(!d.moved&&Math.hypot(e.clientX-d.start[0],e.clientY-d.start[1])<3)return;d.moved=true;d.uv=pointerUV(e,d.panel).map((v,i)=>v-d.offset[i]);setPreview({id:d.id,uv:d.uv});}
 async function finish(e:React.PointerEvent<SVGCircleElement>){const d=drag.current;if(!d||e.pointerId!==d.pointerId)return;e.preventDefault();e.stopPropagation();drag.current=null;if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);if(!d.moved){setPreview(null);return;}setSaving(true);try{await onPointMove?.(d.id,d.panel.key,d.uv);}finally{setPreview(null);setSaving(false);}}
 function cancel(){drag.current=null;setPreview(null);}
 function focusPoint(next=false){
  if(!net.fixed_points.length||!svg.current)return;
  const current=net.fixed_points.findIndex((p:any)=>p.id===target?.id),index=next?(current+1)%net.fixed_points.length:Math.max(0,current),point=net.fixed_points[index],panel=panels[point.panel_key],q=sheetPoint(net,panel,point.uv_mm);
  const boundary=[...(panel.outer_loop?.points||[]),...(net.overlaps||[]).filter((tab:any)=>tab.owner_panel===panel.key).flatMap((tab:any)=>tab.uv)].map((uv:number[])=>sheetPoint(net,panel,uv));
  const pw=boundary.length?Math.max(...boundary.map((v:number[])=>v[0]))-Math.min(...boundary.map((v:number[])=>v[0])):40,ph=boundary.length?Math.max(...boundary.map((v:number[])=>v[1]))-Math.min(...boundary.map((v:number[])=>v[1])):40;
  const width=svg.current.clientWidth,height=svg.current.clientHeight,baseScale=Math.min(width/w,height/h),focusScale=Math.min(width/(Math.max(pw,10)*1.4),height/(Math.max(ph,10)*1.4));
  setZoom(Math.max(1,Math.min(200,Math.round(focusScale/baseScale*2)/2)));setPan([q[0]-(x+w/2),q[1]-(y+h/2)]);onTarget('point',point.id);
 }
 return <div><div className="drawing-toolbar"><label>二维缩放<input aria-label="二维缩放" type="range" min="1" max="200" step=".5" value={zoom} disabled={saving||!!preview} onChange={e=>setZoom(Number(e.target.value))}/></label>{[[1,0,'右'],[-1,0,'左'],[0,-1,'上'],[0,1,'下']].map(([dx,dy,label])=><button key={String(label)} disabled={saving||!!preview} onClick={()=>setPan([pan[0]+Number(dx)*vw/5,pan[1]+Number(dy)*vh/5])}>{label}</button>)}<button disabled={saving||!!preview} onClick={()=>{setZoom(1);setPan([0,0]);}}>复位视图</button>{onPointMove&&net.fixed_points.length>0&&<><button disabled={saving||!!preview} onClick={()=>focusPoint()}>聚焦定位标记</button><button disabled={saving||!!preview} onClick={()=>focusPoint(true)}>下一个定位标记</button></>}</div>
 {onPointMove&&<p className="fixed-point-help">定位标记可直接拖动，松开后自动保存；标记不表示钻孔。{saving?' 正在保存位置…':''}</p>}
 <svg ref={svg} data-testid="blanket-drawing" data-revision={doc.revision_id} data-point-saving={saving} data-point-editable={!locked&&!!onPointMove} viewBox={`${x+(w-vw)/2+pan[0]} ${y+(h-vh)/2+pan[1]} ${vw} ${vh}`} aria-label="真实二维裁片图纸" onKeyDown={e=>{if(e.key==='Escape')cancel();}} style={{width:'100%',height:340,background:'#fff'}}>
 {doc.entities.map((e:any)=>{const color=({CUT:'#304765',FOLD:'#288f81',OVERLAP:'#d68b24',FIXING:'#263cc4',TEXT:'#182b42'} as any)[e.layer]||'#8e9aab';
 // Interactive markers below render FIXING point entities exactly once, including their drag preview.
 if(e.kind==='point'&&e.layer==='FIXING')return null;
 if(e.kind==='line')return <line key={e.id} x1={e.start[0]} y1={e.start[1]} x2={e.end[0]} y2={e.end[1]} stroke={color} strokeWidth=".8" vectorEffect="non-scaling-stroke" strokeDasharray={e.layer==='FOLD'?'3 2':undefined}/>;
 if(e.kind==='polyline')return <polygon key={e.id} points={e.points.map((p:any)=>p.join(',')).join(' ')} fill="none" stroke={color} strokeWidth=".8" vectorEffect="non-scaling-stroke"/>;
 if(e.kind==='point')return <circle key={e.id} cx={e.position[0]} cy={e.position[1]} r="1.2" fill={color}/>;
 if(e.kind==='text')return <text key={e.id} x={e.position[0]} y={e.position[1]} fontSize={e.height_mm}>{e.text}</text>;
 if(e.kind==='dimension')return <text key={e.id} x={e.position[0]} y={e.position[1]} fontSize="2.4" fill={color}>{Math.hypot(e.end[0]-e.start[0],e.end[1]-e.start[1]).toFixed(1)}</text>;return null;})}
 {net.seams.flatMap((s:any)=>[s.edge_a,s.edge_b].map((id:string,i:number)=>{const e=net.edges[id],[a,b]=e.uv.map((q:any)=>sheetPoint(net,panels[e.panel],q));return <line key={id} data-testid={`seam-${s.id}-${i}`} data-seam-id={s.id} onClick={()=>{if(!locked)onTarget('seam',s.id);}} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke={target?.id===s.id?'#f97316':'transparent'} strokeWidth="8" vectorEffect="non-scaling-stroke" style={{cursor:'pointer'}}/>;}))}
 {net.fixed_points.map((p:any)=>{const q=sheetPoint(net,panels[p.panel_key],preview&&preview.id===p.id?preview.uv:p.uv_mm),active=target?.id===p.id;return <g key={p.id}><circle cx={q[0]} cy={q[1]} r="1.2" fill={active?'#f97316':'#263cc4'} pointerEvents="none"/><circle data-testid={`point-${p.id}`} data-point-id={p.id} aria-label="拖动定位标记" onClick={()=>{if(!locked)onTarget('point',p.id);}} onPointerDown={e=>start(e,p)} onPointerMove={move} onPointerUp={finish} onPointerCancel={cancel} cx={q[0]} cy={q[1]} r={Math.max(2.2,Math.max(vw,vh)/80)} fill={active?'#f97316':'#263cc4'} fillOpacity=".24" style={{cursor:locked?'default':onPointMove?'grab':'pointer',touchAction:'none'}}/></g>;})}
 </svg></div>;
}
