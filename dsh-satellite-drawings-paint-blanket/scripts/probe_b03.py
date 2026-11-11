"""Characterization process. Never imports legacy services or writes source pyc."""
import argparse, dataclasses, hashlib, importlib, itertools, json, sys
from pathlib import Path
import cadquery as cq
from b03_cases import CAD, PARAMETERS, analytic_pairs, patch_cases, external_inputs

def probe(mode):
    if mode=='source':
        sys.dont_write_bytecode=True
        sys.path.insert(0,str(CAD))
        prefix='backend.geometry.'; reader='xcaf_source'
    else: prefix='geometry_core.'; reader='xcaf'
    m=importlib.import_module(prefix+'solid_pairs')
    xcaf=importlib.import_module(prefix+reader)
    topology=importlib.import_module(prefix+'topology')
    def measure(a,b):
        r=m.measure_shape_pair(a,b,**PARAMETERS)
        return {k:getattr(r,k) for k in ('distance_mm','intersection_volume_mm3','contact_area_mm2')}
    out={'pairs':{},'patches':{},'inputs':[],'assemblies':{}}
    for name,a,b,oracle in analytic_pairs(): out['pairs'][name]=measure(a,b)
    for name,a,b,oracle in patch_cases():
        for fuzzy in (None,1e-7):
            r=m.intersect_face_patches(a,b,fuzzy_tolerance_mm=fuzzy)
            out['patches'][f'{name}/{fuzzy}']={'completed':r.completed,'areas':sorted(abs(f.Area()) for f in r.patches)}
    for name,path in external_inputs().items():
        data=path.read_bytes()  # Required inputs cannot skip.
        out['inputs'].append(dict(path=str(path),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)))
        g=xcaf.read_xcaf_source(path)
        shapes=[cq.Shape.cast(g.geometry(n.key).world_shape) for n in g.leaves]
        out['assemblies'][name]={'occurrences':[n.key for n in g.leaves], 'definitions':[n.definition_label_entry for n in g.leaves], 'topology':[dataclasses.asdict(topology.measure_shape_topology(s)) for s in shapes]}
        if name=='real-gearbox':
            out['pairs'][name]=measure(shapes[0],shapes[0].translate((200,0,0)))
        else:
            for i,((a,b),(sa,sb)) in enumerate(zip(itertools.combinations(g.leaves,2),itertools.combinations(shapes,2),strict=True)):
                out['pairs'][f'{name}/{i}']=measure(sa,sb)
    if mode=='new':
        assert not any(name=='backend' or name.startswith('backend.') for name in sys.modules)
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['source','new']);p.add_argument('output',type=Path);a=p.parse_args()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(probe(a.mode),indent=2)+'\n')
