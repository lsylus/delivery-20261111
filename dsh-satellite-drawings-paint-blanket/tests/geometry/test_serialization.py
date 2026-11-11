import json, struct
from pathlib import Path
import cadquery as cq
import pytest
from geometry_core.serialization import read_step,inspect_step,write_step_graph,write_step_shape,StepReadError
from geometry_core.xcaf import read_xcaf_source,XcafReadError
from geometry_core.glb_serialization import read_glb,GlbReadError

def test_step_document_readback_covers_all_instances(graph,tmp_path):
    out=write_step_graph(graph,tmp_path/'all.step')
    back=read_xcaf_source(out)
    assert len(back.root_keys)==2 and len(back.nodes)==5 and len(back.leaves)==3
    assert [(n.occurrence_name,n.definition_name) for n in back.nodes]==[(n.occurrence_name,n.definition_name) for n in graph.nodes]
    for left,right in zip(graph.nodes,back.nodes):
        assert right.world_transform.translation_mm==pytest.approx(left.world_transform.translation_mm,abs=1e-6)
        for a,b in zip(left.world_transform.rotation,right.world_transform.rotation):assert a==pytest.approx(b,abs=1e-9)
    facts=read_step(out).readback
    assert facts.completed and facts.topology.valid
    assert (facts.topology.solid_count,facts.topology.shell_count,facts.topology.face_count,facts.topology.non_solid_face_count)==(3,4,19,1)
    assert facts.volume_mm3==pytest.approx(12000.06,rel=1e-6)
    with pytest.raises(ValueError):write_step_graph(graph,graph.source)

def test_world_compound_does_not_collapse_repeated_definitions(graph,tmp_path):
    shapes=[cq.Shape.cast(graph.geometry(n.key).world_shape) for n in graph.leaves]
    out=write_step_shape(cq.Compound.makeCompound(shapes),tmp_path/'world.step')
    assert read_step(out).readback.volume_mm3==pytest.approx(12000.06,rel=1e-6)
    assert read_step(out).readback.topology.solid_count==3

@pytest.mark.parametrize('kind',['missing','empty','garbage','truncated','external'])
def test_bad_step_fails_explicitly(fixtures,tmp_path,kind):
    p=tmp_path/f'{kind}.step'
    if kind=='empty':p.write_bytes(b'')
    elif kind=='garbage':p.write_bytes(b'ISO-10303-21;\nBOGUS;\nEND-ISO-10303-21;')
    elif kind=='truncated':p.write_bytes((fixtures/'assembly-tree.step').read_bytes()[:-80])
    elif kind=='external':p.write_bytes(b"ISO-10303-21;\n#1=DOCUMENT_FILE('file:///etc/passwd');\nEND-ISO-10303-21;")
    with pytest.raises((StepReadError,XcafReadError)):read_xcaf_source(p)
    with pytest.raises(StepReadError):read_step(p)
    assert inspect_step(p)['completed'] is False

@pytest.mark.parametrize('data',[b'',b'junk',struct.pack('<4sII',b'glTF',2,999),struct.pack('<4sII',b'glTF',1,12)])
def test_corrupt_glb_rejected(tmp_path,data):
    p=tmp_path/'bad.glb';p.write_bytes(data)
    with pytest.raises(GlbReadError):read_glb(p)
