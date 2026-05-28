#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.rescarta_deeplink import DEFAULT_DB_PATH, DEFAULT_TEMPLATE, connect_db, fetch_source_rows, preview_links, render_url, validate_template, build_tokens, SourceLinkRow


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview real ResCarta deep-link URLs from source_links rows.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--base-url", required=True, help="Real ResCarta-Web base URL, e.g. https://host/ResCarta-Web")
    parser.add_argument("--url-template", default=DEFAULT_TEMPLATE, help="URL template using tokens like {base_url}, {object_id}, {page_id}, {page_name}")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--json-output", default="local_data/source_links/rescarta_link_preview.json")
    parser.add_argument("--show-tokens", action="store_true")
    args = parser.parse_args()

    with connect_db(args.db_path) as conn:
        rows = fetch_source_rows(conn, limit=args.limit)
    if not rows:
        print("No source_links rows found.")
        return 2

    # Validate once against the first real row.
    first_tokens = build_tokens(SourceLinkRow.from_mapping(rows[0]), args.base_url)
    validate_template(args.url_template, first_tokens.keys())
    previews = preview_links(rows, args.url_template, args.base_url)

    print("ResCarta deep-link preview")
    print(f"  DB: {args.db_path}")
    print(f"  Base URL: {args.base_url.rstrip('/')}")
    print(f"  Template: {args.url_template}")
    print(f"  Rows previewed: {len(previews)}")
    print()

    if args.show_tokens:
        print("Available template tokens:")
        for key in sorted(first_tokens):
            print(f"  {key}: {first_tokens[key]}")
        print()

    for idx, item in enumerate(previews, 1):
        print(f"{idx}. page={item['page_id']} manual={item['manual_id']} ata={item['ata_code']} label={item['page_label']}")
        print(f"   Current:  {item['current_rescarta_url']}")
        print(f"   Proposed: {item['proposed_rescarta_url']}")

    if args.write_json:
        output = Path(args.json_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"previews": previews, "template": args.url_template, "base_url": args.base_url}, indent=2), encoding="utf-8")
        print(f"\nJSON: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
