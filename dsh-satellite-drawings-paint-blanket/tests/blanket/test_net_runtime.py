from net_workflow import exercise

def test_real_step_worker_net_edit_rebind_failure_restore(tmp_path):
    result=exercise(tmp_path/'b11-http')
    assert result['status']=='pass' and len(result['point_ids'])==5
    assert not (tmp_path/'b11-http').exists()
