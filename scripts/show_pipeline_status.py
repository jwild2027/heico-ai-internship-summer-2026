#!/usr/bin/env python
"""Print the latest TIFF backend pipeline manifest summary."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.pipeline_manifest import (  # noqa: E402
    DEFAULT_MANIFEST_DIR,
    format_manifest_summary,
    read_json_file,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show a TIFF backend pipeline run manifest summary.")
    parser.add_argument("--manifest", default=None, help="Specific manifest JSON path.")
    parser.add_argument("--manifest-dir", default=DEFAULT_MANIFEST_DIR, help="Manifest directory.")
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of a formatted summary.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest) if args.manifest else Path(args.manifest_dir) / "latest_backend_pipeline.json"
    manifest = read_json_file(manifest_path)
    if manifest is None:
        print(f"No readable pipeline manifest found: {manifest_path}", file=sys.stderr)
        return 1

    if args.json:
        print(manifest_path.read_text(encoding="utf-8"), end="")
    else:
        print(format_manifest_summary(manifest))
        print(f"\nManifest path: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
