import test from 'node:test';
import assert from 'node:assert/strict';
import {resolveFace} from '../../packages/host-bridge/src/selection-context.mjs';
const model={project_id:'p',model_id:'m',model_revision:1,assembly_digest:'a'.repeat(64)},hash='b'.repeat(64);
const entry=(start,count,id)=>({node:1,mesh:0,primitive:0,triangle_start:start,triangle_count:count,face_ref:{...model,instance_id:'occ-1',entity_kind:'face',entity_id:id}});
test('merged primitive picks the current face at every inclusive/exclusive boundary',()=>{
 const map={model_ref:model,glb_sha256:hash,faces:[entry(0,2,'bottom'),entry(2,4,'side'),entry(6,2,'top')]};
 for(const [triangle,face] of [[0,'bottom'],[1,'bottom'],[2,'side'],[5,'side'],[6,'top'],[7,'top']])assert.equal(resolveFace(map,model,hash,{node:1,mesh:0,primitive:0,triangle}).entity_id,face);
 for(const triangle of [-1,8,1.5])assert.throws(()=>resolveFace(map,model,hash,{node:1,mesh:0,primitive:0,triangle}));
});
test('missing and overlapping ranges never guess a face',()=>{
 const map={model_ref:model,glb_sha256:hash,faces:[entry(0,2,'bottom'),entry(3,4,'side')]};
 assert.throws(()=>resolveFace(map,model,hash,{node:1,mesh:0,primitive:0,triangle:2}));
 map.faces.push(entry(3,1,'duplicate'));
 assert.throws(()=>resolveFace(map,model,hash,{node:1,mesh:0,primitive:0,triangle:3}));
});
