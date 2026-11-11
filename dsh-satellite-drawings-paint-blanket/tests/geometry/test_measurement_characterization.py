import json, os, subprocess, sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture(scope='module')
def comparison(tmp_path_factory):
    directory=tmp_path_factory.mktemp('b03-characterization'); values={}
    for mode in ('source','new'):
        path=directory/f'{mode}.json'
        subprocess.run([sys.executable,'scripts/probe_b03.py',mode,str(path)],cwd=ROOT,check=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},timeout=180)
        values[mode]=json.loads(path.read_text())
    return values

def test_source_and_new_all_pairs(comparison):
    a,b=comparison['source'],comparison['new']
    assert a['pairs'].keys()==b['pairs'].keys() and len(a['pairs'])>=21
    for key,value in a['pairs'].items():
        for field,n in value.items():
            assert b['pairs'][key][field]==pytest.approx(n,rel=1e-6,abs=1e-6) if n is not None else b['pairs'][key][field] is None
    assert a['patches']==b['patches']
    assert a['inputs']==b['inputs'] and a['assemblies']==b['assemblies']

def test_external_instances_and_contact_oracles(comparison):
    r=comparison['new']
    for name,distances,areas in [('contact',[0,0,3],[36,64,None]),('instances',[12,34.31088913245493,36.72253840244148],[None]*3)]:
        for i,(distance,area) in enumerate(zip(distances,areas)):
            pair=r['pairs'][f'{name}/{i}']
            assert pair['distance_mm']==pytest.approx(distance,abs=1e-6)
            assert pair['intersection_volume_mm3']==0
            assert pair['contact_area_mm2']==pytest.approx(area) if area is not None else pair['contact_area_mm2'] is None
    assembly=r['assemblies']['instances']
    assert len({tuple(key) for key in assembly['occurrences']})==3
    assert len(set(assembly['definitions']))<3

def test_external_mixed_topology_and_real_probe(comparison):
    r=comparison['new']
    topo=r['assemblies']['solid-sheet']['topology']
    assert [(t['solid_count'],t['face_count']) for t in topo]==[(1,6),(0,1)]
    assert r['pairs']['solid-sheet/0']['distance_mm']==pytest.approx(35,abs=1e-6)
    assert r['pairs']['real-gearbox']['distance_mm']==pytest.approx(20,abs=1e-6)
    assert r['pairs']['real-gearbox']['intersection_volume_mm3']==0
