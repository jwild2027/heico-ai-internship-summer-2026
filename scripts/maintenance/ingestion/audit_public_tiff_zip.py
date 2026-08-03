#!/usr/bin/env python
"""Audit a public ResCarta-style TIFF ZIP without extracting it."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.public_tiff_zip_audit import (  # noqa: E402
    audit_public_tiff_zip,
    format_public_tiff_zip_audit,
    write_audit_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", required=True, dest="zip_path", help="Path to public TIFF ZIP file.")
    parser.add_argument("--sample-limit", type=int, default=10)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--json-output", default="local_data/batch_audit/public_tiff_zip_audit.json")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero when status is not OK.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        audit = audit_public_tiff_zip(args.zip_path, sample_limit=args.sample_limit)
    except Exception as exc:
        print(f"Public TIFF ZIP audit\n  Status: FAIL\n  Error: {exc}")
        return 1
    print(format_public_tiff_zip_audit(audit))
    if args.write_json:
        write_audit_json(audit, args.json_output)
        print(f"\nJSON: {args.json_output}")
    if args.strict and audit.status != "OK":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
