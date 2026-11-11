import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {resolveFace,validateSelection} from '../src/selection-context.mjs';
import {acceptChat,attachChat} from '../src/chat-bridge.mjs';
import {safePath,endpoint,createProxy} from '../src/proxy.mjs';
import {toolCatalog,operationEnvelope,callTool} from '../src/commands.mjs';
import {loadHostModule} from '../src/host-runtime.mjs';
import {workspaceEntry} from '../src/workspace.mjs';
const map=JSON.parse(await fs.readFile(new URL('../../../docs/evidence/B06/artifacts/mesh-map.json',import.meta.url),'utf8'));
const ref=map.faces[0].face_ref,model=map.model_ref,hit={node:map.faces[0].node,mesh:map.faces[0].mesh,primitive:map.faces[0].primitive,triangle:0};
const current={session_id:'s',module:'paint',project_id:model.project_id,model_ref:model,engineering_revision:'r1',result_id:null,face_refs:map.faces.map(f=>f.face_ref)};
const selection={...current,entity_refs:[ref],view:'3d',annotation:'check',local_coordinates:[[1,2,3]],view_transform:[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]};delete selection.face_refs;
test('precise GLB face mapping keeps occurrence, signature and model reference',()=>assert.deepEqual(resolveFace(map,model,map.glb_sha256,hit),ref));
for(const [label,m,h,p] of [['model',{...model,model_revision:2},map.glb_sha256,hit],['hash',model,'0'.repeat(64),hit],['triangle',model,map.glb_sha256,{...hit,triangle:999}],['primitive',model,map.glb_sha256,{...hit,primitive:999}],['NaN',model,map.glb_sha256,{...hit,triangle:NaN}]])test('reject stale or invalid '+label,()=>assert.throws(()=>resolveFace(map,m,h,p),/needs_reselection/));
for(const field of ['session_id','module','project_id','engineering_revision','result_id'])test('chat rejects changed '+field,()=>assert.throws(()=>validateSelection({...selection,[field]:'changed'},current)));
test('component-only and modified signature references cannot become face selections',()=>{assert.throws(()=>validateSelection({...selection,entity_refs:[{...ref,entity_kind:'instance'}]},current));assert.throws(()=>validateSelection({...selection,entity_refs:[{...ref,signature:{...ref.signature,area_mm2:0}}]},current));});
test('reject malformed coordinates and annotation',()=>{assert.throws(()=>validateSelection({...selection,local_coordinates:[[NaN,0]]},current));assert.throws(()=>validateSelection({...selection,annotation:'a'.repeat(4001)},current));});
test('chat origin/source/type and replay checks prevent side effects',()=>{
 const source={},origin='http://localhost',seen=new Set(),data={type:'satellite-drawings:chat',request_id:'a',selection};
 for(const e of [{origin:'https://evil',source,data},{origin,source:{},data},{origin,source,data:{...data,type:'execute'}}])assert.throws(()=>acceptChat(e,{origin,source,current,seen}));
 assert.equal(seen.size,0);assert.match(acceptChat({origin,source,data},{origin,source,current,seen}),/check/);assert.throws(()=>acceptChat({origin,source,data},{origin,source,current,seen}));
});
test('detach removes old frame listener and cannot write drafts',()=>{
 let listener,removed=false,drafts=[];const source={postMessage(){}},window={location:{origin:'http://localhost'},addEventListener(t,f){listener=f;},removeEventListener(){removed=true;}};
 const stop=attachChat({window,iframe:{contentWindow:source},getCurrent:()=>current,getDraft:()=>'',setDraft:d=>drafts.push(d)});stop();listener({origin:window.location.origin,source,data:{type:'satellite-drawings:chat',request_id:'b',selection}});assert(removed);assert.equal(drafts.length,0);
});
test('unsafe proxy paths and non-loopback endpoints rejected',()=>{
 for(const raw of ['/p/../secret','/p/%2e%2e/secret','/p/health?owner=bob','/p/\\secret','/prefix/health'])assert.throws(()=>safePath(raw,'/p'));
 for(const u of ['http://example.com','http://127.0.0.1/path','http://user:pass@127.0.0.1','https://127.0.0.1'])assert.throws(()=>endpoint(u));assert.equal(endpoint('http://127.0.0.1:1234'),'http://127.0.0.1:1234');
});
test('missing formal identity fails closed',async()=>{let status,body;const fn=createProxy({module:'paint',serviceUrl:'http://127.0.0.1:1',origin:'http://127.0.0.1:2'});await fn({headers:{host:'127.0.0.1:2'},url:'/api/satellite-paint/context'},{writeHead:s=>status=s,end:b=>body=b});assert.equal(status,503);assert.match(body,/host_identity_not_configured/);});
test('tool enum and commands retain module and revision; unavailable host is explicit',async()=>{assert(toolCatalog('paint')[0].inputSchema.properties.operation.enum.includes('drawing.export'));assert(toolCatalog('paint')[0].inputSchema.properties.operation.enum.includes('paint.generate_batch'));assert(!toolCatalog('paint')[0].inputSchema.properties.operation.enum.includes('blanket.generate'));const e=operationEnvelope({module:'paint'},{id:'r1',model_ref:model,selection:[ref],overrides:[]},'engineering.save');assert.equal(e.expected_revision,'r1');assert.throws(()=>operationEnvelope({module:'paint'},{},'blanket.generate'));await assert.rejects(()=>callTool('paint',{name:'satellite_paint_operation'},null),/host_identity_not_configured/);});
test('installation detection is exposed only to the blanket module',()=>{const paint=toolCatalog('paint')[0].inputSchema.properties.operation.enum,blanket=toolCatalog('blanket')[0].inputSchema.properties.operation.enum;assert(blanket.includes('blanket.detect_installation'));assert(!paint.includes('blanket.detect_installation'));const e=operationEnvelope({module:'blanket'},{id:'r1',model_ref:model,selection:[],overrides:[]},'blanket.detect_installation',{target_instances:['occ-1'],excluded_instances:[],maximum_gap_mm:.1},'detect-key');assert.equal(e.operation,'blanket.detect_installation');assert.equal(e.module,'blanket');assert.equal(e.idempotency_key,'detect-key');assert.throws(()=>operationEnvelope({module:'paint'},{},'blanket.detect_installation'),/wrong_module/);});
test('workspace and namespace identities remain separate',()=>{assert.notEqual(workspaceEntry('paint').id,workspaceEntry('blanket').id);assert.notEqual(toolCatalog('paint')[0].name,toolCatalog('blanket')[0].name);});
test('host module resolves from installAnchor and shares the existing instance',async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'b07-host-'));
 try{const pkg=path.join(root,'node_modules/host-identity');await fs.mkdir(pkg,{recursive:true});await fs.writeFile(path.join(pkg,'package.json'),JSON.stringify({type:'module',exports:'./index.mjs'}));await fs.writeFile(path.join(pkg,'index.mjs'),'export const identity={};');const ctx={get:()=>({installAnchor:path.join(root,'anchor.cjs')})};const a=await loadHostModule(ctx,'host-identity'),b=await loadHostModule(ctx,'host-identity');assert.equal(a.identity,b.identity);await assert.rejects(()=>loadHostModule({},'host-identity'),/anchor/);}finally{await fs.rm(root,{recursive:true,force:true});}
});
