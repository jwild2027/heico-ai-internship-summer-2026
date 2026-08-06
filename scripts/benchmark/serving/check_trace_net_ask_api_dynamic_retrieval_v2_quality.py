from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_ask_api_dynamic_retrieval_v2 import quality_report, read_json, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Ask API Dynamic Retrieval v2 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--require-dynamic-retrieval-available", action="store_true")
    parser.add_argument("--require-final-answer-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()

    report = read_json(Path(args.report_path))
    q = quality_report(
        report,
        require_dynamic_retrieval_available=args.require_dynamic_retrieval_available,
        require_final_answer_quality_pass=args.require_final_answer_quality_pass,
    )
    quality_path = Path(args.report_path).with_name("trace_net_ask_api_dynamic_retrieval_v2_quality.json")
    if args.write_json:
        write_json(quality_path, q)
    s = q.get("summary", {})
    print("TRACE-Net Ask API Dynamic Retrieval v2 quality")
    print(f" Status: {q.get('status')}")
    print(f" read_only_api: {s.get('read_only_api')}")
    print(f" dynamic_retrieval_available: {s.get('dynamic_retrieval_available')}")
    print(f" source_truth_mutation_allowed_count: {s.get('source_truth_mutation_allowed_count')}")
    print(f" feedback_as_proof_count: {s.get('feedback_as_proof_count')}")
    print(f" community_as_proof_count: {s.get('community_as_proof_count')}")
    print(f" category_as_proof_count: {s.get('category_as_proof_count')}")
    print(f" retrieval_only_answer_allowed_count: {s.get('retrieval_only_answer_allowed_count')}")
    print(f" postgres_write_attempt_count: {s.get('postgres_write_attempt_count')}")
    print(f" qdrant_write_attempt_count: {s.get('qdrant_write_attempt_count')}")
    print(f" opensearch_write_attempt_count: {s.get('opensearch_write_attempt_count')}")
    if args.write_json:
        print(f" quality_path: {quality_path}")
    return 0 if q.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
