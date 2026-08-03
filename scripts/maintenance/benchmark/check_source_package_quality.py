#!/usr/bin/env python
"""Check raw source-package to organization traceability quality."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.source_package_quality import (  # noqa: E402
    DEFAULT_SOURCE_PACKAGE_QUALITY_JSON,
    DEFAULT_SOURCE_TRACEABILITY_JSON,
    SourcePackageQualityThresholds,
    build_source_package_quality_result,
    format_source_package_quality_result,
    write_source_package_quality_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traceability-json", default=DEFAULT_SOURCE_TRACEABILITY_JSON)
    parser.add_argument("--json-output", default=DEFAULT_SOURCE_PACKAGE_QUALITY_JSON)
    parser.add_argument("--max-zip-only-pages", type=int, default=0)
    parser.add_argument("--max-organization-only-pages", type=int, default=0)
    parser.add_argument("--max-duplicate-zip-page-numbers", type=int, default=0)
    parser.add_argument("--max-duplicate-organization-page-numbers", type=int, default=0)
    parser.add_argument("--allow-missing-metadata-xml", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()

    result = build_source_package_quality_result(
        args.traceability_json,
        thresholds=SourcePackageQualityThresholds(
            max_zip_tiffs_without_organization_page=args.max_zip_only_pages,
            max_organization_pages_without_zip_tiff=args.max_organization_only_pages,
            max_duplicate_zip_page_numbers=args.max_duplicate_zip_page_numbers,
            max_duplicate_organization_page_numbers=args.max_duplicate_organization_page_numbers,
            require_metadata_xml=not args.allow_missing_metadata_xml,
        ),
    )
    print(format_source_package_quality_result(result))
    if args.write_json:
        path = write_source_package_quality_json(result, args.json_output)
        print()
        print(f"JSON: {path}")
    return 0 if result.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
