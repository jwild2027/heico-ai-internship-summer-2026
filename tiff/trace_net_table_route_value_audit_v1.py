"""TRACE-Net Table Route Value Audit v1.

Audits normalized table-route values before they are promoted into retrieval or
search evidence. This module is intentionally read-only and does not write to
Postgres, Qdrant, OpenSearch, or any source-truth artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "trace_net_table_route_value_audit_v1"
QUALITY_SCHEMA_VERSION = "trace_net_table_route_value_audit_v1_quality"
STATUS_BUILT = "TABLE_ROUTE_VALUE_AUDIT_BUILT"
STATUS_REVIEW = "TABLE_ROUTE_VALUE_AUDIT_REVIEW_REQUIRED"
STATUS_SKIPPED = "TABLE_ROUTE_VALUE_AUDIT_SKIPPED"

SOURCE_SCHEMA_VERSION = "trace_net_table_route_value_normalizer_v1"

PROMOTABLE_FIELDS = {
    "covered_part_number",
    "manual_page_reference",
    "page_rev_or_sequence_value",
    "ipl_part_number",
    "ipl_figure_item_or_quantity",
    "ipl_text",
}
CONTEXT_FIELDS = {
    "lep_context",
    "ipl_context",
    "part_number_coverage_context",
}
PART_NUMBER_FIELDS = {"covered_part_number", "ipl_part_number"}
PAGE_REF_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}(?:-\d{1,4})?\b")
PART_NUMBER_RE = re.compile(r"\b\d{2,3}-\d{2,5}(?:-\d{2,4})?\b")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(dict(record), sort_keys=True, ensure_ascii=False) + "\n")


def stable_id(prefix: str, *parts: Any) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(str(part).encode("utf-8", "ignore"))
        h.update(b"\x1f")
    return f"{prefix}__{h.hexdigest()[:16]}"


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\u00a0", " ").split())


def is_context_field(field_name: str | None, evidence_kind: str | None) -> bool:
    return str(field_name or "") in CONTEXT_FIELDS or str(evidence_kind or "") == "context"


def is_promotable_value(value: Mapping[str, Any], min_confidence: float) -> tuple[bool, list[str]]:
    field = str(value.get("field_name") or "")
    evidence_kind = str(value.get("evidence_kind") or "")
    confidence = float(value.get("normalization_confidence") or 0.0)
    normalized_value = normalize_text(value.get("normalized_value"))
    flags: list[str] = []

    if not normalized_value:
        return False, ["empty_normalized_value"]
    if is_context_field(field, evidence_kind):
        return False, ["context_only_value"]
    if field not in PROMOTABLE_FIELDS:
        return False, ["unpromoted_field"]
    if confidence < min_confidence:
        flags.append("low_normalization_confidence")
    if field in PART_NUMBER_FIELDS and not PART_NUMBER_RE.fullmatch(normalized_value):
        flags.append("part_number_format_review")
    if field == "manual_page_reference" and not PAGE_REF_RE.fullmatch(normalized_value):
        flags.append("manual_page_reference_format_review")

    return len(flags) == 0, flags


def build_promoted_record(value: Mapping[str, Any], flags: list[str]) -> dict[str, Any]:
    promoted = {
        "audit_value_record_id": stable_id(
            "table_route_audited_value",
            value.get("normalized_value_record_id"),
            value.get("table_id"),
            value.get("field_name"),
            value.get("normalized_value"),
        ),
        "schema_version": SCHEMA_VERSION,
        "source_normalized_value_record_id": value.get("normalized_value_record_id"),
        "page_id": value.get("page_id"),
        "table_id": value.get("table_id"),
        "table_template_type": value.get("table_template_type"),
        "field_name": value.get("field_name"),
        "normalized_value": value.get("normalized_value"),
        "raw_value_text": value.get("raw_value_text"),
        "evidence_kind": value.get("evidence_kind"),
        "normalization_confidence": value.get("normalization_confidence"),
        "audit_promotion_state": "search_ready_evidence",
        "audit_flags": flags,
        "row_index": value.get("row_index"),
        "column_index": value.get("column_index"),
        "cell_bbox": value.get("cell_bbox"),
        "source_trace": {
            "source_module": "trace_net_table_route_value_normalizer_v1",
            "source_value_record_id": value.get("normalized_value_record_id"),
            "source_cell_id": value.get("source_cell_id"),
            "page_id": value.get("page_id"),
            "table_id": value.get("table_id"),
            "field_name": value.get("field_name"),
        },
        "retrieval_only": True,
        "search_index_candidate": True,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempted": False,
        "qdrant_write_attempted": False,
        "opensearch_write_attempted": False,
        "unsafe_table_route_value_audit": False,
    }
    return promoted


def _table_requirement(template: str, field_counts: Counter[str], context_ratio: float, max_context_ratio: float) -> tuple[str, list[str]]:
    flags: list[str] = []
    if template == "part_number_coverage_list":
        if field_counts.get("covered_part_number", 0) <= 0:
            flags.append("missing_covered_part_numbers")
    elif template == "list_of_effective_pages":
        if field_counts.get("manual_page_reference", 0) <= 0:
            flags.append("missing_manual_page_references")
        if field_counts.get("page_rev_or_sequence_value", 0) <= 0:
            flags.append("missing_page_rev_or_sequence_values")
        if context_ratio > max_context_ratio:
            flags.append("high_context_ratio")
    elif template == "ipl_split_column_table":
        if field_counts.get("ipl_part_number", 0) <= 0:
            flags.append("missing_ipl_part_numbers")
        if field_counts.get("ipl_figure_item_or_quantity", 0) <= 0:
            flags.append("missing_ipl_fig_item_or_quantity_values")
    elif template in {"unknown_table_template", "generic_table", ""}:
        flags.append("unknown_or_generic_template_review")
    return ("review_required" if flags else "evidence_ready"), flags


def build_audit_records(
    normalizer_report: Mapping[str, Any],
    *,
    min_promote_confidence: float = 0.60,
    max_context_ratio: float = 0.75,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    source_records = [r for r in (normalizer_report.get("table_route_value_normalizer_records") or []) if isinstance(r, Mapping)]
    source_values = [v for v in (normalizer_report.get("table_route_normalized_value_records") or []) if isinstance(v, Mapping)]

    values_by_table: dict[Any, list[Mapping[str, Any]]] = defaultdict(list)
    for value in source_values:
        values_by_table[value.get("table_id")].append(value)

    audit_records: list[dict[str, Any]] = []
    promoted_values: list[dict[str, Any]] = []
    source_record_by_table = {r.get("table_id"): r for r in source_records}
    all_table_ids = list(source_record_by_table.keys())
    for table_id in values_by_table:
        if table_id not in source_record_by_table:
            all_table_ids.append(table_id)

    for table_id in all_table_ids:
        record = source_record_by_table.get(table_id) or {}
        values = values_by_table.get(table_id, [])
        template = str(record.get("table_template_type") or (values[0].get("table_template_type") if values else "unknown_table_template"))
        page_id = record.get("page_id") or (values[0].get("page_id") if values else None)
        review_only = bool(record.get("table_bbox_review_only")) or str(record.get("status") or "") == "TABLE_ROUTE_VALUE_NORMALIZATION_SKIPPED"
        field_counts = Counter(str(v.get("field_name") or "") for v in values)
        evidence_kind_counts = Counter(str(v.get("evidence_kind") or "") for v in values)
        context_count = sum(1 for v in values if is_context_field(v.get("field_name"), v.get("evidence_kind")))
        non_context_count = max(len(values) - context_count, 0)
        context_ratio = round(context_count / len(values), 6) if values else 0.0
        review_value_count = 0
        promoted_count = 0
        duplicate_key_count = 0
        seen_value_keys: set[tuple[str, str]] = set()
        table_review_flags: list[str] = []

        if review_only:
            status = STATUS_SKIPPED
            requirement_flags = ["source_record_review_only_or_skipped"]
        else:
            status, requirement_flags = _table_requirement(template, field_counts, context_ratio, max_context_ratio)
            for value in values:
                ok, flags = is_promotable_value(value, min_promote_confidence)
                key = (str(value.get("field_name") or ""), normalize_text(value.get("normalized_value")))
                if key in seen_value_keys and key[0] in PART_NUMBER_FIELDS:
                    duplicate_key_count += 1
                    ok = False
                    flags = list(flags) + ["duplicate_promotable_value_in_table"]
                seen_value_keys.add(key)
                if ok:
                    promoted_values.append(build_promoted_record(value, flags))
                    promoted_count += 1
                elif not is_context_field(value.get("field_name"), value.get("evidence_kind")):
                    review_value_count += 1

        table_review_flags.extend(requirement_flags)
        if duplicate_key_count:
            table_review_flags.append("duplicate_promotable_values_seen")
        if review_value_count:
            table_review_flags.append("some_values_require_review")
        if context_ratio > max_context_ratio and not review_only:
            table_review_flags.append("context_ratio_above_threshold")

        audit_records.append({
            "audit_record_id": stable_id("table_route_value_audit", table_id, page_id, template),
            "schema_version": SCHEMA_VERSION,
            "page_id": page_id,
            "table_id": table_id,
            "table_template_type": template,
            "source_normalizer_record_id": record.get("normalizer_record_id"),
            "source_value_count": len(values),
            "field_counts": dict(field_counts),
            "evidence_kind_counts": dict(evidence_kind_counts),
            "context_value_count": context_count,
            "non_context_value_count": non_context_count,
            "context_value_ratio": context_ratio,
            "promoted_value_count": promoted_count,
            "review_value_count": review_value_count,
            "duplicate_promotable_value_count": duplicate_key_count,
            "audit_status": status,
            "audit_review_required": bool(table_review_flags) and not review_only,
            "review_flags": table_review_flags,
            "retrieval_only": True,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempted": False,
            "qdrant_write_attempted": False,
            "opensearch_write_attempted": False,
            "unsafe_table_route_value_audit": False,
        })

    summary_extra = {
        "context_only_record_count": sum(1 for v in source_values if is_context_field(v.get("field_name"), v.get("evidence_kind"))),
        "non_context_normalized_record_count": sum(1 for v in source_values if not is_context_field(v.get("field_name"), v.get("evidence_kind"))),
        "review_value_record_count": sum(r.get("review_value_count", 0) for r in audit_records),
    }
    return audit_records, promoted_values, summary_extra


def summarize(normalizer_report: Mapping[str, Any], audit_records: Sequence[Mapping[str, Any]], promoted_values: Sequence[Mapping[str, Any]], summary_extra: Mapping[str, Any]) -> dict[str, Any]:
    source_summary = normalizer_report.get("summary") or {}
    field_counts = Counter(v.get("field_name") for v in promoted_values)
    template_counts = Counter(r.get("table_template_type") for r in audit_records)
    status_counts = Counter(r.get("audit_status") for r in audit_records)
    review_required_count = sum(1 for r in audit_records if r.get("audit_review_required"))
    unknown_review_count = sum(1 for r in audit_records if "unknown_or_generic_template_review" in (r.get("review_flags") or []))
    high_context_count = sum(1 for r in audit_records if "high_context_ratio" in (r.get("review_flags") or []) or "context_ratio_above_threshold" in (r.get("review_flags") or []))
    duplicate_tables = sum(1 for r in audit_records if r.get("duplicate_promotable_value_count", 0) > 0)

    summary = {
        "source_table_route_value_normalizer_quality_status": normalizer_report.get("quality_status"),
        "source_table_route_value_normalizer_status": normalizer_report.get("status"),
        "source_table_route_value_normalizer_record_count": source_summary.get("table_route_value_normalizer_record_count", len(normalizer_report.get("table_route_value_normalizer_records") or [])),
        "source_normalized_table_value_record_count": source_summary.get("normalized_table_value_record_count", len(normalizer_report.get("table_route_normalized_value_records") or [])),
        "source_normalized_table_count": source_summary.get("normalized_table_count"),
        "source_review_only_source_skipped_count": source_summary.get("review_only_source_skipped_count", 0),
        "source_covered_part_number_record_count": source_summary.get("covered_part_number_record_count", 0),
        "source_manual_page_reference_record_count": source_summary.get("manual_page_reference_record_count", 0),
        "source_ipl_part_number_record_count": source_summary.get("ipl_part_number_record_count", 0),
        "table_route_value_audit_record_count": len(audit_records),
        "audited_table_count": len([r for r in audit_records if r.get("audit_status") != STATUS_SKIPPED]),
        "review_only_audit_skipped_count": status_counts.get(STATUS_SKIPPED, 0),
        "evidence_ready_table_count": status_counts.get("evidence_ready", 0),
        "review_required_table_count": review_required_count,
        "unknown_template_review_count": unknown_review_count,
        "high_context_ratio_table_count": high_context_count,
        "duplicate_promotable_table_count": duplicate_tables,
        "promoted_table_value_evidence_record_count": len(promoted_values),
        "search_ready_evidence_record_count": len(promoted_values),
        "context_only_record_count": summary_extra.get("context_only_record_count", 0),
        "non_context_normalized_record_count": summary_extra.get("non_context_normalized_record_count", 0),
        "review_value_record_count": summary_extra.get("review_value_record_count", 0),
        "covered_part_number_promoted_count": field_counts.get("covered_part_number", 0),
        "manual_page_reference_promoted_count": field_counts.get("manual_page_reference", 0),
        "page_rev_or_sequence_value_promoted_count": field_counts.get("page_rev_or_sequence_value", 0),
        "ipl_part_number_promoted_count": field_counts.get("ipl_part_number", 0),
        "ipl_figure_item_or_quantity_promoted_count": field_counts.get("ipl_figure_item_or_quantity", 0),
        "ipl_text_promoted_count": field_counts.get("ipl_text", 0),
        "part_number_coverage_table_count": template_counts.get("part_number_coverage_list", 0),
        "list_effective_pages_table_count": template_counts.get("list_of_effective_pages", 0),
        "ipl_split_column_table_count": template_counts.get("ipl_split_column_table", 0),
        "unknown_table_template_count": template_counts.get("unknown_table_template", 0),
        "unsafe_table_route_value_audit_record_count": 0,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }
    return summary


def evaluate_quality(summary: Mapping[str, Any], thresholds: Mapping[str, Any]) -> tuple[str, list[str]]:
    failures: list[str] = []
    if thresholds.get("require_table_route_value_normalizer_quality_pass") and summary.get("source_table_route_value_normalizer_quality_status") != "PASS":
        failures.append("source_table_route_value_normalizer_quality_not_pass")
    checks = [
        ("source_table_route_value_normalizer_record_count", "min_source_normalizer_records"),
        ("source_normalized_table_value_record_count", "min_source_normalized_records"),
        ("table_route_value_audit_record_count", "min_audit_records"),
        ("audited_table_count", "min_audited_tables"),
        ("promoted_table_value_evidence_record_count", "min_promoted_evidence_records"),
        ("search_ready_evidence_record_count", "min_search_ready_evidence_records"),
        ("covered_part_number_promoted_count", "min_covered_part_number_promoted"),
        ("manual_page_reference_promoted_count", "min_manual_page_reference_promoted"),
        ("ipl_part_number_promoted_count", "min_ipl_part_number_promoted"),
    ]
    for summary_key, threshold_key in checks:
        if summary.get(summary_key, 0) < thresholds.get(threshold_key, 0):
            failures.append(f"{summary_key}_below_min")
    if summary.get("unsafe_table_route_value_audit_record_count", 0) > thresholds.get("max_unsafe_records", 0):
        failures.append("unsafe_records_above_limit")
    if summary.get("answer_permission_count", 0) > thresholds.get("max_answer_permission_count", 0):
        failures.append("answer_permission_above_limit")
    if summary.get("source_truth_mutation_allowed_count", 0) > thresholds.get("max_source_truth_mutation_allowed", 0):
        failures.append("source_truth_mutation_allowed_above_limit")
    if summary.get("postgres_write_attempt_count", 0) or summary.get("qdrant_write_attempt_count", 0) or summary.get("opensearch_write_attempt_count", 0):
        failures.append("write_attempt_detected")
    if thresholds.get("require_no_answer_permission") and summary.get("answer_permission_count", 0) != 0:
        failures.append("answer_permission_nonzero")
    return ("FAIL" if failures else "PASS"), failures


def thresholds_from_args(args: argparse.Namespace) -> dict[str, Any]:
    keys = [
        "min_source_normalizer_records",
        "min_source_normalized_records",
        "min_audit_records",
        "min_audited_tables",
        "min_promoted_evidence_records",
        "min_search_ready_evidence_records",
        "min_covered_part_number_promoted",
        "min_manual_page_reference_promoted",
        "min_ipl_part_number_promoted",
        "max_unsafe_records",
        "max_answer_permission_count",
        "max_source_truth_mutation_allowed",
        "require_table_route_value_normalizer_quality_pass",
        "require_no_answer_permission",
    ]
    return {key: getattr(args, key) for key in keys if hasattr(args, key)}


def build_report(source_report: Mapping[str, Any], output_dir: Path, thresholds: Mapping[str, Any] | None = None, *, min_promote_confidence: float = 0.60, max_context_ratio: float = 0.75) -> dict[str, Any]:
    thresholds = dict(thresholds or {})
    audit_records, promoted_values, summary_extra = build_audit_records(source_report, min_promote_confidence=min_promote_confidence, max_context_ratio=max_context_ratio)
    summary = summarize(source_report, audit_records, promoted_values, summary_extra)
    quality_status, failures = evaluate_quality(summary, thresholds)
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "generated_at": utc_now(),
        "source_schema_version": source_report.get("schema_version"),
        "source_report_status": source_report.get("status"),
        "summary": summary,
        "quality_fail_reasons": failures,
        "thresholds": thresholds,
        "table_route_value_audit_records": audit_records,
        "table_route_search_ready_value_records": promoted_values,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "trace_net_table_route_value_audit_v1.json", report)
    write_json(output_dir / "trace_net_table_route_value_audit_v1_summary.json", summary)
    write_jsonl(output_dir / "trace_net_table_route_value_audit_v1_records.jsonl", audit_records)
    write_jsonl(output_dir / "trace_net_table_route_search_ready_values_v1.jsonl", promoted_values)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "generated_at": report["generated_at"],
        "artifacts": {
            "report": "trace_net_table_route_value_audit_v1.json",
            "summary": "trace_net_table_route_value_audit_v1_summary.json",
            "audit_records": "trace_net_table_route_value_audit_v1_records.jsonl",
            "search_ready_values": "trace_net_table_route_search_ready_values_v1.jsonl",
        },
        "safety_contract": {
            "postgres_writes": False,
            "qdrant_writes": False,
            "opensearch_writes": False,
            "source_truth_mutation": False,
            "answer_permission": False,
        },
    }
    write_json(output_dir / "trace_net_table_route_value_audit_v1_manifest.json", manifest)
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net table route value audit v1.")
    parser.add_argument("--table-route-value-normalizer", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--min-promote-confidence", type=float, default=0.60)
    parser.add_argument("--max-context-ratio", type=float, default=0.75)
    parser.add_argument("--min-source-normalizer-records", type=int, default=1)
    parser.add_argument("--min-source-normalized-records", type=int, default=1)
    parser.add_argument("--min-audit-records", type=int, default=1)
    parser.add_argument("--min-audited-tables", type=int, default=1)
    parser.add_argument("--min-promoted-evidence-records", type=int, default=1)
    parser.add_argument("--min-search-ready-evidence-records", type=int, default=1)
    parser.add_argument("--min-covered-part-number-promoted", type=int, default=0)
    parser.add_argument("--min-manual-page-reference-promoted", type=int, default=0)
    parser.add_argument("--min-ipl-part-number-promoted", type=int, default=0)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-route-value-normalizer-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    source_report = read_json(args.table_route_value_normalizer)
    report = build_report(
        source_report,
        args.output_dir,
        thresholds_from_args(args),
        min_promote_confidence=args.min_promote_confidence,
        max_context_ratio=args.max_context_ratio,
    )
    print("TRACE-Net Table Route Value Audit v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in (
        "source_table_route_value_normalizer_record_count",
        "source_normalized_table_value_record_count",
        "table_route_value_audit_record_count",
        "audited_table_count",
        "evidence_ready_table_count",
        "review_required_table_count",
        "unknown_template_review_count",
        "high_context_ratio_table_count",
        "promoted_table_value_evidence_record_count",
        "search_ready_evidence_record_count",
        "context_only_record_count",
        "covered_part_number_promoted_count",
        "manual_page_reference_promoted_count",
        "page_rev_or_sequence_value_promoted_count",
        "ipl_part_number_promoted_count",
        "ipl_figure_item_or_quantity_promoted_count",
        "ipl_text_promoted_count",
        "unsafe_table_route_value_audit_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {report['summary'].get(key)}")
    print(f" report_path: {args.output_dir / 'trace_net_table_route_value_audit_v1.json'}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
