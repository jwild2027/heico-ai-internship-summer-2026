"""Quality checker for TRACE-Net LLaVA visual summary batch v1."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

MODULE_NAME = "trace_net_llava_visual_summary_batch_v1"
EXPECTED_STATUS = "TRACE_NET_LLAVA_VISUAL_SUMMARY_BATCH_BUILT"


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def bool_count(records: Sequence[Mapping[str, Any]], key: str) -> int:
    return sum(1 for record in records if bool(record.get(key)))


def add_check(checks: List[Dict[str, Any]], name: str, passed: bool, observed: Any, expected: str) -> None:
    checks.append({"name": name, "passed": bool(passed), "observed": observed, "expected": expected})


def evaluate(batch: Mapping[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    records = list(batch.get("records") or [])
    summary = dict(batch.get("summary") or {})
    safety = dict(batch.get("safety_contract") or {})
    checks: List[Dict[str, Any]] = []

    llava_summary_count = int(summary.get("llava_summary_count") or len(records))
    structured_json_count = int(summary.get("structured_json_count") or bool_count(records, "structured_json_ready"))
    figure_candidate_count = int(summary.get("figure_candidate_count") or 0)
    callout_candidate_count = int(summary.get("callout_candidate_count") or 0)
    source_trace_ready_count = int(summary.get("source_trace_ready_count") or bool_count(records, "source_trace_ready"))
    unsafe_count = int(summary.get("unsafe_record_count") or bool_count(records, "unsafe"))
    answer_permission_count = int(summary.get("answer_permission_count") or bool_count(records, "answer_permission"))
    mutation_count = int(summary.get("source_truth_mutation_allowed_count") or bool_count(records, "source_truth_mutation_allowed"))
    write_count = int(summary.get("write_attempt_count") or sum(int(r.get("write_attempt_count") or 0) for r in records))

    add_check(checks, "module_name", batch.get("module_name") == MODULE_NAME, batch.get("module_name"), MODULE_NAME)
    add_check(checks, "status", batch.get("status") == EXPECTED_STATUS, batch.get("status"), EXPECTED_STATUS)
    if args.require_quality_pass:
        add_check(checks, "quality_status", batch.get("quality_status") == "PASS", batch.get("quality_status"), "PASS")
    add_check(checks, "llava_summary_count", llava_summary_count >= args.min_llava_summaries, llava_summary_count, f">= {args.min_llava_summaries}")
    add_check(checks, "structured_json_count", structured_json_count >= args.min_structured_json, structured_json_count, f">= {args.min_structured_json}")
    add_check(checks, "source_trace_ready_count", source_trace_ready_count >= args.min_source_trace_ready, source_trace_ready_count, f">= {args.min_source_trace_ready}")
    add_check(checks, "unsafe_record_count", unsafe_count <= args.max_unsafe, unsafe_count, f"<= {args.max_unsafe}")
    add_check(checks, "answer_permission_count", answer_permission_count <= args.max_answer_permission, answer_permission_count, f"<= {args.max_answer_permission}")
    add_check(checks, "source_truth_mutation_allowed_count", mutation_count <= args.max_source_truth_mutation_allowed, mutation_count, f"<= {args.max_source_truth_mutation_allowed}")
    add_check(checks, "write_attempt_count", write_count <= args.max_write_attempts, write_count, f"<= {args.max_write_attempts}")
    add_check(checks, "ready_for_visual_linking", bool(summary.get("ready_for_visual_linking")), summary.get("ready_for_visual_linking"), "true")
    add_check(checks, "safety_postgres_writes_false", safety.get("postgres_writes") is False, safety.get("postgres_writes"), "False")
    add_check(checks, "safety_qdrant_writes_false", safety.get("qdrant_writes") is False, safety.get("qdrant_writes"), "False")
    add_check(checks, "safety_opensearch_writes_false", safety.get("opensearch_writes") is False, safety.get("opensearch_writes"), "False")
    add_check(checks, "safety_source_truth_mutation_false", safety.get("source_truth_mutation") is False, safety.get("source_truth_mutation"), "False")
    add_check(checks, "safety_answer_permission_false", safety.get("answer_permission") is False, safety.get("answer_permission"), "False")

    pass_status = all(check["passed"] for check in checks)
    return {
        "module_name": MODULE_NAME,
        "status": f"{EXPECTED_STATUS}_QUALITY_CHECKED",
        "quality_status": "PASS" if pass_status else "FAIL",
        "summary": {
            "llava_summary_count": llava_summary_count,
            "structured_json_count": structured_json_count,
            "figure_candidate_count": figure_candidate_count,
            "callout_candidate_count": callout_candidate_count,
            "source_trace_ready_count": source_trace_ready_count,
            "unsafe_record_count": unsafe_count,
            "answer_permission_count": answer_permission_count,
            "source_truth_mutation_allowed_count": mutation_count,
            "write_attempt_count": write_count,
            "ready_for_visual_linking": bool(summary.get("ready_for_visual_linking")),
        },
        "checks": checks,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check TRACE-Net LLaVA visual summary batch v1.")
    p.add_argument("--batch", required=True)
    p.add_argument("--output", default="")
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--min-llava-summaries", type=int, default=1)
    p.add_argument("--min-structured-json", type=int, default=1)
    p.add_argument("--min-source-trace-ready", type=int, default=1)
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-answer-permission", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = evaluate(read_json(Path(args.batch)), args)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, sort_keys=True)
            f.write("\n")
    print(f"status={result['status']}")
    print(f"quality_status={result['quality_status']}")
    for key, value in result["summary"].items():
        print(f"{key}={value}")
    if result["quality_status"] != "PASS":
        for check in result["checks"]:
            if not check["passed"]:
                print(f"FAIL {check['name']}: observed={check['observed']} expected={check['expected']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
