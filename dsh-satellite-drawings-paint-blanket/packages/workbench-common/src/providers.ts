import {Api,sha256} from './api';
import type {Identity,Loaded} from './types';
import {sameModel} from '../../host-bridge/src/selection-context.mjs';
export const paintRecommendationsForRevision=(result:any,revision:any)=>{
  const recommendations=result?.recommendations||null;
  if(recommendations&&!sameModel(recommendations.model_ref,revision.model_ref))throw Error('推荐结果版本冲突，请刷新');
  return recommendations;
};
export const encodeUploadFilename=(name:string)=>encodeURIComponent(name);
export class LiveProvider {
  api:Api;identity:Identity;
  constructor(api:Api,identity:Identity){this.api=api;this.identity=identity;}
  async load(projectId:string):Promise<Loaded|null>{
    const project=await this.api.json('/projects/'+projectId),head=project.module_states[this.identity.module];
    if(!head)return null;
    const revision=await this.api.json(`/projects/${projectId}/revisions/${head}`);
    const model=await this.api.json(`/projects/${projectId}/models/${revision.model_ref.model_id}`);
    const asset=(suffix:string)=>{const a=model.artifacts.find((a:any)=>a.relative_storage_path.endsWith(suffix));if(!a)throw Error('缺少模型资产 '+suffix);return a;};
    const glbAsset=asset('model.glb'),mapAsset=asset('mesh-map.json');
    const download=async(a:any)=>{if(!/^\/api\/v1\/artifacts\/[a-zA-Z0-9_-]+$/.test(a.download_url))throw Error('非法资产地址');const b=await(await this.api.request(a.download_url.replace('/api/v1',''))).arrayBuffer();if(b.byteLength!==a.bytes||await sha256(b)!==a.sha256)throw Error('资产完整性校验失败');return b;};
    const [glb,mapBytes]=await Promise.all([download(glbAsset),download(mapAsset)]),map=JSON.parse(new TextDecoder().decode(mapBytes));
    if(map.glb_sha256!==glbAsset.sha256||!sameModel(map.model_ref,revision.model_ref)||!sameModel(model.snapshot.model_ref,revision.model_ref))throw Error('needs_reselection');
    const [paintResult,recommendationResult,paintBatchResult]=this.identity.module==='paint'?await Promise.all([
      this.api.json(`/projects/${projectId}/paint-result`),
      this.api.json(`/projects/${projectId}/paint-recommendations`),
      this.api.json(`/projects/${projectId}/paint-batch-result`),
    ]):[null,null,null];
    if(paintResult&&(paintResult.paint.revision_id!==revision.id||!sameModel(paintResult.paint.model_ref,revision.model_ref)))throw Error('结果版本冲突，请刷新');
    const paintRecommendations=paintRecommendationsForRevision(recommendationResult,revision);
    if(paintBatchResult&&(paintBatchResult.batch.revision_id!==revision.id||!sameModel(paintBatchResult.batch.model_ref,revision.model_ref)))throw Error('批量结果版本冲突，请刷新');
    const blanketResult=this.identity.module==='blanket'?await this.api.json(`/projects/${projectId}/blanket-result`):null;
    const blanketNet=this.identity.module==='blanket'?await this.api.json(`/projects/${projectId}/blanket-net`):null;
    for(const value of [blanketResult?.blanket,blanketNet?.net])if(value&&(value.revision_id!==revision.id||!sameModel(value.model_ref,revision.model_ref)))throw Error('结果版本冲突，请刷新');
    return {blanketResult,blanketNet,identity:this.identity,project,revision,snapshot:model.snapshot,map,glb,hash:glbAsset.sha256,checks:paintResult?.paint.checks||paintBatchResult?.batch?.checks||[],paintResult,paintRecommendations,paintBatchResult};
  }
  async create(){const p=await this.api.json('/projects',{method:'POST',body:JSON.stringify({name:this.identity.host_mode==='dsh-account'?'TEST-qmh-图纸工程':'图纸工程',module:this.identity.module})});await this.bind(p.id,'empty');return p.id;}
  async bind(id:string,expected:string){return this.api.json(`/sessions/${this.identity.session_id}/binding`,{method:'PUT',body:JSON.stringify({session_id:this.identity.session_id,module:this.identity.module,project_id:id,expected_revision:expected})});}
  async upload(project:string,file:File,expected:string,onRun?:(runId:string,stage:string)=>void){const a=await this.api.json(`/projects/${project}/assets`,{method:'POST',headers:{'Content-Type':'application/step','X-Filename':encodeUploadFilename(file.name)},body:file});const r=await this.api.json(`/projects/${project}/imports`,{method:'POST',body:JSON.stringify({asset_id:a.id,main_file:a.filename,format_options:{},expected_revision:expected,idempotency_key:crypto.randomUUID()})});onRun?.(r.run_id,'解析装配并生成三维预览');await this.api.wait(r.run_id,960000);if(this.identity.module==='paint'){const p=await this.api.json('/projects/'+project),revision=await this.api.json(`/projects/${project}/revisions/${p.module_states.paint}`),request={schema_version:1,module:'paint',operation:'paint.recommend',project_id:project,model_ref:revision.model_ref,expected_revision:revision.id,selection_refs:revision.selection,parameters:{model_ref:revision.model_ref},overrides:revision.overrides,idempotency_key:crypto.randomUUID()};const recommendation=await this.api.json(`/projects/${project}/operations`,{method:'POST',body:JSON.stringify(request)});onRun?.(recommendation.run_id,'分析板件并计算候选面');await this.api.wait(recommendation.run_id,960000);}return this.load(project);}
}
// Demo is an explicit, offline reference page. It never supplies live data or exports.
export const demoProvider={mode:'demo',canExport:false,canSave:false,description:'原型交互示例；不是计算结果',url:'./demo/index.html'};
