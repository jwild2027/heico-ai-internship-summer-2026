#!/usr/bin/env python3
"""Run the local browser-based TIFF search UI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.search_web_ui import run_server  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve a local browser UI for the TIFF search database.")
    parser.add_argument(
        "--db-path",
        default="local_data/db/tiff_search.db",
        help="SQLite search database created by build_tiff_search_index.py.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host/interface for the local web server.")
    parser.add_argument("--port", type=int, default=8080, help="Port for the local web server.")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Base folder used to resolve relative TIFF/OCR paths stored in the search database.",
    )
    parser.add_argument("--open", action="store_true", help="Open the search UI in your browser automatically.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_server(
        db_path=Path(args.db_path),
        host=args.host,
        port=args.port,
        repo_root=Path(args.repo_root),
        open_browser=args.open,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
