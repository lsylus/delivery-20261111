"""Exact preflight through the existing B02 writer/readback implementation."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from heater_drawing.domain.models import DrawingPage

from .dxf_writer import write_page_dxf
from .readback import ReadbackError, inspect_dxf


def preflight_page(page: DrawingPage, template: dict) -> tuple[bool, dict | None, str | None]:
    """Validate full visible semantics without retaining or registering an artifact."""

    with TemporaryDirectory(prefix="heater-layout-preflight-") as temporary:
        candidate = Path(temporary) / "diagnostic-not-an-artifact.dxf"
        try:
            write_page_dxf(
                candidate,
                page,
                template["layout"],
                template["fonts"],
                template_path=template["directory"] / "template.dxf",
            )
            report = inspect_dxf(
                candidate, [page], template["layout"], template["fonts"]
            )
        except (OSError, ValueError, ReadbackError) as exc:
            return False, None, str(exc)
    return True, report, None


def is_scale_sensitive(reason: str) -> bool:
    """Only geometry/dimension failures may be solved by a smaller paper scale."""

    scale_terms = (
        "heater/lead/dimension bounds",
        "lead/dimension clearance",
        "heater/lead/dimension collision",
        "complete content bounds leave paper",
    )
    return any(term in reason for term in scale_terms)
