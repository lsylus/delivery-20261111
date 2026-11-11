from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from heater_drawing.domain.models import Revision, Scale
from heater_drawing.drawing.layout import plan_pages
from heater_drawing.drawing.template import load_template
from heater_drawing.excel import parse_workbook, validate_rows


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def controlled_template():
    return load_template(ROOT / "templates/heater-a4-v1")


@pytest.fixture(scope="session")
def real_rows():
    parsed = parse_workbook(ROOT / "fixtures/case/加热器图纸.xlsx")
    validated = validate_rows(parsed.rows)
    assert not parsed.issues and not validated.issues
    return parsed, validated.rows


def revision_for(
    template,
    rows,
    *,
    scales=None,
    issues=(),
    proposals=(),
    decisions=(),
):
    if scales is None:
        scales = {
            row.row_id: Scale(
                denominator=row.values.requested_scale.split(":", 1)[1],
                label=row.values.requested_scale,
            )
            for row in rows
        }
    return Revision.create(
        revision_id=UUID("7785cd2e-eaa6-4f77-a951-a58bf2d83f07"),
        parent_revision_id=None,
        source_sha256="a" * 64,
        template_version=template["manifest"]["version"],
        template_hash=template["template_sha256"],
        font_manifest_hash=template["fonts_sha256"],
        output_profile="dxf_pdf_v1",
        rows=list(rows),
        final_scales=scales,
        issues=list(issues),
        proposals=list(proposals),
        decisions=list(decisions),
        skipped_row_ids=[],
        expected_row_ids=[row.row_id for row in rows],
    )


@pytest.fixture(scope="session")
def real_revision(controlled_template, real_rows):
    return revision_for(controlled_template, real_rows[1])


@pytest.fixture(scope="session")
def real_plan(real_revision, controlled_template):
    result = plan_pages(real_revision, controlled_template)
    assert result.exportable
    return result
