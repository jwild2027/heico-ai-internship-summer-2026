from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_dublin_core_source_package_extension_v1 import check_quality


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Dublin Core Source Package Extension v1 quality")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--require-page-count", type=int, default=None)
    parser.add_argument("--min-page-records", type=int, default=1)
    parser.add_argument("--min-pages-with-source-package-entry", type=int, default=1)
    parser.add_argument("--require-metadata-xml", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()
    quality = check_quality(
        report_path=args.report_path,
        require_page_count=args.require_page_count,
        min_page_records=args.min_page_records,
        min_pages_with_source_package_entry=args.min_pages_with_source_package_entry,
        require_metadata_xml=args.require_metadata_xml,
        write_json_report=args.write_json,
    )
    print("TRACE-Net Dublin Core Source Package Extension v1 quality")
    print(f" Status: {quality['status']}")
    for key in [
        "page_record_count",
        "document_record_count",
        "pages_with_source_package_entry_count",
        "missing_source_package_entry_count",
        "checksum_mismatch_count",
        "source_truth_mutation_allowed_count",
        "direct_answer_allowed_count",
        "claim_proof_allowed_count",
    ]:
        print(f" {key}: {quality.get(key)}")
    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
