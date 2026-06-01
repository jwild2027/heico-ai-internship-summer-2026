#!/usr/bin/env python
"""Write production schema draft artifacts for PostgreSQL/OpenSearch/Qdrant."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.production_schema import (  # noqa: E402
    DEFAULT_OUTPUT_DIR,
    generated_artifacts,
    validate_schema_drafts,
    write_schema_drafts,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write production storage schema drafts.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--validate-only", action="store_true", help="Only validate existing artifacts; do not write.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.validate_only:
        issues = validate_schema_drafts(args.output_dir)
        status = "OK" if not issues else "FAIL"
        print("Production schema draft validation")
        print(f"  Status: {status}")
        print(f"  Output dir: {args.output_dir}")
        if issues:
            print("  Issues:")
            for issue in issues:
                print(f"    - {issue}")
        return 0 if not issues else 1

    summary = write_schema_drafts(args.output_dir)
    issues = validate_schema_drafts(args.output_dir)
    status = "OK" if not issues else "FAIL"

    print("Production schema drafts")
    print(f"  Status: {status}")
    print(f"  Schema version: {summary.schema_version}")
    print(f"  Output dir: {summary.output_dir}")
    print(f"  Artifacts written: {summary.artifacts_written}")
    print("\nPostgreSQL:")
    print(f"  Tables: {len(summary.postgres_tables)}")
    for name in summary.postgres_tables[:10]:
        print(f"    - {name}")
    if len(summary.postgres_tables) > 10:
        print(f"    ... {len(summary.postgres_tables) - 10} more")
    print("\nOpenSearch:")
    for name in summary.opensearch_indices:
        print(f"  - {name}")
    print("\nQdrant:")
    for name in summary.qdrant_collections:
        print(f"  - {name}")
    print("\nFiles written:")
    for artifact in generated_artifacts():
        print(f"  {args.output_dir / artifact.relative_path}")
    print(f"  {args.output_dir / 'production_schema_summary.json'}")
    if issues:
        print("\nValidation issues:")
        for issue in issues:
            print(f"  - {issue}")
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
