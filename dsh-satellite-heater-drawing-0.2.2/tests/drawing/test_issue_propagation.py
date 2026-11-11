from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

from openpyxl import load_workbook

from heater_drawing.domain.models import Severity
from heater_drawing.drawing.layout import plan_pages
from heater_drawing.excel import parse_workbook, validate_rows

from .conftest import revision_for


ROOT = Path(__file__).resolve().parents[2]


def _warning_workbook(path: Path) -> Path:
    shutil.copy2(ROOT / "fixtures" / "case" / "加热器图纸.xlsx", path)
    workbook = load_workbook(path)
    extra = workbook.create_sheet("Unprocessed")
    extra["A1"] = "must remain visible as a warning"
    workbook.save(path)
    workbook.close()
    return path


def test_warning_is_preserved_in_exportable_page_plan(
    tmp_path, controlled_template
):
    source = _warning_workbook(tmp_path / "warning.xlsx")
    parsed = parse_workbook(source)
    validated = validate_rows(parsed.rows, controlled_template)
    issues = [*parsed.issues, *validated.issues]
    assert len(issues) == 1 and issues[0].severity == Severity.WARNING
    revision = revision_for(
        controlled_template,
        validated.rows,
        issues=issues,
    )
    plan = plan_pages(revision, controlled_template)
    assert plan.exportable
    assert plan.issues == tuple(issues)


def test_successful_draw_cli_retains_parse_warning(tmp_path):
    source = _warning_workbook(tmp_path / "warning-cli.xlsx")
    output = tmp_path / "output"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "draw_case.py"),
            "--input",
            str(source),
            "--template",
            str(ROOT / "templates" / "heater-a4-v1"),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads((output / "plan.json").read_text(encoding="utf-8"))
    assert payload["status"] == "ready"
    assert len(payload["issues"]) == 1
    assert payload["issues"][0]["severity"] == "warning"
    assert payload["issues"][0]["error_code"] == "UNSUPPORTED_INPUT"
