import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import {createHash,generateKeyPairSync,createPrivateKey,createPublicKey,randomBytes,sign} from 'node:crypto';
import {endpoint} from './proxy.mjs';
const digest=x=>createHash('sha256').update(x).digest('hex');
const validId=x=>typeof x==='string'&&/^[A-Za-z0-9._-]{1,160}$/.test(x)&&!['.','..'].includes(x);
const encoded=x=>Buffer.from(JSON.stringify(x)).toString('base64url');
export async function accountIdentity(ctx,tenant) {
  const profile=ctx.get?.('profileContext')||ctx.profileContext;
  if(!profile?.home||!path.isAbsolute(profile.home)||!validId(tenant))throw Error('account_profile_required');
  const home=await fs.realpath(profile.home);
  const file=path.join(home,'private-plugin-context.json'),st=await fs.lstat(file);
  if(!st.isFile()||st.isSymbolicLink()||(st.mode&0o077))throw Error('private_account_context_required');
  const value=JSON.parse(await fs.readFile(file,'utf8'));
  if(!validId(value.userId)||value.home!==home||path.basename(home)!=='home'||path.basename(path.dirname(home))!==digest(value.userId))throw Error('account_context_mismatch');
  const manifest=JSON.parse(await fs.readFile(path.join(value.harnessRoot,'apps/cli/package.json'),'utf8'));
  if(manifest.name!=='@deepseek-ai/dsh'||manifest.version!=='0.2.2-rc.1')throw Error('unsupported_host_version');
  return Object.freeze({tenant,user:value.userId,home_hash:digest(value.userId),owner:digest(tenant+'\0'+value.userId),home,contextFile:file});
}
export async function createHostIdentity(ctx,config,module) {
  if(!['paint','blanket'].includes(module)||!ctx.connection?.admit||!ctx.sessions?.get)throw Error('host_services_required');
  const identity=await accountIdentity(ctx,config.tenant||'xingqiao-9999');
  // CredentialKey is a nominal TypeScript scope/id string; no second credentials module.
  const key=`satellite-${module}/drawings-host-signing`;
  const record=await ctx.credentials.modifyRecord(key,async current=>{
    if(current)return undefined;
    const keys=generateKeyPairSync('ed25519');
    return {kind:'grant',payload:{version:1,private_key:keys.privateKey.export({format:'pem',type:'pkcs8'})}};
  });
  if(record?.kind!=='grant'||record.payload?.version!==1)throw Error('host_key_unavailable');
  const privateKey=createPrivateKey(record.payload.private_key);
  if(privateKey.asymmetricKeyType!=='ed25519')throw Error('invalid_host_key');
  const publicKey=createPublicKey(privateKey).export({type:'spki',format:'der'}).toString('base64url');
  const kid=digest(Buffer.from(publicKey,'base64url')),pending=new Map(),lifetime=new AbortController();
  const serviceUrl=endpoint(config.serviceUrl||'http://127.0.0.1:18777');
  const accountStillValid=async()=>{
    if(lifetime.signal.aborted)return false;
    const now=await accountIdentity(ctx,identity.tenant);
    return now.owner===identity.owner&&now.home===identity.home;
  };
  const live=async(session)=>Boolean(session&&validId(session.id)&&ctx.sessions.get(session.id)===session&&await accountStillValid());
  const server=http.createServer(async(req,res)=>{
    const deny=()=>{res.writeHead(403);res.end();};
    if(req.socket.remoteAddress!=='127.0.0.1'||req.method!=='POST'||req.url!=='/b07/authorize'||req.headers.origin||req.headers.host!==`127.0.0.1:${server.address().port}`)return deny();
    try{
      let raw='';for await(const part of req){raw+=part;if(raw.length>1024)return deny();}
      const {nonce}=JSON.parse(raw),lease=pending.get(nonce);
      const active=Boolean(lease&&lease.expires>Date.now()&&await lease.valid()&&pending.get(nonce)===lease&&!lifetime.signal.aborted);
      const payload=encoded({nonce,active});
      res.writeHead(200,{'content-type':'application/json','cache-control':'no-store'});
      res.end(JSON.stringify({payload,signature:sign(null,Buffer.from(payload),privateKey).toString('base64url')}));
    }catch{deny();}
  });
  server.requestTimeout=3000;server.headersTimeout=3000;
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  const stop=async()=>{if(lifetime.signal.aborted)return;lifetime.abort();pending.clear();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));};
  ctx.effect(()=>stop);
  const sessionContext=async(session,valid)=>{
    if(!await valid())throw Error('session_unavailable');
    const api=async(route,options={})=>{
      if(!/^\/(health|capabilities|sessions|projects|runs|artifacts)(\/[A-Za-z0-9_-]+)*$/.test(route))throw Error('invalid_path');
      const method=options.method||'GET';if(!['GET','POST','PUT'].includes(method))throw Error('invalid_method');
      const body=options.body===undefined?Buffer.alloc(0):Buffer.from(options.body);
      if(body.length>64*1024*1024)throw Error('too_large');
      if(!await valid())throw Error('session_unavailable');
      for(const [n,g] of pending)if(g.expires<=Date.now())pending.delete(n);
      if(pending.size>=64)throw Error('host_busy');
      const headers={};for(const n of ['content-type','x-filename'])if(options.headers?.[n])headers[n]=options.headers[n];
      const nonce=randomBytes(32).toString('base64url'),expires=Date.now()+15000;
      const claims={v:1,kid,tenant:identity.tenant,user:identity.user,home_hash:identity.home_hash,module,session:session.id,
        method,path:'/api/v1'+route,body_sha256:digest(body),headers,nonce,expires,callback_port:server.address().port};
      const payload=encoded(claims),signature=sign(null,Buffer.from(payload),privateKey).toString('base64url');
      pending.set(nonce,{expires,valid});
      try{
        const response=await fetch(serviceUrl+claims.path,{method,body:method==='GET'?undefined:body,
          headers:{...headers,'x-drawings-host':payload+'.'+signature},redirect:'error',signal:AbortSignal.any([lifetime.signal,options.signal||AbortSignal.timeout(30000)])});
        const data=Buffer.from(await response.arrayBuffer());
        if(!await valid())throw Error('session_unavailable');
        return {status:response.status,headers:response.headers,data};
      }finally{pending.delete(nonce);}
    };
    return {identity:{owner_id:identity.owner,session_id:session.id,module,mode:'live',host_mode:'dsh-account',formal_host:'awaiting_platform_acceptance'},api};
  };
  return {
    info:()=>({tenant:identity.tenant,user:identity.user,home_hash:identity.home_hash,module,kid,public_key:publicKey,service_url:serviceUrl,host_version:'0.2.2-rc.1',node:process.version}),
    async browser(req,res){
      const peer=ctx.connection.admit(req).peer;
      if(!peer||peer!==ctx.connection.browserPeer||peer.principal.kind!=='owner'||peer.signal.aborted)throw Error('unauthenticated');
      const session=ctx.sessions.get(req.headers['x-satellite-session']);
      return sessionContext(session,async()=>!res.destroyed&&ctx.connection.admit(req).peer===peer&&!peer.signal.aborted&&await live(session));
    },
    async tool(exec){
      const session=exec?.agent?.session;
      return sessionContext(session,async()=>Boolean(exec?.agent?.id===session?.id&&exec?.signal&&!exec.signal.aborted&&await live(session)));
    },
    stop,
  };
}
