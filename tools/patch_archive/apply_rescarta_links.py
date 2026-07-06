#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.rescarta_deeplink import DEFAULT_DB_PATH, DEFAULT_TEMPLATE, connect_db, fetch_source_rows, preview_links, source_link_columns, update_source_link_urls


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply real ResCarta deep-link URLs to the source_links table.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--url-template", default=DEFAULT_TEMPLATE)
    parser.add_argument("--limit", type=int, default=None, help="Limit rows for a controlled test update")
    parser.add_argument("--dry-run", action="store_true", help="Preview only; do not update")
    parser.add_argument("--confirm", action="store_true", help="Required for real updates")
    parser.add_argument("--keep-source-url", action="store_true", help="Update rescarta_url only; leave source_url unchanged")
    args = parser.parse_args()

    with connect_db(args.db_path) as conn:
        rows = fetch_source_rows(conn, limit=min(args.limit or 5, 5))
        cols = source_link_columns(conn)
        previews = preview_links(rows, args.url_template, args.base_url)

        print("Apply ResCarta deep links")
        print(f"  DB: {args.db_path}")
        print(f"  Base URL: {args.base_url.rstrip('/')}")
        print(f"  Template: {args.url_template}")
        print(f"  source_url column present: {'source_url' in cols}")
        print(f"  Mode: {'dry-run' if args.dry_run else 'apply'}")
        print()
        print("Preview:")
        for idx, item in enumerate(previews, 1):
            print(f"  {idx}. {item['page_id']}")
            print(f"     Current:  {item['current_rescarta_url']}")
            print(f"     Proposed: {item['proposed_rescarta_url']}")

        if args.dry_run:
            print("\nDry run only. No DB rows updated.")
            return 0
        if not args.confirm:
            print("\nRefusing to update without --confirm. Rerun with --dry-run first, then --confirm.")
            return 2

        count = update_source_link_urls(
            conn,
            args.url_template,
            args.base_url,
            update_source_url=not args.keep_source_url,
            limit=args.limit,
        )
        conn.commit()

    print(f"\nUpdated source_links rows: {count}")
    print("Next recommended commands:")
    print("  python scripts/audit_source_links.py --config local_config.yaml --strict")
    print("  python scripts/run_tiff_backend_pipeline.py --config local_config.yaml")
    print("  python scripts/check_pipeline_quality.py --require-incremental-smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
