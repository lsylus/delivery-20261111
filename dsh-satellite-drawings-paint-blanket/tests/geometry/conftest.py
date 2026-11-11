import sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
@pytest.fixture
def fixtures(): return ROOT/'fixtures/synthetic'
@pytest.fixture
def graph(fixtures):
    from geometry_core.xcaf import read_xcaf_source
    return read_xcaf_source(fixtures/'assembly-tree.step')
@pytest.fixture
def model_ref(graph):
    from geometry_core.hashing import digest_files, file_sha256
    return dict(project_id='p1',model_id='m1',model_revision=1,assembly_digest=digest_files([dict(relative_path=graph.source.name,sha256=file_sha256(graph.source),bytes=graph.source.stat().st_size)]))
