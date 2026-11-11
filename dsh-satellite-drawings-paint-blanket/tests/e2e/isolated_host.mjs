import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const config=JSON.parse(await fs.readFile(process.argv[2],'utf8'));
const routes=[],workspaces=[];
const sessions=config.sessions;
const server=http.createServer(async(req,res)=>{
  const origin=`http://127.0.0.1:${server.address().port}`;
  if(req.headers.host!==new URL(origin).host){res.writeHead(403);return res.end();}
  if(req.url==='/host'||req.url==='/host/'){
    res.writeHead(200,{'content-type':'text/html; charset=utf-8'});return res.end('<!doctype html><html><head><meta charset="utf-8"><title>B07 isolated host</title></head><body><div id="host-root"></div><script src="/host/app.js"></script></body></html>');
  }
  if(req.url==='/host/app.js'){res.writeHead(200,{'content-type':'text/javascript'});return res.end(await fs.readFile('work/b07-host.js'));}
  if(/^\/client\/(paint|blanket)\.js$/.test(req.url)){const module=req.url.split('/')[2].split('.')[0];res.writeHead(200,{'content-type':'text/javascript'});return res.end(await fs.readFile(path.join(config.packages,module,'lib/client.js')));}
  const route=routes.find(r=>req.url===r.path||req.url.startsWith(r.path+'/'));
  if(!route){res.writeHead(404);return res.end();}
  const started=Date.now();res.once('finish',()=>fs.appendFile(config.audit,JSON.stringify({method:req.method,path:req.url.split('?')[0],status:res.statusCode,duration_ms:Date.now()-started})+'\n'));
  try{await route.handler(req,res);}catch{res.writeHead(500);res.end('handler_error');}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin=`http://127.0.0.1:${server.address().port}`;
const ctx={inject(_names,fn){fn({effect:fn=>fn(),agentWorkspaces:{register:e=>{workspaces.push(e);return()=>{};}}});},effect:fn=>fn(),webServer:{register:r=>{routes.push(r);return()=>{};}},get(name){
  if(name==='satelliteDrawingsIsolatedIdentity')return {resolve(req,module){const cookie=(req.headers.cookie||'').split(';').map(x=>x.trim()).find(x=>x.startsWith('b07_session='))?.slice(12);return sessions[cookie]?.[module]||null;}};
}};
for(const module of ['paint','blanket']){
  const plugin=await import(pathToFileURL(path.join(config.packages,module,'lib/index.mjs')));
  await plugin.apply(ctx,{serviceUrl:config.serviceUrl,origin});
}
await fs.writeFile(config.ready,JSON.stringify({origin,workspaces,pid:process.pid}));
process.on('SIGTERM',()=>server.close(()=>process.exit(0)));
