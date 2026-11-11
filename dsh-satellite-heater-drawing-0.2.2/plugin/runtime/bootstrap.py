"""Install bundled, hash-locked wheels offline into private per-profile storage."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

if sys.version_info[:2] != (3, 12):
    raise SystemExit("需要 Python 3.12，请配置 pythonExecutable")
package = Path(__file__).resolve().parent
data = Path(os.environ["HEATER_PROFILE_DATA"]).resolve()
data.mkdir(parents=True, exist_ok=True, mode=0o700)
os.umask(0o077)
manifest = json.loads((package / "files.json").read_text())
for name, expected in manifest.items():
    source = package / name
    if source.is_symlink() or not source.resolve().is_relative_to(package) or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
        raise SystemExit("插件运行文件校验失败: " + name)
identity = hashlib.sha256((package / "files.json").read_bytes()).hexdigest()[:20]
release = data / ("engine-" + identity)
environment = data / ("venv-" + hashlib.sha256((package / "requirements.txt").read_bytes()).hexdigest()[:20])
with (data / "bootstrap.lock").open("w") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    if not (environment / "complete").is_file():
        venv.EnvBuilder(with_pip=True).create(environment)
        subprocess.run([str(environment / "bin/python"), "-m", "pip", "install", "--disable-pip-version-check",
                        "--no-index", "--find-links", str(package / "wheels"), "--require-hashes",
                        "-r", str(package / "requirements.txt")], check=True, stdout=sys.stderr)
        (environment / "complete").write_text(identity)
    if not release.is_dir():
        temporary = data / ("engine-" + identity + ".preparing")
        if temporary.exists():
            assert temporary.parent == data
            shutil.rmtree(temporary)
        temporary.mkdir()
        for name in ("service", "templates", "schemas"):
            shutil.copytree(package / name, temporary / name)
        temporary.replace(release)
os.environ.update(PYTHONPATH=str(release / "service/src"),
                  HEATER_TEMPLATE_DIR=str(release / "templates/heater-a4-v1"),
                  HEATER_DRAWING_RESOURCE_ROOT=str(release),
                  HEATER_DATA_DIR=str(data / "jobs-data"), HEATER_PARENT_BOUND="1")
os.execv(str(environment / "bin/python"), [str(environment / "bin/python"), "-m", "heater_drawing.app.server"])
