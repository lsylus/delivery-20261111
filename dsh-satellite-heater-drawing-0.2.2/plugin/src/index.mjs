import {fileURLToPath} from 'node:url';
import path from 'node:path';
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {startRuntime} from './runtime.mjs';
import {registerWorkspace} from './workspace.mjs';
import {browserIdentity,toolIdentity,sameOrigin,boundedBody,json,hostModule,signReceipt,validId} from './host.mjs';

export const name='satellite-heater-drawing';
export const inject=['webServer','connection','sessions','tools'];
const root=fileURLToPath(new URL('../',import.meta.url));
const prefix='/api/satellite-heater',publicPrefix='/satellite-heater';
const read=value=>typeof value?.get==='function'?value.get():value;
export async function apply(ctx,config={}){
  const profile=ctx.get?.('profileContext');
  if(!profile?.home||!path.isAbsolute(profile.home))throw Error('heater_requires_account_profile');
  const owner=createHash('sha256').update(await fs.realpath(profile.home)).digest('hex');
  const data=path.join(profile.home,'satellite-heater-drawing');
  const runtime=await startRuntime({root,data,python:read(config.pythonExecutable),cad:read(config.cadExecutable),hz:read(config.hzFont)});
  ctx.effect(()=>runtime.close);
  registerWorkspace(ctx);
  const api=async(identity,route,options={})=>runtime.api(route,{...identity,...options});
  const handler=async(req,res)=>{
    try{
      if(!sameOrigin(req,req.method!=='GET'))return json(res,403,{error:{message:'需要经过认证的同源请求'}});
      const identity=browserIdentity(ctx,req,owner);
      if(req.url===prefix+'/context'&&req.method==='GET')return json(res,200,{session_id:identity.session,version:runtime.version});
      if(req.url===prefix+'/confirm'&&req.method==='POST'){
        const body=JSON.parse((await boundedBody(req,256*1024)).toString());
        if(!validId(body.job_id)||!['decision','review'].includes(body.action))return json(res,400,{error:{message:'确认内容不正确'}});
        const response=await api(identity,'/jobs/'+body.job_id);const current=await response.json();
        if(!response.ok)return json(res,response.status,current);
        if(body.revision_hash!==current.revision?.revision_hash)return json(res,409,{error:{message:'修订已改变，请刷新'}});
        let payload,route,outgoing;
        if(body.action==='decision'){
          if(current.state!=='awaiting_resolution')return json(res,409,{error:{message:'当前没有待确认问题'}});
          payload=body.selection; route=`/jobs/${body.job_id}/decisions`;
          outgoing={base_revision_hash:body.revision_hash,selection:payload};
        }else{
          if(current.run?.state!=='generated'||current.run.id!==body.run_id)return json(res,409,{error:{message:'出图结果已改变'}});
          payload={run_id:body.run_id,status:body.status,comment:body.comment,manifest_sha:current.run.manifest_sha};
          route=`/jobs/${body.job_id}/runs/${body.run_id}/reviews`;
          outgoing={revision_hash:body.revision_hash,status:body.status,comment:body.comment};
        }
        if(!identity.live())throw Error('session_unavailable');
        const receipt=signReceipt(runtime.receiptKey,{owner,session:identity.session,job:body.job_id,
          action:body.action,revision:body.revision_hash,payload});
        const result=await api(identity,route,{method:'POST',body:JSON.stringify({...outgoing,receipt}),headers:{'content-type':'application/json'}});
        if(!identity.live())throw Error('session_unavailable');
        return json(res,result.status,await result.json());
      }
      if(!req.url.startsWith(prefix+'/service/'))return json(res,404,{error:{message:'接口不存在'}});
      const route=req.url.slice((prefix+'/service').length);
      // Decisions/reviews are issued only by the browser confirmation route.
      const allowed=req.method==='GET'&&/^\/(capabilities|jobs(?:\/[A-Za-z0-9_-]+(?:\/runs\/[A-Za-z0-9_-]+\/artifacts\/[A-Za-z0-9_-]+)?)?)$/.test(route)
        ||req.method==='POST'&&/^\/jobs(?:\/[A-Za-z0-9_-]+\/runs(?:\/[A-Za-z0-9_-]+\/cancel)?)?$/.test(route);
      if(!allowed)return json(res,405,{error:{message:'接口不支持此操作'}});
      const headers={};for(const key of ['content-type','x-heater-name','idempotency-key'])if(req.headers[key])headers[key]=req.headers[key];
      const body=req.method==='GET'?undefined:await boundedBody(req,route==='/jobs'?10*1024*1024:256*1024);
      const response=await api(identity,route,{method:req.method,body,headers});
      const content=Buffer.from(await response.arrayBuffer());
      if(!identity.live())throw Error('session_unavailable');
      const responseHeaders={'content-type':response.headers.get('content-type')||'application/octet-stream','cache-control':'no-store','x-content-type-options':'nosniff'};
      if(response.headers.get('content-disposition'))responseHeaders['content-disposition']=response.headers.get('content-disposition');
      res.writeHead(response.status,responseHeaders);res.end(content);
    }catch(error){json(res,error.message==='payload_too_large'?413:['unauthenticated','session_unavailable'].includes(error.message)?401:502,{error:{message:'请求失败，请检查会话或重新加载插件'}});}
  };
  ctx.effect(()=>ctx.webServer.register({kind:'prefix',path:prefix,handler}));
  ctx.effect(()=>ctx.webServer.register({kind:'prefix',path:publicPrefix,handler:async(req,res)=>{
    if(ctx.connection.requestRejection(req)||!sameOrigin(req))return json(res,403,{error:{message:'需要登录'}});
    if(req.method!=='GET')return json(res,405,{});
    const filename={'/':'index.html','/app.js':'app.js','/app.css':'app.css','/pdf.mjs':'pdf.mjs','/pdf.worker.mjs':'pdf.worker.mjs','/PDFJS-LICENSE.txt':'PDFJS-LICENSE.txt'}[req.url.split('?')[0].slice(publicPrefix.length)];
    if(!filename)return json(res,404,{});
    try{
      const bytes=await fs.readFile(path.join(root,'public',filename));
      res.writeHead(200,{'content-type':{'.html':'text/html; charset=utf-8','.js':'text/javascript','.mjs':'text/javascript','.css':'text/css','.txt':'text/plain; charset=utf-8'}[path.extname(filename)],
        'x-content-type-options':'nosniff','content-security-policy':"default-src 'self'; script-src 'self'; style-src 'self'; worker-src 'self' blob:; object-src 'none'; connect-src 'self'; frame-ancestors 'self'"});res.end(bytes);
    }catch{json(res,404,{});}
  }}));
  const {defineTool}=await hostModule(ctx,'@deepseek-ai/dsh-tools');
  for(const [tool,description,parameters] of [
    ['heater_capabilities','读取矩形加热器插件可用格式和输入限制。',{}],
    ['heater_job_status','读取当前会话任务状态。generated 表示完整出图通过，仍需工程复核。',{job_id:{type:'string',required:true}}],
    ['heater_explain_issues','读取 Excel 行错误与比例建议。不能代替用户确认比例、跳过或复核。',{job_id:{type:'string',required:true}}],
    ['heater_open_workspace','返回矩形加热器工作台入口；上传、生成与确认均在工作台完成。',{}],
  ]){
    ctx.tools.register(defineTool({name:tool,description,parameters,
      output:{schema:{type:'json'},render:(_args,value)=>[{type:'text',text:JSON.stringify(value)}]},
      execute:async(args,exec)=>{
        const identity=toolIdentity(ctx,exec,owner);
        if(tool==='heater_open_workspace')return {workspace_key:'heater-drawing',url:publicPrefix+'/?session='+encodeURIComponent(identity.session)};
        if(tool!=='heater_capabilities'&&(!validId(args?.job_id)||Object.keys(args).some(k=>k!=='job_id')))throw Error('invalid_job_id');
        const response=await api(identity,tool==='heater_capabilities'?'/capabilities':'/jobs/'+args.job_id,{signal:exec.signal});
        const value=await response.json();if(!response.ok)throw Error(value.error?.message||'service_failed');
        if(tool==='heater_explain_issues')return {job_id:args.job_id,state:value.state,issues:value.issues,proposals:value.proposals};
        return value;
      },
    }));
  }
}
