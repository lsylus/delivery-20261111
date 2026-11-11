export function canonical(value) {
  if (Array.isArray(value)) return '['+value.map(canonical).join(',')+']';
  if (value && typeof value==='object') return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
  return JSON.stringify(value);
}
export const same = (a,b)=>canonical(a)===canonical(b);
export const modelKeys=['project_id','model_id','model_revision','assembly_digest'];
export const sameModel=(a,b)=>!!a&&!!b&&modelKeys.every(k=>a[k]===b[k]);
export function resolveFace(map, model, hash, hit) {
  if (!sameModel(map.model_ref,model)||map.glb_sha256!==hash||!Number.isInteger(hit.triangle)||hit.triangle<0) throw Error('needs_reselection');
  const faces=map.faces.filter(f=>f.node===hit.node&&f.mesh===hit.mesh&&f.primitive===hit.primitive&&hit.triangle>=f.triangle_start&&hit.triangle<f.triangle_start+f.triangle_count);
  if(faces.length!==1||faces[0].face_ref.entity_kind!=='face'||!sameModel(faces[0].face_ref,model)) throw Error('needs_reselection');
  return structuredClone(faces[0].face_ref);
}
export function validateSelection(value, current) {
  if (!value || value.session_id!==current.session_id || value.module!==current.module || value.project_id!==current.project_id ||
      value.engineering_revision!==current.engineering_revision || value.result_id!==current.result_id || !sameModel(value.model_ref,current.model_ref) ||
      !['2d','3d'].includes(value.view) || !Array.isArray(value.entity_refs) || value.entity_refs.length===0 || value.entity_refs.length>256) throw Error('stale_selection');
  for(const ref of value.entity_refs) if(!current.face_refs.some(f=>same(f,ref))) throw Error('needs_reselection');
  if(typeof value.annotation!=='string'||value.annotation.length>4000) throw Error('invalid_annotation');
  if(!Array.isArray(value.local_coordinates)||!Array.isArray(value.view_transform)||value.view_transform.length!==16 ||
     !value.view_transform.every(Number.isFinite)||!value.local_coordinates.every(p=>Array.isArray(p)&&p.length>=2&&p.length<=3&&p.every(Number.isFinite))) throw Error('invalid_coordinates');
  if(value.blanket_target){
    if(value.module!=='blanket'||!current.net)throw Error('stale_blanket_target');
    const t=value.blanket_target,n=current.net;
    const panel=k=>n.panels.find(p=>p.key===k);
    let expected;
    if(t.kind==='seam'){
      const seam=n.seams.find(s=>s.id===t.id);if(!seam)throw Error('stale_blanket_target');
      const edges=[n.edges[seam.edge_a],n.edges[seam.edge_b]];
      expected={kind:'seam',id:t.id,edges:edges.map(e=>({id:e.id,panel_key:e.panel,panel_id:panel(e.panel).id,mapping_ref:panel(e.panel).mapping_ref,world:e.world}))};
    }else if(t.kind==='point'){
      const p=n.fixed_points.find(p=>p.id===t.id);if(!p)throw Error('stale_blanket_target');
      expected={kind:'point',id:p.id,panel_key:p.panel_key,panel_id:p.panel_id,mapping_ref:p.mapping_ref,uv_mm:p.uv_mm,position3d:p.position3d};
    }else throw Error('invalid_blanket_target');
    if(!same(t,expected))throw Error('stale_blanket_target');
    const keys=t.kind==='seam'?t.edges.map(e=>e.panel_key):[t.panel_key];
    const refs=n.panels.filter(p=>keys.includes(p.key)).flatMap(p=>p.source_refs);
    if(value.entity_refs.some(r=>!refs.some(f=>same(r,f)))||refs.some(r=>!value.entity_refs.some(f=>same(r,f))))throw Error('blanket_target_face_mismatch');
  }
  return structuredClone(value);
}
