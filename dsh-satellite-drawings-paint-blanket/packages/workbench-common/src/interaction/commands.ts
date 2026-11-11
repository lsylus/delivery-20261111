import {operationEnvelope} from '../../../host-bridge/src/commands.mjs';
export async function execute(api:any,identity:any,revision:any,operation:string,parameters:any={}){
  const envelope=operationEnvelope(identity,revision,operation,parameters);
  return api.json(`/projects/${envelope.project_id}/operations`,{method:'POST',body:JSON.stringify(envelope)});
}
