import React,{useRef} from 'react';
import {same} from '../../host-bridge/src/selection-context.mjs';
import {localPoint,rectangleHits,svgTransform} from './interaction/annotations';
export function DrawingView({document,selected,onSelect}:{document:any;selected:any[];onSelect:Function}){
  const svg=useRef<SVGSVGElement>(null),start=useRef<number[]|null>(null);
  return <svg ref={svg} data-testid="drawing" role="img" aria-label="二维选择映射测试夹具" viewBox={`-3 -3 126 ${Math.ceil(document.entities.length/5)*20+6}`} onPointerDown={e=>{if(e.shiftKey){start.current=localPoint(svg.current!,e.clientX,e.clientY);e.currentTarget.setPointerCapture(e.pointerId);}}} onPointerUp={e=>{
    if(!start.current)return;const a=start.current,b=localPoint(svg.current!,e.clientX,e.clientY);start.current=null;
    const hits=rectangleHits(document,a,b);if(hits.length)onSelect(hits.flatMap((h:any)=>h.source_refs),'2d',[a,b],svgTransform(svg.current!));
  }}>
    {document.entities.map((entity:any,i:number)=><g key={entity.id} onClick={e=>{if(e.shiftKey)return;onSelect(entity.source_refs,'2d',[localPoint(svg.current!,e.clientX,e.clientY)],svgTransform(svg.current!));}}>
      <polygon data-testid={`drawing-face-${i}`} data-selected={selected.some(r=>same(r,entity.source_refs[0]))} points={entity.points.map((p:any)=>p.join(',')).join(' ')} fill={selected.some(r=>same(r,entity.source_refs[0]))?'#fbbf24':'#dae7f1'} stroke="#49718f" strokeWidth=".4"/>
      <text x={entity.points[0][0]+2} y={entity.points[0][1]+9} fontSize="3" pointerEvents="none">{i+1} · {entity.source_refs[0].entity_id}</text>
    </g>)}
  </svg>;
}
