import fs from 'node:fs/promises';
import {endpoint} from './proxy.mjs';
export async function isolatedMcpContext(module,file) {
  if(!file)return undefined;
  const stat=await fs.stat(file);if((stat.mode&0o077)!==0)throw Error('private_config_required');
  const config=JSON.parse(await fs.readFile(file,'utf8'));
  if(config.mode!=='isolated-adapter'||config.identity.module!==module)throw Error('isolated_identity_required');
  const base=endpoint(config.serviceUrl);
  const api=async(path,options={})=>{
    if(!/^\/(sessions|projects|runs)\/[a-zA-Z0-9_-]+(\/[a-zA-Z0-9_-]+)*$/.test(path))throw Error('invalid_path');
    const response=await fetch(base+'/api/v1'+path,{...options,headers:{'content-type':'application/json',authorization:'Bearer '+config.credential},redirect:'error',signal:AbortSignal.timeout(10000)});
    const value=await response.json();if(!response.ok)throw Error(`${response.status} ${value.code||value.message}`);return value;
  };
  return async()=>{
    const identity=config.identity,binding=await api('/sessions/'+identity.session_id+'/binding'),project=await api('/projects/'+binding.project_id);
    const revision=await api(`/projects/${project.id}/revisions/${project.module_states[module]}`);
    return {identity,revision,api};
  };
}
