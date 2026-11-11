import pytest
from http_harness import Service, ROOT


@pytest.fixture
def service(tmp_path):
    s = Service(tmp_path / 'service')
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def imported(service):
    return service.imported()
