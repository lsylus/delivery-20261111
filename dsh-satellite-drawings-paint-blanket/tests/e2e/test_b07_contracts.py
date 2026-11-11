"""B07 contract assertions use current model evidence; no demo qualifies as live."""
from pathlib import Path
import json,subprocess,sys
import pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from contracts import validate

def node(code):
    return subprocess.check_output([str(ROOT/'.tools/node/bin/node'),'--input-type=module','-e',code],cwd=ROOT,text=True)

def test_fixture_is_real_drawing_contract_with_exact_faces(tmp_path):
    subprocess.run([str(ROOT/'.tools/node/bin/node'),'--input-type=module','-e',"import {build} from 'esbuild';await build({entryPoints:['packages/workbench-common/src/fixture.ts'],outfile:'work/b07-fixture.mjs',bundle:true,platform:'node',format:'esm'});"],cwd=ROOT,check=True)
    code="import fs from 'node:fs';import {drawingFixture} from './work/b07-fixture.mjs';const map=JSON.parse(fs.readFileSync('docs/evidence/B06/artifacts/mesh-map.json'));console.log(JSON.stringify(drawingFixture({map,revision:{id:'b07-fixture-revision'}})));"
    fixture=json.loads(node(code));validate('drawing',fixture)
    refs=json.loads((ROOT/'docs/evidence/B06/artifacts/mesh-map.json').read_text())['faces']
    assert fixture['source_links']==[f['face_ref'] for f in refs]
    assert all(e['source_refs']==[refs[i]['face_ref']] for i,e in enumerate(fixture['entities']))
    (ROOT/'docs/evidence/B07/drawing-fixture.json').write_text(json.dumps(fixture,indent=2)+'\n')

@pytest.mark.parametrize('module',['paint','blanket'])
def test_built_plugin_is_self_contained(module):
    root=ROOT/'plugins'/module/'plugin'
    p=json.loads((root/'package.json').read_text())
    assert p['name']==f'@satellite-drawings/{module}-plugin'
    for name in ['lib/index.mjs','lib/client.js','lib/mcp.mjs','public/index.html','public/app.js','mcp/server.mjs','cordis.patch.yml']:
        assert (root/name).is_file()
    for name in ['lib/index.mjs','lib/client.js','lib/mcp.mjs']:
        assert '../../../../packages/' not in (root/name).read_text()
    for name in ['lib/client.js','public/app.js']:
        text=(root/name).read_text()
        assert 'backendCredential' not in text and 'Bearer ' not in text and 'dsh-tools' not in text

def test_draft_dimensions_and_revision_guard():
    code="import {build} from 'esbuild';await build({entryPoints:['packages/workbench-common/src/state.ts'],outfile:'work/b07-state.mjs',bundle:true,platform:'node',format:'esm'});"
    node(code)
    result=json.loads(node("import {draftKey,readDraft} from './work/b07-state.mjs';const id={owner_id:'a',session_id:'s',module:'paint'};const keys=[draftKey(id,'p'),draftKey({...id,owner_id:'b'},'p'),draftKey({...id,session_id:'t'},'p'),draftKey({...id,module:'blanket'},'p'),draftKey(id,'q')];console.log(JSON.stringify({keys,stale:readDraft({getItem:()=>JSON.stringify({revision:'old',annotation:'secret'})},id,'p','new')}));"))
    assert len(set(result['keys']))==5 and result['stale'] is None

def test_required_dependency_evidence_and_dwg_boundary():
    for batch in ['B06','B08']:
        s=json.loads((ROOT/f'docs/evidence/{batch}/summary.json').read_text())
        assert s['status']=='passed' and not s['dirty'] and s['tests']['required']==s['tests']['passed']>0
    assert json.loads((ROOT/'docs/evidence/B04/summary.json').read_text())['status']=='blocked'
    assert '**FAIL**' in (ROOT/'docs/reviews/B04.md').read_text()
