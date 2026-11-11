"""Packed MCP submits the same bounded command and queries real completion."""
import os,json,subprocess,tempfile,shutil
from pathlib import Path
from b12_workflow import ROOT,configured,setup,current,result,run,current_net
def main():
 base=Path(tempfile.mkdtemp(prefix='b12-mcp-',dir=ROOT/'work'));s=None
 try:
  s=configured(base/'backend');p,rev,_,_=setup(s);run(s,p,rev,'blanket.generate',rev['parameters']);cover=result(s,p);run(s,p,current(s,p),'blanket.unfold',dict(result_id=cover['result_id']));rev=current(s,p);net=current_net(s,p)
  config=base/'mcp.json';config.write_text(json.dumps(dict(mode='isolated-adapter',serviceUrl=s.url.removesuffix('/api/v1'),identity=dict(owner_id='alice',session_id='a-blanket',module='blanket'),credential=s.tokens['blanket'])));config.chmod(0o600)
  env=dict(os.environ,B07_MCP_CONTEXT_FILE=str(config))
  def call(name,args):
   request=dict(jsonrpc='2.0',id=1,method='tools/call',params=dict(name=name,arguments=args))
   child=subprocess.run([str(ROOT/'.tools/node/bin/node'),'plugins/blanket/plugin/mcp/server.mjs'],input=json.dumps(request)+'\n',cwd=ROOT,env=env,capture_output=True,text=True,check=True,timeout=30)
   value=json.loads(child.stdout);assert 'error' not in value,value
   return json.loads(value['result']['content'][0]['text'])
  command=dict(operation='blanket.edit_fixed_points',parameters=dict(result_id=net['result_id'],command=dict(action='add',id='mcp-anchor',panel_key='z+',uv_mm=[45,50])))
  submitted=call('satellite_blanket_operation',command);assert set(submitted)=={'run_id'}
  completed=s.wait(submitted['run_id'],'blanket');queried=call('satellite_blanket_run',dict(run_id=submitted['run_id'],action='status'))
  assert completed==queried and queried['state']=='succeeded' and current(s,p)['id']!=rev['id']
  record=dict(status='pass',submitted=submitted,queried=queried,revision=current(s,p),result_id=current_net(s,p)['result_id'],resources_created=[str(base)],resources_cleaned=[str(base)])
 finally:
  if s:s.close()
  shutil.rmtree(base)
 (ROOT/os.environ.get('B12_EVIDENCE_DIR','docs/evidence/B12')/'mcp.json').write_text(json.dumps(record,indent=2)+'\n')
 print('Real MCP edit and run completion query passed')
if __name__=='__main__':main()
