"""Command-line wrapper for the installable real OpenCADStudio preview module."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "service/src"))
from thermal_drawings.drawing.opencad_preview import main
if __name__ == "__main__":
    main()
