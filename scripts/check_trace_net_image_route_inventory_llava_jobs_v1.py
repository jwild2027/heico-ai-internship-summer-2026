#!/usr/bin/env python3
"""Quality checker for TRACE-Net image route inventory + LLaVA jobs v1."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

MODULE_NAME = "trace_net_image_route_inventory_llava_jobs_v1"
EXPECTED_STATUS = "TRACE_NET_IMAGE_ROUTE_INVENTORY_LLAVA_JOBS_BUILT"


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def count_records(records: Sequence[Mapping[str, Any]], key: str) -> int:
    return sum(1 for record in records if bool(record.get(key)))


def sum_records(records: Sequence[Mapping[str, Any]], key: str) -> int:
    total = 0
    for record in records:
        try:
            total += int(record.get(key) or 0)
        except (TypeError, ValueError):
            total += 1
    return total


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "unsafe", "fail"}


def add_check(checks: List[Dict[str, Any]], name: str, passed: bool, observed: Any, expected: str) -> None:
    checks.append({"name": name, "passed": bool(passed), "observed": observed, "expected": expected})


def evaluate(inventory: Mapping[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    summary = dict(inventory.get("summary") or {})
    records = list(inventory.get("records") or [])
    inputs = dict(inventory.get("inputs") or {})
    safety = dict(inventory.get("safety_contract") or {})
    checks: List[Dict[str, Any]] = []

    image_count = int(summary.get("image_route_record_count") or len(records))
    job_count = int(summary.get("llava_job_count") or 0)
    source_trace_ready_count = int(summary.get("source_trace_ready_count") or count_records(records, "source_trace_ready"))
    unsafe_count = int(summary.get("unsafe_record_count") or sum(1 for record in records if boolish(record.get("unsafe"))))
    answer_permission_count = int(summary.get("answer_permission_count") or count_records(records, "answer_permission"))
    mutation_count = int(summary.get("source_truth_mutation_allowed_count") or count_records(records, "source_truth_mutation_allowed"))
    write_count = int(summary.get("write_attempt_count") or sum_records(records, "write_attempt_count"))

    add_check(checks, "module_name", inventory.get("module_name") == MODULE_NAME, inventory.get("module_name"), MODULE_NAME)
    add_check(checks, "status", inventory.get("status") == EXPECTED_STATUS, inventory.get("status"), EXPECTED_STATUS)
    if args.require_quality_pass:
        add_check(checks, "quality_status", inventory.get("quality_status") == "PASS", inventory.get("quality_status"), "PASS")
    add_check(checks, "image_route_record_count", image_count >= args.min_image_route_records, image_count, f">= {args.min_image_route_records}")
    add_check(checks, "llava_job_count", job_count >= args.min_llava_jobs, job_count, f">= {args.min_llava_jobs}")
    add_check(checks, "source_trace_ready_count", source_trace_ready_count >= args.min_source_trace_ready, source_trace_ready_count, f">= {args.min_source_trace_ready}")
    add_check(checks, "unsafe_record_count", unsafe_count <= args.max_unsafe, unsafe_count, f"<= {args.max_unsafe}")
    add_check(checks, "answer_permission_count", answer_permission_count <= args.max_answer_permission, answer_permission_count, f"<= {args.max_answer_permission}")
    add_check(checks, "source_truth_mutation_allowed_count", mutation_count <= args.max_source_truth_mutation_allowed, mutation_count, f"<= {args.max_source_truth_mutation_allowed}")
    add_check(checks, "write_attempt_count", write_count <= args.max_write_attempts, write_count, f"<= {args.max_write_attempts}")

    add_check(checks, "safety_postgres_writes_false", safety.get("postgres_writes") is False, safety.get("postgres_writes"), "False")
    add_check(checks, "safety_qdrant_writes_false", safety.get("qdrant_writes") is False, safety.get("qdrant_writes"), "False")
    add_check(checks, "safety_opensearch_writes_false", safety.get("opensearch_writes") is False, safety.get("opensearch_writes"), "False")
    add_check(checks, "safety_source_truth_mutation_false", safety.get("source_truth_mutation") is False, safety.get("source_truth_mutation"), "False")
    add_check(checks, "safety_answer_permission_false", safety.get("answer_permission") is False, safety.get("answer_permission"), "False")

    route_quality = ((inputs.get("route_validator_runner") or {}).get("quality_status") or "UNKNOWN")
    ocr_quality = ((inputs.get("ocr_route_scan_pack") or {}).get("quality_status") or "UNKNOWN")
    if args.require_source_route_quality_pass:
        add_check(checks, "source_route_quality_pass", route_quality == "PASS", route_quality, "PASS")
    if args.require_ocr_scan_pack_quality_pass:
        add_check(checks, "ocr_scan_pack_quality_pass", ocr_quality == "PASS", ocr_quality, "PASS")

    artifact_paths = dict(inventory.get("artifact_paths") or {})
    for name in ("inventory", "quality_check", "jobs_jsonl", "records_csv"):
        value = artifact_paths.get(name)
        add_check(checks, f"artifact_path_present_{name}", bool(value), value, "non-empty path")

    pass_status = all(check["passed"] for check in checks)
    return {
        "module_name": MODULE_NAME,
        "status": f"{EXPECTED_STATUS}_QUALITY_CHECKED",
        "quality_status": "PASS" if pass_status else "FAIL",
        "summary": {
            "image_route_record_count": image_count,
            "llava_job_count": job_count,
            "source_trace_ready_count": source_trace_ready_count,
            "unsafe_record_count": unsafe_count,
            "answer_permission_count": answer_permission_count,
            "source_truth_mutation_allowed_count": mutation_count,
            "write_attempt_count": write_count,
            "source_route_quality_status": route_quality,
            "ocr_scan_pack_quality_status": ocr_quality,
        },
        "checks": checks,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net image-route inventory quality.")
    parser.add_argument("--inventory", required=True, help="Path to trace_net_image_route_inventory_llava_jobs_v1.json")
    parser.add_argument("--output", default="", help="Optional path to write quality-check JSON.")
    parser.add_argument("--require-quality-pass", action="store_true")
    parser.add_argument("--require-source-route-quality-pass", action="store_true")
    parser.add_argument("--require-ocr-scan-pack-quality-pass", action="store_true")
    parser.add_argument("--min-image-route-records", type=int, default=1)
    parser.add_argument("--min-llava-jobs", type=int, default=1)
    parser.add_argument("--min-source-trace-ready", type=int, default=1)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--max-answer-permission", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--max-write-attempts", type=int, default=0)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    inventory = read_json(Path(args.inventory))
    result = evaluate(inventory, args)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, sort_keys=True)
            f.write("\n")
    print(f"status={result['status']}")
    print(f"quality_status={result['quality_status']}")
    for key, value in result["summary"].items():
        print(f"{key}={value}")
    if result["quality_status"] != "PASS":
        failed = [check for check in result["checks"] if not check["passed"]]
        for check in failed:
            print(f"FAIL {check['name']}: observed={check['observed']} expected={check['expected']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
