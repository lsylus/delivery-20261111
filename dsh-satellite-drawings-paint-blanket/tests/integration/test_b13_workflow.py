from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from b13_workflow import exercise
def test_actual_complex_http_bundle_unique_and_ambiguous_rebinding(tmp_path):
 import os
 archive=ROOT/os.environ['B13_EVIDENCE_DIR']/'http' if 'B13_EVIDENCE_DIR' in os.environ else None
 assert exercise(tmp_path/'b13-service',archive)['status']=='pass'
