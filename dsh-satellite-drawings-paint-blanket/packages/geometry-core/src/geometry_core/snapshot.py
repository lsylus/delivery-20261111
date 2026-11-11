"""Serializable ModelSnapshot v1 adapter; no backend/service dependencies."""
import json
import logging
from time import perf_counter
from pathlib import Path
import cadquery as cq
from .xcaf import read_xcaf_source, XcafReadOptions
from .hashing import file_sha256, digest_files
from .transforms import transform_document
from .tessellation import tessellate_with_face_map, instance_id, validate_model_ref
_LOG = logging.getLogger(__name__)

def load_model_snapshot(path: Path, *, project_id: str, model_id: str, model_revision: int, asset_id: str, output_dir: Path) -> dict:
    path=Path(path).resolve(); output=Path(output_dir).resolve()
    if not isinstance(asset_id,str) or not asset_id: raise ValueError('asset_id is required')
    files=[{'relative_path':path.name,'sha256':file_sha256(path),'bytes':path.stat().st_size}]
    digest=digest_files(files)
    ref={'project_id':project_id,'model_id':model_id,'model_revision':model_revision,'assembly_digest':digest}
    validate_model_ref(ref)
    graph=read_xcaf_source(path,options=XcafReadOptions(read_colors=False,read_layers=False,read_metadata=False))
    started=perf_counter()
    _LOG.info('STEP import definition BRep export start nodes=%d',len(graph.nodes))
    output.mkdir(parents=True,exist_ok=True)
    definitions=[]; by_label={}
    for node in graph.nodes:
        label=node.definition_label_entry
        if label in by_label: continue
        id_=f'def-{len(definitions)+1}'; by_label[label]=id_
        relative=f'shapes/{id_}.brep'; target=output/relative; target.parent.mkdir(exist_ok=True)
        if not cq.Shape.cast(graph.geometry(node.key).definition_shape).exportBrep(str(target)):
            raise RuntimeError('BRep export failed')
        definitions.append({'id':id_,'shape_asset':relative})
    _LOG.info('STEP import definition BRep export done seconds=%.3f definitions=%d',perf_counter()-started,len(definitions))
    # C01 records source units, while all loaded coordinates and BRep assets are mm.
    units=graph.source_length_units
    known={'millimetre':'mm','millimeter':'mm','metre':'m','meter':'m','inch':'inch'}
    source_units=known.get(units[0].lower()) if len(units)==1 else None
    snapshot={'schema_version':1,'model_ref':ref,'units':'mm',
              'source_manifest':{'schema_version':1,'asset_id':asset_id,'main_file':path.name,'files':files,'assembly_digest':digest,'detected_format':'STEP','vendor':None,'vendor_version':None,'units':source_units,'load_status':'complete','missing_refs':[],'conversion_evidence':[]},
              'definitions':definitions,'instances':[{'instance_id':instance_id(n.key),'definition_id':by_label[n.definition_label_entry],'parent_instance_id':instance_id(n.parent_key) if n.parent_key else None,'name':n.occurrence_name or n.definition_name or instance_id(n.key),'local_transform':transform_document(n.local_transform),'world_transform':transform_document(n.world_transform)} for n in graph.nodes],
              'mesh_map_asset':'mesh-map.json'}
    # Staging remains unpublished until every mesh and worker result succeeds.
    # Keep the native assembly checkpoint if a later display stage fails.
    (output/'snapshot.json').write_text(json.dumps(snapshot,indent=2)+'\n')
    started=perf_counter()
    _LOG.info('STEP import tessellation start leaves=%d',len(graph.leaves))
    tessellate_with_face_map(graph,ref,output,adaptive_display=True)
    _LOG.info('STEP import tessellation done seconds=%.3f',perf_counter()-started)
    return snapshot
