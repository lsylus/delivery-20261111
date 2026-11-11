/** Loopback demonstration host using the actual packaged plugin and its nav entry. */
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

const config=JSON.parse(await fs.readFile(process.argv[2],'utf8'));
const routes=[];
const server=http.createServer(async(req,res)=>{
  const origin=`http://127.0.0.1:${server.address().port}`;
  if(req.headers.host!==new URL(origin).host){res.writeHead(403);return res.end();}
  if(req.url==='/'){
    res.writeHead(302,{'location':'/host','set-cookie':`simple_session=${config.cookie}; HttpOnly; SameSite=Strict; Path=/`});
    return res.end();
  }
  if(req.url==='/host'){
    res.writeHead(200,{'content-type':'text/html; charset=utf-8','set-cookie':`simple_session=${config.cookie}; HttpOnly; SameSite=Strict; Path=/`});
    const title=config.module==='paint'?'喷涂图纸工作台':'多层包覆工作台';
    return res.end(`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>${title}</title></head><body style="margin:0"><div id="host-root"></div><script>window.__SIMPLE_MODULE__=${JSON.stringify(config.module||'blanket')}</script><script src="/host.js"></script></body></html>`);
  }
  if(req.url==='/host.js'){
    res.writeHead(200,{'content-type':'text/javascript'});return res.end(await fs.readFile(config.hostBundle));
  }
  if(req.url===`/client/${config.module||'blanket'}.js`){
    res.writeHead(200,{'content-type':'text/javascript'});return res.end(await fs.readFile(path.join(config.pluginRoot,'lib/client.js')));
  }
  const route=routes.find(r=>req.url===r.path||req.url.startsWith(r.path+'/'));
  if(!route){res.writeHead(404);return res.end();}
  try{await route.handler(req,res);}catch{if(!res.headersSent)res.writeHead(500);res.end();}
});
await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(config.port||0,'127.0.0.1',resolve);});
const origin=`http://127.0.0.1:${server.address().port}`;
const ctx={inject(_names,fn){fn({effect:fn=>fn(),agentWorkspaces:{register:()=>()=>{}}});},effect:fn=>fn(),
  webServer:{register:r=>{routes.push(r);return()=>{};}},get(name){
    if(name==='satelliteDrawingsIsolatedIdentity')return {resolve(req,module){
      const cookie=(req.headers.cookie||'').split(';').map(x=>x.trim()).find(x=>x.startsWith('simple_session='))?.slice(15);
      return cookie===config.cookie&&module===(config.module||'blanket')?config.identity:null;
    }};
  }};
const plugin=await import(pathToFileURL(path.join(config.pluginRoot,'lib/index.mjs')));
await plugin.apply(ctx,{serviceUrl:config.serviceUrl,origin,uploadLimitBytes:config.uploadLimitBytes,requestTimeoutMs:300000});
await fs.writeFile(config.ready,JSON.stringify({origin,pid:process.pid}));
process.on('SIGTERM',()=>server.close(()=>process.exit(0)));
