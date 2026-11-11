from http_case import Service,exercise


def test_real_http_brep_worker_versions_drafts_failure_and_restart(tmp_path):
    service=Service(tmp_path/'service',timeout=120)
    try:
        record,files=exercise(service)
        assert record['status']=='pass' and set(files)=={'paint-result.json','drawing.json'}
    finally:
        service.close()
