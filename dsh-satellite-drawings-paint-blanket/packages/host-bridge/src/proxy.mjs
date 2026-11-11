import {readFile,stat} from 'node:fs/promises';
import path from 'node:path';
import {Readable} from 'node:stream';
import {pipeline} from 'node:stream/promises';
const fail=(res,status,code)=>{res.writeHead(status,{'content-type':'application/json','cache-control':'no-store'});res.end(JSON.stringify({code,message:code}));};
export function safePath(raw,prefix) {
  if(!raw.startsWith(prefix+'/')||/[\\%?#]/.test(raw)||raw.split('/').some(p=>p==='.'||p==='..')) throw Error('invalid_path');
  return raw.slice(prefix.length);
}
export function endpoint(value) {
  const u=new URL(value);
  if(u.protocol!=='http:'||!['127.0.0.1','[::1]'].includes(u.hostname)||u.username||u.password||u.pathname!=='/'||u.search||u.hash)throw Error('isolated_loopback_endpoint_required');
  return u.origin;
}
export function createProxy({module,serviceUrl,resolveIdentity,origin,uploadLimitBytes=64*1024*1024,requestTimeoutMs=30000}) {
  if(!Number.isSafeInteger(uploadLimitBytes)||uploadLimitBytes<1||uploadLimitBytes>2*1024*1024*1024)throw Error('invalid_upload_limit');
  if(!Number.isSafeInteger(requestTimeoutMs)||requestTimeoutMs<1||requestTimeoutMs>900000)throw Error('invalid_request_timeout');
  const prefix=`/api/satellite-${module}/service`, base=endpoint(serviceUrl);
  return async(req,res)=>{
    try {
      if(req.headers.host!==new URL(origin).host || (req.headers.origin&&req.headers.origin!==origin) || req.headers['sec-fetch-site']==='cross-site')return fail(res,403,'untrusted_origin');
      if(!resolveIdentity)return fail(res,503,'host_identity_not_configured');
      const identity=await resolveIdentity(req,module);
      if(!identity||identity.module!==module||!identity.owner_id||!identity.session_id||!identity.backendCredential)return fail(res,401,'session_unavailable');
      if(req.url===`/api/satellite-${module}/context`) {
        res.writeHead(200,{'content-type':'application/json','cache-control':'no-store'});
        return res.end(JSON.stringify({owner_id:identity.owner_id,session_id:identity.session_id,module,mode:'live',host_mode:'isolated-adapter',formal_host:'not_configured'}));
      }
      let rel;try{rel=safePath(req.url,prefix);}catch{return fail(res,400,'invalid_path');}
      if(!['GET','POST','PUT'].includes(req.method)||!/^\/(health|capabilities|projects|runs|artifacts|sessions)(\/|$)/.test(rel))return fail(res,405,'unsupported_route');
      if(!['GET'].includes(req.method)&&req.headers.origin!==origin)return fail(res,403,'origin_required');
      const isUpload=req.method==='POST'&&/^\/projects\/[^/]+\/assets$/.test(rel);
      const limit=isUpload?uploadLimitBytes:1024*1024;
      const length=req.headers['content-length'];
      if(length!==undefined&&(!/^\d+$/.test(String(length))||Number(length)>limit))return fail(res,413,'too_large');
      let exceeded=false;
      async function* limitedBody(){let size=0;for await(const chunk of req){size+=chunk.length;if(size>limit){exceeded=true;throw Error('too_large');}yield chunk;}}
      const headers={authorization:`Bearer ${identity.backendCredential}`};
      for(const name of ['content-type','x-filename'])if(req.headers[name])headers[name]=req.headers[name];
      let response;
      try{response=await fetch(base+'/api/v1'+rel,{method:req.method,headers,body:req.method==='GET'?undefined:limitedBody(),duplex:'half',redirect:'error',signal:AbortSignal.timeout(requestTimeoutMs)});}
      catch(error){if(exceeded)return fail(res,413,'too_large');throw error;}
      res.writeHead(response.status,{'content-type':response.headers.get('content-type')||'application/octet-stream','cache-control':'no-store','x-content-type-options':'nosniff'});
      if(response.body)await pipeline(Readable.fromWeb(response.body),res);else res.end();
    }catch{if(!res.headersSent)return fail(res,502,'service_unavailable');res.destroy?.();}
  };
}
export function staticHandler(root,prefix) {
  return async(req,res)=>{
    try{
      const raw=req.url.split('?')[0];
      const rel=safePath(raw,prefix);
      if(!['GET','HEAD'].includes(req.method))return fail(res,405,'method_not_allowed');
      const file=path.join(root,rel==='/'?'index.html':rel);
      if(!(await stat(file)).isFile())return fail(res,404,'not_found');
      const type={'.html':'text/html; charset=utf-8','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml'}[path.extname(file)]||'application/octet-stream';
      res.writeHead(200,{'content-type':type,'x-content-type-options':'nosniff','content-security-policy':rel==='/demo/original.html'?"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'none'; frame-ancestors 'self'; sandbox allow-scripts":"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'self'"});
      res.end(req.method==='HEAD'?undefined:await readFile(file));
    }catch{return fail(res,404,'not_found');}
  };
}
