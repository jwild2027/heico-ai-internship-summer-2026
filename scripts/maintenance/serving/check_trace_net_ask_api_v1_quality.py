from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_ask_api_v1 import quality_report, write_json


def main() -> int:
    p = argparse.ArgumentParser(description="Check TRACE-Net Ask API v1 quality")
    p.add_argument("--report-path", type=Path, required=True)
    p.add_argument("--require-final-answer-quality-pass", action="store_true")
    p.add_argument("--write-json", action="store_true")
    args = p.parse_args()

    report = json.loads(args.report_path.read_text(encoding="utf-8"))
    quality = quality_report(report, require_final_answer_quality_pass=args.require_final_answer_quality_pass)
    if args.write_json:
        out = args.report_path.with_name("trace_net_ask_api_v1_quality.json")
        write_json(out, quality)
    print("TRACE-Net Ask API v1 quality")
    print(f" Status: {quality['quality_status']}")
    summary = quality["summary"]
    for key in [
        "read_only_api",
        "source_truth_mutation_allowed_count",
        "feedback_as_proof_count",
        "community_as_proof_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "final_answer_quality_status",
    ]:
        print(f" {key}: {summary.get(key)}")
    return 0 if quality["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
