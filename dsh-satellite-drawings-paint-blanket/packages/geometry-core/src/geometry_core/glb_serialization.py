"""Policy-neutral GLB container writing and parser readback facts."""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

from geometry_core.hashing import file_sha256


_HEADER = struct.Struct("<4sII")
_CHUNK_HEADER = struct.Struct("<I4s")
_JSON_CHUNK = b"JSON"
_BIN_CHUNK = b"BIN\x00"
_TRIANGLES = 4


class GlbReadError(ValueError):
    """A GLB file is missing or structurally invalid."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class GlbChunk:
    """One GLB chunk header fact."""

    kind: str
    byte_count: int


@dataclass(frozen=True, slots=True)
class GlbReadback:
    """Immutable GLB container and display facts without service policy."""

    byte_count: int
    sha256: str
    version: int
    generator: str | None
    chunks: tuple[GlbChunk, ...]
    scene_count: int
    node_count: int
    mesh_count: int
    primitive_count: int
    material_count: int
    accessor_count: int
    position_accessor_count: int
    index_accessor_count: int
    triangle_count: int
    has_normals: bool
    has_embedded_binary: bool
    node_names: tuple[str, ...]
    component_ids: tuple[str, ...]
    prototype_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GlbReadResult:
    """A parsed JSON document and its immutable neutral readback summary."""

    document: dict = field(repr=False, compare=False)
    readback: GlbReadback


def _fail(path: Path, code: str, detail: str) -> GlbReadError:
    return GlbReadError(f"invalid GLB {path.name}: {detail}", code=code)


def _items(document: dict, name: str, path: Path) -> list:
    value = document.get(name, [])
    if not isinstance(value, list):
        raise _fail(path, "invalid_json", f"{name} must be an array")
    return value


def _accessor_count(accessors: list, index, path: Path) -> int:
    if not isinstance(index, int) or index < 0 or index >= len(accessors):
        raise _fail(path, "invalid_json", "primitive references an invalid accessor")
    accessor = accessors[index]
    if not isinstance(accessor, dict):
        raise _fail(path, "invalid_json", "accessor must be an object")
    count = accessor.get("count")
    if not isinstance(count, int) or count < 0:
        raise _fail(path, "invalid_json", "accessor count must be non-negative")
    return count


def read_glb(path: Path) -> GlbReadResult:
    """Parse one GLB v2 file and return its document plus neutral facts."""
    source = path.resolve()
    if not source.is_file() or source.stat().st_size <= 0:
        raise GlbReadError(
            f"GLB file is missing or empty: {source}", code="missing_or_empty"
        )
    raw = source.read_bytes()
    if len(raw) < _HEADER.size:
        raise _fail(source, "truncated_header", "header is truncated")
    magic, version, declared_length = _HEADER.unpack_from(raw)
    if magic != b"glTF":
        raise _fail(source, "invalid_header", "magic is not glTF")
    if version != 2:
        raise _fail(source, "invalid_header", f"unsupported version {version}")
    if declared_length != len(raw):
        raise _fail(source, "invalid_header", "declared length does not match file")

    offset = _HEADER.size
    chunks = []
    json_payload = None
    binary_payload = None
    while offset < len(raw):
        if offset + _CHUNK_HEADER.size > len(raw):
            raise _fail(source, "invalid_chunk", "chunk header is truncated")
        byte_count, kind = _CHUNK_HEADER.unpack_from(raw, offset)
        offset += _CHUNK_HEADER.size
        end = offset + byte_count
        if byte_count % 4 or end > len(raw):
            raise _fail(source, "invalid_chunk", "chunk size is invalid")
        payload = raw[offset:end]
        chunks.append(GlbChunk(kind=kind.decode("latin-1"), byte_count=byte_count))
        if kind == _JSON_CHUNK:
            if json_payload is not None:
                raise _fail(source, "invalid_json", "multiple JSON chunks")
            json_payload = payload
        elif kind == _BIN_CHUNK and binary_payload is None:
            binary_payload = payload
        offset = end

    if not chunks or chunks[0].kind != "JSON" or json_payload is None:
        raise _fail(source, "invalid_json", "first chunk must be JSON")
    try:
        document = json.loads(json_payload.rstrip(b" \x00"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _fail(source, "invalid_json", "JSON payload cannot be decoded") from exc
    if not isinstance(document, dict):
        raise _fail(source, "invalid_json", "JSON document must be an object")
    asset = document.get("asset")
    if not isinstance(asset, dict) or str(asset.get("version")) != "2.0":
        raise _fail(source, "invalid_json", "asset.version must be 2.0")

    buffers = _items(document, "buffers", source)
    if buffers and binary_payload is not None:
        first_buffer = buffers[0]
        if not isinstance(first_buffer, dict):
            raise _fail(source, "invalid_json", "buffer must be an object")
        declared_buffer_length = first_buffer.get("byteLength")
        if (
            not isinstance(declared_buffer_length, int)
            or declared_buffer_length < 0
            or declared_buffer_length > len(binary_payload)
            or len(binary_payload) - declared_buffer_length > 3
        ):
            raise _fail(source, "invalid_chunk", "BIN chunk length is inconsistent")

    scenes = _items(document, "scenes", source)
    nodes = _items(document, "nodes", source)
    meshes = _items(document, "meshes", source)
    materials = _items(document, "materials", source)
    accessors = _items(document, "accessors", source)
    primitive_count = 0
    triangle_count = 0
    position_indices = []
    index_indices = []
    has_normals = False
    for mesh in meshes:
        if not isinstance(mesh, dict):
            raise _fail(source, "invalid_json", "mesh must be an object")
        primitives = mesh.get("primitives", [])
        if not isinstance(primitives, list):
            raise _fail(source, "invalid_json", "mesh primitives must be an array")
        for primitive in primitives:
            if not isinstance(primitive, dict):
                raise _fail(source, "invalid_json", "primitive must be an object")
            primitive_count += 1
            attributes = primitive.get("attributes", {})
            if not isinstance(attributes, dict):
                raise _fail(source, "invalid_json", "attributes must be an object")
            position_index = attributes.get("POSITION")
            if position_index is not None:
                position_indices.append(position_index)
                position_count = _accessor_count(accessors, position_index, source)
            else:
                position_count = 0
            if "NORMAL" in attributes:
                _accessor_count(accessors, attributes["NORMAL"], source)
                has_normals = True
            index = primitive.get("indices")
            if index is not None:
                index_indices.append(index)
                element_count = _accessor_count(accessors, index, source)
            else:
                element_count = position_count
            if primitive.get("mode", _TRIANGLES) == _TRIANGLES:
                triangle_count += element_count // 3

    node_names = []
    component_ids = []
    prototype_ids = []
    for node in nodes:
        if not isinstance(node, dict):
            raise _fail(source, "invalid_json", "node must be an object")
        name = node.get("name")
        if isinstance(name, str):
            node_names.append(name)
        extras = node.get("extras")
        if isinstance(extras, dict):
            component_id = extras.get("componentId")
            prototype_id = extras.get("prototypeId")
            if isinstance(component_id, str):
                component_ids.append(component_id)
            if isinstance(prototype_id, str):
                prototype_ids.append(prototype_id)

    readback = GlbReadback(
        byte_count=len(raw),
        sha256=file_sha256(source),
        version=version,
        generator=asset.get("generator") if isinstance(asset.get("generator"), str) else None,
        chunks=tuple(chunks),
        scene_count=len(scenes),
        node_count=len(nodes),
        mesh_count=len(meshes),
        primitive_count=primitive_count,
        material_count=len(materials),
        accessor_count=len(accessors),
        position_accessor_count=len(position_indices),
        index_accessor_count=len(index_indices),
        triangle_count=triangle_count,
        has_normals=has_normals,
        has_embedded_binary=binary_payload is not None,
        node_names=tuple(node_names),
        component_ids=tuple(component_ids),
        prototype_ids=tuple(prototype_ids),
    )
    return GlbReadResult(document=document, readback=readback)


def read_glb_summary(path: Path) -> GlbReadback:
    """Parse one GLB file and return only immutable neutral facts."""
    return read_glb(path).readback


def write_cadquery_glb(
    assembly,
    destination: Path,
    *,
    tolerance: float,
    angular_tolerance: float,
) -> Path:
    """Write one existing CadQuery assembly without imposing compression policy."""
    target = destination.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    assembly.export(
        str(target),
        exportType="GLB",
        tolerance=tolerance,
        angularTolerance=angular_tolerance,
    )
    if not target.is_file() or target.stat().st_size <= 0:
        raise RuntimeError(f"GLB writer produced no output: {target}")
    return target


def write_glb_document(document: dict, binary_blob: bytes, destination: Path) -> Path:
    """Write a caller-built glTF JSON document and embedded buffer as GLB v2."""
    target = destination.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    json_bytes = json.dumps(
        document, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    json_bytes += b" " * ((-len(json_bytes)) % 4)
    blob = bytes(binary_blob)
    blob += b"\x00" * ((-len(blob)) % 4)
    total = (
        _HEADER.size
        + _CHUNK_HEADER.size
        + len(json_bytes)
        + _CHUNK_HEADER.size
        + len(blob)
    )
    with target.open("wb") as output:
        output.write(_HEADER.pack(b"glTF", 2, total))
        output.write(_CHUNK_HEADER.pack(len(json_bytes), _JSON_CHUNK))
        output.write(json_bytes)
        output.write(_CHUNK_HEADER.pack(len(blob), _BIN_CHUNK))
        output.write(blob)
    return target
