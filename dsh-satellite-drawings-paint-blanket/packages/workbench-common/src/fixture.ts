// Selection-map fixture only: rectangles deliberately do not represent manufactured geometry.
export function drawingFixture(loaded:any){
  const entities=loaded.map.faces.map((f:any,i:number)=>{const x=(i%5)*24,y=Math.floor(i/5)*20;return {id:`fixture-${loaded.revision.id}-${i}`,kind:'polyline',layer:'OUTLINE',source_refs:[f.face_ref],points:[[x,y],[x+20,y],[x+20,y+16],[x,y+16]],closed:true};});
  return {schema_version:1,id:'b07-selection-fixture',revision_id:loaded.revision.id,units:'mm',frame:{origin:[0,0,0],x_axis:[1,0,0],y_axis:[0,1,0],z_axis:[0,0,1],units:'mm',handedness:'right'},layers:[{name:'OUTLINE',color:5,line_type:'CONTINUOUS'}],entities,source_links:entities.flatMap((e:any)=>e.source_refs)};
}
