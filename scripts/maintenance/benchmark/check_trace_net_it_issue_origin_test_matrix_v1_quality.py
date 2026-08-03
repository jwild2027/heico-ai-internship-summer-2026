import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_it_issue_origin_test_matrix_v1 import check_it_issue_origin_test_matrix_quality


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net IT issue-origin test matrix v1 quality")
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--min-scenarios", type=int, default=60)
    parser.add_argument("--min-origin-categories", type=int, default=15)
    parser.add_argument("--allow-undetected-scenarios", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()
    quality = check_it_issue_origin_test_matrix_quality(
        report_path=args.report_path,
        min_scenarios=args.min_scenarios,
        min_origin_categories=args.min_origin_categories,
        require_all_scenarios_detected=not args.allow_undetected_scenarios,
        write_json_report=args.write_json,
    )
    print("TRACE-Net IT issue-origin test matrix v1 quality")
    print(f" Status: {quality['status']}")
    summary = quality["summary"]
    for key in [
        "scenario_count",
        "origin_category_count",
        "detected_scenario_count",
        "undetected_scenario_count",
        "critical_scenario_count",
        "warning_scenario_count",
        "review_scenario_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    if quality.get("quality_path"):
        print(f" quality_path: {quality['quality_path']}")
    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
