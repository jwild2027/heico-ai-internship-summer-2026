#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.rescarta_deeplink import DEFAULT_DB_PATH, DEFAULT_TEMPLATE, SourceLinkRow, build_tokens, connect_db, fetch_source_rows, is_placeholder_url, render_url, template_fields, validate_template


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a ResCarta URL template against current source_links data.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--url-template", default=DEFAULT_TEMPLATE)
    args = parser.parse_args()

    with connect_db(args.db_path) as conn:
        rows = fetch_source_rows(conn, limit=1)
    if not rows:
        print("No source_links rows found.")
        return 2
    row = SourceLinkRow.from_mapping(rows[0])
    tokens = build_tokens(row, args.base_url)
    validate_template(args.url_template, tokens.keys())
    proposed = render_url(args.url_template, row, args.base_url)

    print("ResCarta template validation")
    print("  Status: OK")
    print(f"  DB: {args.db_path}")
    print(f"  Base URL: {args.base_url.rstrip('/')}")
    print(f"  Template fields: {', '.join(sorted(template_fields(args.url_template)))}")
    print(f"  Proposed URL is placeholder: {is_placeholder_url(proposed)}")
    print("  Sample tokens:")
    for key in sorted(tokens):
        print(f"    {key}: {tokens[key]}")
    print(f"  Sample URL: {proposed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
