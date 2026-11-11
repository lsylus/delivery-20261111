import type {Identity} from './types';
export function draftKey(identity:Identity,project:string){return 'satellite-drawings:v1:'+JSON.stringify([identity.owner_id,identity.session_id,project,identity.module]);}
export function readDraft(storage:Storage,identity:Identity,project:string,revision:string){
  try{const d=JSON.parse(storage.getItem(draftKey(identity,project))||'null');return d?.revision===revision?d:null;}catch{return null;}
}
export function writeDraft(storage:Storage,identity:Identity,project:string,draft:any){storage.setItem(draftKey(identity,project),JSON.stringify(draft));}
