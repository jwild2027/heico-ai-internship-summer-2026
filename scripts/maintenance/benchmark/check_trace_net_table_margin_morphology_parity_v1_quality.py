import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_table_margin_morphology_parity_v1 import Thresholds
from tiff.trace_net_table_margin_morphology_parity_v1_quality import check_quality


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net table margin morphology parity quality.")
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--min-parity-cards", type=int, default=1)
    parser.add_argument("--min-experiment-improvement-cards", type=int, default=0)
    parser.add_argument("--min-parity-gap-cards", type=int, default=0)
    parser.add_argument("--max-unsafe-parity-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-line-geometry-quality-pass", action="store_true")
    parser.add_argument("--require-margin-experiment-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()
    quality = check_quality(
        args.report_path,
        Thresholds(
            min_parity_cards=args.min_parity_cards,
            min_experiment_improvement_cards=args.min_experiment_improvement_cards,
            min_parity_gap_cards=args.min_parity_gap_cards,
            max_unsafe_parity_cards=args.max_unsafe_parity_cards,
            max_answer_permission_count=args.max_answer_permission_count,
            max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
            require_table_line_geometry_quality_pass=args.require_table_line_geometry_quality_pass,
            require_margin_experiment_quality_pass=args.require_margin_experiment_quality_pass,
            require_no_answer_permission=args.require_no_answer_permission,
        ),
        write_quality=args.write_json,
    )
    summary = quality["summary"]
    print("TRACE-Net Table Margin Morphology Parity v1 quality")
    print(f" Status: {quality['quality_status']}")
    for key in (
        "parity_card_count",
        "experiment_improvement_card_count",
        "production_margin_selected_card_count",
        "parity_gap_card_count",
        "unsafe_parity_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    return 0 if quality["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
