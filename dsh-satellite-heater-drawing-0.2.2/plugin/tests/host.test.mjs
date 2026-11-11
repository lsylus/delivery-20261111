import test from 'node:test';
import assert from 'node:assert/strict';
import {createHmac} from 'node:crypto';
import {browserIdentity,toolIdentity,sameOrigin,signReceipt,canonical} from '../src/host.mjs';
import {workspaceEntry} from '../src/workspace.mjs';

test('browser identities require admitted owner peer and live server-side session',()=>{
 const session={id:'session'},peer={principal:{kind:'owner'},signal:new AbortController().signal};
 const req={headers:{'x-heater-session':'session'}};
 const ctx={connection:{requestRejection:()=>null,admit:()=>({peer}),browserPeer:peer},sessions:{get:id=>id==='session'?session:null}};
 const identity=browserIdentity(ctx,req,'trusted-profile-owner');assert.equal(identity.owner,'trusted-profile-owner');assert.equal(identity.live(),true);
 req.headers['x-heater-owner']='attacker';assert.equal(browserIdentity(ctx,req,'trusted-profile-owner').owner,'trusted-profile-owner');
 req.headers['x-heater-session']='unknown';assert.throws(()=>browserIdentity(ctx,req,'owner'));
 req.headers['x-heater-session']='session';peer.principal.kind='guest';assert.throws(()=>browserIdentity(ctx,req,'owner'));
});
test('tool identities cannot self-report a session or use cancelled executions',()=>{
 const session={id:'session'},ctx={sessions:{get:()=>session}},controller=new AbortController();
 const exec={agent:{id:'session',session},signal:controller.signal};
 assert.equal(toolIdentity(ctx,exec,'owner').session,'session');
 assert.throws(()=>toolIdentity(ctx,{agent:{id:'other',session},signal:controller.signal},'owner'));
 controller.abort();assert.throws(()=>toolIdentity(ctx,exec,'owner'));
});
test('CSRF rejects cross-site and originless mutations',()=>{
 assert.equal(sameOrigin({headers:{host:'localhost:9999',origin:'http://localhost:9999'}},true),true);
 assert.equal(sameOrigin({headers:{host:'localhost:9999'}},true),false);
 assert.equal(sameOrigin({headers:{host:'localhost:9999',origin:'https://other'}},true),false);
 assert.equal(sameOrigin({headers:{host:'localhost:9999','sec-fetch-site':'cross-site'}}),false);
});
test('receipts bind exact payload, revision and session without leaking key',()=>{
 const key='private'.repeat(12),payload={kind:'skip',reason:'明确跳过',row_ids:['Sheet1:2']};
 const token=signReceipt(key,{owner:'owner',session:'session',job:'job',action:'decision',revision:'a'.repeat(64),payload});
 const [encoded,signature]=token.split('.');
 assert.equal(signature,createHmac('sha256',key).update(encoded).digest('hex'));
 const claims=JSON.parse(Buffer.from(encoded,'base64url'));assert.equal(claims.session,'session');assert.equal(claims.revision,'a'.repeat(64));
 assert.ok(!token.includes(key));assert.equal(canonical({z:1,a:payload}),canonical({a:payload,z:1}));
});
test('workspace has independent identity',()=>{
 assert.equal(workspaceEntry.key,'heater-drawing');assert.equal(workspaceEntry.id,'custom-heater-drawing');
});
