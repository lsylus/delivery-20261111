export class Api {
  prefix:string; signal:AbortSignal;
  constructor(module:string,signal:AbortSignal){this.prefix=`/api/satellite-${module}`;this.signal=signal;}
  async request(path:string,options:RequestInit={}) {
    const r=await fetch(this.prefix+'/service'+path,{...options,signal:this.signal,cache:'no-store',headers:{'x-satellite-session':new URLSearchParams(location.search).get('session')||'',...(typeof options.body==='string'?{'Content-Type':'application/json'}:{}),...options.headers}});
    if(!r.ok){let e:any;try{e=await r.json();}catch{}throw Error(`${r.status} ${e?.message||e?.code||'服务请求失败'}`);}
    return r;
  }
  async json(path:string,options:RequestInit={}){return (await this.request(path,options)).json();}
  async identity(){const r=await fetch(this.prefix+'/context',{signal:this.signal,cache:'no-store',headers:{'x-satellite-session':new URLSearchParams(location.search).get('session')||''}});if(!r.ok)throw Error(`${r.status} 身份连接不可用`);return r.json();}
  async wait(id:string,timeoutMs=60000){const deadline=Date.now()+timeoutMs;while(Date.now()<deadline){const r=await this.json('/runs/'+id);if(r.state==='succeeded')return r;if(['failed','cancelled'].includes(r.state))throw Error(r.error?.message||r.state);await new Promise(resolve=>setTimeout(resolve,timeoutMs>60000?1000:250));}throw Error('作业等待超时，请刷新工程查看结果');}
}
export async function sha256(buffer:ArrayBuffer){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',buffer))).map(v=>v.toString(16).padStart(2,'0')).join('');}
