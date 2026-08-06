#!/usr/bin/env python
"""
TRACE-Net Leiden Navigation Metadata Bridge v1.

Read-only adapter that turns tightened Leiden community profiles into navigation
metadata for retrieval/UI. The output is explicitly advisory/routing-only:
communities, labels, and category hints are never proof and never grant answer
permission.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_leiden_navigation_metadata_bridge_v1"
DEFAULT_REPORT_NAME = "trace_net_leiden_navigation_metadata_bridge_v1.json"
DEFAULT_QUALITY_NAME = "trace_net_leiden_navigation_metadata_bridge_v1_quality.json"
DEFAULT_RECORDS_NAME = "trace_net_leiden_navigation_metadata_bridge_v1_records.jsonl"
DEFAULT_PAGE_HINTS_NAME = "trace_net_leiden_navigation_metadata_bridge_v1_page_hints.jsonl"
DEFAULT_MARKDOWN_NAME = "trace_net_leiden_navigation_metadata_bridge_v1.md"

PASS_STATUSES = {"PASS", "OK", "BUILT", "LOADED", "LEIDEN_REPRESENTATIVE_LABELS_REFINED"}
NAVIGABLE_CONFIDENCES = {"HIGH_NAVIGATION_CONFIDENCE", "MODERATE_NAVIGATION_CONFIDENCE"}
REVIEW_CONFIDENCES = {"LOW_NAVIGATION_CONFIDENCE", "REVIEW_ONLY"}
SAFE_ZERO_COUNTERS = (
    "community_as_proof_count",
    "category_as_proof_count",
    "retrieval_only_answer_allowed_count",
    "can_answer_directly_count",
    "can_prove_claims_count",
    "source_truth_mutation_allowed_count",
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
    "opensearch_write_attempt_count",
)


@dataclass(frozen=True)
class BridgeThresholds:
    min_community_records: int = 1
    min_retrieval_hints: int = 1
    min_page_navigation_hints: int = 1
    max_review_only_communities: int | None = None
    max_low_confidence_communities: int | None = None
    max_missing_page_membership: int | None = None
    max_community_as_proof: int = 0
    max_category_as_proof: int = 0
    max_retrieval_only_answer_allowed: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_label_tightening_quality_pass: bool = False
    require_no_answer_permission: bool = False


def load_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing JSON input: {p}")
    with p.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise TypeError(f"Expected JSON object at {p}")
    return payload


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: str | Path, records: Iterable[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def normalize_status(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    return str(value).strip()


def quality_is_pass(payload: dict[str, Any]) -> bool:
    status = normalize_status(payload.get("quality_status") or payload.get("status"))
    return status.upper() in PASS_STATUSES or status in PASS_STATUSES


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def unique_strings(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def find_community_profiles(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in (
        "community_profile_records",
        "community_profiles",
        "navigation_profiles",
        "records",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def normalize_part_family(value: Any, part_numbers: list[str]) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    for part in part_numbers:
        match = re.match(r"^(\d{3}-\d{5})", part)
        if match:
            return match.group(1)
    return None


def navigation_tags(record: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    for key in ("navigation_intent", "navigation_confidence", "dominant_evidence_category"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            tags.append(value.strip())
    part_family = normalize_part_family(
        record.get("representative_part_family"),
        unique_strings(record.get("representative_part_numbers") or []),
    )
    if part_family:
        tags.append(f"part_family:{part_family}")
    for flag in record.get("risk_flags") or []:
        tags.append(f"risk:{flag}")
    return unique_strings(tags)


def build_hint_text(record: dict[str, Any], part_numbers: list[str], page_ids: list[str]) -> str:
    label = str(record.get("refined_label") or record.get("source_label") or record.get("label") or "TRACE-Net Leiden community")
    intent = str(record.get("navigation_intent") or "community_navigation")
    category = str(record.get("dominant_evidence_category") or "mixed_evidence")
    pieces = [label, f"Intent: {intent}", f"Dominant evidence: {category}"]
    part_family = normalize_part_family(record.get("representative_part_family"), part_numbers)
    if part_family:
        pieces.append(f"Part family: {part_family}")
    if part_numbers:
        pieces.append("Representative parts: " + ", ".join(part_numbers[:12]))
    if page_ids:
        pieces.append("Representative pages: " + ", ".join(page_ids[:8]))
    pieces.append("Use as navigation/ranking metadata only; not proof and not answer authority.")
    return " | ".join(pieces)


def source_quality_statuses(label_payload: dict[str, Any]) -> dict[str, str]:
    summary = label_payload.get("summary") if isinstance(label_payload.get("summary"), dict) else {}
    statuses = summary.get("source_quality_statuses") if isinstance(summary.get("source_quality_statuses"), dict) else {}
    out = {str(k): str(v) for k, v in statuses.items()}
    out.setdefault("leiden_representative_label_tightening", normalize_status(label_payload.get("quality_status")))
    return out


def build_navigation_metadata_bridge(
    *,
    label_tightening_path: str | Path,
    output_dir: str | Path | None = None,
    thresholds: BridgeThresholds | None = None,
    write_files: bool = True,
) -> dict[str, Any]:
    thresholds = thresholds or BridgeThresholds()
    label_payload = load_json(label_tightening_path)
    profiles = find_community_profiles(label_payload)

    community_records: list[dict[str, Any]] = []
    retrieval_hint_records: list[dict[str, Any]] = []
    page_hint_records: list[dict[str, Any]] = []
    review_records: list[dict[str, Any]] = []

    for index, record in enumerate(profiles, start=1):
        community_id = str(record.get("community_id") or f"community_{index:05d}")
        page_ids = unique_strings(record.get("representative_page_ids") or record.get("sample_page_ids") or [])
        part_numbers = unique_strings(record.get("representative_part_numbers") or record.get("sample_part_numbers") or [])
        confidence = str(record.get("navigation_confidence") or "REVIEW_ONLY")
        risk_flags = unique_strings(record.get("risk_flags") or [])
        review_reasons = unique_strings(record.get("review_reasons") or [])
        page_count = safe_int(record.get("page_count"), len(page_ids))
        part_family = normalize_part_family(record.get("representative_part_family"), part_numbers)
        missing_page_membership = page_count <= 0 or not page_ids or "missing_page_membership" in risk_flags
        review_only = confidence == "REVIEW_ONLY" or missing_page_membership
        retrieval_boost_allowed = confidence in NAVIGABLE_CONFIDENCES and not missing_page_membership
        graph_ui_navigation_allowed = not missing_page_membership

        bridge_record = {
            "schema_version": SCHEMA_VERSION,
            "record_type": "leiden_navigation_metadata",
            "bridge_record_id": f"{SCHEMA_VERSION}:{community_id}",
            "source_profile_index": index - 1,
            "community_id": community_id,
            "source_label": record.get("source_label") or record.get("label"),
            "refined_label": record.get("refined_label") or record.get("source_label") or record.get("label"),
            "page_count": page_count,
            "representative_page_ids": page_ids[:10],
            "representative_part_family": part_family,
            "representative_part_numbers": part_numbers[:20],
            "dominant_evidence_category": record.get("dominant_evidence_category"),
            "dominant_evidence_ratio": safe_float(record.get("dominant_evidence_ratio")),
            "navigation_intent": record.get("navigation_intent") or "community_navigation",
            "navigation_confidence": confidence,
            "macro_category_counts": record.get("macro_category_counts") if isinstance(record.get("macro_category_counts"), dict) else {},
            "navigation_tags": navigation_tags(record),
            "navigation_hint_text": build_hint_text(record, part_numbers, page_ids),
            "retrieval_boost_allowed": retrieval_boost_allowed,
            "graph_ui_navigation_allowed": graph_ui_navigation_allowed,
            "review_only": review_only,
            "review_recommended": bool(review_reasons or risk_flags or review_only or confidence in REVIEW_CONFIDENCES),
            "risk_flags": risk_flags,
            "review_reasons": review_reasons,
            "routing_only": True,
            "retrieval_only": True,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "answer_permission": False,
            "community_as_proof": False,
            "category_as_proof": False,
            "source_truth_mutation_allowed": False,
        }
        community_records.append(bridge_record)

        if retrieval_boost_allowed:
            retrieval_hint_records.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "record_type": "leiden_retrieval_navigation_hint",
                    "retrieval_hint_id": f"{SCHEMA_VERSION}:retrieval_hint:{community_id}",
                    "community_id": community_id,
                    "refined_label": bridge_record["refined_label"],
                    "navigation_intent": bridge_record["navigation_intent"],
                    "navigation_confidence": confidence,
                    "representative_page_ids": page_ids[:10],
                    "representative_part_family": part_family,
                    "representative_part_numbers": part_numbers[:20],
                    "navigation_hint_text": bridge_record["navigation_hint_text"],
                    "navigation_tags": bridge_record["navigation_tags"],
                    "boost_scope": "navigation_and_ranking_only",
                    "retrieval_only": True,
                    "can_answer_directly": False,
                    "can_prove_claims": False,
                    "answer_permission": False,
                }
            )

        for page_id in page_ids[:10]:
            page_hint_records.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "record_type": "leiden_page_navigation_hint",
                    "page_navigation_hint_id": f"{SCHEMA_VERSION}:page:{page_id}:{community_id}",
                    "page_id": page_id,
                    "community_id": community_id,
                    "refined_label": bridge_record["refined_label"],
                    "navigation_intent": bridge_record["navigation_intent"],
                    "navigation_confidence": confidence,
                    "representative_part_family": part_family,
                    "dominant_evidence_category": bridge_record["dominant_evidence_category"],
                    "graph_ui_navigation_allowed": graph_ui_navigation_allowed,
                    "retrieval_only": True,
                    "can_answer_directly": False,
                    "can_prove_claims": False,
                    "answer_permission": False,
                }
            )

        if bridge_record["review_recommended"]:
            review_records.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "record_type": "leiden_navigation_review_record",
                    "review_record_id": f"{SCHEMA_VERSION}:review:{community_id}",
                    "community_id": community_id,
                    "refined_label": bridge_record["refined_label"],
                    "page_count": page_count,
                    "representative_page_ids": page_ids[:10],
                    "navigation_confidence": confidence,
                    "risk_flags": risk_flags,
                    "review_reasons": review_reasons or (["community_requires_navigation_label_review"] if confidence in REVIEW_CONFIDENCES else []),
                    "review_priority": "HIGH" if review_only else "NORMAL",
                    "can_answer_directly": False,
                    "can_prove_claims": False,
                    "source_truth_mutation_allowed": False,
                }
            )

    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_label_tightening_quality_status": normalize_status(label_payload.get("quality_status")),
        "source_label_tightening_status": normalize_status(label_payload.get("status")),
        "source_quality_statuses": source_quality_statuses(label_payload),
        "community_navigation_record_count": len(community_records),
        "retrieval_navigation_hint_count": len(retrieval_hint_records),
        "page_navigation_hint_count": len(page_hint_records),
        "review_navigation_record_count": len(review_records),
        "review_only_community_count": sum(1 for r in community_records if r.get("review_only")),
        "low_navigation_confidence_count": sum(1 for r in community_records if r.get("navigation_confidence") == "LOW_NAVIGATION_CONFIDENCE"),
        "high_navigation_confidence_count": sum(1 for r in community_records if r.get("navigation_confidence") == "HIGH_NAVIGATION_CONFIDENCE"),
        "moderate_navigation_confidence_count": sum(1 for r in community_records if r.get("navigation_confidence") == "MODERATE_NAVIGATION_CONFIDENCE"),
        "missing_page_membership_count": sum(1 for r in community_records if "missing_page_membership" in (r.get("risk_flags") or []) or not r.get("representative_page_ids")),
        "mixed_navigation_intent_count": sum(1 for r in community_records if "mixed_navigation_intent" in (r.get("risk_flags") or [])),
        "part_family_navigation_hint_count": sum(1 for r in retrieval_hint_records if r.get("navigation_intent") == "part_family_navigation"),
        "table_navigation_hint_count": sum(1 for r in retrieval_hint_records if r.get("navigation_intent") == "table_evidence_navigation"),
        "visual_navigation_hint_count": sum(1 for r in retrieval_hint_records if r.get("navigation_intent") == "visual_evidence_navigation"),
        "mixed_navigation_hint_count": sum(1 for r in retrieval_hint_records if r.get("navigation_intent") == "mixed_evidence_navigation"),
        "community_as_proof_count": 0,
        "category_as_proof_count": 0,
        "retrieval_only_answer_allowed_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }

    quality_status, quality_issues = evaluate_bridge_quality(summary, thresholds, label_payload)
    summary["status"] = quality_status
    summary["quality_issues"] = quality_issues

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "LEIDEN_NAVIGATION_METADATA_BRIDGE_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "source_artifacts": {
            "leiden_representative_label_tightening": str(label_tightening_path),
        },
        "community_navigation_records": community_records,
        "retrieval_navigation_hints": retrieval_hint_records,
        "page_navigation_hints": page_hint_records,
        "review_navigation_records": review_records,
    }

    if write_files and output_dir is not None:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        report_path = out_dir / DEFAULT_REPORT_NAME
        quality_path = out_dir / DEFAULT_QUALITY_NAME
        records_path = out_dir / DEFAULT_RECORDS_NAME
        page_hints_path = out_dir / DEFAULT_PAGE_HINTS_NAME
        markdown_path = out_dir / DEFAULT_MARKDOWN_NAME
        write_json(report_path, report)
        write_json(quality_path, quality_report_from_report(report))
        write_jsonl(records_path, community_records)
        write_jsonl(page_hints_path, page_hint_records)
        markdown_path.write_text(render_markdown(report), encoding="utf-8")
        report["report_path"] = str(report_path)
        report["quality_path"] = str(quality_path)
        report["records_path"] = str(records_path)
        report["page_hints_path"] = str(page_hints_path)
        report["markdown_path"] = str(markdown_path)
    return report


def evaluate_bridge_quality(
    summary: dict[str, Any],
    thresholds: BridgeThresholds,
    label_payload: dict[str, Any] | None = None,
) -> tuple[str, list[str]]:
    issues: list[str] = []
    if safe_int(summary.get("community_navigation_record_count")) < thresholds.min_community_records:
        issues.append("community_navigation_record_count_below_minimum")
    if safe_int(summary.get("retrieval_navigation_hint_count")) < thresholds.min_retrieval_hints:
        issues.append("retrieval_navigation_hint_count_below_minimum")
    if safe_int(summary.get("page_navigation_hint_count")) < thresholds.min_page_navigation_hints:
        issues.append("page_navigation_hint_count_below_minimum")
    if thresholds.max_review_only_communities is not None and safe_int(summary.get("review_only_community_count")) > thresholds.max_review_only_communities:
        issues.append("review_only_community_count_above_maximum")
    if thresholds.max_low_confidence_communities is not None and safe_int(summary.get("low_navigation_confidence_count")) > thresholds.max_low_confidence_communities:
        issues.append("low_navigation_confidence_count_above_maximum")
    if thresholds.max_missing_page_membership is not None and safe_int(summary.get("missing_page_membership_count")) > thresholds.max_missing_page_membership:
        issues.append("missing_page_membership_count_above_maximum")
    if safe_int(summary.get("community_as_proof_count")) > thresholds.max_community_as_proof:
        issues.append("community_as_proof_count_above_maximum")
    if safe_int(summary.get("category_as_proof_count")) > thresholds.max_category_as_proof:
        issues.append("category_as_proof_count_above_maximum")
    if safe_int(summary.get("retrieval_only_answer_allowed_count")) > thresholds.max_retrieval_only_answer_allowed:
        issues.append("retrieval_only_answer_allowed_count_above_maximum")
    if safe_int(summary.get("source_truth_mutation_allowed_count")) > thresholds.max_source_truth_mutation_allowed:
        issues.append("source_truth_mutation_allowed_count_above_maximum")
    if thresholds.require_label_tightening_quality_pass and label_payload is not None and not quality_is_pass(label_payload):
        issues.append("label_tightening_quality_not_pass")
    if thresholds.require_no_answer_permission:
        if safe_int(summary.get("can_answer_directly_count")) != 0:
            issues.append("can_answer_directly_count_must_be_zero")
        if safe_int(summary.get("can_prove_claims_count")) != 0:
            issues.append("can_prove_claims_count_must_be_zero")
    return ("PASS" if not issues else "FAIL", issues)


def quality_report_from_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report.get("schema_version"),
        "status": report.get("status"),
        "quality_status": report.get("quality_status"),
        "summary": report.get("summary", {}),
    }


def check_bridge_quality(
    *,
    report_path: str | Path,
    thresholds: BridgeThresholds | None = None,
    write_json_report: bool = False,
) -> dict[str, Any]:
    thresholds = thresholds or BridgeThresholds()
    report = load_json(report_path)
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    quality_status, issues = evaluate_bridge_quality(summary, thresholds, None)
    report["quality_status"] = quality_status
    summary["status"] = quality_status
    summary["quality_issues"] = issues
    report["summary"] = summary
    quality = quality_report_from_report(report)
    if write_json_report:
        p = Path(report_path)
        write_json(p.with_name(DEFAULT_QUALITY_NAME), quality)
    return quality


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# TRACE-Net Leiden Navigation Metadata Bridge v1",
        "",
        f"Quality status: {report.get('quality_status')}",
        f"Status: {report.get('status')}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "community_navigation_record_count",
        "retrieval_navigation_hint_count",
        "page_navigation_hint_count",
        "review_navigation_record_count",
        "review_only_community_count",
        "low_navigation_confidence_count",
        "missing_page_membership_count",
        "community_as_proof_count",
        "category_as_proof_count",
        "retrieval_only_answer_allowed_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend([
        "",
        "## Safety Contract",
        "",
        "These records are routing/navigation metadata only. They cannot answer directly, prove claims, or mutate source truth.",
        "",
    ])
    return "\n".join(lines)


def add_threshold_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-community-records", type=int, default=1)
    parser.add_argument("--min-retrieval-hints", type=int, default=1)
    parser.add_argument("--min-page-navigation-hints", type=int, default=1)
    parser.add_argument("--max-review-only-communities", type=int, default=None)
    parser.add_argument("--max-low-confidence-communities", type=int, default=None)
    parser.add_argument("--max-missing-page-membership", type=int, default=None)
    parser.add_argument("--max-community-as-proof", type=int, default=0)
    parser.add_argument("--max-category-as-proof", type=int, default=0)
    parser.add_argument("--max-retrieval-only-answer-allowed", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-label-tightening-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")


def thresholds_from_args(args: argparse.Namespace) -> BridgeThresholds:
    return BridgeThresholds(
        min_community_records=args.min_community_records,
        min_retrieval_hints=args.min_retrieval_hints,
        min_page_navigation_hints=args.min_page_navigation_hints,
        max_review_only_communities=args.max_review_only_communities,
        max_low_confidence_communities=args.max_low_confidence_communities,
        max_missing_page_membership=args.max_missing_page_membership,
        max_community_as_proof=args.max_community_as_proof,
        max_category_as_proof=args.max_category_as_proof,
        max_retrieval_only_answer_allowed=args.max_retrieval_only_answer_allowed,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_label_tightening_quality_pass=args.require_label_tightening_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )


def print_summary(report: dict[str, Any]) -> None:
    summary = report.get("summary", {})
    print("TRACE-Net Leiden Navigation Metadata Bridge v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "source_label_tightening_quality_status",
        "community_navigation_record_count",
        "retrieval_navigation_hint_count",
        "page_navigation_hint_count",
        "review_navigation_record_count",
        "review_only_community_count",
        "low_navigation_confidence_count",
        "missing_page_membership_count",
        "part_family_navigation_hint_count",
        "table_navigation_hint_count",
        "visual_navigation_hint_count",
        "mixed_navigation_hint_count",
        "community_as_proof_count",
        "category_as_proof_count",
        "retrieval_only_answer_allowed_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    for key in ("report_path", "quality_path", "records_path", "page_hints_path"):
        if key in report:
            print(f" {key}: {report[key]}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Leiden Navigation Metadata Bridge v1")
    parser.add_argument("--leiden-representative-label-tightening", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", action="store_true")
    add_threshold_args(parser)
    return parser


def quality_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Leiden Navigation Metadata Bridge v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    add_threshold_args(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = build_navigation_metadata_bridge(
        label_tightening_path=args.leiden_representative_label_tightening,
        output_dir=args.output_dir,
        thresholds=thresholds_from_args(args),
        write_files=True,
    )
    print_summary(report)
    return 0 if report.get("quality_status") == "PASS" else 2


def quality_main(argv: list[str] | None = None) -> int:
    parser = quality_arg_parser()
    args = parser.parse_args(argv)
    quality = check_bridge_quality(
        report_path=args.report_path,
        thresholds=thresholds_from_args(args),
        write_json_report=args.write_json,
    )
    print_summary(quality)
    return 0 if quality.get("quality_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
