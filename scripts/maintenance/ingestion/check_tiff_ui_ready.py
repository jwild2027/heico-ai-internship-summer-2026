#!/usr/bin/env python
"""Check whether the local TIFF Streamlit UI has the files it needs."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.streamlit_ui_backend import format_status_text, load_ui_status  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-dir", default="local_data/organization/export")
    parser.add_argument("--manifest", default="local_data/pipeline_runs/latest_backend_pipeline.json")
    parser.add_argument("--quality", default="local_data/pipeline_runs/latest_quality_gate.json")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero if UI readiness is not OK.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    status = load_ui_status(export_dir=args.export_dir, manifest_path=args.manifest, quality_path=args.quality)
    print(format_status_text(status))
    return 1 if args.strict and not status.ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
