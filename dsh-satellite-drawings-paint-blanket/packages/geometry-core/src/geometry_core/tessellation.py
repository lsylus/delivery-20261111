"""Real face tessellation with revision-scoped selection; GLB is display-only."""
import json, math
import logging
from collections import Counter
from time import perf_counter
from pathlib import Path
import cadquery as cq
import numpy as np
from OCP.TopLoc import TopLoc_Location
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRep import BRep_Tool
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.OSD import OSD_Parallel, OSD_ThreadPool
from .hashing import file_sha256, digest_files
from .glb_serialization import write_glb_document, read_glb_summary
from .display_triangles import tessellate_face, triangle_payload as _triangle_payload, classify_unrenderable_face
_LOG=logging.getLogger(__name__)

def instance_id(key):
    return 'occ-' + '-'.join(map(str,key))

def validate_model_ref(ref):
    if set(ref) != {'project_id','model_id','model_revision','assembly_digest'}:
        raise ValueError('invalid ModelRef fields')
    if any(not isinstance(ref[k],str) or not ref[k] for k in ('project_id','model_id')):
        raise ValueError('invalid ModelRef identity')
    if type(ref['model_revision']) is not int or ref['model_revision']<1:
        raise ValueError('invalid model revision')
    import re
    if not isinstance(ref['assembly_digest'],str) or not re.fullmatch('[0-9a-f]{64}',ref['assembly_digest']):
        raise ValueError('invalid assembly digest')

def face_refs(shape, model_ref, occurrence):
    faces=shape.Faces(); edges=[f.Edges() for f in faces]
    # Hash by native TShape/location identity, then confirm IsSame. Unlike
    # comparing every face/edge pair, work follows actual shared edge use.
    # Orientation is intentionally ignored, as in the former IsSame loop.
    buckets={}; adjacent=[set() for _ in faces]
    for face_index, face_edges in enumerate(edges):
        for edge in face_edges:
            candidates=buckets.setdefault(edge.hashCode(),[])
            entry=next((item for item in candidates if edge.isSame(item[0])),None)
            if entry is None:
                candidates.append((edge,{face_index}))
            else:
                for other in entry[1]:
                    if other!=face_index:
                        adjacent[face_index].add(other);adjacent[other].add(face_index)
                entry[1].add(face_index)
    result=[]
    for index,face in enumerate(faces):
        kind=face.geomType()
        # CadQuery Face.Area and Face.Center both use this identical default
        # native surface integration. Reuse its mass and center together.
        properties=GProp_GProps();BRepGProp.SurfaceProperties_s(face.wrapped,properties)
        center=properties.CentreOfMass()
        adjacency=[f'face-{j+1}' for j in sorted(adjacent[index])]
        result.append({**model_ref,'instance_id':occurrence,'entity_kind':'face','entity_id':f'face-{index+1}',
                       'signature':{'type':kind,'area_mm2':properties.Mass(),'centroid_mm':[center.X(),center.Y(),center.Z()],
                                    'normal':list(face.normalAt().toTuple()) if kind=='PLANE' else None,'adjacency':adjacency}})
    return faces,result

def tessellate_with_face_map(graph, model_ref, destination: Path, *, tolerance_mm=0.1, angular_tolerance=0.1, merge_face_threshold=50000, adaptive_display=False, reuse_definition_meshes=None):
    """Millimetre display mesh with exact world-space face selection records.

    Large displays share local definition buffers through world node matrices.
    Small displays retain occurrence buffers unless explicitly opted in.

    Picking uses (node, mesh, primitive, triangle) and this exact GLB hash. Face IDs
    never persist across a model revision. Native shapes stay in this worker.
    """
    validate_model_ref(model_ref)
    if file_sha256(graph.source)!=graph.source_sha256:
        raise ValueError('source changed after graph load; reload required')
    source_files=[{'relative_path':graph.source.name,'sha256':file_sha256(graph.source),'bytes':graph.source.stat().st_size}]
    if digest_files(source_files)!=model_ref['assembly_digest']:
        raise ValueError('model digest does not match source geometry')
    if any(not math.isfinite(x) or x<=0 for x in (tolerance_mm,angular_tolerance)):
        raise ValueError('positive finite tessellation tolerances required')
    destination=Path(destination); destination.mkdir(parents=True,exist_ok=True)
    blob=bytearray(); views=[]; accessors=[]; meshes=[]; nodes=[]; entries=[]; audits=[];unrenderable=[]
    def accessor(values, component, kind, target):
        array=np.asarray(values,dtype='<f4' if component==5126 else '<u4')
        if component==5126 and not np.isfinite(array).all():
            raise ValueError('non-finite tessellation position')
        offset=len(blob); data=array.tobytes(); blob.extend(data)
        views.append({'buffer':0,'byteOffset':offset,'byteLength':len(data),'target':target})
        item={'bufferView':len(views)-1,'componentType':component,'count':len(array),'type':kind}
        if kind=='VEC3': item.update(min=array.min(axis=0).tolist(),max=array.max(axis=0).tolist())
        accessors.append(item); return len(accessors)-1
    leaves=graph.leaves
    definition_face_counts={}
    for leaf in leaves:
        label=leaf.definition_label_entry
        if label not in definition_face_counts:
            definition_face_counts[label]=len(cq.Shape.cast(graph.geometry(leaf.key).definition_shape).Faces())
    native_face_count=sum(definition_face_counts[leaf.definition_label_entry] for leaf in leaves)
    merge_primitives=native_face_count>merge_face_threshold
    large_display=adaptive_display and native_face_count>50000
    native_meshing=dict(parallel=False,thread_backend='sequential',maximum_threads=1)
    if large_display:
        tolerance_mm=max(tolerance_mm,1.0); angular_tolerance=max(angular_tolerance,0.5)
        # Workers mesh sequentially at the Python level. Bound OCCT's actual
        # native pool here, without restricting the worker's CPU affinity.
        OSD_Parallel.SetUseOcctThreads_s(True)
        pool=OSD_ThreadPool.DefaultPool_s(4)
        if pool.NbThreads()!=4:pool.Init(4)
        native_meshing=dict(parallel=True,thread_backend='occt',maximum_threads=pool.NbThreads())
    uses=Counter(leaf.definition_label_entry for leaf in leaves)
    reusable={label for label,count in uses.items() if count>1}
    share_definition_meshes=large_display if reuse_definition_meshes is None else bool(reuse_definition_meshes)
    prototypes={};prototype_meshes=0;shared_mesh_indices={}
    maximum_tolerance=tolerance_mm;maximum_angular=angular_tolerance
    first_display_error=None
    _LOG.info('STEP import display native_faces=%d leaves=%d merged_occurrence_primitives=%s',native_face_count,len(leaves),merge_primitives)
    _LOG.info('STEP import display profile=%s tolerance=%s angular=%s reusable_definitions=%d','absolute' if large_display else 'relative',tolerance_mm,angular_tolerance,len(reusable))
    for leaf_index,leaf in enumerate(leaves):
        leaf_started=perf_counter()
        label=leaf.definition_label_entry
        cached=label in prototypes
        if not cached:
            native=graph.geometry(leaf.key).world_shape
            # Cache reusable definitions in unlocated definition coordinates.
            # Child face locations remain intact; each occurrence receives its
            # own world transform, face signatures and pick ranges.
            if label in reusable:native=native.Located(TopLoc_Location())
            shape=cq.Shape.cast(native).copy()
            if large_display:
                mesher=BRepMesh_IncrementalMesh(shape.wrapped,tolerance_mm,False,angular_tolerance,True)
                if not mesher.IsDone():raise ValueError('native display mesher failed')
            else:shape.mesh(tolerance_mm,angular_tolerance)
            faces,refs=face_refs(shape,model_ref,instance_id(leaf.key))
            payloads=[]
            for face,ref in zip(faces,refs):
                try:
                    if ref['signature']['area_mm2']<0:raise ValueError('negative native face area')
                    positions,normals,collapsed,emitted,area,diagnostic=tessellate_face(face,tolerance_mm,angular_tolerance,relative=not large_display)
                except ValueError as error:
                    known_errors={'face has no triangles; refusing incomplete display map','face has no nondegenerate triangles; refusing incomplete display map','degenerate tessellation triangle','invalid native face with collapsed display triangles','invalid native face with degenerate display triangles','negative native face area'}
                    if str(error) not in known_errors:raise
                    if first_display_error is None:first_display_error=error
                    fact=classify_unrenderable_face(face) if str(error)=='face has no triangles; refusing incomplete display map' else None
                    if fact is None:
                        area=ref['signature']['area_mm2']
                        if not math.isfinite(area):raise
                        # An OCCT-valid face can still have self-intersecting
                        # discrete wires. Catalog that display failure openly;
                        # all native geometry and manufacturing checks remain.
                        poly=BRep_Tool.Triangulation_s(face.wrapped,TopLoc_Location())
                        fact=dict(reason='native_mesher_failure',failure=str(error),native_valid=bool(face.copy(mesh=False).isValid()),native_area_mm2=area,native_retained=True,source_triangles=poly.NbTriangles() if poly is not None else 0)
                        _LOG.warning('STEP face retained without display triangles instance=%s face=%s area_mm2=%.9g',instance_id(leaf.key),ref['entity_id'],area)
                    # Native area integration can return a tiny negative zero
                    # on a collapsed loop. The diagnostic keeps the raw value.
                    if ref['signature']['area_mm2']<0:
                        ref={**ref,'signature':{**ref['signature'],'area_mm2':0.}}
                    # A zero-measure source face cannot have a display triangle.
                    # Keep its native BRep and exact FaceRef in a separate,
                    # explicit catalog; never invent a selectable triangle.
                    positions=normals=None;collapsed=[];emitted=[];area=0.
                    diagnostic=dict(remeshed=False,source_triangles=fact['source_triangles'],maximum_tolerance_mm=tolerance_mm,maximum_angular_tolerance_rad=angular_tolerance,unrenderable=fact)
                maximum_tolerance=max(maximum_tolerance,diagnostic['maximum_tolerance_mm'])
                maximum_angular=max(maximum_angular,diagnostic['maximum_angular_tolerance_rad'])
                payloads.append((ref,positions,normals,collapsed,emitted,area,diagnostic))
            prototype_meshes+=1
            if label in reusable:prototypes[label]=payloads
        else:payloads=prototypes[label]
        rotation=np.asarray(leaf.world_transform.rotation);translation=np.asarray(leaf.world_transform.translation_mm)
        shared=share_definition_meshes and label in reusable
        write_mesh=not (shared and label in shared_mesh_indices)
        primitives=[]; mesh_index=shared_mesh_indices.get(label,len(meshes)) if shared else len(meshes)
        node_index=len(nodes)+1;primitive_index=0
        merged_positions=[];merged_normals=[];merged_vertex_count=0
        for template,positions,normals,collapsed,emitted,area,diagnostic in payloads:
            ref=template
            if label in reusable:
                signature=dict(template['signature'])
                signature['centroid_mm']=(np.asarray(signature['centroid_mm'])@rotation.T+translation).tolist()
                if signature['normal'] is not None:signature['normal']=(np.asarray(signature['normal'])@rotation.T).tolist()
                ref={**template,'instance_id':instance_id(leaf.key),'signature':signature}
                if positions is not None and not shared:positions=positions@rotation.T+translation;normals=normals@rotation.T
                collapsed=[{**item,'points_mm':(np.asarray(item['points_mm'])@rotation.T+translation).tolist()} for item in collapsed]
            audits.append(dict(face_ref=ref,native_area_mm2=ref['signature']['area_mm2'],display_triangle_area_mm2=area,source_triangles=diagnostic['source_triangles'],emitted_triangles=len(emitted),emitted_source_triangle_indices=emitted,collapsed_zero_area_triangles=collapsed,meshing=diagnostic))
            if positions is None:
                unrenderable.append(dict(face_ref=ref,diagnostic=diagnostic['unrenderable']))
                continue
            if merge_primitives:
                start=merged_vertex_count//3;merged_vertex_count+=len(positions)
                if write_mesh:merged_positions.append(positions);merged_normals.append(normals)
                entries.append({'node':node_index,'mesh':mesh_index,'primitive':0,'triangle_start':start,'triangle_count':len(emitted),'face_ref':ref})
            else:
                entries.append({'node':node_index,'mesh':mesh_index,'primitive':primitive_index,'triangle_start':0,'triangle_count':len(emitted),'face_ref':ref})
                primitive_index+=1
                if write_mesh:
                    pos=accessor(positions,5126,'VEC3',34962); normal=accessor(normals,5126,'VEC3',34962)
                    idx=accessor(list(range(len(positions))),5125,'SCALAR',34963)
                    primitives.append({'attributes':{'POSITION':pos,'NORMAL':normal},'indices':idx,'mode':4,'material':0})
        if merge_primitives and merged_positions:
            pos=accessor(np.concatenate(merged_positions),5126,'VEC3',34962);normal=accessor(np.concatenate(merged_normals),5126,'VEC3',34962)
            idx=accessor(np.arange(merged_vertex_count,dtype='<u4'),5125,'SCALAR',34963)
            primitives.append({'attributes':{'POSITION':pos,'NORMAL':normal},'indices':idx,'mode':4,'material':0})
        node={'name':leaf.occurrence_name or leaf.definition_name or instance_id(leaf.key),'extras':{'instance_id':instance_id(leaf.key)}}
        if shared:
            matrix=np.eye(4);matrix[:3,:3]=rotation;matrix[:3,3]=translation
            node['matrix']=matrix.flatten(order='F').tolist()
        if write_mesh:
            if primitives:
                meshes.append({'primitives':primitives});node['mesh']=mesh_index
            if shared:shared_mesh_indices[label]=mesh_index if primitives else None
        elif mesh_index is not None:node['mesh']=mesh_index
        nodes.append(node)
        uses[label]-=1
        if not uses[label]:prototypes.pop(label,None)
        if leaf_index%50==0 or perf_counter()-leaf_started>2:
            _LOG.info('STEP import mesh leaf=%d/%d mapped_faces=%d buffer_bytes=%d seconds=%.3f cached=%s',leaf_index+1,len(leaves),len(entries),len(blob),perf_counter()-leaf_started,cached)
    if not entries:
        if first_display_error is not None:raise first_display_error
        raise ValueError('face has no triangles; no renderable faces in model')
    root={'name':'CAD mm Z-up to glTF m Y-up','children':list(range(1,len(nodes)+1)),
          'matrix':[.001,0,0,0, 0,0,-.001,0, 0,.001,0,0, 0,0,0,1]}
    document={'asset':{'version':'2.0','generator':'satellite-geometry-core B02'},'scene':0,'scenes':[{'nodes':[0]}],
              'nodes':[root,*nodes],'meshes':meshes,'materials':[{'doubleSided':True,'pbrMetallicRoughness':{'baseColorFactor':[.65,.7,.8,1],'metallicFactor':0,'roughnessFactor':.8}}],
              'buffers':[{'byteLength':len(blob)}],'bufferViews':views,'accessors':accessors}
    glb=write_glb_document(document,bytes(blob),destination/'model.glb')
    read_glb_summary(glb)
    mapping={'schema_version':1,'model_ref':model_ref,'units':'mm','coordinate_system':'right-handed Z-up; GLB scene root converts to metres/Y-up',
             'glb_sha256':file_sha256(glb),'tolerance_mm':maximum_tolerance,'angular_tolerance_rad':maximum_angular,'faces':entries}
    if unrenderable:mapping['unrenderable_faces']=unrenderable
    audit=destination/'tessellation-audit.json'
    audit.write_text(json.dumps(dict(schema_version=1,model_ref=model_ref,glb_sha256=file_sha256(glb),native_faces=len(audits),mapped_faces=len(entries),unrenderable_native_faces=len(unrenderable),zero_measure_native_faces=sum(e['diagnostic']['reason']=='zero_measure_planar_face' for e in unrenderable),dropped_native_faces=0,prototype_meshes=prototype_meshes,cached_instances=len(leaves)-prototype_meshes,shared_definition_meshes=sum(index is not None for index in shared_mesh_indices.values()),glb_meshes=len(meshes),remeshed_faces=sum(fact['meshing']['remeshed'] for fact in audits),display_profile='absolute' if large_display else 'relative',native_meshing=native_meshing,tolerance_mm=maximum_tolerance,angular_tolerance_rad=maximum_angular,degenerate_threshold_mm2=1e-15,definition='All native BReps and FaceRefs are retained. Zero-measure and other faces without display triangles are explicitly catalogued as unrenderable; only rendered faces have selectable triangle ranges. Manufacturing validity checks remain separate and strict. Valid faces may be remeshed once on a private copy under the same triangle checks. Display area is not a certified coverage bound.',faces=audits),indent=2 if not large_display else None,separators=None if not large_display else (',',':'))+'\n')
    target=destination/'mesh-map.json'; target.write_text(json.dumps(mapping,indent=2 if not large_display else None,separators=None if not large_display else (',',':'))+'\n')
    return {'glb':{'path':glb.name,'sha256':file_sha256(glb),'bytes':glb.stat().st_size},
            'mesh_map':{'path':target.name,'sha256':file_sha256(target),'bytes':target.stat().st_size},'triangle_count':sum(e['triangle_count'] for e in entries)}

def resolve_face(mapping, *, model_ref, glb_sha256, node, mesh, primitive, triangle):
    if mapping['model_ref']!=model_ref or mapping['glb_sha256']!=glb_sha256:
        raise ValueError('needs_reselection: stale revision or GLB')
    if type(triangle) is not int: raise ValueError('invalid triangle')
    matches=[e for e in mapping['faces'] if (e['node'],e['mesh'],e['primitive'])==(node,mesh,primitive) and e['triangle_start']<=triangle<e['triangle_start']+e['triangle_count']]
    if len(matches)!=1: raise ValueError('needs_reselection: missing/ambiguous triangle')
    return matches[0]['face_ref']
