import json
import pytest
from workflow import Service,exercise,setup,run,result,current


def test_real_step_http_save_restore_restart_and_failure_preservation(tmp_path):
    assert exercise(tmp_path/'runtime')['status']=='pass'


def test_failed_reconstruction_preserves_current_revision(tmp_path):
    service=Service(tmp_path/'runtime')
    try:
        p,rev,_,_=setup(service);generated=run(service,p,rev,'blanket.generate',rev['parameters'])
        saved=run(service,p,rev,'engineering.save')
        artifact=next(a for a in saved['artifacts'] if a['role']=='engineering_bundle')
        geometry=next(a for a in generated['artifacts'] if a['relative_storage_path'].endswith('/baseline.brep'))
        (service.data/geometry['relative_storage_path']).write_bytes(b'corrupt')
        failed=service.wait(service.operation(p,rev,'engineering.restore',dict(artifact_id=artifact['id']),who='blanket')['run_id'],'blanket')
        assert failed['state']=='failed' and failed['artifacts']==[]
        assert current(service,p)['id']==rev['id']
    finally:service.close()


def test_parameter_change_invalidates_result_and_save_until_regenerated(tmp_path):
    service=Service(tmp_path/'runtime')
    try:
        p,rev,_,_=setup(service);run(service,p,rev,'blanket.generate',rev['parameters']);before=result(service,p)
        params=dict(rev['parameters'],dimensions_mm=[110,100,100])
        newer=service.edit(p,rev,params,who='blanket')
        assert result(service,p) is None
        service.operation(p,newer,'engineering.save',who='blanket',expected=409)
        run(service,p,newer,'blanket.generate',params)
        assert result(service,p)['blanket']['baseline']==before['blanket']['baseline']
    finally:service.close()


def test_edit_cancellation_and_late_publication_never_move_current_head(tmp_path):
    import os,signal
    service=Service(tmp_path/'runtime')
    try:
        p,rev,_,_=setup(service);run(service,p,rev,'blanket.generate',rev['parameters']);source=result(service,p)
        command=dict(result_id=source['result_id'],baseline_id=source['blanket']['baseline']['id'],dimensions_mm=[110,100,100])
        id_=service.operation(p,rev,'blanket.edit_shape',command,who='blanket',key='cancel')['run_id']
        assert service.operation(p,rev,'blanket.edit_shape',command,who='blanket',key='cancel')['run_id']==id_
        pid=service.native_pid(id_);os.kill(pid,signal.SIGSTOP)
        service.call('POST','/runs/'+id_+'/cancel',who='blanket',expected=202)
        cancelled=service.wait(id_,'blanket')
        assert cancelled['state']=='cancelled' and cancelled['artifacts']==[]
        assert not os.path.exists('/proc/'+str(pid)) and current(service,p)['id']==rev['id']
        id_=service.operation(p,rev,'blanket.edit_shape',command,who='blanket')['run_id']
        pid=service.native_pid(id_);os.kill(pid,signal.SIGSTOP)
        newer=service.edit(p,rev,dict(rev['parameters'],dimensions_mm=[100,100,110]),who='blanket')
        os.kill(pid,signal.SIGCONT);late=service.wait(id_,'blanket')
        assert late['state']=='succeeded' and late['checks'][0]['observed']['current'] is False
        assert current(service,p)['id']==newer['id'] and result(service,p) is None
    finally:service.close()


def test_out_of_scope_input_returns_explicit_worker_diagnostic(tmp_path):
    service=Service(tmp_path/'runtime')
    try:
        p,rev,_,_=setup(service)
        params=dict(rev['parameters'],unfold_base_panel='not-yet-supported')
        newer=service.edit(p,rev,params,who='blanket')
        failed=service.wait(service.operation(p,newer,'blanket.generate',params,who='blanket')['run_id'],'blanket')
        assert failed['state']=='failed' and not failed['artifacts']
        assert 'unsupported_B11_B13' in failed['error']['message']
        assert current(service,p)['id']==newer['id']
    finally:service.close()
