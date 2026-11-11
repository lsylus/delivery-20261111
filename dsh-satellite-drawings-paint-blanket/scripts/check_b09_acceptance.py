"""Produce inspectable DWG, revision and reference-area evidence from real workers."""
import json,tempfile,shutil
from pathlib import Path
from b09_workflow import ROOT,configured_service,exercise
def main():
 base=Path(tempfile.mkdtemp(prefix='b09-accept-',dir=ROOT/'work'));service=None
 out=ROOT/'docs/evidence/B09'
 try:
  service=configured_service(base/'backend');record=exercise(service,out/'artifacts')
  (out/'workflow.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
 finally:
  if service:service.close()
  shutil.rmtree(base)
  (out/'resources.json').write_text(json.dumps(dict(status='pass',resources_created=[str(base)],resources_cleaned=[str(base)]),indent=2)+'\n')
 print('B09 HTTP/worker/revision/real DWG checks passed; full acceptance remains separate')
if __name__=='__main__':main()
