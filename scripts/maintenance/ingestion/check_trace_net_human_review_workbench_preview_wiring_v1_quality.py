from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_human_review_workbench_preview_wiring_v1 import print_quality_summary, quality_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Human Review Workbench Source/Image Preview Wiring v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-workbench-cards", type=int, default=1)
    parser.add_argument("--min-page-profiles", type=int, default=1)
    parser.add_argument("--min-page-scoped-cards", type=int, default=1)
    parser.add_argument("--min-cards-with-page-preview", type=int, default=1)
    parser.add_argument("--min-cards-with-source-package-summary", type=int, default=1)
    parser.add_argument("--min-page-profiles-with-preview", type=int, default=1)
    parser.add_argument("--require-source-workbench-quality-pass", action="store_true")
    parser.add_argument("--require-source-package-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    quality = quality_report(
        report_path=args.report_path,
        min_workbench_cards=args.min_workbench_cards,
        min_page_profiles=args.min_page_profiles,
        min_page_scoped_cards=args.min_page_scoped_cards,
        min_cards_with_page_preview=args.min_cards_with_page_preview,
        min_cards_with_source_package_summary=args.min_cards_with_source_package_summary,
        min_page_profiles_with_preview=args.min_page_profiles_with_preview,
        require_source_workbench_quality_pass=args.require_source_workbench_quality_pass,
        require_source_package_quality_pass=args.require_source_package_quality_pass,
        write_json_report=args.write_json,
    )
    print_quality_summary(quality)
    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
