import {spawn} from 'node:child_process';
import {randomBytes} from 'node:crypto';
import {createInterface} from 'node:readline';
import path from 'node:path';

export const DEFAULT_PYTHON = '/data/qmh/satellite-plugins-20261029/dsh-satellite-heater-drawing/.python/cpython-3.12-linux-x86_64-gnu/bin/python3.12';
export const DEFAULT_CAD = '/data/qmh/OpenCADStudio/current/squashfs-root/usr/bin/OpenCADStudio';
export const DEFAULT_HZ = '/data/qmh/satellite-plugins-20261029/dsh-satellite-heater-drawing/fixtures/case/HZDX.SHX';
export async function startRuntime({root, data, python=DEFAULT_PYTHON, cad=DEFAULT_CAD, hz=DEFAULT_HZ, timeout=240000}) {
  for(const value of [root,data,python,cad,hz]) if(!path.isAbsolute(value)) throw Error('runtime_paths_must_be_absolute');
  const token=randomBytes(32).toString('hex'), receiptKey=randomBytes(32).toString('hex');
  const child=spawn(python,[path.join(root,'runtime/bootstrap.py')],{
    env:{...process.env,HEATER_PROFILE_DATA:data,HEATER_SERVICE_TOKEN:token,HEATER_RECEIPT_KEY:receiptKey,
      HEATER_OPENCADSTUDIO:cad,HEATER_HZDX_FONT:hz,PYTHONUNBUFFERED:'1',MPLBACKEND:'Agg'},
    stdio:['pipe','pipe','pipe'], detached:true,
  });
  // Diagnostic messages are deliberately not forwarded to the browser or logs:
  // third-party startup failures may contain local paths. Keep a bounded tail.
  let tail=''; child.stderr.on('data',chunk=>{tail=(tail+chunk.toString()).slice(-8000);});
  let closed=false;
  const close=async()=>{
    if(closed)return; closed=true; child.stdin.end();
    if(child.exitCode!==null||child.signalCode)return;
    await new Promise(resolve=>{
      const timer=setTimeout(()=>{try{process.kill(-child.pid,'SIGTERM');}catch{}; resolve();},10000);
      child.once('exit',()=>{clearTimeout(timer);resolve();});
    });
    if(child.exitCode===null&&!child.signalCode)try{process.kill(-child.pid,'SIGKILL');}catch{}
  };
  const lines=createInterface({input:child.stdout});
  let ready;
  try {
    ready=await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(Error('backend_startup_timeout')),timeout);
      const failed=()=>{clearTimeout(timer);reject(Error('backend_startup_failed_check_python_cad_fonts'));};
      child.once('error',failed); child.once('exit',failed);
      lines.on('line',line=>{
        try{const value=JSON.parse(line);if(value.ready===true&&Number.isInteger(value.port)&&value.port>0&&value.port<65536){clearTimeout(timer);resolve(value);}}catch{}
      });
    });
  }catch(error){await close();throw error;}
  const api=async(route,{method='GET',body,owner,session,headers={},signal}={})=>{
    if(closed||child.exitCode!==null||child.signalCode)throw Error('backend_stopped_reload_plugin');
    const response=await fetch(`http://127.0.0.1:${ready.port}/api/heater/v1${route}`,{
      method,body,headers:{...headers,authorization:'Bearer '+token,'x-heater-owner':owner,'x-heater-session':session},
      signal:signal||AbortSignal.timeout(30000),redirect:'error',
    });
    return response;
  };
  return {api,close,receiptKey,version:ready.version};
}
