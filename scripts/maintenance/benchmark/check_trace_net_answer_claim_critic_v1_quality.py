#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_answer_claim_critic_v1 import quality_report, read_json, write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Answer Claim Critic v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-answer-records", type=int, default=1)
    parser.add_argument("--min-queries", type=int, default=1)
    parser.add_argument("--min-claim-records", type=int, default=0)
    parser.add_argument("--require-dynamic-final-gate-quality-pass", action="store_true")
    parser.add_argument("--require-evidence-sufficiency-quality-pass", action="store_true")
    parser.add_argument("--require-retrieval-critic-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = read_json(args.report_path)
    q = quality_report(
        report,
        min_answer_records=args.min_answer_records,
        min_queries=args.min_queries,
        min_claim_records=args.min_claim_records,
        require_dynamic_final_gate_quality_pass=args.require_dynamic_final_gate_quality_pass,
        require_evidence_sufficiency_quality_pass=args.require_evidence_sufficiency_quality_pass,
        require_retrieval_critic_quality_pass=args.require_retrieval_critic_quality_pass,
    )
    if args.write_json:
        out = Path(args.report_path).with_name("trace_net_answer_claim_critic_v1_quality.json")
        write_json(out, q)
    summary = q.get("summary", {})
    print("TRACE-Net Answer Claim Critic v1 quality")
    print(f" Status: {q['status']}")
    for key in [
        "answer_claim_record_count",
        "claim_critic_record_count",
        "answer_claims_clear_for_return_count",
        "answer_claims_clear_but_audit_required_count",
        "answer_claims_need_audit_count",
        "local_path_leak_count",
        "raw_bytes_repr_count",
        "feedback_as_proof_count",
        "community_as_proof_count",
        "category_as_proof_count",
        "retrieval_only_as_proof_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    return 0 if q["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
