from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import pytest

from heater_drawing.delivery import build_delivery
from heater_drawing.domain.models import Revision
from heater_drawing.drawing.dxf_writer import export_planned_dxf
from heater_drawing.drawing.layout import plan_pages
from heater_drawing.drawing.template import load_template


ROOT = Path(__file__).resolve().parents[2]


def write_pages(path: Path, revision: Revision, plan) -> None:
    value = {
        "schema_version": 1,
        "revision_hash": revision.revision_hash,
        "template_hash": revision.template_hash,
        "page_order": list(plan.expected_row_ids),
        "layout_mapping": [
            {
                "page_index": index,
                "row_id": page.row_id,
                "code": page.code,
                "layout_name": page.placement.layout_name,
                "scale": page.scale.label,
            }
            for index, page in enumerate(plan.pages, start=1)
        ],
        "pages": [page.model_dump(mode="json") for page in plan.pages],
    }
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_case(root: Path, revision_name: str = "case-revision.json") -> tuple[Path, Revision]:
    revision = Revision.model_validate_json(
        (ROOT / "fixtures/delivery" / revision_name).read_text(encoding="utf-8")
    )
    template = load_template(ROOT / "templates/heater-a4-v1")
    plan = plan_pages(revision, template)
    assert plan.exportable
    source_dxf = root / "source.dxf"
    pages = root / "pages.json"
    export_planned_dxf(source_dxf, plan, revision, template)
    write_pages(pages, revision, plan)
    output = root / "candidate"
    build_delivery(
        revision,
        input_dxf=source_dxf,
        pages_path=pages,
        original_workbook=ROOT / "fixtures/case/加热器图纸.xlsx",
        output=output,
        template_dir=ROOT / "templates/heater-a4-v1",
        package_name="加热器图纸",
    )
    return output, revision


@pytest.fixture(scope="session")
def delivery_case(tmp_path_factory):
    return build_case(tmp_path_factory.mktemp("delivery-case"))


@pytest.fixture(scope="session")
def skipped_delivery_case(tmp_path_factory):
    return build_case(
        tmp_path_factory.mktemp("delivery-skip"),
        "case-revision-skip-excel-row-3.json",
    )


@pytest.fixture()
def copied_case(delivery_case, tmp_path):
    destination = tmp_path / "candidate"
    shutil.copytree(delivery_case[0], destination)
    return destination, delivery_case[1]


@pytest.fixture()
def copied_skipped_case(skipped_delivery_case, tmp_path):
    destination = tmp_path / "candidate"
    shutil.copytree(skipped_delivery_case[0], destination)
    return destination, skipped_delivery_case[1]


def rebind_candidate(root: Path) -> None:
    """Rebind a deliberately mutated candidate so validation reaches its target check."""

    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest["files"]:
        path = root / item["relative_path"]
        if path.is_file():
            item["bytes"] = path.stat().st_size
            item["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    run_path = root / "run.json"
    run = json.loads(run_path.read_text(encoding="utf-8"))
    zip_path = root / run["zip"]["relative_path"]
    members = sorted([item["relative_path"] for item in manifest["files"]] + ["manifest.json"])
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in members:
            path = root / relative
            if path.is_file():
                archive.write(path, relative)
    run["manifest"]["bytes"] = manifest_path.stat().st_size
    run["manifest"]["sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    run["zip"]["bytes"] = zip_path.stat().st_size
    run["zip"]["sha256"] = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    run_path.write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
