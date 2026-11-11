"""Isolated DWG 2018 save, semantic readback and PDF plotting.

Each delivery uses a private native process and font/profile directories. PDF
pages are always plotted after reopening the exact DWG that will be delivered.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import tempfile
import time
from uuid import uuid4

import ezdxf
from pypdf import PdfReader

from .readback import inspect_dxf
from .plot_style import apply_sample_strokes
from .profile import NATIVE_PROFILE


PROFILE = NATIVE_PROFILE
DEFAULT_EXECUTABLE = "/data/qmh/OpenCADStudio/current/squashfs-root/usr/bin/OpenCADStudio"
# Measured from the supplied AutoCAD PDF and checked against the original DWG
# frame. These are printing settings only; model geometry remains true size.
SAMPLE_PRINT_SCALE = 1.041982
SAMPLE_OFFSET_MM = (0.7056, 1.0335888889)


class NativeCadError(ValueError):
    pass


def bind_to_parent():
    """Linux private service: kill native children if their worker is killed."""
    import ctypes
    parent = os.getppid()
    if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL) != 0:
        os._exit(127)
    if os.getppid() != parent:
        os._exit(127)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_executable(executable=None) -> Path:
    executable = executable or os.environ.get("HEATER_OPENCADSTUDIO", DEFAULT_EXECUTABLE)
    resolved = shutil.which(str(executable))
    if not resolved:
        raise NativeCadError("OpenCADStudio native executable is unavailable")
    with Path(resolved).open("rb") as binary:
        if binary.read(2) == b"#!":
            raise NativeCadError("HEATER_OPENCADSTUDIO must name the native executable, not a profile wrapper")
    return Path(resolved).resolve()


class NativeSession:
    """Bounded JSON-lines transport; no shell and no shared CAD preferences."""

    def __init__(self, root: Path, font_paths, *, executable=None, timeout=90):
        self.timeout = timeout
        self.calls = []
        self.buffer = bytearray()
        self.process = None
        self.executable = resolve_executable(executable)
        env = dict(os.environ)
        for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR"):
            folder = root / name
            folder.mkdir(parents=True, mode=0o700)
            env[name] = str(folder)
        fonts = Path(env["XDG_CONFIG_HOME"]) / "OpenCADStudio" / "fonts"
        fonts.mkdir(parents=True)
        self.fonts = []
        for font in font_paths:
            font = Path(font)
            if not font.is_file():
                raise NativeCadError(f"CAD font missing: {font}")
            target = fonts / font.name.lower()
            shutil.copyfile(font, target)
            self.fonts.append({"name": target.name, "sha256": digest(target)})
        self.stderr = (root / "native-stderr.log").open("wb")
        try:
            self.process = subprocess.Popen(
                [str(self.executable), "--serve"], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=self.stderr, env=env,
                start_new_session=True,
                preexec_fn=bind_to_parent if os.environ.get("HEATER_PARENT_BOUND") == "1" else None,
            )
            self.greeting = self._read()
            if not self.greeting.get("ready"):
                raise NativeCadError("OpenCADStudio did not become ready")
        except Exception:
            self.close()
            raise

    def _read(self):
        deadline = time.monotonic() + self.timeout
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            while b"\n" not in self.buffer:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise NativeCadError("OpenCADStudio operation timed out")
                chunk = os.read(self.process.stdout.fileno(), 65536)
                if not chunk:
                    raise NativeCadError("OpenCADStudio closed its control channel")
                self.buffer.extend(chunk)
                if len(self.buffer) > 32 * 1024 * 1024:
                    raise NativeCadError("OpenCADStudio reply exceeds 32 MiB")
        line, _, tail = self.buffer.partition(b"\n")
        self.buffer = bytearray(tail)
        try:
            return json.loads(line)
        except (ValueError, UnicodeError) as exc:
            raise NativeCadError("OpenCADStudio returned invalid JSON") from exc

    def call(self, request):
        deadline = time.monotonic() + self.timeout
        self.process.stdin.write((json.dumps(request, ensure_ascii=False) + "\n").encode())
        self.process.stdin.flush()
        reply = self._read()
        self.calls.append({"request": request, "response": reply})
        while reply.get("ok") and reply.get("status") in {"accepted", "running"}:
            # A bounded operation poll also supports native builds with asynchronous plots.
            if time.monotonic() >= deadline:
                raise NativeCadError("OpenCADStudio operation did not settle")
            poll = {"protocol": 1, "op": "operation", "request_id": request["request_id"]}
            self.process.stdin.write((json.dumps(poll) + "\n").encode())
            self.process.stdin.flush()
            reply = self._read()
            self.calls.append({"request": poll, "response": reply})
        if reply.get("ok") is not True:
            raise NativeCadError(f"OpenCADStudio refused {request['op']}: {reply.get('error', reply)}")
        return reply

    def operation(self, op, **options):
        state = self.call({"protocol": 1, "op": "state"})
        return self.call({"protocol": 1, "op": op, "request_id": uuid4().hex,
                          "document_id": state["document_id"], **options})

    def save(self, path: Path, fmt: str):
        reply = self.operation("save_verified", path=str(path), target_format=fmt,
                               target_version="2018", overwrite=False)
        result = reply.get("result", {})
        if (result.get("verified") is not True or result.get("target_version") != "AC1032"
                or result.get("dropped_on_save") != 0):
            raise NativeCadError("CAD save was not verified losslessly as DWG/DXF 2018")
        return result

    def close(self):
        if self.process is not None and self.process.poll() is None:
            try:
                self.process.stdin.close()
                self.process.wait(timeout=3)
            except (subprocess.TimeoutExpired, BrokenPipeError):
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=3)
        stream = getattr(self, "stderr", None)
        if stream:
            stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def font_paths(controlled: dict) -> list[Path]:
    from .fonts import prepare_runtime_font
    resource_root = controlled["directory"].parents[1]
    render_font = prepare_runtime_font(controlled["fonts"], resource_root)
    hzdx = Path(os.environ.get("HEATER_HZDX_FONT", resource_root / "fixtures/case/HZDX.SHX"))
    expected = controlled["fonts"]["original_hzdx_shx"]["sha256"]
    if not hzdx.is_file() or digest(hzdx) != expected:
        raise NativeCadError("HZDX.SHX must match the engineer-supplied template font")
    return [hzdx, render_font]


def inspect_native_readback(raw: Path, pages, controlled: dict):
    """Allow only the known non-graphical orphan TABLESTYLE repair, on a sidecar."""
    doc = ezdxf.readfile(raw)
    orphan_styles = {e.dxf.handle for e in doc.objects
                     if e.dxftype() == "TABLESTYLE" and e.dxf.owner == "0"}
    audit = doc.audit()
    pattern = re.compile(r"Deleted TABLESTYLE\(#([0-9A-Fa-f]+)\) entity with invalid owner handle #0\.")
    for fix in audit.fixes:
        match = pattern.fullmatch(fix.message)
        if int(fix.code) != 202 or not match or match.group(1) not in orphan_styles:
            raise NativeCadError(f"Unexpected native DXF repair: {fix.message}")
    if audit.errors:
        raise NativeCadError(f"Native DXF audit errors: {[e.message for e in audit.errors]}")
    checked = raw
    if audit.fixes:
        checked = raw.with_name("normalized.dxf")
        doc.saveas(checked)
    report = inspect_dxf(checked, list(pages), controlled["layout"], controlled["fonts"])
    return {"passed": True, "sha256": digest(raw), "inspection": report,
            "auxiliary_repairs": [fix.message for fix in audit.fixes]}


def plot_options(page, controlled: dict) -> dict:
    factor = float(page.scale.denominator)
    origin = page.placement.model_origin_mm
    border = controlled["layout"]["outer_border_mm"]
    return {"layout": "Model", "area": "window", "window": [
        float(origin.x) + border["left"] * factor,
        float(origin.y) + border["bottom"] * factor,
        float(origin.x) + border["right"] * factor,
        float(origin.y) + border["top"] * factor,
    ], "paper": "ISO_full_bleed_A4_(210.00_x_297.00_MM)", "orientation": "Portrait",
        "fit": False, "scale": f"{SAMPLE_PRINT_SCALE / factor:.12g}:1", "center": False,
        "offset_x": SAMPLE_OFFSET_MM[0], "offset_y": SAMPLE_OFFSET_MM[1],
        "plot_style": "monochrome.ctb", "lineweights": True,
        "transparency": False, "stamp": False}


def plot_pages(session: NativeSession, dwg: Path, pages, controlled: dict, output: Path):
    session.call({"op": "open", "path": str(dwg.resolve())})
    state = session.call({"protocol": 1, "op": "state"})
    if state.get("missing_fonts"):
        raise NativeCadError(f"CAD fonts unresolved: {state['missing_fonts']}")
    reports = []
    for index, page in enumerate(pages, start=1):
        pdf = output / f"{page.code}.pdf"
        pdf.parent.mkdir(parents=True, exist_ok=True)
        options = plot_options(page, controlled)
        reply = session.operation("plot", path=str(pdf.resolve()), **options)
        raw_pdf_sha256 = digest(pdf)
        stroke_report = apply_sample_strokes(pdf)
        reader = PdfReader(pdf, strict=True)
        if len(reader.pages) != 1 or reply.get("result", {}).get("pages") != 1:
            raise NativeCadError("Native plot did not produce exactly one page")
        paper = reader.pages[0].mediabox
        if abs(float(paper.width) * 25.4 / 72 - 210) > .2 or abs(float(paper.height) * 25.4 / 72 - 297) > .2:
            raise NativeCadError("Native plot did not produce portrait A4")
        reports.append({"row_id": page.row_id, "code": page.code, "page_index": index,
                        "renderer": "opencadstudio", "source_dwg_sha256": digest(dwg),
                        "pdf_sha256": digest(pdf), "plot_options": options,
                        "native_plot_sha256": raw_pdf_sha256, "stroke_style": stroke_report,
                        "viewport_transform": {"origin_mm": [float(page.placement.model_origin_mm.x),
                                                                  float(page.placement.model_origin_mm.y)],
                                               "model_to_paper_scale": SAMPLE_PRINT_SCALE / float(page.scale.denominator)},
                        "print_policy": "sample_fit_to_frame"})
    return reports


def export_dwg_pdf(dxf: Path, dwg: Path, pages, controlled: dict, output: Path) -> dict:
    if dwg.exists():
        raise NativeCadError("DWG destination already exists")
    with tempfile.TemporaryDirectory(prefix="heater-native-") as folder:
        root = Path(folder)
        with NativeSession(root, font_paths(controlled)) as session:
            session.call({"op": "open", "path": str(dxf.resolve())})
            saved = session.save(dwg.resolve(), "dwg")
            if dwg.read_bytes()[:6] != b"AC1032":
                raise NativeCadError("Output is not DWG 2018")
            session.call({"op": "open", "path": str(dwg.resolve())})
            raw = root / "readback.dxf"
            reverse = session.save(raw, "dxf")
            readback = inspect_native_readback(raw, pages, controlled)
            reports = plot_pages(session, dwg, pages, controlled, output)
            return {"schema_version": 1, "adapter": "opencadstudio", "profile": PROFILE,
                    "version": session.greeting["version"], "executable_sha256": digest(session.executable),
                    "input_dxf_sha256": digest(dxf), "dwg_sha256": digest(dwg),
                    "fonts": session.fonts, "verified_save": saved,
                    "dimension_style": {
                        "font": controlled["fonts"].get("dimension_cad_font_file", controlled["fonts"]["render_cad_style_font_file"]),
                        "width_factor": controlled["fonts"].get("dimension_style_width_factor", 1.0),
                        "overrides": controlled["fonts"].get("dimension_overrides", {}),
                        "style_values": controlled["fonts"].get("dimension_style_values", {}),
                        "overrides_by_code": controlled["fonts"].get("dimension_overrides_by_code", {}),
                    },
                    "verified_reverse_save": reverse, "readback": readback,
                    "render_reports": reports, "autocad_reopen": "not_run"}


def verify_dwg_pdf(dwg: Path, pages, controlled: dict, output: Path) -> list[dict]:
    with tempfile.TemporaryDirectory(prefix="heater-native-verify-") as folder:
        root = Path(folder)
        with NativeSession(root, font_paths(controlled)) as session:
            session.call({"op": "open", "path": str(dwg.resolve())})
            raw = root / "readback.dxf"
            session.save(raw, "dxf")
            inspect_native_readback(raw, pages, controlled)
            return plot_pages(session, dwg, pages, controlled, output)
