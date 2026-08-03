from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_promotion_writeback_dry_run_v1 import quality_report, write_json


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check TRACE-Net promotion writeback dry-run quality v1")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-writeback-plans", type=int, default=0)
    parser.add_argument("--require-promotion-gate-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    path = Path(args.report_path)
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        quality = quality_report(
            report,
            min_writeback_plans=args.min_writeback_plans,
            require_promotion_gate_quality_pass=args.require_promotion_gate_quality_pass,
        )
        if args.write_json:
            quality_path = path.with_name("trace_net_promotion_writeback_dry_run_v1_quality.json")
            write_json(quality_path, quality)
        else:
            quality_path = path.with_name("trace_net_promotion_writeback_dry_run_v1_quality.json")
    except Exception as exc:
        print(f"TRACE-Net promotion writeback dry run quality check failed: {exc}")
        return 1

    print("TRACE-Net promotion writeback dry run v1 quality")
    print(f" Status: {quality['quality_status']}")
    print(f" writeback_plan_count: {quality['writeback_plan_count']}")
    print(f" promotion_candidate_count: {quality['promotion_candidate_count']}")
    print(f" approved_promotion_candidate_count: {quality['approved_promotion_candidate_count']}")
    print(f" postgres_write_attempt_count: {quality['postgres_write_attempt_count']}")
    print(f" source_truth_mutation_allowed_count: {quality['source_truth_mutation_allowed_count']}")
    print(f" direct_answer_allowed_count: {quality['direct_answer_allowed_count']}")
    print(f" claim_proof_allowed_count: {quality['claim_proof_allowed_count']}")
    if args.write_json:
        print(f" quality_path: {quality_path}")
    return 0 if quality["quality_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
