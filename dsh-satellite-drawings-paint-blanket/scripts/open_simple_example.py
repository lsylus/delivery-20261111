"""Open a previously verified example in the local trial session."""
import argparse
import json
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('case',choices=['cube','cylinder','cube-cylinder'])
args=parser.parse_args()
state=ROOT/'work/simple-v1-trial'
session=json.loads((state/'session.json').read_text())
token=json.loads((state/'private.json').read_text())['token']
case=json.loads((ROOT/'work/simple-v1-evidence/final'/f'{args.case}.json').read_text())
base=f'http://127.0.0.1:{session["backend_port"]}/api/v1'
def call(method,path,value=None):
    headers={'Authorization':'Bearer '+token}
    data=None
    if value is not None:
        data=json.dumps(value).encode();headers['Content-Type']='application/json'
    with urllib.request.urlopen(urllib.request.Request(base+path,data=data,method=method,headers=headers),timeout=20) as response:
        return json.loads(response.read())
project=call('GET','/projects/'+case['project'])
call('PUT','/sessions/simple-blanket/binding',dict(session_id='simple-blanket',module='blanket',project_id=project['id'],expected_revision=project['module_states']['blanket']))
print('Opened verified example:',args.case)
