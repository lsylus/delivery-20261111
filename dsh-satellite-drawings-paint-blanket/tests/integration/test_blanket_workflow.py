import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from b12_workflow import exercise

def test_blanket_real_http_document_history_bundle_and_dwg(tmp_path):
    assert exercise(tmp_path/'service',tmp_path/'artifacts')['status']=='pass'


def test_blanket_cancel_late_annotation_and_stale_export_preserve_head(tmp_path):
    import os,signal
    from b12_workflow import configured,setup,current,result,run,current_net
    s=configured(tmp_path/'service')
    try:
        p,rev,_,_=setup(s);run(s,p,rev,'blanket.generate',rev['parameters']);run(s,p,current(s,p),'blanket.unfold',{'result_id':result(s,p)['result_id']});rev=current(s,p);before=current_net(s,p)
        params=dict(result_id=before['result_id'],annotation_id='late',text='late note',position=[5,5])
        id_=s.operation(p,rev,'drawing.edit_annotation',params,who='blanket')['run_id'];pid=s.native_pid(id_);os.kill(pid,signal.SIGSTOP)
        s.call('POST','/runs/'+id_+'/cancel',who='blanket',expected=202);assert s.wait(id_,'blanket')['state']=='cancelled' and current(s,p)==rev and current_net(s,p)==before
        id_=s.operation(p,rev,'drawing.edit_annotation',params,who='blanket')['run_id'];pid=s.native_pid(id_);os.kill(pid,signal.SIGSTOP)
        run(s,p,rev,'history.undo');older=current(s,p);os.kill(pid,signal.SIGCONT);late=s.wait(id_,'blanket');assert late['state']=='succeeded' and late['checks'][0]['observed']['current'] is False and current(s,p)==older
        run(s,p,older,'history.redo');assert current_net(s,p)==before
        id_=s.operation(p,rev,'drawing.export',dict(result_id=before['result_id'],draft=True),who='blanket')['run_id'];pid=s.native_pid(id_);os.kill(pid,signal.SIGSTOP)
        run(s,p,rev,'history.undo');older=current(s,p);os.kill(pid,signal.SIGCONT);late=s.wait(id_,'blanket');assert late['state']=='failed' and late['artifacts']==[] and current(s,p)==older
    finally:s.close()
