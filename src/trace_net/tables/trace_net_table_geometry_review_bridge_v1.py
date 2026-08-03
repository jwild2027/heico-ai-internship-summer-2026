"""TRACE-Net Table Geometry Review Bridge v1.

Converts low-confidence/advisory table geometry cards into human-review tasks.

Safety contract:
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority

The bridge is a review-workflow adapter only. It does not decide whether a table
is correct, does not repair source data, and does not authorize final answers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "trace_net_table_geometry_review_bridge_v1"
SOURCE_SCHEMA_VERSION = "trace_net_table_line_geometry_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/table_geometry_review_bridge")
DEFAULT_REPORT_NAME = "trace_net_table_geometry_review_bridge_v1.json"

HARD_FALSE_FIELDS = (
    "can_answer_directly",
    "can_prove_claims",
    "source_truth_mutation_allowed",
    "retrieval_only_answer_allowed",
    "answer_permission",
    "final_answer_allowed",
    "feedback_as_proof",
    "community_as_proof",
    "category_as_proof",
    "corrective_action_as_proof",
)

WRITE_COUNTER_FIELDS = (
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
    "opensearch_write_attempt_count",
)

UNSAFE_INPUT_FIELDS = (
    "can_answer_directly",
    "can_prove_claims",
    "source_truth_mutation_allowed",
    "retrieval_only_answer_allowed",
    "answer_permission",
    "final_answer_allowed",
)


@dataclass(frozen=True)
class QualityThresholds:
    min_review_tasks: int = 1
    min_source_cards: int = 1
    max_unsafe_review_tasks: int = 0
    max_unsafe_source_cards: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_source_quality_pass: bool = False
    require_no_answer_permission: bool = False


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True))
            f.write("\n")


def stable_hash(value: Any, length: int = 14) -> str:
    data = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha1(data.encode("utf-8")).hexdigest()[:length]


def as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return [value]


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "allowed", "pass"}
    return bool(value)


def as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def compact_text(value: Any, max_len: int = 500) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > max_len:
        return text[: max_len - 3].rstrip() + "..."
    return text


def get_source_cards(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    for key in (
        "table_geometry_cards",
        "geometry_cards",
        "cards",
        "records",
        "review_cards",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            return [c for c in value if isinstance(c, dict)]
    return []


def card_needs_review(card: Mapping[str, Any], low_confidence_threshold: float) -> bool:
    if as_bool(card.get("review_required")):
        return True
    if as_list(card.get("review_flags")):
        return True
    if as_int(card.get("merged_cell_candidate_count")) > 0:
        return True
    if as_float(card.get("geometry_confidence"), 1.0) < low_confidence_threshold:
        return True
    if not as_bool(card.get("image_line_detection_available")):
        return True
    return False


def priority_for_card(card: Mapping[str, Any], low_confidence_threshold: float) -> str:
    confidence = as_float(card.get("geometry_confidence"), 0.0)
    merged_count = as_int(card.get("merged_cell_candidate_count"))
    flags = {str(f) for f in as_list(card.get("review_flags"))}
    table_type = str(card.get("table_type") or "").lower()
    part_count = as_int((card.get("domain_validation") or {}).get("part_number_count") if isinstance(card.get("domain_validation"), dict) else 0)

    if merged_count > 0:
        return "HIGH"
    if confidence < max(0.45, low_confidence_threshold - 0.15):
        return "HIGH"
    if "parts" in table_type or part_count > 0:
        return "HIGH"
    if "line_detection_unavailable_or_empty" in flags or "image_not_available_for_geometry_card" in flags:
        return "MEDIUM"
    return "LOW"


def issue_type_for_card(card: Mapping[str, Any], low_confidence_threshold: float) -> str:
    if as_int(card.get("merged_cell_candidate_count")) > 0:
        return "merged_cell_candidate_review"
    if not as_bool(card.get("image_line_detection_available")):
        return "table_geometry_image_line_detection_missing"
    if as_float(card.get("geometry_confidence"), 1.0) < low_confidence_threshold:
        return "table_geometry_low_confidence"
    if as_list(card.get("review_flags")):
        return "table_geometry_review_flag"
    return "table_geometry_review"


def build_reason(card: Mapping[str, Any], low_confidence_threshold: float) -> str:
    parts: List[str] = []
    confidence = as_float(card.get("geometry_confidence"), 0.0)
    if not as_bool(card.get("image_line_detection_available")):
        parts.append("image/ruling-line detection is unavailable for this table geometry card")
    if confidence < low_confidence_threshold:
        parts.append(f"geometry confidence {confidence:.3f} is below threshold {low_confidence_threshold:.3f}")
    merged = as_int(card.get("merged_cell_candidate_count"))
    if merged:
        parts.append(f"{merged} merged-cell candidate(s) require review")
    flags = [str(f) for f in as_list(card.get("review_flags"))]
    if flags:
        parts.append("review flags: " + ", ".join(flags[:8]))
    if not parts:
        parts.append("table geometry card is marked for review")
    return "; ".join(parts)


def normalize_actions(card: Mapping[str, Any]) -> List[str]:
    actions = [str(a) for a in as_list(card.get("recommended_actions")) if str(a).strip()]
    defaults = [
        "verify_table_geometry_against_source_page",
        "confirm_row_column_boundaries",
        "confirm_table_cell_assignment",
    ]
    if as_int(card.get("merged_cell_candidate_count")) > 0:
        defaults.append("review_merged_cell_candidates")
    if not as_bool(card.get("image_line_detection_available")):
        defaults.append("run_or_expand_morphological_line_detection")
    result: List[str] = []
    for action in actions + defaults:
        if action not in result:
            result.append(action)
    return result


def unsafe_source_card_count(cards: Sequence[Mapping[str, Any]]) -> int:
    count = 0
    for card in cards:
        if any(as_bool(card.get(field)) for field in UNSAFE_INPUT_FIELDS):
            count += 1
    return count


def build_review_task(card: Mapping[str, Any], low_confidence_threshold: float) -> Dict[str, Any]:
    domain_validation = card.get("domain_validation") if isinstance(card.get("domain_validation"), dict) else {}
    page_id = card.get("page_id")
    table_id = card.get("table_id")
    geometry_card_id = card.get("geometry_card_id") or card.get("card_id") or stable_hash(card)
    issue_type = issue_type_for_card(card, low_confidence_threshold)
    priority = priority_for_card(card, low_confidence_threshold)
    task_seed = {
        "schema": SCHEMA_VERSION,
        "geometry_card_id": geometry_card_id,
        "page_id": page_id,
        "table_id": table_id,
        "issue_type": issue_type,
    }

    task: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "review_task_id": f"table_geometry_review::{stable_hash(task_seed)}",
        "task_type": "human_review_task",
        "origin_category": "table_geometry",
        "source_module": SOURCE_SCHEMA_VERSION,
        "source_stage": SCHEMA_VERSION,
        "target_type": "table_geometry_card",
        "target_id": geometry_card_id,
        "page_id": page_id,
        "source_page_ids": as_list(card.get("source_page_ids")) or ([page_id] if page_id else []),
        "table_id": table_id,
        "table_type": card.get("table_type"),
        "issue_type": issue_type,
        "priority": priority,
        "severity": priority,
        "reason": build_reason(card, low_confidence_threshold),
        "review_flags": [str(f) for f in as_list(card.get("review_flags"))],
        "recommended_actions": normalize_actions(card),
        "geometry_confidence": as_float(card.get("geometry_confidence"), 0.0),
        "image_line_detection_available": as_bool(card.get("image_line_detection_available")),
        "geometry_inference_method": card.get("geometry_inference_method"),
        "horizontal_line_count": as_int(card.get("horizontal_line_count")),
        "vertical_line_count": as_int(card.get("vertical_line_count")),
        "merged_cell_candidate_count": as_int(card.get("merged_cell_candidate_count")),
        "cell_record_count": as_int(card.get("cell_record_count")),
        "row_record_count": as_int(card.get("row_record_count")),
        "row_count_estimate": as_int(card.get("row_count_estimate")),
        "column_count_estimate": as_int(card.get("column_count_estimate")),
        "domain_validation": domain_validation,
        "domain_table_type_hints": as_list(domain_validation.get("domain_table_type_hints")) if isinstance(domain_validation, dict) else [],
        "part_number_count": as_int(domain_validation.get("part_number_count")) if isinstance(domain_validation, dict) else 0,
        "part_number_row_count": as_int(domain_validation.get("part_number_row_count")) if isinstance(domain_validation, dict) else 0,
        "part_numbers_sample": as_list(domain_validation.get("part_numbers_sample"))[:20] if isinstance(domain_validation, dict) else [],
        "citation_ids": as_list(card.get("citation_ids")),
        "requires_human_review": True,
        "review_status": "OPEN",
        "routing_only": True,
        "retrieval_only": True,
        "read_only_review_task": True,
        "created_at": utc_now_iso(),
        "safety_contract": {
            "no_postgres_writes": True,
            "no_qdrant_writes": True,
            "no_opensearch_writes": True,
            "no_source_truth_mutation": True,
            "no_answer_permission": True,
            "no_claim_proof_authority": True,
            "human_review_required_before_promotion": True,
        },
    }

    for field in HARD_FALSE_FIELDS:
        task[field] = False
    for field in WRITE_COUNTER_FIELDS:
        task[field] = 0
    task["source_truth_mutations_performed"] = 0
    task["unsafe_review_task"] = any(as_bool(task.get(field)) for field in HARD_FALSE_FIELDS)
    return task


def compute_summary(
    *,
    source_payload: Mapping[str, Any],
    source_cards: Sequence[Mapping[str, Any]],
    review_tasks: Sequence[Mapping[str, Any]],
    thresholds: QualityThresholds,
) -> Dict[str, Any]:
    source_quality_status = str(source_payload.get("quality_status") or source_payload.get("status") or "UNKNOWN")
    priority_counts: Dict[str, int] = {}
    issue_type_counts: Dict[str, int] = {}
    review_flag_counts: Dict[str, int] = {}
    recommended_action_counts: Dict[str, int] = {}
    table_type_counts: Dict[str, int] = {}

    for task in review_tasks:
        priority_counts[str(task.get("priority") or "UNKNOWN")] = priority_counts.get(str(task.get("priority") or "UNKNOWN"), 0) + 1
        issue_type_counts[str(task.get("issue_type") or "UNKNOWN")] = issue_type_counts.get(str(task.get("issue_type") or "UNKNOWN"), 0) + 1
        table_type_counts[str(task.get("table_type") or "UNKNOWN")] = table_type_counts.get(str(task.get("table_type") or "UNKNOWN"), 0) + 1
        for flag in as_list(task.get("review_flags")):
            key = str(flag)
            review_flag_counts[key] = review_flag_counts.get(key, 0) + 1
        for action in as_list(task.get("recommended_actions")):
            key = str(action)
            recommended_action_counts[key] = recommended_action_counts.get(key, 0) + 1

    summary: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "TABLE_GEOMETRY_REVIEW_BRIDGE_BUILT",
        "source_schema_version": source_payload.get("schema_version"),
        "source_quality_status": source_quality_status,
        "source_table_geometry_card_count": len(source_cards),
        "review_task_count": len(review_tasks),
        "review_required_task_count": sum(1 for t in review_tasks if as_bool(t.get("requires_human_review"))),
        "high_priority_task_count": sum(1 for t in review_tasks if t.get("priority") == "HIGH"),
        "medium_priority_task_count": sum(1 for t in review_tasks if t.get("priority") == "MEDIUM"),
        "low_priority_task_count": sum(1 for t in review_tasks if t.get("priority") == "LOW"),
        "priority_counts": priority_counts,
        "issue_type_counts": issue_type_counts,
        "review_flag_counts": review_flag_counts,
        "recommended_action_counts": recommended_action_counts,
        "table_type_counts": table_type_counts,
        "merged_cell_review_task_count": sum(1 for t in review_tasks if as_int(t.get("merged_cell_candidate_count")) > 0),
        "image_line_detection_missing_task_count": sum(1 for t in review_tasks if not as_bool(t.get("image_line_detection_available"))),
        "part_number_table_review_task_count": sum(1 for t in review_tasks if as_int(t.get("part_number_count")) > 0),
        "unsafe_source_card_count": unsafe_source_card_count(source_cards),
        "unsafe_review_task_count": sum(1 for t in review_tasks if as_bool(t.get("unsafe_review_task"))),
        "answer_permission_count": sum(1 for t in review_tasks if as_bool(t.get("answer_permission")) or as_bool(t.get("final_answer_allowed"))),
        "can_answer_directly_count": sum(1 for t in review_tasks if as_bool(t.get("can_answer_directly"))),
        "can_prove_claims_count": sum(1 for t in review_tasks if as_bool(t.get("can_prove_claims"))),
        "retrieval_only_answer_allowed_count": sum(1 for t in review_tasks if as_bool(t.get("retrieval_only_answer_allowed"))),
        "source_truth_mutation_allowed_count": sum(1 for t in review_tasks if as_bool(t.get("source_truth_mutation_allowed"))),
        "postgres_write_attempt_count": sum(as_int(t.get("postgres_write_attempt_count")) for t in review_tasks),
        "qdrant_write_attempt_count": sum(as_int(t.get("qdrant_write_attempt_count")) for t in review_tasks),
        "opensearch_write_attempt_count": sum(as_int(t.get("opensearch_write_attempt_count")) for t in review_tasks),
    }

    quality_fail_reasons = quality_fail_reasons_for_summary(summary, thresholds)
    summary["quality_fail_reasons"] = quality_fail_reasons
    summary["quality_status"] = "PASS" if not quality_fail_reasons else "FAIL"
    return summary


def quality_fail_reasons_for_summary(summary: Mapping[str, Any], thresholds: QualityThresholds) -> List[str]:
    reasons: List[str] = []
    if thresholds.require_source_quality_pass and str(summary.get("source_quality_status")) != "PASS":
        reasons.append("source table line geometry quality is not PASS")
    if as_int(summary.get("source_table_geometry_card_count")) < thresholds.min_source_cards:
        reasons.append("source_table_geometry_card_count below minimum")
    if as_int(summary.get("review_task_count")) < thresholds.min_review_tasks:
        reasons.append("review_task_count below minimum")
    if as_int(summary.get("unsafe_source_card_count")) > thresholds.max_unsafe_source_cards:
        reasons.append("unsafe_source_card_count above maximum")
    if as_int(summary.get("unsafe_review_task_count")) > thresholds.max_unsafe_review_tasks:
        reasons.append("unsafe_review_task_count above maximum")
    if as_int(summary.get("answer_permission_count")) > thresholds.max_answer_permission_count:
        reasons.append("answer_permission_count above maximum")
    if as_int(summary.get("source_truth_mutation_allowed_count")) > thresholds.max_source_truth_mutation_allowed:
        reasons.append("source_truth_mutation_allowed_count above maximum")
    if thresholds.require_no_answer_permission:
        for key in ("answer_permission_count", "can_answer_directly_count", "can_prove_claims_count", "retrieval_only_answer_allowed_count"):
            if as_int(summary.get(key)) != 0:
                reasons.append(f"{key} must be zero")
    for key in ("postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"):
        if as_int(summary.get(key)) != 0:
            reasons.append(f"{key} must be zero")
    return reasons


def build_checks(summary: Mapping[str, Any], thresholds: QualityThresholds) -> Dict[str, bool]:
    return {
        "schema_version_ok": True,
        "source_quality_pass": (str(summary.get("source_quality_status")) == "PASS") or not thresholds.require_source_quality_pass,
        "min_source_cards_met": as_int(summary.get("source_table_geometry_card_count")) >= thresholds.min_source_cards,
        "min_review_tasks_met": as_int(summary.get("review_task_count")) >= thresholds.min_review_tasks,
        "unsafe_source_cards_within_limit": as_int(summary.get("unsafe_source_card_count")) <= thresholds.max_unsafe_source_cards,
        "unsafe_review_tasks_within_limit": as_int(summary.get("unsafe_review_task_count")) <= thresholds.max_unsafe_review_tasks,
        "answer_permission_zero": as_int(summary.get("answer_permission_count")) == 0,
        "can_answer_directly_zero": as_int(summary.get("can_answer_directly_count")) == 0,
        "can_prove_claims_zero": as_int(summary.get("can_prove_claims_count")) == 0,
        "source_truth_mutation_allowed_zero": as_int(summary.get("source_truth_mutation_allowed_count")) == 0,
        "write_attempts_zero": all(as_int(summary.get(k)) == 0 for k in ("postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count")),
    }


def build_review_bridge_report(
    *,
    table_line_geometry_path: Path,
    output_dir: Path,
    thresholds: QualityThresholds,
    low_confidence_threshold: float = 0.75,
    include_non_review_cards: bool = False,
) -> Dict[str, Any]:
    source_payload = read_json(table_line_geometry_path)
    source_cards = get_source_cards(source_payload)
    review_tasks: List[Dict[str, Any]] = []

    for card in source_cards:
        if include_non_review_cards or card_needs_review(card, low_confidence_threshold):
            review_tasks.append(build_review_task(card, low_confidence_threshold))

    summary = compute_summary(
        source_payload=source_payload,
        source_cards=source_cards,
        review_tasks=review_tasks,
        thresholds=thresholds,
    )
    checks = build_checks(summary, thresholds)
    quality_status = summary["quality_status"]

    report: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "TABLE_GEOMETRY_REVIEW_BRIDGE_BUILT" if quality_status == "PASS" else "TABLE_GEOMETRY_REVIEW_BRIDGE_NOT_READY",
        "quality_status": quality_status,
        "generated_at": utc_now_iso(),
        "source_artifacts": {
            "table_line_geometry": str(table_line_geometry_path),
        },
        "thresholds": {
            "min_review_tasks": thresholds.min_review_tasks,
            "min_source_cards": thresholds.min_source_cards,
            "max_unsafe_review_tasks": thresholds.max_unsafe_review_tasks,
            "max_unsafe_source_cards": thresholds.max_unsafe_source_cards,
            "max_answer_permission_count": thresholds.max_answer_permission_count,
            "max_source_truth_mutation_allowed": thresholds.max_source_truth_mutation_allowed,
            "require_source_quality_pass": thresholds.require_source_quality_pass,
            "require_no_answer_permission": thresholds.require_no_answer_permission,
            "low_confidence_threshold": low_confidence_threshold,
        },
        "summary": summary,
        "checks": checks,
        "review_tasks": review_tasks,
        "safety_contract": {
            "read_only_bridge": True,
            "human_review_tasks_are_not_source_truth": True,
            "no_postgres_writes": True,
            "no_qdrant_writes": True,
            "no_opensearch_writes": True,
            "no_source_truth_mutation": True,
            "no_answer_permission": True,
            "no_claim_proof_authority": True,
        },
    }

    write_report_artifacts(report, output_dir)
    return report


def write_report_artifacts(report: Mapping[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / DEFAULT_REPORT_NAME
    tasks_path = output_dir / "trace_net_table_geometry_review_bridge_v1_tasks.jsonl"
    summary_path = output_dir / "trace_net_table_geometry_review_bridge_v1_summary.json"
    quality_path = output_dir / "trace_net_table_geometry_review_bridge_v1_quality.json"
    manifest_path = output_dir / "trace_net_table_geometry_review_bridge_v1_manifest.json"

    write_json(report_path, report)
    write_jsonl(tasks_path, report.get("review_tasks") or [])
    write_json(summary_path, report.get("summary") or {})
    quality_payload = {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": report.get("quality_status"),
        "quality_status": report.get("quality_status"),
        "generated_at": report.get("generated_at"),
        "summary": report.get("summary"),
        "checks": report.get("checks"),
        "quality_errors": (report.get("summary") or {}).get("quality_fail_reasons", []),
    }
    write_json(quality_path, quality_payload)
    manifest = {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": report.get("generated_at"),
        "quality_status": report.get("quality_status"),
        "artifacts": {
            "report": str(report_path),
            "tasks_jsonl": str(tasks_path),
            "summary": str(summary_path),
            "quality": str(quality_path),
        },
        "source_artifacts": report.get("source_artifacts"),
    }
    write_json(manifest_path, manifest)


def thresholds_from_args(args: argparse.Namespace) -> QualityThresholds:
    return QualityThresholds(
        min_review_tasks=args.min_review_tasks,
        min_source_cards=args.min_source_cards,
        max_unsafe_review_tasks=args.max_unsafe_review_tasks,
        max_unsafe_source_cards=args.max_unsafe_source_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_source_quality_pass=args.require_source_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net table geometry review bridge v1")
    parser.add_argument("--table-line-geometry", required=True, type=Path)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, type=Path)
    parser.add_argument("--low-confidence-threshold", default=0.75, type=float)
    parser.add_argument("--include-non-review-cards", action="store_true")
    parser.add_argument("--min-review-tasks", default=1, type=int)
    parser.add_argument("--min-source-cards", default=1, type=int)
    parser.add_argument("--max-unsafe-review-tasks", default=0, type=int)
    parser.add_argument("--max-unsafe-source-cards", default=0, type=int)
    parser.add_argument("--max-answer-permission-count", default=0, type=int)
    parser.add_argument("--max-source-truth-mutation-allowed", default=0, type=int)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    thresholds = thresholds_from_args(args)
    report = build_review_bridge_report(
        table_line_geometry_path=args.table_line_geometry,
        output_dir=args.output_dir,
        thresholds=thresholds,
        low_confidence_threshold=args.low_confidence_threshold,
        include_non_review_cards=args.include_non_review_cards,
    )
    summary = report.get("summary") or {}
    print("TRACE-Net Table Geometry Review Bridge v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in (
        "source_table_geometry_card_count",
        "review_task_count",
        "review_required_task_count",
        "high_priority_task_count",
        "merged_cell_review_task_count",
        "image_line_detection_missing_task_count",
        "part_number_table_review_task_count",
        "unsafe_source_card_count",
        "unsafe_review_task_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {args.output_dir / DEFAULT_REPORT_NAME}")
    print(f" quality_path: {args.output_dir / 'trace_net_table_geometry_review_bridge_v1_quality.json'}")
    if args.quality and report.get("quality_status") != "PASS":
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
