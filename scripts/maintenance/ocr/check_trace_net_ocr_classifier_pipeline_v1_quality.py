from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_ocr_classifier_pipeline_runner_v1 import check_quality


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Check TRACE-Net OCR/classifier pipeline runner quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-stage-reports", type=int, default=9)
    parser.add_argument("--min-postgres-contract-ready", type=int, default=509)
    parser.add_argument("--min-qdrant-contract-ready", type=int, default=400)
    parser.add_argument("--min-opensearch-contract-ready", type=int, default=250)
    parser.add_argument("--min-qdrant-payloads", type=int, default=400)
    parser.add_argument("--min-opensearch-payloads", type=int, default=250)
    parser.add_argument("--max-violation-records", type=int, default=0)
    parser.add_argument("--require-all-stage-quality-pass", action="store_true")
    parser.add_argument("--require-dry-run-only", action="store_true")
    parser.add_argument("--require-no-human-review-required", action="store_true")
    parser.add_argument("--max-unsafe", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args()

    check_quality(
        report_path=args.report_path,
        write_json=args.write_json,
        min_stage_reports=args.min_stage_reports,
        min_postgres_contract_ready=args.min_postgres_contract_ready,
        min_qdrant_contract_ready=args.min_qdrant_contract_ready,
        min_opensearch_contract_ready=args.min_opensearch_contract_ready,
        min_qdrant_payloads=args.min_qdrant_payloads,
        min_opensearch_payloads=args.min_opensearch_payloads,
        max_violation_records=args.max_violation_records,
        require_all_stage_quality_pass=args.require_all_stage_quality_pass,
        require_dry_run_only=args.require_dry_run_only,
        require_no_human_review_required=args.require_no_human_review_required,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
    )


if __name__ == "__main__":
    main()
