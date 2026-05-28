#!/usr/bin/env python3
"""Print a logical manual/ATA/part organization audit for the TIFF backend."""

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

from tiff.document_organization_audit import (  # noqa: E402
    DEFAULT_DB_PATH,
    audit_document_organization,
    format_document_organization_audit,
    write_document_organization_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None, help="Optional local_config.yaml/json path")
    parser.add_argument("--db-path", default=None, help="SQLite search/RAG DB path")
    parser.add_argument("--top-ata", type=int, default=20, help="Number of manual/ATA groups to print")
    parser.add_argument("--top-parts", type=int, default=20, help="Number of part-tree entries to print")
    parser.add_argument("--write-json", action="store_true", help="Write JSON output")
    parser.add_argument("--json-output", default="local_data/organization/document_organization_audit.json")
    parser.add_argument("--no-refresh-manifest", action="store_true", help="Accepted for pipeline compatibility; this audit does not refresh manifests directly.")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero if the logical tree is not ready")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_local_config(args.config) if args.config else {}
    db_path = args.db_path or str(cfg.get("db_path") or DEFAULT_DB_PATH)

    summary = audit_document_organization(
        db_path,
        top_ata_limit=max(1, args.top_ata),
        top_part_limit=max(1, args.top_parts),
    )
    print(
        format_document_organization_audit(
            summary,
            top_ata_limit=max(0, args.top_ata),
            top_part_limit=max(0, args.top_parts),
        )
    )

    if args.write_json:
        path = write_document_organization_json(summary, args.json_output)
        print("")
        print(f"JSON: {path}")

    if args.strict and not summary.logical_tree_ready:
        print("")
        print("Logical document organization is not ready.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
