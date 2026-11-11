"""Packed MCP submits the same bounded command and queries real completion."""
import os,json,subprocess,tempfile,shutil
from pathlib import Path
from b09_workflow import ROOT,configured_service,generate_case,head,result
def main():
 base=Path(tempfile.mkdtemp(prefix='b09-mcp-',dir=ROOT/'work'));s=None
 try:
  s=configured_service(base/'backend');p,rev,run=generate_case(s)
  config=base/'mcp.json';config.write_text(json.dumps(dict(mode='isolated-adapter',serviceUrl=s.url.removesuffix('/api/v1'),identity=dict(owner_id='alice',session_id='a-session',module='paint'),credential=s.tokens['alice'])));config.chmod(0o600)
  env=dict(os.environ,B07_MCP_CONTEXT_FILE=str(config))
  def call(name,args):
   request=dict(jsonrpc='2.0',id=1,method='tools/call',params=dict(name=name,arguments=args))
   child=subprocess.run([str(ROOT/'.tools/node/bin/node'),'plugins/paint/plugin/mcp/server.mjs'],input=json.dumps(request)+'\n',cwd=ROOT,env=env,capture_output=True,text=True,check=True,timeout=30)
   value=json.loads(child.stdout);assert 'error' not in value,value
   return json.loads(value['result']['content'][0]['text'])
  command=dict(operation='paint.edit_regions',parameters=dict(result_id=run['id'],action='add',points=[[-45,25],[-35,25],[-35,35],[-45,35]],reason='MCP bounded chat command'))
  submitted=call('satellite_paint_operation',command);assert set(submitted)=={'run_id'}
  completed=s.wait(submitted['run_id']);queried=call('satellite_paint_run',dict(run_id=submitted['run_id'],action='status'))
  assert completed==queried and queried['state']=='succeeded' and head(s,p)['id']!=rev['id']
  record=dict(status='pass',submitted=submitted,queried=queried,revision=head(s,p),result_id=result(s,p)['result_id'],resources_created=[str(base)],resources_cleaned=[str(base)])
 finally:
  if s:s.close()
  shutil.rmtree(base)
 (ROOT/'docs/evidence/B09/mcp.json').write_text(json.dumps(record,indent=2)+'\n')
 print('Real MCP edit and run completion query passed')
if __name__=='__main__':main()
