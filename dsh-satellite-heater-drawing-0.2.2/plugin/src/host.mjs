import {createHash,createHmac,randomBytes} from 'node:crypto';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';

export const validId=x=>typeof x==='string'&&/^[A-Za-z0-9_-]{1,160}$/.test(x);
export function canonical(value){
  if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
  if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
  return JSON.stringify(value);
}
export function signReceipt(key,{owner,session,job,action,revision,payload}){
  const claims={owner,session,job,action,revision,payload_sha:createHash('sha256').update(canonical(payload)).digest('hex'),
    nonce:randomBytes(24).toString('hex'),expires:Math.floor(Date.now()/1000)+120};
  const encoded=Buffer.from(JSON.stringify(claims)).toString('base64url');
  return encoded+'.'+createHmac('sha256',key).update(encoded).digest('hex');
}
export function browserIdentity(ctx,req,owner){
  const rejection=ctx.connection.requestRejection(req);if(rejection)throw Error('unauthenticated');
  const peer=ctx.connection.admit(req).peer;
  if(!peer||peer!==ctx.connection.browserPeer||peer.principal?.kind!=='owner'||peer.signal?.aborted)throw Error('unauthenticated');
  const id=req.headers['x-heater-session'],session=validId(id)&&ctx.sessions.get(id);
  if(!session||session.id!==id)throw Error('session_unavailable');
  return {owner,session:id,live:()=>!peer.signal?.aborted&&ctx.connection.admit(req).peer===peer&&ctx.sessions.get(id)===session};
}
export function toolIdentity(ctx,exec,owner){
  const session=exec?.agent?.session;
  if(!exec?.signal||exec.signal.aborted||!session||!validId(session.id)||exec.agent.id!==session.id||ctx.sessions.get(session.id)!==session)throw Error('session_unavailable');
  return {owner,session:session.id};
}
export function sameOrigin(req,required=false){
  if(!req.headers.host||req.headers['sec-fetch-site']==='cross-site')return false;
  if(!req.headers.origin)return !required;
  try{const url=new URL(req.headers.origin);return ['http:','https:'].includes(url.protocol)&&url.host===req.headers.host;}catch{return false;}
}
export async function hostModule(ctx,name){
  const anchor=ctx.get?.('profileContext')?.installAnchor;
  if(!anchor)throw Error('host_install_anchor_required');
  return import(pathToFileURL(createRequire(anchor).resolve(name)).href);
}
export async function boundedBody(req,limit){
  const chunks=[];let size=0;
  for await(const part of req){size+=part.length;if(size>limit)throw Error('payload_too_large');chunks.push(part);}
  return Buffer.concat(chunks);
}
export const json=(res,status,value)=>{
  if(res.destroyed)return;
  res.writeHead(status,{'content-type':'application/json; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff'});
  res.end(JSON.stringify(value));
};
