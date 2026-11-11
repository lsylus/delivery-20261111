"""Render controlled DXF geometry and text from one canonical glyph algorithm."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import ezdxf
from ezdxf.addons import MTextExplode, text2path
from ezdxf.fonts import fonts as ezdxf_fonts
from fontTools.pens.recordingPen import DecomposingRecordingPen
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch, Polygon
from matplotlib.font_manager import FontProperties
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pypdf import PdfReader, PdfWriter

from .dxf_writer import ALLOWED_MODELSPACE_TYPES
from .display_profile import (
    controlled_dimension_linetype_error,
    controlled_entity_display_error,
    controlled_layer_error,
)
from .text_metrics import locked_font


class RenderError(ValueError):
    pass


CONTROLLED_ACI_COLORS = {
    2: "#ffff00",
    7: "#000000",
}


def _controlled_display_error(entity) -> str | None:
    error = controlled_entity_display_error(entity)
    return error.replace("controlled display profile", "controlled renderer profile") if error else None


def _stroke_color(entity, doc, inherited_color: str | None = None) -> str:
    true_color = entity.dxf.get("true_color", None)
    if true_color is not None:
        if int(true_color) != 16308017:
            raise RenderError(f"unsupported controlled true color: {true_color}")
        return "#f8d731"
    aci = int(entity.dxf.get("color", 256))
    if aci == 0:
        return inherited_color or "#000000"
    if aci == 256:
        try:
            aci = abs(int(doc.layers.get(entity.dxf.get("layer", "0")).dxf.color))
        except (ezdxf.DXFTableEntryError, ValueError):
            aci = 7
    if aci not in CONTROLLED_ACI_COLORS:
        raise RenderError(f"unsupported controlled ACI color: {aci}")
    return CONTROLLED_ACI_COLORS[aci]


def _solid_count(entities) -> int:
    count = 0
    for entity in entities:
        if entity.dxftype() == "SOLID":
            count += 1
        elif entity.dxftype() == "INSERT":
            count += _solid_count(entity.virtual_entities())
    return count


def _alignment(entity) -> str:
    if entity.dxftype() == "MTEXT":
        return {
            1: "TOP_LEFT", 2: "TOP_CENTER", 3: "TOP_RIGHT",
            4: "MIDDLE_LEFT", 5: "MIDDLE_CENTER", 6: "MIDDLE_RIGHT",
            7: "BOTTOM_LEFT", 8: "BOTTOM_CENTER", 9: "BOTTOM_RIGHT",
        }.get(int(entity.dxf.get("attachment_point", 1)), "TOP_LEFT")
    halign = int(entity.dxf.get("halign", 0))
    valign = int(entity.dxf.get("valign", 0))
    return {
        (0, 0): "LEFT", (1, 0): "CENTER", (2, 0): "RIGHT",
        (0, 1): "BOTTOM_LEFT", (1, 1): "BOTTOM_CENTER", (2, 1): "BOTTOM_RIGHT",
        (0, 2): "MIDDLE_LEFT", (1, 2): "MIDDLE_CENTER", (2, 2): "MIDDLE_RIGHT",
        (0, 3): "TOP_LEFT", (1, 3): "TOP_CENTER", (2, 3): "TOP_RIGHT",
    }.get((halign, valign), "LEFT")


def _cad_glyph_path(contours, denominator: float) -> MplPath:
    vertices: list[tuple[float, float]] = []
    codes: list[int] = []
    for contour in contours:
        start = contour.start
        vertices.append((float(start.x) / denominator, float(start.y) / denominator))
        codes.append(MplPath.MOVETO)
        for command in contour:
            kind = command.type.name
            if kind == "LINE_TO":
                vertices.append((float(command.end.x) / denominator, float(command.end.y) / denominator))
                codes.append(MplPath.LINETO)
            elif kind == "CURVE3_TO":
                vertices.extend([
                    (float(command.ctrl.x) / denominator, float(command.ctrl.y) / denominator),
                    (float(command.end.x) / denominator, float(command.end.y) / denominator),
                ])
                codes.extend([MplPath.CURVE3, MplPath.CURVE3])
            elif kind == "CURVE4_TO":
                vertices.extend([
                    (float(command.ctrl1.x) / denominator, float(command.ctrl1.y) / denominator),
                    (float(command.ctrl2.x) / denominator, float(command.ctrl2.y) / denominator),
                    (float(command.end.x) / denominator, float(command.end.y) / denominator),
                ])
                codes.extend([MplPath.CURVE4, MplPath.CURVE4, MplPath.CURVE4])
            elif kind == "MOVE_TO":
                vertices.append((float(command.end.x) / denominator, float(command.end.y) / denominator))
                codes.append(MplPath.MOVETO)
            else:
                raise RenderError(f"unsupported CAD glyph path command: {kind}")
        vertices.append((0.0, 0.0))
        codes.append(MplPath.CLOSEPOLY)
    return MplPath(vertices, codes)


@contextmanager
def _locked_ezdxf_font(font_path: Path):
    saved_fonts = ezdxf_fonts.font_manager.dumps()
    try:
        ezdxf_fonts.font_manager.clear()
        ezdxf_fonts.font_manager.scan_folder(font_path.parent)
        ezdxf_fonts.TrueTypeFont._glyph_caches.clear()
        font_face = ezdxf_fonts.get_font_face(font_path.name)
        if Path(font_face.filename).name.lower() != font_path.name.lower():
            raise RenderError(f"ezdxf did not resolve the locked font: {font_face.filename}")
        yield font_face
    finally:
        ezdxf_fonts.font_manager.clear()
        ezdxf_fonts.font_manager.loads(saved_fonts)
        ezdxf_fonts.TrueTypeFont._glyph_caches.clear()


def _exact_text_paths(entity, font_path: Path):
    with _locked_ezdxf_font(font_path) as font_face:
        path = text2path.make_path_from_str(
            entity.plain_text(),
            font_face,
            size=entity.dxf.height,
            align=entity.get_align_enum(),
            length=entity.fit_length(),
        )
        return list(path.transform(entity.wcs_transformation_matrix()).sub_paths())


def _explode_mtext_exact(entity, doc, font_path: Path, font_profile: dict):
    with _locked_ezdxf_font(font_path):
        render_style = "HEATER_PDF_HZ"
        if render_style not in doc.styles:
            style = doc.styles.add(
                render_style, font=font_profile["render_cad_style_font_file"]
            )
            style.dxf.width = font_profile["cad_style_width_factor"]
        temporary = doc.blocks.new_anonymous_block()
        exploder = MTextExplode(temporary, doc=doc)
        original_style = entity.dxf.style
        if original_style == font_profile["cad_style_name"]:
            entity.dxf.style = render_style
        try:
            exploder.explode(entity, destroy=False)
        finally:
            entity.dxf.style = original_style
        return list(temporary.query("TEXT"))


def _draw_editable_text(
    ax,
    entity,
    font: FontProperties,
    denominator: float,
    font_profile: dict,
    exact_font_path: Path,
    color: str,
    text_scale: float,
) -> None:
    text = entity.dxf.text
    insert = entity.dxf.insert
    if int(entity.dxf.get("halign", 0)) or int(entity.dxf.get("valign", 0)):
        insert = entity.dxf.align_point
    original_height = float(entity.dxf.height)
    height = original_height * text_scale
    rotation = float(entity.dxf.get("rotation", 0.0))
    entity.dxf.height = height
    try:
        cad_paths = _exact_text_paths(entity, exact_font_path)
    finally:
        entity.dxf.height = original_height
    locked = locked_font(font_profile)
    glyph_set = locked.getGlyphSet()
    cmap = locked.getBestCmap() or {}
    contour_counts: list[int] = []
    for character in text:
        name = cmap.get(ord(character))
        if name is None:
            raise RenderError(f"locked font lacks glyph U+{ord(character):04X}")
        pen = DecomposingRecordingPen(glyph_set)
        glyph_set[name].draw(pen)
        contours = sum(operation == "moveTo" for operation, _ in pen.value)
        if contours:
            contour_counts.append(contours)
    if sum(contour_counts) != len(cad_paths):
        raise RenderError(
            f"CAD glyph contour count differs for {text!r}: "
            f"expected {sum(contour_counts)}, found {len(cad_paths)}"
        )
    cursor = 0
    for count in contour_counts:
        glyph_path = _cad_glyph_path(cad_paths[cursor:cursor + count], denominator)
        cursor += count
        ax.add_patch(PathPatch(glyph_path, facecolor=color, edgecolor="none"))
    # Preserve searchable text and the locked embedded font while visible ink follows CAD paths.
    ax.text(
        float(insert.x) / denominator, float(insert.y) / denominator, text,
        fontsize=height / denominator * 72.0 / 25.4,
        fontproperties=font,
        rotation=rotation,
        color=color, alpha=0.0, clip_on=True,
    )


def _draw_entity(
    ax,
    entity,
    denominator: float,
    font: FontProperties,
    font_profile: dict,
    doc,
    exact_font_path: Path,
    inherited_color: str | None = None,
    dimension_cache: bool = False,
    block_child: bool = False,
) -> None:
    kind = entity.dxftype()
    if kind == "POINT":
        return
    display_error = _controlled_display_error(entity)
    if display_error:
        raise RenderError(f"{kind} {display_error}")
    binding_error = controlled_entity_display_error(
        entity,
        top_level=not dimension_cache,
        dimension_cache=dimension_cache,
        block_child=block_child,
    )
    if binding_error:
        raise RenderError(f"{kind} {binding_error}")
    color = _stroke_color(entity, doc, inherited_color)
    if kind == "TEXT":
        text_scale = (
            float(font_profile["pdf_hz_substitution_text_scale"])
            if entity.dxf.style == font_profile["cad_style_name"]
            else float(font_profile["pdf_native_noto_text_scale"])
        )
        _draw_editable_text(
            ax,
            entity,
            font,
            denominator,
            font_profile,
            exact_font_path,
            color,
            text_scale,
        )
    elif kind == "MTEXT":
        text_scale = (
            float(font_profile["pdf_hz_substitution_text_scale"])
            if entity.dxf.style == font_profile["cad_style_name"]
            else float(font_profile["pdf_native_noto_text_scale"])
        )
        exploded = _explode_mtext_exact(entity, doc, exact_font_path, font_profile)
        if not exploded:
            raise RenderError(f"CAD MTEXT expansion is empty: {entity.plain_text()!r}")
        for text_entity in exploded:
            text_color = _stroke_color(text_entity, doc, color)
            _draw_editable_text(
                ax,
                text_entity,
                font,
                denominator,
                font_profile,
                exact_font_path,
                text_color,
                text_scale,
            )
    elif kind == "LINE":
        ax.plot(
            [entity.dxf.start.x / denominator, entity.dxf.end.x / denominator],
            [entity.dxf.start.y / denominator, entity.dxf.end.y / denominator],
            color=color, linewidth=0.35,
        )
    elif kind == "LWPOLYLINE":
        points = [(x / denominator, y / denominator) for x, y in entity.get_points("xy")]
        if entity.closed and points:
            points.append(points[0])
        if points:
            ax.plot([p[0] for p in points], [p[1] for p in points], color=color, linewidth=0.35)
    elif kind == "SOLID":
        points = [(entity.dxf.get(name).x / denominator, entity.dxf.get(name).y / denominator) for name in ("vtx0", "vtx1", "vtx2", "vtx3")]
        ax.add_patch(Polygon(points, closed=True, facecolor=color, edgecolor=color))
    elif kind == "INSERT":
        for child in entity.virtual_entities():
            _draw_entity(
                ax, child, denominator, font, font_profile, doc, exact_font_path, color,
                dimension_cache=dimension_cache, block_child=dimension_cache,
            )
    elif kind == "DIMENSION":
        for child in entity.virtual_entities():
            _draw_entity(
                ax, child, denominator, font, font_profile, doc, exact_font_path, color,
                dimension_cache=True,
            )
    else:
        raise RenderError(f"unsupported rendered entity: {kind}")


def render_page(
    dxf_path: Path,
    pdf_path: Path,
    png_path: Path,
    denominator: float,
    font_path: Path,
    font_profile: dict | None = None,
    *,
    model_origin_mm: tuple[float, float] = (0.0, 0.0),
) -> dict:
    doc = ezdxf.readfile(dxf_path)
    layer_error = controlled_layer_error(doc)
    if layer_error:
        raise RenderError(layer_error)
    msp = doc.modelspace()
    unknown = sorted({entity.dxftype() for entity in msp if entity.dxftype() not in ALLOWED_MODELSPACE_TYPES})
    if unknown:
        raise RenderError(f"unsupported modelspace entities: {', '.join(unknown)}")
    for dimension in msp.query("DIMENSION"):
        linetype_error = controlled_dimension_linetype_error(doc, dimension)
        if linetype_error:
            raise RenderError(linetype_error)
    if not font_path.is_file():
        raise RenderError(f"locked render font is missing: {font_path}")
    if font_profile is None:
        raise RenderError("locked font profile is required")
    fig = plt.figure(figsize=(210 / 25.4, 297 / 25.4), dpi=144)
    ax = fig.add_axes((0, 0, 1, 1))
    font = FontProperties(fname=str(font_path))
    for entity in msp:
        _draw_entity(ax, entity, denominator, font, font_profile, doc, font_path)
    origin_x = model_origin_mm[0] / denominator
    origin_y = model_origin_mm[1] / denominator
    ax.set_xlim(origin_x, origin_x + 210)
    ax.set_ylim(origin_y, origin_y + 297)
    ax.set_aspect("equal", adjustable="box")
    ax.set_axis_off()
    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(pdf_path, format="pdf", dpi=144, metadata={"Creator": "heater-drawing ezdxf dxf_pdf_v1"})
    fig.savefig(png_path, format="png", dpi=144, facecolor="white")
    plt.close(fig)
    page = PdfReader(str(pdf_path)).pages[0]
    width_mm = float(page.mediabox.width) * 25.4 / 72.0
    height_mm = float(page.mediabox.height) * 25.4 / 72.0
    dimensions = list(msp.query("DIMENSION"))
    arrows = sum(_solid_count(entity.virtual_entities()) for entity in dimensions)
    return {
        "source_dxf": str(dxf_path), "pdf": str(pdf_path), "png": str(png_path),
        "page_mm": {"width": width_mm, "height": height_mm},
        "viewport_transform": {
            "model_to_paper_scale": 1.0 / denominator,
            "origin_mm": [float(model_origin_mm[0]), float(model_origin_mm[1])],
        },
        "renderer": "ezdxf CAD glyph paths grouped by locked fontTools glyphs plus direct DXF geometry",
        "native_dimensions": len(dimensions), "dimension_arrow_solids": arrows,
        "text_face": {"path": str(font_path), "family": "Noto Sans CJK SC", "postscript": "NotoSansCJKsc-Regular"},
        "paper_position_tolerance_mm": 0.1,
    }


def merge_pdfs(inputs: list[Path], output: Path) -> None:
    writer = PdfWriter()
    for path in inputs:
        for page in PdfReader(str(path)).pages:
            writer.add_page(page)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as stream:
        writer.write(stream)
