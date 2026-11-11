import subprocess,sys
from pathlib import Path
r=Path(__file__).resolve().parents[1]
script='scripts/run_b12_browser.py' if 'tests/e2e/blanket-workflow.spec.ts' in sys.argv else 'scripts/run_b07_browser.py'
raise SystemExit(subprocess.call([sys.executable,script,*sys.argv[1:]],cwd=r))
