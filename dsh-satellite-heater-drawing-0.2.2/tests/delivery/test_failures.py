from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from heater_drawing.delivery import DeliveryError, build_delivery, validate_delivery
from heater_drawing.delivery.pdf_merge import merge_single_page_pdfs
from heater_drawing.domain.models import Revision
from heater_drawing.drawing.layout import plan_pages

from .conftest import ROOT, rebind_candidate, write_pages


def _validate(root, revision) -> None:
    validate_delivery(root, revision, template_dir=ROOT / "templates/heater-a4-v1")


def test_two_page_single_pdf_is_rejected(copied_case) -> None:
    root, revision = copied_case
    single = root / "pdf/CX-29-KR05-XM01.pdf"
    merge_single_page_pdfs([single, single], root / "two.pdf")
    (root / "two.pdf").replace(single)
    rebind_candidate(root)
    with pytest.raises(DeliveryError, match="PAGE_COUNT_MISMATCH"):
        _validate(root, revision)


def test_damaged_pdf_is_rejected_even_when_rehashed(copied_case) -> None:
    root, revision = copied_case
    (root / "pdf/CX-29-KR05-XM01.pdf").write_bytes(b"not a pdf")
    rebind_candidate(root)
    with pytest.raises(DeliveryError, match="INVALID_PDF"):
        _validate(root, revision)


def test_path_escape_is_rejected(copied_case) -> None:
    root, revision = copied_case
    path = root / "manifest.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["files"][0]["relative_path"] = "../escaped.dxf"
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rebind_candidate(root)
    with pytest.raises(DeliveryError, match="PATH_ESCAPE"):
        _validate(root, revision)


def test_casefold_filename_collision_is_rejected(copied_case) -> None:
    root, revision = copied_case
    path = root / "manifest.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    duplicate = dict(value["files"][1])
    duplicate["relative_path"] = duplicate["relative_path"].upper()
    value["files"].append(duplicate)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rebind_candidate(root)
    with pytest.raises(DeliveryError, match="NAME_COLLISION"):
        _validate(root, revision)


def test_missing_skip_decision_and_all_skip_are_rejected() -> None:
    value = json.loads((ROOT / "fixtures/delivery/case-revision-skip-excel-row-3.json").read_text(encoding="utf-8"))
    value["decisions"] = []
    with pytest.raises((ValidationError, ValueError), match="skip decisions"):
        Revision.model_validate(value)
    value = json.loads((ROOT / "fixtures/delivery/case-revision.json").read_text(encoding="utf-8"))
    value["skipped_row_ids"] = [row["row_id"] for row in value["rows"]]
    value["expected_row_ids"] = []
    with pytest.raises((ValidationError, ValueError)):
        Revision.model_validate(value)


def test_skip_decision_must_cover_the_failed_rows_errors() -> None:
    value = json.loads((ROOT / "fixtures/delivery/case-revision-skip-excel-row-3.json").read_text(encoding="utf-8"))
    value["decisions"][0]["issue_ids"] = []
    with pytest.raises((ValidationError, ValueError), match="cover every skippable row error"):
        Revision.create(**{key: item for key, item in value.items() if key != "revision_hash"})


@pytest.mark.parametrize(
    ("scope", "skippable"),
    [("system", False), ("row", False)],
)
def test_skip_never_suppresses_forbidden_error_scope(scope, skippable) -> None:
    value = json.loads(
        (ROOT / "fixtures/delivery/case-revision-skip-excel-row-3.json").read_text(
            encoding="utf-8"
        )
    )
    value.pop("revision_hash")
    value["issues"][0].update(scope=scope, skippable=skippable)
    value["decisions"][0]["issue_ids"] = []
    revision = Revision.create(**value)

    plan = plan_pages(revision, ROOT / "templates/heater-a4-v1")

    assert not plan.exportable
    assert plan.pages == ()
    assert plan.issues == tuple(revision.issues)


def test_overlong_quantity_is_rejected_at_frozen_revision_boundary() -> None:
    value = json.loads((ROOT / "fixtures/delivery/case-revision.json").read_text(encoding="utf-8"))
    value["rows"][0]["values"]["quantity_text"] = "X" * 257
    with pytest.raises(ValidationError):
        Revision.model_validate(value)


def test_second_row_render_failure_leaves_no_candidate(monkeypatch, tmp_path) -> None:
    revision = Revision.model_validate_json(
        (ROOT / "fixtures/delivery/case-revision.json").read_text(encoding="utf-8")
    )
    from heater_drawing.drawing.dxf_writer import export_planned_dxf
    from heater_drawing.drawing.layout import plan_pages
    from heater_drawing.drawing.template import load_template
    import heater_drawing.delivery.package as package_module

    template = load_template(ROOT / "templates/heater-a4-v1")
    plan = plan_pages(revision, template)
    source_dxf = tmp_path / "source.dxf"
    pages = tmp_path / "pages.json"
    export_planned_dxf(source_dxf, plan, revision, template)
    write_pages(pages, revision, plan)
    real_render = package_module.render_page
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected second-row failure")
        return real_render(*args, **kwargs)

    monkeypatch.setattr(package_module, "render_page", fail_second)
    output = tmp_path / "must-not-exist"
    with pytest.raises(RuntimeError, match="second-row"):
        build_delivery(
            revision,
            input_dxf=source_dxf,
            pages_path=pages,
            original_workbook=ROOT / "fixtures/case/加热器图纸.xlsx",
            output=output,
            template_dir=ROOT / "templates/heater-a4-v1",
            package_name="加热器图纸",
        )
    assert not output.exists()
