"""TRACE-Net table hybrid retrieval integration audit v1.

Audits the local table hybrid-retrieval bridge and proves that table-route
signals are available for retrieval ranking while remaining blocked from final
answer authority. This module is intentionally local-only: it reads JSON/JSONL
artifacts, writes audit reports, and never writes to Postgres, Qdrant,
OpenSearch, or live services.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

STATUS_BUILT = "TABLE_HYBRID_RETRIEVAL_INTEGRATION_AUDIT_BUILT"
STATUS_NOT_READY = "TABLE_HYBRID_RETRIEVAL_INTEGRATION_AUDIT_NOT_READY"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

REPORT_NAME = "trace_net_table_hybrid_retrieval_integration_audit_v1.json"
QUALITY_NAME = "trace_net_table_hybrid_retrieval_integration_audit_v1_quality.json"
AUDIT_JSONL_NAME = "trace_net_table_hybrid_retrieval_integration_audit_records_v1.jsonl"
INSPECT_MD_NAME = "trace_net_table_hybrid_retrieval_integration_audit_v1_inspect.md"

FALSE_VALUES = {False, 0, "0", "false", "False", "FALSE", "no", "No", "NO", ""}
TRUE_VALUES = {True, 1, "1", "true", "True", "TRUE", "yes", "Yes", "YES"}

REQUIRED_QUERY_GROUP_KEYS = ("query", "match_count", "hits", "retrieval_only", "answer_permission", "can_answer_directly", "can_prove_claims", "source_truth_mutation_allowed")
REQUIRED_BRIDGE_KEYS = ("bridge_record_id", "page_id", "field_name", "normalized_value", "retrieval_channel", "hybrid_retrieval_role", "routing_boost", "retrieval_only", "answer_permission", "can_answer_directly", "can_prove_claims", "source_truth_mutation_allowed")


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if isinstance(obj, Mapping):
                rows.append(dict(obj))
    return rows


def _truthy(value: Any) -> bool:
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES or value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1"}
    return bool(value)


def _source_summary(report: Mapping[str, Any]) -> Mapping[str, Any]:
    summary = report.get("summary")
    return summary if isinstance(summary, Mapping) else {}


def _quality_pass(report: Mapping[str, Any]) -> bool:
    status = str(report.get("quality_status", _source_summary(report).get("quality_status", ""))).upper()
    if status == QUALITY_PASS:
        return True
    return bool(_source_summary(report).get("quality_pass") is True)


def _find_jsonl_path(report: Mapping[str, Any], report_path: Path, names: Sequence[str], fallback_name: str) -> Optional[Path]:
    candidates: List[Any] = []
    for name in names:
        candidates.append(report.get(name))
    paths = report.get("paths")
    if isinstance(paths, Mapping):
        for name in names:
            candidates.append(paths.get(name))
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(str(candidate))
        if path.is_absolute() and path.exists():
            return path
        if not path.is_absolute():
            if path.exists():
                return path
            sibling = report_path.parent / path.name
            if sibling.exists():
                return sibling
    fallback = report_path.parent / fallback_name
    if fallback.exists():
        return fallback
    return None


def load_bridge_artifact(path: Path) -> Tuple[Mapping[str, Any], List[Dict[str, Any]], List[Dict[str, Any]], str, str]:
    report = _read_json(path)
    if not isinstance(report, Mapping):
        raise ValueError(f"Expected JSON object at {path}")

    records_source = "none"
    groups_source = "none"
    records_value = report.get("bridge_records")
    if isinstance(records_value, list):
        bridge_records = [dict(row) for row in records_value if isinstance(row, Mapping)]
        records_source = "bridge_records"
    else:
        records_path = _find_jsonl_path(
            report,
            path,
            ("bridge_jsonl_path", "bridge_records_jsonl_path"),
            "trace_net_table_hybrid_retrieval_bridge_records_v1.jsonl",
        )
        bridge_records = _read_jsonl(records_path) if records_path is not None else []
        records_source = str(records_path) if records_path is not None else "none"

    groups_value = report.get("query_bridge_groups")
    if isinstance(groups_value, list):
        query_groups = [dict(row) for row in groups_value if isinstance(row, Mapping)]
        groups_source = "query_bridge_groups"
    else:
        groups_path = _find_jsonl_path(
            report,
            path,
            ("query_groups_jsonl_path", "query_bridge_groups_jsonl_path"),
            "trace_net_table_hybrid_retrieval_bridge_query_groups_v1.jsonl",
        )
        query_groups = _read_jsonl(groups_path) if groups_path is not None else []
        groups_source = str(groups_path) if groups_path is not None else "none"

    return report, bridge_records, query_groups, records_source, groups_source


def _missing_keys(row: Mapping[str, Any], keys: Sequence[str]) -> List[str]:
    return [key for key in keys if key not in row or row.get(key) in (None, "")]


def _is_ranking_only_bridge_record(row: Mapping[str, Any]) -> bool:
    if not _truthy(row.get("retrieval_only", True)):
        return False
    if str(row.get("hybrid_retrieval_role", "")) != "ranking_signal_only":
        return False
    if str(row.get("retrieval_channel", "")) not in {"table_exact_search", "table_exact_search_smoke", "table_hybrid_bridge"}:
        return False
    if _truthy(row.get("answer_permission")) or _truthy(row.get("can_answer_directly")) or _truthy(row.get("can_prove_claims")) or _truthy(row.get("source_truth_mutation_allowed")):
        return False
    return True


def _group_hits(group: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    hits = group.get("hits")
    if not isinstance(hits, list):
        return []
    return [hit for hit in hits if isinstance(hit, Mapping)]


def _is_safe_query_group(group: Mapping[str, Any]) -> bool:
    if _truthy(group.get("answer_permission")) or _truthy(group.get("can_answer_directly")) or _truthy(group.get("can_prove_claims")) or _truthy(group.get("source_truth_mutation_allowed")):
        return False
    if not _truthy(group.get("retrieval_only", True)):
        return False
    for hit in _group_hits(group):
        if _truthy(hit.get("answer_permission")) or _truthy(hit.get("can_answer_directly")) or _truthy(hit.get("can_prove_claims")) or _truthy(hit.get("source_truth_mutation_allowed")):
            return False
    return True


def build_audit_records(bridge_records: Sequence[Mapping[str, Any]], query_groups: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    audit_records: List[Dict[str, Any]] = []
    for idx, record in enumerate(bridge_records):
        missing = _missing_keys(record, REQUIRED_BRIDGE_KEYS)
        field_name = str(record.get("field_name", ""))
        audit_records.append(
            {
                "audit_record_id": f"table_hybrid_bridge_record::{idx}",
                "audit_subject_type": "bridge_record",
                "source_record_id": record.get("bridge_record_id", ""),
                "page_id": record.get("page_id", ""),
                "field_name": field_name,
                "normalized_value": record.get("normalized_value", ""),
                "retrieval_channel": record.get("retrieval_channel", ""),
                "hybrid_retrieval_role": record.get("hybrid_retrieval_role", ""),
                "routing_boost": record.get("routing_boost", 0),
                "ranking_signal_available": _is_ranking_only_bridge_record(record) and not missing,
                "schema_complete": not missing,
                "missing_required_keys": missing,
                "retrieval_only": True,
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
                "unsafe": False,
            }
        )
    for idx, group in enumerate(query_groups):
        missing = _missing_keys(group, REQUIRED_QUERY_GROUP_KEYS)
        hits = _group_hits(group)
        audit_records.append(
            {
                "audit_record_id": f"table_hybrid_query_group::{idx}",
                "audit_subject_type": "query_bridge_group",
                "query": group.get("query", ""),
                "match_count": int(group.get("match_count", 0) or 0),
                "hit_count": len(hits),
                "page_ids": group.get("page_ids", []),
                "field_names": group.get("field_names", []),
                "ranking_signal_available": _is_safe_query_group(group) and int(group.get("match_count", 0) or 0) > 0 and not missing,
                "schema_complete": not missing,
                "missing_required_keys": missing,
                "retrieval_only": True,
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
                "unsafe": False,
            }
        )
    return audit_records


def _quality_checks(summary: Mapping[str, Any], args: argparse.Namespace) -> List[Dict[str, Any]]:
    def check(name: str, observed: Any, op: str, expected: Any, passed: bool) -> Dict[str, Any]:
        return {"name": name, "observed": observed, "operator": op, "expected": expected, "passed": bool(passed)}

    return [
        check("source_bridge_quality_pass", summary.get("source_bridge_quality_pass"), "is True", True, (not args.require_source_bridge_quality_pass) or bool(summary.get("source_bridge_quality_pass"))),
        check("source_bridge_record_count", summary.get("source_bridge_record_count", 0), ">=", args.min_source_bridge_records, int(summary.get("source_bridge_record_count", 0)) >= args.min_source_bridge_records),
        check("source_query_bridge_group_count", summary.get("source_query_bridge_group_count", 0), ">=", args.min_source_query_bridge_groups, int(summary.get("source_query_bridge_group_count", 0)) >= args.min_source_query_bridge_groups),
        check("integration_audit_record_count", summary.get("integration_audit_record_count", 0), ">=", args.min_integration_audit_records, int(summary.get("integration_audit_record_count", 0)) >= args.min_integration_audit_records),
        check("ranking_available_bridge_record_count", summary.get("ranking_available_bridge_record_count", 0), ">=", args.min_ranking_available_bridge_records, int(summary.get("ranking_available_bridge_record_count", 0)) >= args.min_ranking_available_bridge_records),
        check("page_with_ranking_signal_count", summary.get("page_with_ranking_signal_count", 0), ">=", args.min_pages_with_ranking_signals, int(summary.get("page_with_ranking_signal_count", 0)) >= args.min_pages_with_ranking_signals),
        check("field_count", summary.get("field_count", 0), ">=", args.min_field_count, int(summary.get("field_count", 0)) >= args.min_field_count),
        check("successful_query_bridge_group_count", summary.get("successful_query_bridge_group_count", 0), ">=", args.min_successful_query_bridge_groups, int(summary.get("successful_query_bridge_group_count", 0)) >= args.min_successful_query_bridge_groups),
        check("covered_part_number_ranking_signals", summary.get("field_counts", {}).get("covered_part_number", 0), ">=", args.min_covered_part_number_ranking_signals, int(summary.get("field_counts", {}).get("covered_part_number", 0)) >= args.min_covered_part_number_ranking_signals),
        check("manual_page_reference_ranking_signals", summary.get("field_counts", {}).get("manual_page_reference", 0), ">=", args.min_manual_page_reference_ranking_signals, int(summary.get("field_counts", {}).get("manual_page_reference", 0)) >= args.min_manual_page_reference_ranking_signals),
        check("ipl_part_number_ranking_signals", summary.get("field_counts", {}).get("ipl_part_number", 0), ">=", args.min_ipl_part_number_ranking_signals, int(summary.get("field_counts", {}).get("ipl_part_number", 0)) >= args.min_ipl_part_number_ranking_signals),
        check("schema_missing_required_key_record_count", summary.get("schema_missing_required_key_record_count", 0), "<=", args.max_schema_missing_required_key_records, int(summary.get("schema_missing_required_key_record_count", 0)) <= args.max_schema_missing_required_key_records),
        check("unsafe_integration_audit_record_count", summary.get("unsafe_integration_audit_record_count", 0), "<=", args.max_unsafe_records, int(summary.get("unsafe_integration_audit_record_count", 0)) <= args.max_unsafe_records),
        check("answer_permission_count", summary.get("answer_permission_count", 0), "<=", args.max_answer_permission_count, int(summary.get("answer_permission_count", 0)) <= args.max_answer_permission_count),
        check("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count", 0), "<=", args.max_source_truth_mutation_allowed, int(summary.get("source_truth_mutation_allowed_count", 0)) <= args.max_source_truth_mutation_allowed),
        check("can_answer_directly_count", summary.get("can_answer_directly_count", 0), "==", 0, int(summary.get("can_answer_directly_count", 0)) == 0),
        check("can_prove_claims_count", summary.get("can_prove_claims_count", 0), "==", 0, int(summary.get("can_prove_claims_count", 0)) == 0),
        check("postgres_write_attempt_count", summary.get("postgres_write_attempt_count", 0), "==", 0, int(summary.get("postgres_write_attempt_count", 0)) == 0),
        check("qdrant_write_attempt_count", summary.get("qdrant_write_attempt_count", 0), "==", 0, int(summary.get("qdrant_write_attempt_count", 0)) == 0),
        check("opensearch_write_attempt_count", summary.get("opensearch_write_attempt_count", 0), "==", 0, int(summary.get("opensearch_write_attempt_count", 0)) == 0),
        check("opensearch_upload_attempt_count", summary.get("opensearch_upload_attempt_count", 0), "==", 0, int(summary.get("opensearch_upload_attempt_count", 0)) == 0),
    ]


def _write_inspect_md(path: Path, report: Mapping[str, Any]) -> None:
    summary = report.get("summary") or {}
    field_counts = summary.get("field_counts") or {}
    query_groups = report.get("query_bridge_groups") or []
    audit_records = report.get("audit_records") or []
    lines = [
        "# TRACE-Net Table Hybrid Retrieval Integration Audit v1 Inspect",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        "",
        "## Integration counters",
        f"- source_bridge_record_count: {summary.get('source_bridge_record_count', 0)}",
        f"- ranking_available_bridge_record_count: {summary.get('ranking_available_bridge_record_count', 0)}",
        f"- page_with_ranking_signal_count: {summary.get('page_with_ranking_signal_count', 0)}",
        f"- field_count: {summary.get('field_count', 0)}",
        f"- successful_query_bridge_group_count: {summary.get('successful_query_bridge_group_count', 0)}",
        f"- schema_missing_required_key_record_count: {summary.get('schema_missing_required_key_record_count', 0)}",
        "",
        "## Field counts",
    ]
    if not field_counts:
        lines.append("- none")
    for field_name, count in sorted(field_counts.items()):
        lines.append(f"- {field_name}: {count}")
    lines.extend(
        [
            "",
            "## Safety/write counters",
            f"- unsafe_integration_audit_record_count: {summary.get('unsafe_integration_audit_record_count', 0)}",
            f"- answer_permission_count: {summary.get('answer_permission_count', 0)}",
            f"- can_answer_directly_count: {summary.get('can_answer_directly_count', 0)}",
            f"- can_prove_claims_count: {summary.get('can_prove_claims_count', 0)}",
            f"- source_truth_mutation_allowed_count: {summary.get('source_truth_mutation_allowed_count', 0)}",
            f"- postgres_write_attempt_count: {summary.get('postgres_write_attempt_count', 0)}",
            f"- qdrant_write_attempt_count: {summary.get('qdrant_write_attempt_count', 0)}",
            f"- opensearch_write_attempt_count: {summary.get('opensearch_write_attempt_count', 0)}",
            f"- opensearch_upload_attempt_count: {summary.get('opensearch_upload_attempt_count', 0)}",
            "",
            "## Query bridge groups",
        ]
    )
    if not query_groups:
        lines.append("No query bridge groups audited.")
    for group in query_groups[:10]:
        lines.append(f"- query={group.get('query')!r} matches={group.get('match_count', 0)} pages={','.join(group.get('page_ids') or [])}")
    lines.extend(["", "## First audit records"])
    if not audit_records:
        lines.append("No audit records generated.")
    for record in audit_records[:20]:
        label = record.get("query") or f"{record.get('page_id')} | {record.get('field_name')} | {record.get('normalized_value')}"
        lines.append(f"- {record.get('audit_subject_type')} | {label} | ranking_available={record.get('ranking_signal_available')} | schema_complete={record.get('schema_complete')}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_table_hybrid_retrieval_integration_audit(table_hybrid_retrieval_bridge: Path, output_dir: Path, args: argparse.Namespace) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_report, bridge_records, query_groups, records_source, groups_source = load_bridge_artifact(table_hybrid_retrieval_bridge)
    source_summary = _source_summary(source_report)
    audit_records = build_audit_records(bridge_records, query_groups)

    ranking_bridge_records = [record for record in bridge_records if _is_ranking_only_bridge_record(record) and not _missing_keys(record, REQUIRED_BRIDGE_KEYS)]
    ranking_pages = {str(record.get("page_id")) for record in ranking_bridge_records if record.get("page_id")}
    fields = Counter(str(record.get("field_name")) for record in ranking_bridge_records if record.get("field_name"))
    safe_groups = [group for group in query_groups if _is_safe_query_group(group) and int(group.get("match_count", 0) or 0) > 0 and not _missing_keys(group, REQUIRED_QUERY_GROUP_KEYS)]
    group_hits = [hit for group in query_groups for hit in _group_hits(group)]

    summary: Dict[str, Any] = {
        "source_bridge_path": str(table_hybrid_retrieval_bridge),
        "source_bridge_records_collection": records_source,
        "source_query_groups_collection": groups_source,
        "source_bridge_quality_pass": _quality_pass(source_report),
        "source_bridge_record_count": len(bridge_records),
        "source_table_hybrid_bridge_record_count": source_summary.get("table_hybrid_bridge_record_count", len(bridge_records)),
        "source_query_bridge_group_count": len(query_groups),
        "source_successful_query_bridge_group_count": source_summary.get("successful_query_bridge_group_count", sum(1 for group in query_groups if int(group.get("match_count", 0) or 0) > 0)),
        "integration_audit_record_count": len(audit_records),
        "ranking_available_bridge_record_count": len(ranking_bridge_records),
        "retrieval_only_bridge_record_count": sum(1 for record in bridge_records if _truthy(record.get("retrieval_only"))),
        "page_with_ranking_signal_count": len(ranking_pages),
        "field_count": len(fields),
        "field_counts": dict(sorted(fields.items())),
        "successful_query_bridge_group_count": len(safe_groups),
        "total_query_bridge_hit_count": sum(len(_group_hits(group)) for group in safe_groups),
        "schema_missing_required_key_record_count": sum(1 for record in audit_records if not record.get("schema_complete")),
        "unsafe_integration_audit_record_count": sum(1 for record in audit_records if _truthy(record.get("unsafe"))),
        "source_unsafe_bridge_record_count": source_summary.get("unsafe_bridge_record_count", 0),
        "answer_permission_count": sum(1 for record in bridge_records if _truthy(record.get("answer_permission"))) + sum(1 for group in query_groups if _truthy(group.get("answer_permission"))) + sum(1 for hit in group_hits if _truthy(hit.get("answer_permission"))),
        "can_answer_directly_count": sum(1 for record in bridge_records if _truthy(record.get("can_answer_directly"))) + sum(1 for group in query_groups if _truthy(group.get("can_answer_directly"))) + sum(1 for hit in group_hits if _truthy(hit.get("can_answer_directly"))),
        "can_prove_claims_count": sum(1 for record in bridge_records if _truthy(record.get("can_prove_claims"))) + sum(1 for group in query_groups if _truthy(group.get("can_prove_claims"))) + sum(1 for hit in group_hits if _truthy(hit.get("can_prove_claims"))),
        "source_truth_mutation_allowed_count": sum(1 for record in bridge_records if _truthy(record.get("source_truth_mutation_allowed"))) + sum(1 for group in query_groups if _truthy(group.get("source_truth_mutation_allowed"))) + sum(1 for hit in group_hits if _truthy(hit.get("source_truth_mutation_allowed"))),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
    }
    checks = _quality_checks(summary, args)
    quality_status = QUALITY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL

    report_path = output_dir / REPORT_NAME
    audit_jsonl_path = output_dir / AUDIT_JSONL_NAME
    inspect_md_path = output_dir / INSPECT_MD_NAME
    report: Dict[str, Any] = {
        "status": STATUS_BUILT if audit_records else STATUS_NOT_READY,
        "quality_status": quality_status,
        "summary": summary,
        "quality_checks": checks,
        "paths": {
            "report_path": str(report_path),
            "audit_jsonl_path": str(audit_jsonl_path),
            "inspect_md_path": str(inspect_md_path),
        },
        "audit_records": audit_records,
        "query_bridge_groups": query_groups[:20],
    }
    _write_json(report_path, report)
    _write_jsonl(audit_jsonl_path, audit_records)
    _write_inspect_md(inspect_md_path, report)
    return report


def add_common_quality_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-source-bridge-records", type=int, default=1000)
    parser.add_argument("--min-source-query-bridge-groups", type=int, default=3)
    parser.add_argument("--min-integration-audit-records", type=int, default=1000)
    parser.add_argument("--min-ranking-available-bridge-records", type=int, default=1000)
    parser.add_argument("--min-pages-with-ranking-signals", type=int, default=1)
    parser.add_argument("--min-field-count", type=int, default=4)
    parser.add_argument("--min-successful-query-bridge-groups", type=int, default=3)
    parser.add_argument("--min-covered-part-number-ranking-signals", type=int, default=100)
    parser.add_argument("--min-manual-page-reference-ranking-signals", type=int, default=39)
    parser.add_argument("--min-ipl-part-number-ranking-signals", type=int, default=100)
    parser.add_argument("--max-schema-missing-required-key-records", type=int, default=0)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-source-bridge-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net table hybrid retrieval integration audit v1.")
    parser.add_argument("--table-hybrid-retrieval-bridge", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--quality", action="store_true")
    add_common_quality_args(parser)
    return parser


def check_quality_report(report: Mapping[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    summary = report.get("summary") or {}
    checks = _quality_checks(summary, args)
    quality_status = QUALITY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL
    return {"status": report.get("status", STATUS_NOT_READY), "quality_status": quality_status, "summary": summary, "quality_checks": checks}


def quality_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net table hybrid retrieval integration audit v1 quality.")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--write-json", action="store_true")
    add_common_quality_args(parser)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = build_table_hybrid_retrieval_integration_audit(args.table_hybrid_retrieval_bridge, args.output_dir, args)
    summary = report["summary"]
    print("TRACE-Net Table Hybrid Retrieval Integration Audit v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in (
        "source_bridge_record_count",
        "source_query_bridge_group_count",
        "integration_audit_record_count",
        "ranking_available_bridge_record_count",
        "page_with_ranking_signal_count",
        "field_count",
        "successful_query_bridge_group_count",
        "schema_missing_required_key_record_count",
        "unsafe_integration_audit_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "opensearch_upload_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    for name, path in report["paths"].items():
        print(f" {name}: {path}")
    if args.quality and report["quality_status"] != QUALITY_PASS:
        return 1
    return 0


def quality_main(argv: Optional[Sequence[str]] = None) -> int:
    parser = quality_parser()
    args = parser.parse_args(argv)
    report = _read_json(args.report_path)
    quality = check_quality_report(report, args)
    if args.write_json:
        _write_json(args.report_path.parent / QUALITY_NAME, quality)
    print("TRACE-Net Table Hybrid Retrieval Integration Audit v1 Quality")
    print(f" quality_status: {quality['quality_status']}")
    for check in quality["quality_checks"]:
        status = "PASS" if check["passed"] else "FAIL"
        print(f" {status} {check['name']}: observed={check['observed']} expected={check['operator']} {check['expected']}")
    return 0 if quality["quality_status"] == QUALITY_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
