from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

MODULE = "trace_net_dry_run_loader_planner_v1"
VERSION = "v1"
REPORT_NAME = "trace_net_dry_run_loader_planner_v1.json"
RECORDS_JSONL_NAME = "trace_net_dry_run_loader_planner_v1_records.jsonl"
POSTGRES_PLAN_JSONL_NAME = "trace_net_dry_run_loader_planner_v1_postgres_dry_run_plan.jsonl"
QDRANT_PLAN_JSONL_NAME = "trace_net_dry_run_loader_planner_v1_qdrant_dry_run_plan.jsonl"
OPENSEARCH_PLAN_JSONL_NAME = "trace_net_dry_run_loader_planner_v1_opensearch_dry_run_plan.jsonl"
BLOCKED_CSV_NAME = "trace_net_dry_run_loader_planner_v1_blocked_records.csv"
SUMMARY_NAME = "trace_net_dry_run_loader_planner_v1_summary.json"
QUALITY_CHECK_NAME = "trace_net_dry_run_loader_planner_v1_quality_check.json"
README_NAME = "trace_net_dry_run_loader_planner_v1.md"

ALLOWED_ROUTES = {"blank", "plain_text", "table", "image", None, ""}


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _write_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    preferred = [
        "page_number",
        "page_id",
        "final_validated_operational_route",
        "storage_decision",
        "loader_decision",
        "blocked_reason",
        "source_member",
        "source_image_sha256",
    ]
    fields: List[str] = []
    for field in preferred:
        if any(field in r for r in records):
            fields.append(field)
    for record in records:
        for key in sorted(record.keys()):
            if key not in fields and not isinstance(record.get(key), (dict, list)):
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            row = {k: record.get(k) for k in fields}
            writer.writerow(row)


def _as_bool(value: Any) -> bool:
    return bool(value) is True


def _records_from_storage_gate(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    records = payload.get("records")
    if isinstance(records, list):
        return [dict(r) for r in records if isinstance(r, Mapping)]
    raise ValueError("storage gate report does not contain a records list")


def _page_identity(record: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "page_id": record.get("page_id"),
        "page_number": record.get("page_number") or record.get("canonical_page_number"),
        "source_member": record.get("source_member"),
        "source_image_sha256": record.get("source_image_sha256"),
        "raw_tiff_reference": record.get("raw_tiff_reference") or record.get("source_image_path"),
    }


def _storage_route(record: Mapping[str, Any]) -> str:
    return str(record.get("final_validated_operational_route") or record.get("operational_route") or "")


def _make_postgres_plan(record: Mapping[str, Any]) -> Dict[str, Any]:
    base = _page_identity(record)
    route = _storage_route(record)
    return {
        **base,
        "loader_target": "postgres_graph",
        "loader_action": "dry_run_upsert_page_source_trace_node",
        "dry_run_only": True,
        "live_write_enabled": False,
        "write_attempted": False,
        "postgres_write_attempt": False,
        "route": route,
        "storage_decision": record.get("storage_decision"),
        "validator_gated": bool(record.get("validator_gated")),
        "final_do_not_embed": bool(record.get("final_do_not_embed")),
        "source_truth_mutation_allowed": False,
        "answer_permission": False,
        "evidence_policy": "graph_source_map_only" if record.get("final_do_not_embed") else "graph_source_map_plus_validated_evidence_links",
    }


def _make_qdrant_plan(record: Mapping[str, Any]) -> Dict[str, Any]:
    base = _page_identity(record)
    route = _storage_route(record)
    return {
        **base,
        "loader_target": "qdrant",
        "loader_action": "dry_run_prepare_embedding_payload",
        "dry_run_only": True,
        "live_write_enabled": False,
        "write_attempted": False,
        "qdrant_write_attempt": False,
        "route": route,
        "embedding_scope": "validated_page_or_evidence_summary",
        "storage_decision": record.get("storage_decision"),
        "source_truth_mutation_allowed": False,
        "answer_permission": False,
        "candidate_reason": "validated_nonblank_semantic_evidence",
    }


def _make_opensearch_plan(record: Mapping[str, Any]) -> Dict[str, Any]:
    base = _page_identity(record)
    route = _storage_route(record)
    return {
        **base,
        "loader_target": "opensearch",
        "loader_action": "dry_run_prepare_exact_or_table_payload",
        "dry_run_only": True,
        "live_write_enabled": False,
        "write_attempted": False,
        "opensearch_write_attempt": False,
        "route": route,
        "exact_index_scope": "validated_table_or_exact_evidence",
        "storage_decision": record.get("storage_decision"),
        "source_truth_mutation_allowed": False,
        "answer_permission": False,
        "candidate_reason": "validated_exact_table_evidence",
    }


def _make_blocked_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    route = _storage_route(record)
    reasons = record.get("storage_reasons") or []
    if not reasons and route == "blank":
        reasons = ["blank_pages_are_not_embedded_or_exact_indexed"]
    if not reasons and record.get("validator_gated"):
        reasons = ["validator_gated_until_retry_or_probe_passes"]
    if not reasons:
        reasons = ["not_allowed_by_storage_gate"]
    return {
        **_page_identity(record),
        "loader_target": "blocked_from_retrieval_loaders",
        "loader_decision": "graph_only_no_qdrant_no_opensearch",
        "final_validated_operational_route": route,
        "storage_decision": record.get("storage_decision"),
        "blocked_reason": "; ".join(str(r) for r in reasons),
        "final_do_not_embed": bool(record.get("final_do_not_embed")),
        "validator_gated": bool(record.get("validator_gated")),
        "dry_run_only": True,
        "live_write_enabled": False,
        "write_attempted": False,
        "source_truth_mutation_allowed": False,
        "answer_permission": False,
    }


def _build_loader_records(records: Sequence[Mapping[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    planner_records: List[Dict[str, Any]] = []
    postgres_plan: List[Dict[str, Any]] = []
    qdrant_plan: List[Dict[str, Any]] = []
    opensearch_plan: List[Dict[str, Any]] = []
    blocked_records: List[Dict[str, Any]] = []

    for index, record in enumerate(records, 1):
        route = _storage_route(record)
        postgres_allowed = bool(record.get("postgres_graph_record", True))
        qdrant_allowed = bool(record.get("qdrant_embedding_allowed")) and not bool(record.get("final_do_not_embed")) and route != "blank"
        opensearch_allowed = bool(record.get("opensearch_index_allowed")) and not bool(record.get("final_do_not_embed")) and route == "table"
        blocked = bool(record.get("final_do_not_embed")) or route == "blank" or bool(record.get("validator_gated"))

        pg_plan = _make_postgres_plan(record) if postgres_allowed else None
        q_plan = _make_qdrant_plan(record) if qdrant_allowed else None
        os_plan = _make_opensearch_plan(record) if opensearch_allowed else None
        block_record = _make_blocked_record(record) if blocked or not (qdrant_allowed or opensearch_allowed) else None

        if pg_plan:
            postgres_plan.append(pg_plan)
        if q_plan:
            qdrant_plan.append(q_plan)
        if os_plan:
            opensearch_plan.append(os_plan)
        if block_record:
            blocked_records.append(block_record)

        planner_records.append(
            {
                **_page_identity(record),
                "record_index": index,
                "final_validated_operational_route": route,
                "storage_decision": record.get("storage_decision"),
                "postgres_graph_record": postgres_allowed,
                "qdrant_embedding_allowed": qdrant_allowed,
                "opensearch_index_allowed": opensearch_allowed,
                "final_do_not_embed": bool(record.get("final_do_not_embed")),
                "validator_gated": bool(record.get("validator_gated")),
                "dry_run_only": True,
                "live_write_enabled": False,
                "write_attempted": False,
                "loader_targets": [
                    target
                    for target, allowed in [
                        ("postgres_graph", postgres_allowed),
                        ("qdrant", qdrant_allowed),
                        ("opensearch", opensearch_allowed),
                    ]
                    if allowed
                ],
                "blocked_from_retrieval_loaders": bool(block_record) and not (qdrant_allowed or opensearch_allowed),
                "source_truth_mutation_allowed": False,
                "answer_permission": False,
                "unsafe": False,
            }
        )
    return planner_records, postgres_plan, qdrant_plan, opensearch_plan, blocked_records


def build_dry_run_loader_planner(*, four_route_storage_gate: Path | str, output_dir: Path | str, quality: bool = False) -> Dict[str, Any]:
    source_path = Path(four_route_storage_gate)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    source_payload = _read_json(source_path)
    source_summary = dict(source_payload.get("summary") or {})
    records = _records_from_storage_gate(source_payload)
    planner_records, postgres_plan, qdrant_plan, opensearch_plan, blocked_records = _build_loader_records(records)

    invalid_operational_route_count = sum(1 for r in planner_records if r.get("final_validated_operational_route") not in {"blank", "plain_text", "table", "image", ""})
    write_attempt_count = sum(1 for r in planner_records if r.get("write_attempted"))
    postgres_write_attempt_count = sum(1 for r in postgres_plan if r.get("postgres_write_attempt"))
    qdrant_write_attempt_count = sum(1 for r in qdrant_plan if r.get("qdrant_write_attempt"))
    opensearch_write_attempt_count = sum(1 for r in opensearch_plan if r.get("opensearch_write_attempt"))

    report_path = out / REPORT_NAME
    records_jsonl_path = out / RECORDS_JSONL_NAME
    postgres_plan_path = out / POSTGRES_PLAN_JSONL_NAME
    qdrant_plan_path = out / QDRANT_PLAN_JSONL_NAME
    opensearch_plan_path = out / OPENSEARCH_PLAN_JSONL_NAME
    blocked_csv_path = out / BLOCKED_CSV_NAME

    summary: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "source_four_route_storage_gate": str(source_path),
        "source_four_route_storage_gate_quality_status": source_payload.get("quality_status"),
        "source_record_count": len(records),
        "loader_plan_record_count": len(planner_records),
        "postgres_dry_run_plan_count": len(postgres_plan),
        "qdrant_dry_run_plan_count": len(qdrant_plan),
        "opensearch_dry_run_plan_count": len(opensearch_plan),
        "blocked_loader_record_count": len(blocked_records),
        "dry_run_only": True,
        "live_write_enabled": False,
        "write_attempt_count": write_attempt_count,
        "postgres_write_attempt_count": postgres_write_attempt_count,
        "qdrant_write_attempt_count": qdrant_write_attempt_count,
        "opensearch_write_attempt_count": opensearch_write_attempt_count,
        "source_truth_mutation_allowed_count": 0,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "unsafe_record_count": 0,
        "human_review_required_count": 0,
        "manual_review_required_count": 0,
        "invalid_operational_route_count": invalid_operational_route_count,
        "ready_for_postgres_dry_run_loader": len(postgres_plan) == len(records),
        "ready_for_qdrant_dry_run_loader": len(qdrant_plan) > 0,
        "ready_for_opensearch_dry_run_loader": len(opensearch_plan) > 0,
        "ready_for_blocked_record_audit": len(blocked_records) > 0,
        "records_jsonl_path": str(records_jsonl_path),
        "postgres_dry_run_plan_jsonl_path": str(postgres_plan_path),
        "qdrant_dry_run_plan_jsonl_path": str(qdrant_plan_path),
        "opensearch_dry_run_plan_jsonl_path": str(opensearch_plan_path),
        "blocked_records_csv_path": str(blocked_csv_path),
        "source_storage_summary": source_summary,
    }

    failures: List[str] = []
    if source_payload.get("quality_status") != "PASS":
        failures.append("source storage gate quality_status is not PASS")
    if len(planner_records) != len(records):
        failures.append("loader plan records do not match source records")
    if len(postgres_plan) != len(records):
        failures.append("not every page has a postgres graph dry-run plan")
    if write_attempt_count or postgres_write_attempt_count or qdrant_write_attempt_count or opensearch_write_attempt_count:
        failures.append("one or more write attempts were recorded")
    if invalid_operational_route_count:
        failures.append("invalid operational routes found")

    quality_status = "PASS" if not failures else "FAIL"
    payload: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "status": "TRACE_NET_DRY_RUN_LOADER_PLANNER_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "quality_failures": failures,
        "records": planner_records,
        "postgres_dry_run_plan_records": postgres_plan,
        "qdrant_dry_run_plan_records": qdrant_plan,
        "opensearch_dry_run_plan_records": opensearch_plan,
        "blocked_records": blocked_records,
    }

    _write_json(report_path, payload)
    _write_jsonl(records_jsonl_path, planner_records)
    _write_jsonl(postgres_plan_path, postgres_plan)
    _write_jsonl(qdrant_plan_path, qdrant_plan)
    _write_jsonl(opensearch_plan_path, opensearch_plan)
    _write_csv(blocked_csv_path, blocked_records)
    _write_json(out / SUMMARY_NAME, summary)
    _write_markdown(out / README_NAME, payload)
    if quality:
        check_payload = check_dry_run_loader_planner_quality(report_path=report_path, write_json=True)
        payload["quality_check"] = check_payload
        # Preserve main report quality generated by builder, but include check sidecar.
        _write_json(report_path, payload)

    print("Status: TRACE_NET_DRY_RUN_LOADER_PLANNER_BUILT")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    return payload


def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    s = payload.get("summary") or {}
    lines = [
        "# TRACE-Net Dry Run Loader Planner v1",
        "",
        "This artifact prepares no-write loader plans from the four-route storage gate.",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "loader_plan_record_count",
        "postgres_dry_run_plan_count",
        "qdrant_dry_run_plan_count",
        "opensearch_dry_run_plan_count",
        "blocked_loader_record_count",
        "dry_run_only",
        "live_write_enabled",
        "write_attempt_count",
        "source_truth_mutation_allowed_count",
        "answer_permission_count",
    ]:
        lines.append(f"- **{key}:** {s.get(key)}")
    lines.extend([
        "",
        "## Safety",
        "",
        "No database writes are performed. The generated plans are dry-run manifests only.",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def check_dry_run_loader_planner_quality(
    *,
    report_path: Path | str,
    min_records: int = 1,
    min_postgres_plans: int = 1,
    min_qdrant_plans: int = 0,
    min_opensearch_plans: int = 0,
    max_blocked_records: Optional[int] = None,
    require_source_quality_pass: bool = False,
    require_decision_files: bool = False,
    require_dry_run_only: bool = False,
    require_no_human_review_required: bool = False,
    max_unsafe: Optional[int] = None,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
    write_json: bool = False,
) -> Dict[str, Any]:
    path = Path(report_path)
    payload = _read_json(path)
    summary = dict(payload.get("summary") or {})
    failures: List[str] = []

    def count(name: str) -> int:
        try:
            return int(summary.get(name) or 0)
        except Exception:
            return 0

    if payload.get("quality_status") != "PASS":
        failures.append("manifest quality_status is not PASS")
    if count("loader_plan_record_count") < min_records:
        failures.append(f"loader_plan_record_count below minimum {min_records}")
    if count("postgres_dry_run_plan_count") < min_postgres_plans:
        failures.append(f"postgres_dry_run_plan_count below minimum {min_postgres_plans}")
    if count("qdrant_dry_run_plan_count") < min_qdrant_plans:
        failures.append(f"qdrant_dry_run_plan_count below minimum {min_qdrant_plans}")
    if count("opensearch_dry_run_plan_count") < min_opensearch_plans:
        failures.append(f"opensearch_dry_run_plan_count below minimum {min_opensearch_plans}")
    if max_blocked_records is not None and count("blocked_loader_record_count") > max_blocked_records:
        failures.append(f"blocked_loader_record_count above maximum {max_blocked_records}")
    if require_source_quality_pass and summary.get("source_four_route_storage_gate_quality_status") != "PASS":
        failures.append("source storage gate quality_status is not PASS")
    if require_dry_run_only and not summary.get("dry_run_only"):
        failures.append("dry_run_only is not true")
    if require_dry_run_only and summary.get("live_write_enabled"):
        failures.append("live_write_enabled is true")
    if require_no_human_review_required and (count("human_review_required_count") or count("manual_review_required_count")):
        failures.append("human/manual review required count is nonzero")
    if max_unsafe is not None and count("unsafe_record_count") > max_unsafe:
        failures.append("unsafe_record_count exceeds maximum")
    if require_no_answer_permission and (count("answer_permission_count") or count("can_answer_directly_count") or count("can_prove_claims_count")):
        failures.append("answer permission or proof/answer counters are nonzero")
    if require_no_source_truth_mutation and count("source_truth_mutation_allowed_count"):
        failures.append("source_truth_mutation_allowed_count is nonzero")
    if require_no_write_attempts and (count("write_attempt_count") or count("postgres_write_attempt_count") or count("qdrant_write_attempt_count") or count("opensearch_write_attempt_count")):
        failures.append("write attempt counter is nonzero")
    if require_decision_files:
        for key in [
            "records_jsonl_path",
            "postgres_dry_run_plan_jsonl_path",
            "qdrant_dry_run_plan_jsonl_path",
            "opensearch_dry_run_plan_jsonl_path",
            "blocked_records_csv_path",
        ]:
            candidate = Path(str(summary.get(key) or ""))
            if not candidate.exists():
                failures.append(f"required decision file missing: {key}")

    result = {
        "module": MODULE,
        "version": VERSION,
        "quality_status": "PASS" if not failures else "FAIL",
        "summary": summary,
        "failures": failures,
        "source_report_path": str(path),
    }
    if write_json:
        _write_json(path.with_name(QUALITY_CHECK_NAME), result)
        print(f"Wrote: {path.with_name(QUALITY_CHECK_NAME)}")
    print(f"Quality status: {result['quality_status']}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures, indent=2))
    return result


def main_build(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Build TRACE-Net dry-run loader planner v1")
    parser.add_argument("--four-route-storage-gate", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    return build_dry_run_loader_planner(
        four_route_storage_gate=Path(args.four_route_storage_gate),
        output_dir=Path(args.output_dir),
        quality=args.quality,
    )


def main_check(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Check TRACE-Net dry-run loader planner v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-postgres-plans", type=int, default=1)
    parser.add_argument("--min-qdrant-plans", type=int, default=0)
    parser.add_argument("--min-opensearch-plans", type=int, default=0)
    parser.add_argument("--max-blocked-records", type=int)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-decision-files", action="store_true")
    parser.add_argument("--require-dry-run-only", action="store_true")
    parser.add_argument("--require-no-human-review-required", action="store_true")
    parser.add_argument("--max-unsafe", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args(argv)
    return check_dry_run_loader_planner_quality(
        report_path=Path(args.report_path),
        min_records=args.min_records,
        min_postgres_plans=args.min_postgres_plans,
        min_qdrant_plans=args.min_qdrant_plans,
        min_opensearch_plans=args.min_opensearch_plans,
        max_blocked_records=args.max_blocked_records,
        require_source_quality_pass=args.require_source_quality_pass,
        require_decision_files=args.require_decision_files,
        require_dry_run_only=args.require_dry_run_only,
        require_no_human_review_required=args.require_no_human_review_required,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
        write_json=args.write_json,
    )


if __name__ == "__main__":
    main_build()
