export const operations=Object.freeze(['geometry.analyze','engineering.rebind','paint.recommend','paint.generate','paint.generate_batch','paint.edit_regions','blanket.detect_installation','blanket.generate','blanket.edit_shape','blanket.unfold','blanket.edit_seams','blanket.edit_fixed_points','drawing.edit_annotation','drawing.export','engineering.save','engineering.restore','history.undo','history.redo']);
export function operationEnvelope(identity,revision,operation,parameters={},key=crypto.randomUUID()) {
  if(!operations.includes(operation))throw Error('unknown_operation');
  if(operation.startsWith('paint.')&&identity.module!=='paint'||operation.startsWith('blanket.')&&identity.module!=='blanket')throw Error('wrong_module');
  return {schema_version:1,module:identity.module,operation,project_id:revision.model_ref.project_id,model_ref:revision.model_ref,expected_revision:revision.id,selection_refs:revision.selection,parameters,overrides:revision.overrides,idempotency_key:key};
}
export function toolCatalog(module) {
  return [{name:`satellite_${module}_operation`,description:'Submit a version-bound operation; a run_id is not completion. Query the run before reporting success. Edits/export require current result_id; export is draft:true only.',inputSchema:{type:'object',properties:{operation:{type:'string',enum:operations.filter(o=>!o.startsWith(module==='paint'?'blanket.':'paint.'))},parameters:{type:'object'}},required:['operation','parameters'],additionalProperties:false}},
    {name:`satellite_${module}_run`,description:'Query completion or request cancellation of an authorized run.',inputSchema:{type:'object',properties:{run_id:{type:'string',pattern:'^[a-zA-Z0-9_-]+$'},action:{enum:['status','cancel']}},required:['run_id','action'],additionalProperties:false}}];
}
export async function callTool(module,request,context) {
  if(!toolCatalog(module).some(t=>t.name===request.name)||!context)throw Error('host_identity_not_configured');
  const {identity,revision,api}=await context();
  if(identity.module!==module)throw Error('wrong_module');
  if(request.name===`satellite_${module}_run`){
    const args=request.arguments;
    if(!args||Object.keys(args).sort().join(',')!=='action,run_id'||!/^[a-zA-Z0-9_-]+$/.test(args.run_id)||!['status','cancel'].includes(args.action))throw Error('invalid_run_request');
    return api(`/runs/${args.run_id}`+(args.action==='cancel'?'/cancel':''),{method:args.action==='cancel'?'POST':'GET'});
  }
  const envelope=operationEnvelope(identity,revision,request.arguments.operation,request.arguments.parameters);
  return api(`/projects/${envelope.project_id}/operations`,{method:'POST',body:JSON.stringify(envelope)});
}
