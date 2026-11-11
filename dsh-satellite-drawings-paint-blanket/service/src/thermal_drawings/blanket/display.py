"""CadQuery GLB is Y-up but retains millimetres; normalize to B02 glTF metres."""
import struct
from geometry_core.glb_serialization import read_glb,write_glb_document


def normalize(path,panels):
    raw=path.read_bytes();document=read_glb(path).document
    offset=12;binary=None
    while offset<len(raw):
        length,kind=struct.unpack_from('<I4s',raw,offset);offset+=8
        if kind==b'BIN\x00':binary=raw[offset:offset+length]
        offset+=length
    if binary is None:
        raise ValueError('Missing native GLB mesh buffer')
    for node in document['nodes']:
        matches=[p['id'] for p in panels if node.get('name')==p['id'].replace(':','_')]
        if matches:node['extras']={'panel_id':matches[0]}
    for scene in document['scenes']:
        root=len(document['nodes'])
        document['nodes'].append(dict(name='B10 mm to glTF metres',scale=[.001,.001,.001],children=scene['nodes']))
        scene['nodes']=[root]
    write_glb_document(document,binary,path)
