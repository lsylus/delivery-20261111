from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil

import pytest

from heater_drawing.drawing.dxf_writer import export_planned_dxf
from heater_drawing.drawing.layout import plan_pages
from heater_drawing.drawing.template import load_template

from .conftest import revision_for


def _assert_rejected(path: Path, plan, revision, template) -> None:
    with pytest.raises(ValueError):
        export_planned_dxf(path, plan, revision, template)
    assert not path.exists()


def test_formal_export_rejects_stale_page_content(
    tmp_path, real_plan, real_revision, controlled_template
):
    page = real_plan.pages[0]
    fields = page.fields.model_copy(update={"organization": "超" * 120})
    stale = page.model_copy(update={"fields": fields})
    plan = replace(real_plan, pages=(stale, *real_plan.pages[1:]))
    _assert_rejected(tmp_path / "stale.dxf", plan, real_revision, controlled_template)


@pytest.mark.parametrize("field", ["template_hash", "revision_hash"])
def test_formal_export_rejects_wrong_page_binding(
    field, tmp_path, real_plan, real_revision, controlled_template
):
    changed = real_plan.pages[0].model_copy(update={field: "b" * 64})
    plan = replace(real_plan, pages=(changed, *real_plan.pages[1:]))
    _assert_rejected(tmp_path / f"wrong-{field}.dxf", plan, real_revision, controlled_template)


def test_formal_export_rejects_missing_expected_pages(
    tmp_path, real_plan, real_revision, controlled_template
):
    plan = replace(real_plan, pages=real_plan.pages[:1])
    _assert_rejected(tmp_path / "missing-pages.dxf", plan, real_revision, controlled_template)


def test_formal_export_reloads_controlled_template_after_planning(
    tmp_path, real_rows
):
    source = Path(__file__).resolve().parents[2] / "templates" / "heater-a4-v1"
    copied = tmp_path / "template"
    shutil.copytree(source, copied)
    template = load_template(copied)
    revision = revision_for(template, real_rows[1])
    plan = plan_pages(revision, template)
    with (copied / "template.dxf").open("ab") as stream:
        stream.write(b"template-drift")
    _assert_rejected(tmp_path / "drift.dxf", plan, revision, template)
