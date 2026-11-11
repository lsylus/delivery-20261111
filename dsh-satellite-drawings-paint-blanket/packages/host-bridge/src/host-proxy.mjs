import {safePath,staticHandler} from './proxy.mjs';
import {createHostIdentity} from './host-identity.mjs';
import {loadHostModule} from './host-runtime.mjs';
import {callTool,toolCatalog} from './commands.mjs';
const fail=(res,status,code)=>{if(res.destroyed)return;res.writeHead(status,{'content-type':'application/json','cache-control':'no-store'});res.end(JSON.stringify({code,message:code}));};
export async function registerHost(ctx,config,module,publicRoot){
  const authority=await createHostIdentity(ctx,config,module),prefix=`/api/satellite-${module}`;
  const handler=async(req,res)=>{
    try{
      const rejection=ctx.connection.requestRejection(req);if(rejection)return fail(res,rejection,'unauthenticated');
      if(req.url===prefix+'/host-info'){
        if(req.method!=='GET')return fail(res,405,'method_not_allowed');
        if(ctx.connection.admit(req).peer!==ctx.connection.browserPeer)return fail(res,403,'browser_required');
        res.writeHead(200,{'content-type':'application/json','cache-control':'no-store'});return res.end(JSON.stringify(authority.info()));
      }
      const context=await authority.browser(req,res);
      if(req.url===prefix+'/context'){
        if(req.method!=='GET')return fail(res,405,'method_not_allowed');
        res.writeHead(200,{'content-type':'application/json','cache-control':'no-store'});return res.end(JSON.stringify(context.identity));
      }
      const route=safePath(req.url,prefix+'/service');
      if(!['GET','POST','PUT'].includes(req.method))return fail(res,405,'method_not_allowed');
      if(req.method!=='GET'&&!req.headers.origin)return fail(res,403,'origin_required');
      let size=0;const chunks=[];
      for await(const chunk of req){size+=chunk.length;if(size>64*1024*1024)return fail(res,413,'too_large');chunks.push(chunk);}
      const result=await context.api(route,{method:req.method,body:req.method==='GET'?undefined:Buffer.concat(chunks),headers:req.headers});
      if(res.destroyed)return;
      res.writeHead(result.status,{'content-type':result.headers.get('content-type')||'application/octet-stream','cache-control':'no-store','x-content-type-options':'nosniff'});res.end(result.data);
    }catch(e){return fail(res,['unauthenticated','session_unavailable'].includes(e.message)?401:502,'host_request_unavailable');}
  };
  ctx.effect(()=>ctx.webServer.register({kind:'prefix',path:prefix,handler}));
  const serve=staticHandler(publicRoot,`/satellite-${module}`);
  ctx.effect(()=>ctx.webServer.register({kind:'prefix',path:`/satellite-${module}`,handler:(req,res)=>{
    const rejection=ctx.connection.requestRejection(req);return rejection?fail(res,rejection,'unauthenticated'):serve(req,res);
  }}));
  const {defineTool}=await loadHostModule(ctx,'@deepseek-ai/dsh-tools');
  ctx.tools.register(defineTool({name:`satellite_${module}_host_status`,description:'Read this account drawings host public enrollment and backend connection facts; contains no private keys.',parameters:{},
    output:{schema:{type:'json'},render:(_args,v)=>[{type:'text',text:JSON.stringify(v)}]},
    execute:async(_args,exec)=>{await authority.tool(exec);return authority.info();}}));
  for(const [index,tool] of toolCatalog(module).entries()) {
    const parameters=index===0
      ? {operation:{type:'string',required:true,enum:tool.inputSchema.properties.operation.enum},parameters:{type:'object',required:true,additionalProperties:true}}
      : {run_id:{type:'string',required:true},action:{type:'string',required:true,enum:['status','cancel']}};
    ctx.tools.register(defineTool({name:tool.name,description:tool.description,parameters,
      output:{schema:{type:'json'},render:(_args,v)=>[{type:'text',text:JSON.stringify(v)}]},
      execute:async(args,exec)=>{
        const context=await authority.tool(exec);
        const api=async(route,options={})=>{const result=await context.api(route,{...options,headers:options.body?{'content-type':'application/json'}:{},signal:exec.signal});const v=JSON.parse(result.data);if(result.status>=400)throw Error(v.code||'service_error');return v;};
        return callTool(module,{name:tool.name,arguments:args},async()=>{
          if(index===1)return {identity:context.identity,api};
          const binding=await api('/sessions/'+context.identity.session_id+'/binding');
          const project=await api('/projects/'+binding.project_id);
          const revision=await api(`/projects/${project.id}/revisions/${project.module_states[module]}`);
          return {identity:context.identity,revision,api};
        });
      }}));
  }
}
