import sys,json,os,signal,copy
import time
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from b09_workflow import configured_service,generate_case,completed,head,result,exercise,signature

@pytest.fixture
def service(tmp_path):
 s=configured_service(tmp_path/'service')
 try:yield s
 finally:s.close()

def test_full_step_edit_history_restore_real_dwg(service):
 exercise(service,ROOT/'work/b09-integration')

@pytest.mark.parametrize('params',[
 {'action':'add','points':[[0,0],[1,1],[1,0],[0,1]],'reason':'x'},
 {'action':'add','points':[[0,0],[1,0],[1,1]],'reason':''},
 {'action':'move','region_id':'old','delta_mm':[float('nan'),0],'reason':'x'},
 {'action':'delete_all','reason':'x'},
])
def test_bad_command_fails_closed(service,params):
 p,rev,r=generate_case(service);params['result_id']=r['id']
 service.operation(p,rev,'paint.edit_regions',params,expected=422)
 assert head(service,p)==rev

def test_cancel_late_result_session_and_failed_edit_preserve_head(service):
 s=service;p,rev,r=generate_case(s);before=result(s,p)
 params=dict(result_id=r['id'],action='add',points=[[10000,10000],[10001,10000],[10001,10001]],reason='outside')
 bad=s.wait(s.operation(p,rev,'paint.edit_regions',params)['run_id'])
 assert bad['state']=='failed' and not bad['artifacts'] and head(s,p)==rev and result(s,p)==before
 params['points']=[[-45,25],[-35,25],[-35,35],[-45,35]]
 s.operation(p,rev,'paint.edit_regions',params,who='other_session',expected=403)
 id_=s.operation(p,rev,'paint.edit_regions',params)['run_id'];pid=s.native_pid(id_);os.kill(pid,signal.SIGSTOP)
 s.call('POST','/runs/'+id_+'/cancel',expected=202)
 assert s.wait(id_)['state']=='cancelled' and head(s,p)==rev and result(s,p)==before
 id_=s.operation(p,rev,'paint.edit_regions',params)['run_id'];pid=s.native_pid(id_);os.kill(pid,signal.SIGSTOP)
 current=s.edit(p,rev,rev['parameters']);os.kill(pid,signal.SIGCONT)
 late=s.wait(id_);assert late['state']=='succeeded' and late['checks'][0]['observed']['current'] is False and head(s,p)==current
 # An export made stale during the converter must not publish downloadable files.
 completed(s,p,current,'paint.generate',current['parameters']);source=result(s,p)
 id_=s.operation(p,current,'drawing.export',dict(result_id=source['result_id'],draft=True))['run_id'];pid=s.native_pid(id_);os.kill(pid,signal.SIGSTOP)
 newer=s.edit(p,current,current['parameters']);os.kill(pid,signal.SIGCONT)
 late=s.wait(id_);assert late['state']=='failed' and late['artifacts']==[] and head(s,p)==newer

def test_move_exclude_regenerate_and_redo_invalidation(service):
 s=service;p,rev,r=generate_case(s);initial=result(s,p)
 completed(s,p,rev,'paint.edit_regions',dict(result_id=r['id'],action='add',points=[[-45,25],[-35,25],[-35,35],[-45,35]],reason='manual'))
 rev=head(s,p);source=result(s,p);manual=next(r for r in source['paint']['regions'] if r['kind']=='manual')
 completed(s,p,rev,'paint.edit_regions',dict(result_id=source['result_id'],action='move',region_id=manual['id'],delta_mm=[2,0],reason='move'))
 rev=head(s,p);source=result(s,p)
 completed(s,p,rev,'paint.edit_regions',dict(result_id=source['result_id'],action='exclude',points=[[-43,25],[-33,25],[-33,35],[-43,35]],reason='retain paint'))
 rev=head(s,p);source=result(s,p)
 assert abs(sum(r['area_mm2'] for r in source['paint']['regions'])-sum(r['area_mm2'] for r in initial['paint']['regions']))<1e-6
 completed(s,p,rev,'paint.generate',rev['parameters']);assert signature(result(s,p)['paint'])==signature(source['paint'])
 completed(s,p,rev,'history.undo');prior=head(s,p)
 changed=s.edit(p,prior,prior['parameters']);s.operation(p,changed,'history.redo',expected=409)

def test_cancel_during_real_converter_reaps_owned_group(service):
 s=service;p,rev,r=generate_case(s)
 id_=s.operation(p,rev,'drawing.export',dict(result_id=r['id'],draft=True))['run_id'];pid=s.native_pid(id_)
 def members():
  found=[]
  for path in Path('/proc').glob('[0-9]*/stat'):
   try:
    data=path.read_text().rsplit(')',1)[1].split()
    if int(data[2])==pid and data[0]!='Z':found.append((int(path.parent.name),(path.parent/'cmdline').read_bytes()))
   except (OSError,ValueError,IndexError):pass
  return found
 deadline=time.monotonic()+30
 while time.monotonic()<deadline:
  processes=members()
  if any(b'ODAFileConverter' in cmd or b'Xvfb' in cmd for _,cmd in processes):break
  time.sleep(.1)
 else:pytest.fail('Actual converter child did not start')
 s.call('POST','/runs/'+id_+'/cancel',expected=202)
 assert s.wait(id_)['state']=='cancelled' and not members()
 assert head(s,p)==rev and result(s,p)['result_id']==r['id']
