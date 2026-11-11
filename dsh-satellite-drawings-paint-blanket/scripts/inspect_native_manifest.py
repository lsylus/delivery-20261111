"""Inventory existing sources without opening/modifying them in a native CAD tool."""
import argparse
import json
from pathlib import Path
from thermal_drawings.importers.manifest import inventory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.source_root.resolve()):
        parser.error('output must be outside the read-only source root')
    data = inventory(args.source_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(status='indexed_not_loaded', files=len(data['files']), output=str(args.output))))


if __name__ == '__main__':
    main()
