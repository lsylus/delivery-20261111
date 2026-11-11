import {validateSelection} from '../../../host-bridge/src/selection-context.mjs';
export const identityMatrix=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
export function selectionContext(loaded:any,refs:any[],view:'2d'|'3d',annotation:string,coordinates:number[][]=[],transform:number[]=identityMatrix){
  const context={session_id:loaded.identity.session_id,module:loaded.identity.module,project_id:loaded.project.id,model_ref:loaded.revision.model_ref,engineering_revision:loaded.revision.id,result_id:loaded.paintResult?.result_id||null,entity_refs:refs,view,local_coordinates:coordinates,annotation,view_transform:transform};
  return validateSelection(context,{...context,face_refs:loaded.map.faces.map((f:any)=>f.face_ref)});
}
