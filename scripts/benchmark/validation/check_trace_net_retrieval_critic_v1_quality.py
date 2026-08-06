from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_retrieval_critic_v1 import quality_report, read_json, write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Retrieval Critic v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-critic-records", type=int, default=1)
    parser.add_argument("--min-queries", type=int, default=1)
    parser.add_argument("--require-hybrid-v2-quality-pass", action="store_true")
    parser.add_argument("--require-dynamic-final-gate-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = read_json(args.report_path)
    q = quality_report(
        report,
        min_critic_records=args.min_critic_records,
        min_queries=args.min_queries,
        require_hybrid_v2_quality_pass=args.require_hybrid_v2_quality_pass,
        require_dynamic_final_gate_quality_pass=args.require_dynamic_final_gate_quality_pass,
    )
    if args.write_json:
        out = Path(args.report_path).with_name("trace_net_retrieval_critic_v1_quality.json")
        write_json(out, q)
    print("TRACE-Net Retrieval Critic v1 quality")
    print(f" Status: {q['status']}")
    summary = q["summary"]
    for key in [
        "critic_record_count",
        "strong_enough_for_final_gate_attempt_count",
        "retrieval_only_not_answer_ready_count",
        "needs_exact_search_count",
        "needs_semantic_expansion_count",
        "abstain_no_evidence_count",
        "unsafe_critic_record_count",
        "critic_can_answer_directly_count",
        "critic_can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key, 0)}")
    return 0 if q["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
