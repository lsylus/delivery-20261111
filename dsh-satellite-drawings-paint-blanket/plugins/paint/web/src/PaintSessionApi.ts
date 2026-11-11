import {Api} from '../../../../packages/workbench-common/src/api';
import {same} from '../../../../packages/host-bridge/src/selection-context.mjs';

export const sessionChanged='会话已改变，请重新打开工作台';

// Scope checks cover requests as well as their completions. An aborted epoch
// must never issue the next request or publish a late result into the UI.
export class PaintSessionApi extends Api {
 constructor(signal:AbortSignal,private original:any,private assertCurrent:()=>void,private invalidate:(message:string)=>void){super('paint',signal);}
 async checkIdentity(){
  this.assertCurrent();
  try {
   const next=await super.identity();
   this.assertCurrent();
   if(!same(next,this.original))throw Error(sessionChanged);
  }catch(e){
   if(!this.signal.aborted)this.invalidate(String(e));
   throw e;
  }
 }
 async request(path:string,options:RequestInit={}){
  await this.checkIdentity();
  this.assertCurrent();
  const response=await super.request(path,options);
  this.assertCurrent();
  return response;
 }
 async json(path:string,options:RequestInit={}){
  const value=await super.json(path,options);
  await this.checkIdentity();
  this.assertCurrent();
  return value;
 }
}
