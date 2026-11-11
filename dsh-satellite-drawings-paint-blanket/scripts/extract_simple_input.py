"""Extract just the original STEP, without unpacking unrelated archive contents."""
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
archive = ROOT / "work/simple-inputs/source.zip"
target = ROOT / "work/simple-inputs/satellite-assembly.step"
with zipfile.ZipFile(archive) as source:
    entries = [x for x in source.infolist() if x.filename.lower().endswith((".step", ".stp"))]
    if len(entries) != 1:
        raise ValueError(f"Expected one original STEP, found {len(entries)}")
    with source.open(entries[0]) as input_file, target.open("wb") as output_file:
        shutil.copyfileobj(input_file, output_file, 1024 * 1024)
print(target, target.stat().st_size)
