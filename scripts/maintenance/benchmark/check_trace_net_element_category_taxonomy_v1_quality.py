from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_element_category_taxonomy_v1 import quality_report, write_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Element Category Taxonomy v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-page-profiles", type=int, default=0)
    parser.add_argument("--min-categorized-elements", type=int, default=1)
    parser.add_argument("--min-diagram-categories", type=int, default=0)
    parser.add_argument("--min-table-categories", type=int, default=0)
    parser.add_argument("--min-part-categories", type=int, default=0)
    parser.add_argument("--min-review-categories", type=int, default=0)
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    report_path = Path(args.report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    quality = quality_report(
        report,
        require_page_count=args.require_page_count,
        min_page_profiles=args.min_page_profiles,
        min_categorized_elements=args.min_categorized_elements,
        min_diagram_categories=args.min_diagram_categories,
        min_table_categories=args.min_table_categories,
        min_part_categories=args.min_part_categories,
        min_review_categories=args.min_review_categories,
    )
    if args.write_json:
        quality_path = report_path.with_name("trace_net_element_category_taxonomy_v1_quality.json")
        write_json(quality_path, quality)
    print("TRACE-Net element category taxonomy v1 quality")
    print(f" Status: {quality['status']}")
    for key in [
        "page_count",
        "page_category_profile_count",
        "category_record_count",
        "categorized_element_count",
        "diagram_category_count",
        "table_category_count",
        "part_category_count",
        "review_category_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {quality.get(key)}")
    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
