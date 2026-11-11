#!/usr/bin/env python3
"""Install the built wheel in isolation and verify external resources."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(argv: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    uv = ROOT / ".tools/uv"
    wheels = sorted(args.wheel_dir.glob("heater_drawing_service-*.whl"))
    if not uv.is_file() or len(wheels) != 1:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "reason": "project-local uv and exactly one wheel are required",
                }
            )
        )
        return 2

    env = os.environ.copy()
    env["UV_CACHE_DIR"] = str(ROOT / ".uv-cache")
    with tempfile.TemporaryDirectory(prefix="heater-wheel-check-") as value:
        work = Path(value)
        venv = work / "venv"
        resources = work / "resources"
        resources.mkdir()
        shutil.copytree(ROOT / "schemas", resources / "schemas")
        create = run(
            [str(uv), "venv", str(venv), "--python", sys.executable],
            ROOT,
            env,
        )
        if create.returncode != 0:
            print(create.stdout + create.stderr)
            return 2
        python = venv / "bin/python"
        install = run(
            [str(uv), "pip", "install", "--python", str(python), str(wheels[0])],
            work,
            env,
        )
        if install.returncode != 0:
            print(install.stdout + install.stderr)
            return 2
        check_env = env.copy()
        check_env["HEATER_DRAWING_RESOURCE_ROOT"] = str(resources)
        code = (
            "import json, heater_drawing;"
            "from heater_drawing.config import ResourceConfig;"
            "from heater_drawing.domain.models import ErrorCode;"
            "from heater_drawing.excel import parse_workbook,validate_rows;"
            "c=ResourceConfig.from_environment();"
            "print(json.dumps({'module':heater_drawing.__file__,"
            "'schemas':len(list(c.schema_dir.glob('*.json'))),"
            "'error_code':ErrorCode.WORKER_INTERRUPTED.value,"
            "'excel_api':callable(parse_workbook) and callable(validate_rows)}))"
        )
        checked = run([str(python), "-c", code], work, check_env)
        if checked.returncode != 0:
            print(checked.stdout + checked.stderr)
            return 1
        payload = json.loads(checked.stdout)
        payload["status"] = "passed"
        payload["outside_source_tree"] = not Path(payload["module"]).is_relative_to(ROOT)
        if payload["schemas"] != 6 or not payload["outside_source_tree"] or not payload["excel_api"]:
            print(json.dumps(payload))
            return 1
        print(json.dumps(payload))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
