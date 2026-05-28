#!/usr/bin/env python3
"""Export UI/API-friendly logical organization JSON files for the TIFF backend."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from tiff.local_config import load_local_config  # type: ignore
except Exception:  # pragma: no cover
    def load_local_config(path=None):  # type: ignore
        return {}

from tiff.document_organization_export import (  # noqa: E402
    DEFAULT_DB_PATH,
    DEFAULT_OUTPUT_DIR,
    build_document_organization_export,
    format_document_organization_export,
    write_document_organization_export,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None, help="Optional local_config.yaml/json path")
    parser.add_argument("--db-path", default=None, help="SQLite search/RAG DB path")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directory for organization JSON files")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero if organization export is not ready")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_local_config(args.config) if args.config else {}
    db_path = args.db_path or str(cfg.get("db_path") or DEFAULT_DB_PATH)

    export = build_document_organization_export(db_path, output_dir=args.output_dir)
    summary = write_document_organization_export(export, args.output_dir)
    print(format_document_organization_export(summary))

    if args.strict and not summary.ready:
        print("")
        print("Document organization export is not ready.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
