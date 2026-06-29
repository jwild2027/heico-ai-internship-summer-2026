"""TRACE-Net Loader Contract Audit v1.

Audits dry-run loader plans before any live Postgres/Qdrant/OpenSearch adapter is
allowed to write.  The audit repairs missing raw-TIFF lineage from the OCR route
scan pack when possible, validates per-target loader contracts, and emits
safe no-write contract manifests.
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

MODULE = "trace_net_loader_contract_audit_v1"
VERSION = "v1"

REPORT_NAME = "trace_net_loader_contract_audit_v1.json"
RECORDS_JSONL = "trace_net_loader_contract_audit_v1_records.jsonl"
RECORDS_CSV = "trace_net_loader_contract_audit_v1_records.csv"
POSTGRES_CONTRACT_JSONL = "trace_net_loader_contract_audit_v1_postgres_contract_ready.jsonl"
QDRANT_CONTRACT_JSONL = "trace_net_loader_contract_audit_v1_qdrant_contract_ready.jsonl"
OPENSEARCH_CONTRACT_JSONL = "trace_net_loader_contract_audit_v1_opensearch_contract_ready.jsonl"
BLOCKED_CSV = "trace_net_loader_contract_audit_v1_contract_blocked_records.csv"
QUALITY_JSON = "trace_net_loader_contract_audit_v1_quality_check.json"
SUMMARY_JSON = "trace_net_loader_contract_audit_v1_summary.json"

VALID_ROUTES = {"blank", "plain_text", "table", "image", None, ""}
REQUIRED_LINEAGE_FIELDS = ("page_id", "page_number", "source_member", "raw_tiff_reference", "source_image_sha256")


@dataclass(frozen=True)
class AuditPaths:
    output_dir: Path
    report: Path
    records_jsonl: Path
    records_csv: Path
    postgres_contract_jsonl: Path
    qdrant_contract_jsonl: Path
    opensearch_contract_jsonl: Path
    blocked_csv: Path
    quality_json: Path
    summary_json: Path


def _paths(output_dir: Path) -> AuditPaths:
    return AuditPaths(
        output_dir=output_dir,
        report=output_dir / REPORT_NAME,
        records_jsonl=output_dir / RECORDS_JSONL,
        records_csv=output_dir / RECORDS_CSV,
        postgres_contract_jsonl=output_dir / POSTGRES_CONTRACT_JSONL,
        qdrant_contract_jsonl=output_dir / QDRANT_CONTRACT_JSONL,
        opensearch_contract_jsonl=output_dir / OPENSEARCH_CONTRACT_JSONL,
        blocked_csv=output_dir / BLOCKED_CSV,
        quality_json=output_dir / QUALITY_JSON,
        summary_json=output_dir / SUMMARY_JSON,
    )


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _flatten_for_csv(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return value


def _write_csv(path: Path, records: List[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys: List[str] = []
    for record in records:
        for key in record.keys():
            if key not in keys:
                keys.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        for record in records:
            writer.writerow({key: _flatten_for_csv(record.get(key)) for key in keys})


def _records(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    records = payload.get("records") or []
    if not isinstance(records, list):
        return []
    return [dict(r) for r in records if isinstance(r, Mapping)]


def _nonempty(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _candidate_page_number(record: Mapping[str, Any]) -> Optional[int]:
    for key in ("page_number", "canonical_page_number", "source_page_number"):
        value = record.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
    return None


def _candidate_page_id(record: Mapping[str, Any]) -> Optional[str]:
    for key in ("page_id", "canonical_page_id", "source_page_id"):
        value = record.get(key)
        if _nonempty(value):
            return str(value)
    return None


def _candidate_sha(record: Mapping[str, Any]) -> Optional[str]:
    for key in ("source_image_sha256", "raw_image_sha256", "source_tiff_sha256", "image_sha256", "sha256"):
        value = record.get(key)
        if _nonempty(value):
            return str(value)
    return None


def _candidate_source_member(record: Mapping[str, Any]) -> Optional[str]:
    for key in ("source_member", "source_package_member", "zip_member", "member", "tiff_member"):
        value = record.get(key)
        if _nonempty(value):
            return str(value)
    return None


def _candidate_raw_tiff_reference(record: Mapping[str, Any]) -> Optional[str]:
    for key in ("raw_tiff_reference", "source_member", "source_package_member", "zip_member", "member", "tiff_member", "source_image_path", "image_path"):
        value = record.get(key)
        if _nonempty(value):
            return str(value)
    return None


def _build_lineage_index(ocr_payload: Optional[Mapping[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], Dict[int, Dict[str, Any]]]:
    by_page_id: Dict[str, Dict[str, Any]] = {}
    by_page_number: Dict[int, Dict[str, Any]] = {}
    if not ocr_payload:
        return by_page_id, by_page_number
    for record in _records(ocr_payload):
        page_id = _candidate_page_id(record)
        page_number = _candidate_page_number(record)
        lineage = {
            "page_id": page_id,
            "page_number": page_number,
            "source_member": _candidate_source_member(record),
            "raw_tiff_reference": _candidate_raw_tiff_reference(record),
            "source_image_sha256": _candidate_sha(record),
            "source_package": record.get("source_package"),
            "source_image_path": record.get("source_image_path") or record.get("image_path"),
            "ocr_text_path": record.get("ocr_text_path"),
        }
        if page_id:
            by_page_id[page_id] = lineage
        if page_number is not None:
            by_page_number[page_number] = lineage
    return by_page_id, by_page_number


def _lookup_lineage(record: Mapping[str, Any], by_page_id: Mapping[str, Mapping[str, Any]], by_page_number: Mapping[int, Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    page_id = _candidate_page_id(record)
    if page_id and page_id in by_page_id:
        return by_page_id[page_id]
    page_number = _candidate_page_number(record)
    if page_number is not None and page_number in by_page_number:
        return by_page_number[page_number]
    return None


def _loader_targets(record: Mapping[str, Any]) -> List[str]:
    targets = record.get("loader_targets")
    if isinstance(targets, list):
        return [str(t) for t in targets]
    targets = []
    if record.get("postgres_graph_record") or record.get("loader_target") == "postgres_graph":
        targets.append("postgres_graph")
    if record.get("qdrant_embedding_allowed"):
        targets.append("qdrant")
    if record.get("opensearch_index_allowed"):
        targets.append("opensearch")
    return targets


def _target_plan_records(payload: Mapping[str, Any], target: str) -> List[Dict[str, Any]]:
    key = {
        "postgres_graph": "postgres_dry_run_plan_records",
        "qdrant": "qdrant_dry_run_plan_records",
        "opensearch": "opensearch_dry_run_plan_records",
    }[target]
    records = payload.get(key) or []
    if not isinstance(records, list):
        return []
    return [dict(r) for r in records if isinstance(r, Mapping)]


def _build_target_plan_index(payload: Mapping[str, Any]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Index per-target dry-run plan records by page id and page number.

    The top-level planner records intentionally stay generic.  Contract-specific
    fields such as ``evidence_policy``, ``embedding_scope``, and
    ``exact_index_scope`` are stored on the target-specific dry-run plan records.
    The audit must join those records back by page identity before judging
    contract readiness.
    """
    index: Dict[str, Dict[str, Dict[str, Any]]] = {
        "postgres_graph": {},
        "qdrant": {},
        "opensearch": {},
    }
    for target in index:
        for record in _target_plan_records(payload, target):
            page_id = _candidate_page_id(record)
            page_number = _candidate_page_number(record)
            if page_id:
                index[target][f"id:{page_id}"] = record
            if page_number is not None:
                index[target][f"num:{page_number}"] = record
    return index


def _lookup_target_plan(record: Mapping[str, Any], target: str, target_plan_index: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> Optional[Mapping[str, Any]]:
    target_index = target_plan_index.get(target) or {}
    page_id = _candidate_page_id(record)
    if page_id and f"id:{page_id}" in target_index:
        return target_index[f"id:{page_id}"]
    page_number = _candidate_page_number(record)
    if page_number is not None and f"num:{page_number}" in target_index:
        return target_index[f"num:{page_number}"]
    return None


def _merge_target_contract_fields(record: Mapping[str, Any], target_plan_index: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> Dict[str, Any]:
    merged = dict(record)
    merged_from_targets: List[str] = []
    for target in _loader_targets(merged):
        plan = _lookup_target_plan(merged, target, target_plan_index)
        if not plan:
            continue
        merged_from_targets.append(target)
        for key in (
            "evidence_policy",
            "embedding_scope",
            "exact_index_scope",
            "dry_run_only",
            "live_write_enabled",
            "write_attempted",
            "answer_permission",
            "source_truth_mutation_allowed",
            "postgres_write_attempt",
            "qdrant_write_attempt",
            "opensearch_write_attempt",
        ):
            if not _nonempty(merged.get(key)) and key in plan:
                merged[key] = plan.get(key)
        # Preserve per-target plan details for downstream debug without changing
        # the generic top-level route/storage fields.
        merged[f"{target}_plan_joined"] = True
    if merged_from_targets:
        merged["target_plan_join_status"] = "joined_target_specific_dry_run_plans"
        merged["target_plan_joined_targets"] = merged_from_targets
    else:
        merged.setdefault("target_plan_join_status", "no_target_specific_plan_joined")
        merged.setdefault("target_plan_joined_targets", [])
    return merged


def _required_for_target(target: str) -> List[str]:
    base = ["page_id", "page_number", "source_member", "raw_tiff_reference", "source_image_sha256", "route", "storage_decision"]
    if target == "postgres_graph":
        return base + ["evidence_policy"]
    if target == "qdrant":
        return base + ["embedding_scope"]
    if target == "opensearch":
        return base + ["exact_index_scope"]
    return base


def _target_contract_ready(record: Mapping[str, Any], target: str) -> Tuple[bool, List[str]]:
    missing = []
    for field in _required_for_target(target):
        if not _nonempty(record.get(field)):
            missing.append(field)
    if record.get("dry_run_only") is not True:
        missing.append("dry_run_only_true")
    if record.get("live_write_enabled") not in (False, None):
        missing.append("live_write_disabled")
    if record.get("write_attempted") is True:
        missing.append("write_attempted_false")
    if record.get("answer_permission") is True:
        missing.append("answer_permission_false")
    if record.get("source_truth_mutation_allowed") is True:
        missing.append("source_truth_mutation_allowed_false")
    if target == "opensearch" and record.get("route") != "table":
        missing.append("opensearch_requires_table_route")
    if target == "qdrant" and record.get("final_do_not_embed") is True:
        missing.append("qdrant_requires_not_do_not_embed")
    return not missing, missing


def _repair_record(record: Mapping[str, Any], lineage: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    repaired = dict(record)
    # Normalize route naming from either storage-gate records or per-target plan records.
    if not _nonempty(repaired.get("route")):
        repaired["route"] = repaired.get("final_validated_operational_route") or repaired.get("operational_route")
    if not _nonempty(repaired.get("page_number")):
        repaired["page_number"] = repaired.get("canonical_page_number")
    # Patch lineage only when missing so prior plan fields are preserved.
    if lineage:
        for key in ("page_id", "page_number", "source_member", "raw_tiff_reference", "source_image_sha256", "source_package", "source_image_path", "ocr_text_path"):
            if not _nonempty(repaired.get(key)) and _nonempty(lineage.get(key)):
                repaired[key] = lineage.get(key)
        repaired["lineage_repair_status"] = "repaired_from_ocr_scan_pack"
    else:
        repaired["lineage_repair_status"] = "no_matching_ocr_lineage"
    if all(_nonempty(repaired.get(f)) for f in REQUIRED_LINEAGE_FIELDS):
        repaired["lineage_ready"] = True
    else:
        repaired["lineage_ready"] = False
    repaired["missing_lineage_fields"] = [field for field in REQUIRED_LINEAGE_FIELDS if not _nonempty(repaired.get(field))]
    repaired.setdefault("dry_run_only", True)
    repaired.setdefault("live_write_enabled", False)
    repaired.setdefault("write_attempted", False)
    repaired.setdefault("answer_permission", False)
    repaired.setdefault("source_truth_mutation_allowed", False)
    return repaired


def _audit_record(
    record: Mapping[str, Any],
    lineage_index: Tuple[Mapping[str, Mapping[str, Any]], Mapping[int, Mapping[str, Any]]],
    target_plan_index: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> Dict[str, Any]:
    by_page_id, by_page_number = lineage_index
    lineage = _lookup_lineage(record, by_page_id, by_page_number)
    repaired = _repair_record(record, lineage)
    audited = _merge_target_contract_fields(repaired, target_plan_index)
    targets = _loader_targets(audited)
    if not targets:
        targets = ["postgres_graph"] if audited.get("storage_decision") in {"graph_only_blank", "graph_only_validator_gated"} else []
    audited["loader_targets"] = targets
    contract_statuses: Dict[str, str] = {}
    missing_by_target: Dict[str, List[str]] = {}
    ready_targets: List[str] = []
    for target in targets:
        ready, missing = _target_contract_ready(audited, target)
        contract_statuses[target] = "ready" if ready else "blocked"
        missing_by_target[target] = missing
        if ready:
            ready_targets.append(target)
    audited["contract_statuses"] = contract_statuses
    audited["missing_contract_fields_by_target"] = missing_by_target
    audited["contract_ready_targets"] = ready_targets
    audited["postgres_contract_ready"] = "postgres_graph" in ready_targets
    audited["qdrant_contract_ready"] = "qdrant" in ready_targets
    audited["opensearch_contract_ready"] = "opensearch" in ready_targets
    audited["live_write_allowed"] = False
    blockers = []
    if not audited.get("lineage_ready"):
        blockers.append("missing_lineage")
    for target, missing in missing_by_target.items():
        if missing:
            blockers.append(f"{target}_contract_blocked")
    if audited.get("write_attempted") is True:
        blockers.append("write_attempted")
    if audited.get("answer_permission") is True:
        blockers.append("answer_permission")
    if audited.get("source_truth_mutation_allowed") is True:
        blockers.append("source_truth_mutation_allowed")
    audited["loader_contract_blockers"] = sorted(set(blockers))
    audited["loader_contract_status"] = "ready_dry_run_only" if not blockers else "blocked_until_contract_ready"
    return audited


def _select_contract_ready(records: List[Mapping[str, Any]], target: str) -> List[Dict[str, Any]]:
    key = {
        "postgres_graph": "postgres_contract_ready",
        "qdrant": "qdrant_contract_ready",
        "opensearch": "opensearch_contract_ready",
    }[target]
    return [dict(r) for r in records if r.get(key)]


def _summarize(records: List[Mapping[str, Any]], source_payload: Mapping[str, Any], source_path: Path, ocr_path: Optional[Path]) -> Dict[str, Any]:
    record_count = len(records)
    postgres_ready = sum(1 for r in records if r.get("postgres_contract_ready"))
    qdrant_ready = sum(1 for r in records if r.get("qdrant_contract_ready"))
    opensearch_ready = sum(1 for r in records if r.get("opensearch_contract_ready"))
    lineage_ready = sum(1 for r in records if r.get("lineage_ready"))
    missing_lineage = record_count - lineage_ready
    blocked = sum(1 for r in records if r.get("loader_contract_status") != "ready_dry_run_only")
    route_counts: Dict[str, int] = {}
    for r in records:
        route = str(r.get("route"))
        route_counts[route] = route_counts.get(route, 0) + 1
    summary = {
        "module": MODULE,
        "version": VERSION,
        "source_dry_run_loader_planner": str(source_path),
        "source_dry_run_loader_planner_quality_status": source_payload.get("quality_status"),
        "source_ocr_route_scan_pack": str(ocr_path) if ocr_path else None,
        "loader_contract_audit_record_count": record_count,
        "source_record_count": source_payload.get("summary", {}).get("loader_plan_record_count") or record_count,
        "lineage_ready_count": lineage_ready,
        "missing_lineage_count": missing_lineage,
        "contract_blocked_record_count": blocked,
        "postgres_contract_ready_count": postgres_ready,
        "qdrant_contract_ready_count": qdrant_ready,
        "opensearch_contract_ready_count": opensearch_ready,
        "route_counts": route_counts,
        "live_write_enabled": False,
        "live_write_allowed_count": 0,
        "dry_run_only": True,
        "ready_for_postgres_dry_run_loader": postgres_ready == record_count,
        "ready_for_qdrant_dry_run_loader": qdrant_ready > 0,
        "ready_for_opensearch_dry_run_loader": opensearch_ready > 0,
        "ready_for_live_loaders": False,
        "live_write_blocked_reason": "loader_contract_audit_is_dry_run_only_and_requires_explicit_live_loader_patch",
        "human_review_required_count": 0,
        "manual_review_required_count": 0,
        "unsafe_record_count": sum(1 for r in records if r.get("unsafe") is True),
        "answer_permission_count": sum(1 for r in records if r.get("answer_permission") is True),
        "can_answer_directly_count": sum(1 for r in records if r.get("can_answer_directly") is True),
        "can_prove_claims_count": sum(1 for r in records if r.get("can_prove_claims") is True),
        "source_truth_mutation_allowed_count": sum(1 for r in records if r.get("source_truth_mutation_allowed") is True),
        "postgres_write_attempt_count": sum(1 for r in records if r.get("postgres_write_attempt") is True),
        "qdrant_write_attempt_count": sum(1 for r in records if r.get("qdrant_write_attempt") is True),
        "opensearch_write_attempt_count": sum(1 for r in records if r.get("opensearch_write_attempt") is True),
        "write_attempt_count": sum(1 for r in records if r.get("write_attempted") is True),
    }
    return summary


def _quality_status(summary: Mapping[str, Any]) -> str:
    if summary.get("source_dry_run_loader_planner_quality_status") != "PASS":
        return "FAIL"
    if summary.get("loader_contract_audit_record_count", 0) <= 0:
        return "FAIL"
    if summary.get("unsafe_record_count", 0) != 0:
        return "FAIL"
    if summary.get("answer_permission_count", 0) != 0:
        return "FAIL"
    if summary.get("source_truth_mutation_allowed_count", 0) != 0:
        return "FAIL"
    if summary.get("write_attempt_count", 0) != 0:
        return "FAIL"
    return "PASS"


def build_loader_contract_audit(
    *,
    dry_run_loader_planner: Path,
    output_dir: Path,
    ocr_route_scan_pack: Optional[Path] = None,
    quality: bool = False,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = _paths(output_dir)
    source_payload = _read_json(dry_run_loader_planner)
    ocr_payload = _read_json(ocr_route_scan_pack) if ocr_route_scan_pack else None
    lineage_index = _build_lineage_index(ocr_payload)
    target_plan_index = _build_target_plan_index(source_payload)
    records = [_audit_record(r, lineage_index, target_plan_index) for r in _records(source_payload)]
    postgres_ready = _select_contract_ready(records, "postgres_graph")
    qdrant_ready = _select_contract_ready(records, "qdrant")
    opensearch_ready = _select_contract_ready(records, "opensearch")
    blocked = [dict(r) for r in records if r.get("loader_contract_status") != "ready_dry_run_only"]
    summary = _summarize(records, source_payload, dry_run_loader_planner, ocr_route_scan_pack)
    payload: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "quality_status": _quality_status(summary),
        "summary": summary,
        "records": records,
        "postgres_contract_ready_records": postgres_ready,
        "qdrant_contract_ready_records": qdrant_ready,
        "opensearch_contract_ready_records": opensearch_ready,
        "contract_blocked_records": blocked,
    }
    _write_json(paths.report, payload)
    _write_json(paths.summary_json, summary)
    _write_jsonl(paths.records_jsonl, records)
    _write_csv(paths.records_csv, records)
    _write_jsonl(paths.postgres_contract_jsonl, postgres_ready)
    _write_jsonl(paths.qdrant_contract_jsonl, qdrant_ready)
    _write_jsonl(paths.opensearch_contract_jsonl, opensearch_ready)
    _write_csv(paths.blocked_csv, blocked)
    if quality:
        quality_payload = check_loader_contract_audit_quality(report_path=paths.report, write_json=True)
        payload["quality_check"] = quality_payload
        # Re-read after quality write is not needed; main payload already complete.
    print("Status: TRACE_NET_LOADER_CONTRACT_AUDIT_BUILT")
    print(f"Quality status: {payload['quality_status']}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    return payload


def check_loader_contract_audit_quality(
    *,
    report_path: Path,
    write_json: bool = False,
    min_records: int = 1,
    min_lineage_ready: int = 0,
    max_missing_lineage: Optional[int] = None,
    min_postgres_contract_ready: int = 0,
    min_qdrant_contract_ready: int = 0,
    min_opensearch_contract_ready: int = 0,
    require_source_quality_pass: bool = False,
    require_dry_run_only: bool = False,
    require_no_human_review_required: bool = False,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
    max_unsafe: Optional[int] = None,
) -> Dict[str, Any]:
    payload = _read_json(report_path)
    summary = dict(payload.get("summary") or {})
    failures: List[str] = []
    if payload.get("quality_status") != "PASS":
        failures.append("manifest quality_status is not PASS")
    if summary.get("loader_contract_audit_record_count", 0) < min_records:
        failures.append(f"record count below minimum {min_records}")
    if summary.get("lineage_ready_count", 0) < min_lineage_ready:
        failures.append(f"lineage ready count below minimum {min_lineage_ready}")
    if max_missing_lineage is not None and summary.get("missing_lineage_count", 0) > max_missing_lineage:
        failures.append(f"missing lineage count above maximum {max_missing_lineage}")
    if summary.get("postgres_contract_ready_count", 0) < min_postgres_contract_ready:
        failures.append(f"postgres contract ready count below minimum {min_postgres_contract_ready}")
    if summary.get("qdrant_contract_ready_count", 0) < min_qdrant_contract_ready:
        failures.append(f"qdrant contract ready count below minimum {min_qdrant_contract_ready}")
    if summary.get("opensearch_contract_ready_count", 0) < min_opensearch_contract_ready:
        failures.append(f"opensearch contract ready count below minimum {min_opensearch_contract_ready}")
    if require_source_quality_pass and summary.get("source_dry_run_loader_planner_quality_status") != "PASS":
        failures.append("source dry run loader planner quality_status is not PASS")
    if require_dry_run_only and summary.get("dry_run_only") is not True:
        failures.append("dry_run_only is not true")
    if require_no_human_review_required and (summary.get("human_review_required_count", 0) or summary.get("manual_review_required_count", 0)):
        failures.append("human/manual review required count is nonzero")
    if require_no_answer_permission and summary.get("answer_permission_count", 0) != 0:
        failures.append("answer permission count is nonzero")
    if require_no_source_truth_mutation and summary.get("source_truth_mutation_allowed_count", 0) != 0:
        failures.append("source truth mutation allowed count is nonzero")
    if require_no_write_attempts:
        for key in ("write_attempt_count", "postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"):
            if summary.get(key, 0) != 0:
                failures.append(f"{key} is nonzero")
    if max_unsafe is not None and summary.get("unsafe_record_count", 0) > max_unsafe:
        failures.append(f"unsafe record count above maximum {max_unsafe}")
    quality_payload = {
        "quality_status": "PASS" if not failures else "FAIL",
        "summary": summary,
        "failures": failures,
        "report_path": str(report_path),
    }
    if write_json:
        _write_json(report_path.with_name(QUALITY_JSON), quality_payload)
        print(f"Wrote: {report_path.with_name(QUALITY_JSON)}")
    print(f"Quality status: {quality_payload['quality_status']}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures, indent=2))
    return quality_payload


def main_build(argv: Optional[List[str]] = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Build TRACE-Net loader contract audit v1")
    parser.add_argument("--dry-run-loader-planner", required=True, type=Path)
    parser.add_argument("--ocr-route-scan-pack", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    return build_loader_contract_audit(
        dry_run_loader_planner=args.dry_run_loader_planner,
        ocr_route_scan_pack=args.ocr_route_scan_pack,
        output_dir=args.output_dir,
        quality=args.quality,
    )


def main_check(argv: Optional[List[str]] = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Check TRACE-Net loader contract audit v1 quality")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-lineage-ready", type=int, default=0)
    parser.add_argument("--max-missing-lineage", type=int)
    parser.add_argument("--min-postgres-contract-ready", type=int, default=0)
    parser.add_argument("--min-qdrant-contract-ready", type=int, default=0)
    parser.add_argument("--min-opensearch-contract-ready", type=int, default=0)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-dry-run-only", action="store_true")
    parser.add_argument("--require-no-human-review-required", action="store_true")
    parser.add_argument("--max-unsafe", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args(argv)
    return check_loader_contract_audit_quality(
        report_path=args.report_path,
        write_json=args.write_json,
        min_records=args.min_records,
        min_lineage_ready=args.min_lineage_ready,
        max_missing_lineage=args.max_missing_lineage,
        min_postgres_contract_ready=args.min_postgres_contract_ready,
        min_qdrant_contract_ready=args.min_qdrant_contract_ready,
        min_opensearch_contract_ready=args.min_opensearch_contract_ready,
        require_source_quality_pass=args.require_source_quality_pass,
        require_dry_run_only=args.require_dry_run_only,
        require_no_human_review_required=args.require_no_human_review_required,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
        max_unsafe=args.max_unsafe,
    )


if __name__ == "__main__":
    main_build()
