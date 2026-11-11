"""Run source/new characterization in separate processes. Source imports are test-only."""
import argparse, dataclasses, importlib, json, sys
from pathlib import Path
import cadquery as cq

def facts(mode,path):
    if mode=='source':
        sys.dont_write_bytecode=True
        sys.path.insert(0,'/data/qmh/satellite-plugins-20261029/microservice-refactor-shared-core/cad-assembly')
        prefix='backend.geometry.'; module='xcaf_source'; serial='step_serialization'
    else: prefix='geometry_core.'; module='xcaf'; serial='serialization'
    xcaf=importlib.import_module(prefix+module)
    topology=importlib.import_module(prefix+'topology')
    bounds=importlib.import_module(prefix+'bounds')
    graph=xcaf.read_xcaf_source(path)
    nodes=[]
    for n in graph.nodes:
        shape=graph.geometry(n.key).world_shape
        nodes.append({'key':n.key,'parent':n.parent_key,'children':n.child_keys,'occurrence_name':n.occurrence_name,'definition_name':n.definition_name,'definition':n.definition_label_entry,'local':dataclasses.asdict(n.local_transform),'world':dataclasses.asdict(n.world_transform),'topology':dataclasses.asdict(topology.measure_shape_topology(shape)),'volume':sum(s.Volume() for s in cq.Shape.cast(shape).Solids()),'bounds':bounds.measure_shape_bounds(shape,strategy=bounds.BoundsStrategy.OPTIMAL_WITHOUT_SHAPE_TOLERANCE).values})
    return {'roots':graph.root_keys,'nodes':nodes,'step':dataclasses.asdict(importlib.import_module(prefix+serial).read_step_summary(path))}
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('mode',choices=['source','new']);p.add_argument('input',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(facts(a.mode,a.input),indent=2)+'\n')
