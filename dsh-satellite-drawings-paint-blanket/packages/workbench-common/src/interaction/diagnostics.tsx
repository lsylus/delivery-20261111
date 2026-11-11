import React from 'react';

export function ComplexDiagnostics({value}:{value:any}) {
 if(!value)return null;
 const report=value.result,chart=report.chart||report;
 const triangles=chart.triangles||[];
 const entities=report.drawing_document?.entities||[];
 const bounds=entities.flatMap((e:any)=>e.kind==='arc'?[[e.center[0]-e.radius_mm,e.center[1]-e.radius_mm],[e.center[0]+e.radius_mm,e.center[1]+e.radius_mm]]:e.kind==='line'?[e.start,e.end]:e.points||[]);
 const xs=bounds.map((p:number[])=>p[0]),ys=bounds.map((p:number[])=>p[1]);
 const box=bounds.length?[Math.min(...xs)-5,Math.min(...ys)-5,Math.max(...xs)-Math.min(...xs)+10,Math.max(...ys)-Math.min(...ys)+10]:[0,0,1,1];
 return <section aria-label="复杂几何测量"><h3>复杂几何测量 · 待工艺复核</h3>
 <p>版本 {value.revision_id} · {chart.surface_type} · {chart.mapping_type}</p>
 <p>制造公差未批准；测量完成不代表制造合格。</p>
 {chart.pieces?.map((p:any)=><p key={p.key}>{p.key} · {JSON.stringify(p.lengths)} · 折回误差 {p.maximum_foldback_error_mm} mm</p>)}
 {chart.mapping_type==='isometric'&&entities.length>0&&<svg viewBox={box.join(' ')} role="img" aria-label="精确曲面展开轮廓" style={{width:'100%',maxHeight:320}}><g fill="none" stroke="currentColor" strokeWidth={Math.max(box[2],box[3])/700}>{entities.map((e:any)=>{
 if(e.kind==='line')return <line key={e.id} x1={e.start[0]} y1={e.start[1]} x2={e.end[0]} y2={e.end[1]}/>;
 if(e.kind==='polyline')return <polygon key={e.id} points={e.points.map((p:number[])=>p.join(',')).join(' ')}/>;
 if(e.kind==='arc'){const point=(a:number)=>[e.center[0]+e.radius_mm*Math.cos(a),e.center[1]+e.radius_mm*Math.sin(a)].join(' ');const delta=e.direction==='ccw'?e.end_angle_rad-e.start_angle_rad:e.start_angle_rad-e.end_angle_rad;return <path key={e.id} d={`M ${point(e.start_angle_rad)} A ${e.radius_mm} ${e.radius_mm} 0 ${((delta%(2*Math.PI)+2*Math.PI)%(2*Math.PI))>Math.PI?1:0} ${e.direction==='ccw'?1:0} ${point(e.end_angle_rad)}`}/>;}
 return null;
 })}</g></svg>}
 {!!triangles.length&&<><p>裁片 {chart.triangle_count} · 最大采样形偏 {chart.maximum_sampled_deviation_mm} mm · 曲面与弦长相对差 {chart.maximum_surface_chord_strain}</p>
 <svg viewBox="0 0 800 400" role="img" aria-label="分片误差图">
 {triangles.slice(0,400).map((t:any,i:number)=>{
  const points=t.flat_vertices,extent=Math.max(1,...points.flat().map(Math.abs)),x=(i%25)*32,y=Math.floor(i/25)*25;
  const ratio=t.maximum_sampled_deviation_mm/Math.max(chart.maximum_sampled_deviation_mm,1e-12);
  return <polygon key={t.key} points={points.map((p:number[])=>`${x+p[0]*22/extent},${y+22-p[1]*22/extent}`).join(' ')} fill={`hsl(${220*(1-ratio)} 75% 50%)`} stroke="black" strokeWidth=".2"><title>{t.key}: {t.maximum_sampled_deviation_mm} mm</title></polygon>;
 })}
 </svg><p>蓝色较小，红色较大。图示最多400片；完整数据保存在测量记录。</p></>}
 {report.features?.map((f:any)=><p key={f.id}>{f.id} · {f.candidate} · 深度区间 {JSON.stringify(f.signed_depth_range_mm)} mm · 待工艺分类</p>)}
 </section>;
}
