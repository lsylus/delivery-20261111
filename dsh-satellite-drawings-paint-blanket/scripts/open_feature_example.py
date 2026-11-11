"""Open a verified feature-composite example in the private local trial."""
import argparse
import json
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('case',choices=['motor','module','cube','cylinder'])
args=parser.parse_args()
evidence=ROOT/('work/feature-composite-evidence' if args.case=='motor' else f'work/feature-composite-{args.case}-evidence')
report=json.loads((evidence/'workflow.json').read_text())
if report.get('status')!='passed':raise ValueError('This example has not completed its actual feature workflow')
state=ROOT/'work/simple-v1-trial'
session=json.loads((state/'session.json').read_text())
token=json.loads((state/'private.json').read_text())['token']
base=f'http://127.0.0.1:{session["backend_port"]}/api/v1'


def call(method,route,value=None):
    data=None if value is None else json.dumps(value).encode()
    headers={'Authorization':'Bearer '+token}
    if data is not None:headers['Content-Type']='application/json'
    with urllib.request.urlopen(urllib.request.Request(base+route,data=data,headers=headers,method=method),timeout=20) as response:
        return json.loads(response.read())


project=call('GET','/projects/'+report['project'])
head=project['module_states']['blanket']
revision=call('GET',f'/projects/{project["id"]}/revisions/{head}')
source=report['selection']['target_click']['ref']
if any(revision['model_ref'][key]!=source[key] for key in revision['model_ref']):
    raise ValueError('The example project now contains a different source model')
call('PUT','/sessions/simple-blanket/binding',dict(session_id='simple-blanket',module='blanket',
                                               project_id=project['id'],expected_revision=head))
print('Opened feature example:',args.case,'revision:',head)
