from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_dynamic_final_gate_execution_v1 import quality_report, read_json, write_json


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Dynamic Final-Gate Execution v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-queries", type=int, default=1)
    parser.add_argument("--min-results", type=int, default=1)
    parser.add_argument("--require-hybrid-v2-quality-pass", action="store_true")
    parser.add_argument("--require-final-answer-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)
    report = read_json(args.report_path)
    q = quality_report(
        report,
        min_queries=args.min_queries,
        min_results=args.min_results,
        require_hybrid_v2_quality_pass=args.require_hybrid_v2_quality_pass,
        require_final_answer_quality_pass=args.require_final_answer_quality_pass,
    )
    if args.write_json:
        path = Path(args.report_path).with_name("trace_net_dynamic_final_gate_execution_v1_quality.json")
        write_json(path, q)
    summary = q.get("summary", {})
    print("TRACE-Net Dynamic Final-Gate Execution v1 quality")
    print(f" Status: {q['status']}")
    for key in [
        "dynamic_gate_query_count",
        "final_answer_allowed_count",
        "final_claim_count",
        "uncited_final_claim_count",
        "retrieval_only_final_claim_count",
        "feedback_as_proof_count",
        "community_as_proof_count",
        "category_as_proof_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    return 0 if q["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
