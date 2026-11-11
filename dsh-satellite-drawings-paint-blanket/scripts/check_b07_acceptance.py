from pathlib import Path
import json,sys,hashlib,platform,subprocess
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evidence/B07'
browser=json.loads((OUT/'browser-acceptance.json').read_text())
assert browser['status']=='pass' and browser['counts']==dict(passed=7,failed=0,skipped=0)
assert len(browser['commands'])==3 and all(c['exit_code']==0 for c in browser['commands'])
assert browser['resources_created']==browser['resources_cleaned']
records=[]
for spec in ['workspace-isolation','model-selection','live-failure']:
    record=json.loads((OUT/(spec+'-live-inputs.json')).read_text())
    assert record['status']=='pass' and record['formal_host']=='not_configured'
    for p in record['packages']:
        assert hashlib.sha256((OUT/'packages'/(p['module']+'.tgz')).read_bytes()).hexdigest()==p['sha256']
    assert {w['key'] for w in record['workspaces']}=={'satellite-paint','satellite-blanket'}
    for who,input_ in record['inputs'].items():
        assert input_['asset']['sha256']==hashlib.sha256((ROOT/'fixtures/synthetic/assembly-tree.step').read_bytes()).hexdigest()
        for a in input_['downloaded']:
            p=OUT/(spec+'-artifacts')/who/Path(a['path']).name
            assert hashlib.sha256(p.read_bytes()).hexdigest()==a['sha256'] and p.stat().st_size==a['bytes']
    mcp=json.loads((OUT/(spec+'-mcp.json')).read_text());assert mcp['status']=='pass' and len(mcp['records'])==2
    api=[json.loads(line) for line in (OUT/(spec+'-api.jsonl')).read_text().splitlines()]
    assert any('/models/' in r['path'] and r['status']==200 for r in api)
    records.append(dict(spec=spec,requests=len(api),status='pass'))
assert any(r['status']==502 for r in api)
for name in ['selection-flow','annotation-context']:assert json.loads((OUT/(name+'.json')).read_text())['status']=='pass'
for name in ['real-face-selection','fixture-selection','browser-step-import','two-plugin-host','draft-isolation','service-failure']:
    raw=(OUT/(name+'.png')).read_bytes();assert raw.startswith(b'\x89PNG\r\n\x1a\n') and len(raw)>10000
environment=dict(status='pass',python=sys.version,platform=platform.platform(),node=subprocess.check_output([str(ROOT/'.tools/node/bin/node'),'--version'],text=True).strip(),playwright='1.58.2',chromium='145.0.7632.6',host_mode='isolated-adapter',formal_host='not_configured')
(OUT/'environment.json').write_text(json.dumps(environment,indent=2)+'\n')
(OUT/'acceptance.json').write_text(json.dumps(dict(status='pass',scope='isolated-adapter with real B06 HTTP, never demo; production host gate separate',browser=browser['counts'],specs=records,resources_created=browser['resources_created'],resources_cleaned=browser['resources_cleaned']),indent=2)+'\n')
(OUT/'formal-host.json').write_text(json.dumps(dict(status='blocked',code='formal_host_identity_not_configured',attempts=['Read B06 project-runtime ADR and independent review: issuer/audience/signature/key-discovery/revocation contract unavailable','Loaded both packed server and client entrypoints in isolated host; tested per-request server-authorized owner/session/module mapping','Missing identity resolver tested: HTTP 503; MCP without private operator context explicitly unavailable'],missing=['Authorized real host identity assertion protocol and subject-to-owner mapping','Real host session lifecycle/revocation verification in authorized profile'],impact='Only isolated-adapter integration accepted; no production-host acceptance or deployment. B07 remains blocked, not completed.',boundary='B04 blocked/FAIL; final AutoCAD open/edit/save/reopen required; no platform-global or old-plugin modifications'),indent=2)+'\n')
print('B07 isolated acceptance PASS; formal host identity gate BLOCKED')
