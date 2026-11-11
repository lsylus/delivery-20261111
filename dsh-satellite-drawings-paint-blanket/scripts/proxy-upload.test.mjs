import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {createProxy} from '../packages/host-bridge/src/proxy.mjs';

async function exercise(fn,uploadLimitBytes=2048){
  let received=0;
  const backend=http.createServer(async(req,res)=>{try{for await(const chunk of req)received+=chunk.length;res.end(JSON.stringify({received}));}catch{res.destroy();}});
  await new Promise(resolve=>backend.listen(0,'127.0.0.1',resolve));
  const proxy=http.createServer();await new Promise(resolve=>proxy.listen(0,'127.0.0.1',resolve));
  const origin=`http://127.0.0.1:${proxy.address().port}`;
  proxy.on('request',createProxy({module:'blanket',serviceUrl:`http://127.0.0.1:${backend.address().port}`,origin,uploadLimitBytes,
    resolveIdentity:()=>({owner_id:'u',session_id:'s',module:'blanket',backendCredential:'local-test'})}));
  try{await fn(origin,()=>received);}finally{proxy.closeAllConnections();backend.closeAllConnections();await Promise.all([new Promise(resolve=>proxy.close(resolve)),new Promise(resolve=>backend.close(resolve))]);}
}
test('upload limit is configurable and body reaches the backend',()=>exercise(async(origin)=>{
  const response=await fetch(origin+'/api/satellite-blanket/service/projects/p/assets',{method:'POST',headers:{origin,'content-type':'application/step'},body:Buffer.alloc(1500)});
  assert.equal(response.status,200);assert.equal((await response.json()).received,1500);
}));
test('known oversized uploads are rejected before forwarding',()=>exercise(async(origin,received)=>{
  const response=await fetch(origin+'/api/satellite-blanket/service/projects/p/assets',{method:'POST',headers:{origin},body:Buffer.alloc(3000)});
  assert.equal(response.status,413);assert.equal(received(),0);
}));
test('chunked uploads cannot bypass the byte limit',()=>exercise(async(origin)=>{
  async function* body(){yield Buffer.alloc(1500);yield Buffer.alloc(1500);}
  const response=await fetch(origin+'/api/satellite-blanket/service/projects/p/assets',{method:'POST',headers:{origin},body:body(),duplex:'half'});
  assert.equal(response.status,413);
}));
test('large file allowance does not enlarge the JSON request allowance',()=>exercise(async(origin,received)=>{
  const response=await fetch(origin+'/api/satellite-blanket/service/projects',{method:'POST',headers:{origin},body:Buffer.alloc(1024*1024+1)});
  assert.equal(response.status,413);assert.equal(received(),0);
},2*1024*1024));
