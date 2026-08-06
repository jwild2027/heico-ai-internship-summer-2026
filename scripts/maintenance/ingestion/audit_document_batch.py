#!/usr/bin/env python3
"""Read-only intake audit for a TIFF/ResCarta document batch folder."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.document_batch_audit import audit_document_batch, format_batch_audit_report, write_batch_audit_json  # noqa: E402


CONFIG_ROOT_KEYS = (
    "rescarta_export_dir",
    "rescarta_export_root",
    "rescarta_exports_dir",
    "export_root",
    "tiff_root",
    "input_root",
)


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
        return value[1:-1]
    return value


def root_from_config(config_path: str | Path) -> str | None:
    """Very small YAML-ish key reader to avoid adding dependencies."""

    path = Path(config_path)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    for key in CONFIG_ROOT_KEYS:
        pattern = re.compile(rf"^\s*{re.escape(key)}\s*:\s*(.+?)\s*$", re.MULTILINE)
        match = pattern.search(text)
        if match:
            value = _strip_quotes(match.group(1).split("#", 1)[0])
            if value:
                return value
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="Batch folder to audit. Defaults to a ResCarta/export root from config, then local_data/rescarta_exports.")
    parser.add_argument("--config", default="local_config.yaml")
    parser.add_argument("--max-files", type=int, default=250_000, help="Stop scanning after this many files so the audit stays safe on huge trees.")
    parser.add_argument("--sample-limit", type=int, default=10)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--json-output", default="local_data/batch_audit/document_batch_audit.json")
    args = parser.parse_args(argv)

    root = args.root or root_from_config(args.config) or "local_data/rescarta_exports"
    report = audit_document_batch(root, max_files=args.max_files)
    print(format_batch_audit_report(report, sample_limit=args.sample_limit))

    if args.write_json:
        path = write_batch_audit_json(report, args.json_output)
        print()
        print(f"JSON: {path}")

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
