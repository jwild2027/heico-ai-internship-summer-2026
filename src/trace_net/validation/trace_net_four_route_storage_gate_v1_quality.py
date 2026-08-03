"""Quality checker for TRACE-Net Four Route Storage Gate v1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def evaluate_storage_gate_quality(
    payload: Mapping[str, Any],
    *,
    min_records: int = 0,
    min_postgres_graph_records: int = 0,
    min_qdrant_allowed: int = 0,
    min_opensearch_allowed: int = 0,
    max_final_do_not_embed: int | None = None,
    max_validator_gated: int | None = None,
    require_source_quality_pass: bool = False,
    require_decision_files: bool = False,
    require_no_human_review_required: bool = False,
    max_unsafe: int | None = None,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
) -> tuple[str, list[str]]:
    summary = payload.get("summary") or {}
    failures: list[str] = []

    if payload.get("quality_status") != "PASS":
        failures.append("manifest quality_status is not PASS")
    if summary.get("storage_gate_record_count", 0) < min_records:
        failures.append(f"storage_gate_record_count below {min_records}")
    if summary.get("postgres_graph_record_count", 0) < min_postgres_graph_records:
        failures.append(f"postgres_graph_record_count below {min_postgres_graph_records}")
    if summary.get("qdrant_embedding_allowed_count", 0) < min_qdrant_allowed:
        failures.append(f"qdrant_embedding_allowed_count below {min_qdrant_allowed}")
    if summary.get("opensearch_index_allowed_count", 0) < min_opensearch_allowed:
        failures.append(f"opensearch_index_allowed_count below {min_opensearch_allowed}")
    if max_final_do_not_embed is not None and summary.get("final_do_not_embed_count", 0) > max_final_do_not_embed:
        failures.append(f"final_do_not_embed_count above {max_final_do_not_embed}")
    if max_validator_gated is not None and summary.get("validator_gated_count", 0) > max_validator_gated:
        failures.append(f"validator_gated_count above {max_validator_gated}")
    if require_source_quality_pass and summary.get("source_route_unresolved_retry_probe_quality_status") != "PASS":
        failures.append("source route unresolved retry/probe quality_status is not PASS")
    if require_decision_files:
        required_paths = [
            "records_jsonl_path",
            "records_csv_path",
            "postgres_graph_manifest_jsonl_path",
            "qdrant_candidates_jsonl_path",
            "opensearch_candidates_jsonl_path",
            "blocked_records_csv_path",
        ]
        for key in required_paths:
            path = summary.get(key)
            if not path or not Path(path).exists():
                failures.append(f"missing decision file: {key}")
    if require_no_human_review_required:
        for key in ("human_review_required_count", "manual_review_required_count"):
            if summary.get(key, 0) != 0:
                failures.append(f"{key} is not zero")
    if max_unsafe is not None and summary.get("unsafe_record_count", 0) > max_unsafe:
        failures.append(f"unsafe_record_count above {max_unsafe}")
    if require_no_answer_permission:
        for key in ("answer_permission_count", "can_answer_directly_count", "can_prove_claims_count"):
            if summary.get(key, 0) != 0:
                failures.append(f"{key} is not zero")
    if require_no_source_truth_mutation and summary.get("source_truth_mutation_allowed_count", 0) != 0:
        failures.append("source_truth_mutation_allowed_count is not zero")
    if require_no_write_attempts:
        for key in ("postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"):
            if summary.get(key, 0) != 0:
                failures.append(f"{key} is not zero")
    if summary.get("invalid_operational_route_count", 0) != 0:
        failures.append("invalid_operational_route_count is not zero")

    return ("PASS" if not failures else "FAIL", failures)


def main_quality(argv: list[str] | None = None) -> tuple[str, list[str]]:
    parser = argparse.ArgumentParser(description="Check TRACE-Net four-route storage gate quality v1")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-records", type=int, default=0)
    parser.add_argument("--min-postgres-graph-records", type=int, default=0)
    parser.add_argument("--min-qdrant-allowed", type=int, default=0)
    parser.add_argument("--min-opensearch-allowed", type=int, default=0)
    parser.add_argument("--max-final-do-not-embed", type=int)
    parser.add_argument("--max-validator-gated", type=int)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-decision-files", action="store_true")
    parser.add_argument("--require-no-human-review-required", action="store_true")
    parser.add_argument("--max-unsafe", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args(argv)

    payload = _read_json(args.report_path)
    status, failures = evaluate_storage_gate_quality(
        payload,
        min_records=args.min_records,
        min_postgres_graph_records=args.min_postgres_graph_records,
        min_qdrant_allowed=args.min_qdrant_allowed,
        min_opensearch_allowed=args.min_opensearch_allowed,
        max_final_do_not_embed=args.max_final_do_not_embed,
        max_validator_gated=args.max_validator_gated,
        require_source_quality_pass=args.require_source_quality_pass,
        require_decision_files=args.require_decision_files,
        require_no_human_review_required=args.require_no_human_review_required,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
    )

    quality_payload = {
        "quality_status": status,
        "failures": failures,
        "summary": payload.get("summary") or {},
    }
    if args.write_json:
        out = args.report_path.with_name("trace_net_four_route_storage_gate_v1_quality_check.json")
        _write_json(out, quality_payload)
        print("Wrote:", out)
    print("Quality status:", status)
    print("Summary:", json.dumps(payload.get("summary") or {}, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures, indent=2))
    return status, failures


if __name__ == "__main__":  # pragma: no cover
    status, _ = main_quality()
    raise SystemExit(0 if status == "PASS" else 1)
