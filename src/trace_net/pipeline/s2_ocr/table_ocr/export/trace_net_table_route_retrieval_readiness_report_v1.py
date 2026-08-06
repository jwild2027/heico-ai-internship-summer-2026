"""TRACE-Net table-route retrieval readiness report v1.

This module is deliberately local-only. It reads the already-built table route
retrieval artifacts and emits a final readiness report proving that table values
are available for retrieval/ranking while remaining blocked from final-answer
authority.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence

REPORT_FILENAME = "trace_net_table_route_retrieval_readiness_report_v1.json"
INSPECT_MD_FILENAME = "trace_net_table_route_retrieval_readiness_report_v1_inspect.md"
CHECK_FILENAME = "trace_net_table_route_retrieval_readiness_report_v1_quality.json"


def _read_json(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {p}")
    return data


def _write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _summary(data: Mapping[str, Any]) -> Mapping[str, Any]:
    summary = data.get("summary")
    if isinstance(summary, Mapping):
        return summary
    return data


def _int(data: Mapping[str, Any], *keys: str) -> int:
    for key in keys:
        value = data.get(key)
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(float(value))
            except ValueError:
                continue
    return 0


def _bool_quality_pass(data: Mapping[str, Any]) -> bool:
    value = data.get("quality_status")
    if isinstance(value, str):
        return value.upper() == "PASS"
    return bool(data.get("quality_pass") or data.get("quality_status_pass"))


def _field_counts(data: Mapping[str, Any]) -> Dict[str, int]:
    summary = _summary(data)
    value = summary.get("field_counts")
    if isinstance(value, Mapping):
        return {str(k): _int({"v": v}, "v") for k, v in value.items()}
    return {}


def _aggregate_safety_counters(summaries: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    keys = [
        "unsafe_record_count",
        "unsafe_exact_search_document_count",
        "unsafe_smoke_result_count",
        "unsafe_bridge_record_count",
        "unsafe_integration_audit_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "opensearch_upload_attempt_count",
    ]
    out: Dict[str, int] = {}
    for key in keys:
        out[key] = sum(_int(summary, key) for summary in summaries)
    # User-facing aliases used by the quality gate.
    out["unsafe_total_count"] = (
        out["unsafe_record_count"]
        + out["unsafe_exact_search_document_count"]
        + out["unsafe_smoke_result_count"]
        + out["unsafe_bridge_record_count"]
        + out["unsafe_integration_audit_record_count"]
    )
    return out


@dataclass(frozen=True)
class ReadinessThresholds:
    min_exact_search_documents: int = 1000
    min_successful_smoke_queries: int = 3
    min_total_smoke_matches: int = 3
    min_bridge_records: int = 1000
    min_ranking_available_bridge_records: int = 1000
    min_pages_with_ranking_signals: int = 1
    min_field_count: int = 4
    max_unsafe_records: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_source_exact_search_adapter_quality_pass: bool = True
    require_source_exact_search_smoke_quality_pass: bool = True
    require_source_bridge_quality_pass: bool = True
    require_source_integration_audit_quality_pass: bool = True
    require_no_answer_permission: bool = True


def evaluate_quality(summary: Mapping[str, Any], thresholds: ReadinessThresholds) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []

    def add(name: str, observed: Any, expected: str, passed: bool) -> None:
        checks.append({"name": name, "observed": observed, "expected": expected, "passed": bool(passed)})

    add(
        "source_exact_search_adapter_quality_pass",
        summary.get("source_exact_search_adapter_quality_pass"),
        "is True",
        (not thresholds.require_source_exact_search_adapter_quality_pass)
        or bool(summary.get("source_exact_search_adapter_quality_pass")),
    )
    add(
        "source_exact_search_smoke_quality_pass",
        summary.get("source_exact_search_smoke_quality_pass"),
        "is True",
        (not thresholds.require_source_exact_search_smoke_quality_pass)
        or bool(summary.get("source_exact_search_smoke_quality_pass")),
    )
    add(
        "source_bridge_quality_pass",
        summary.get("source_bridge_quality_pass"),
        "is True",
        (not thresholds.require_source_bridge_quality_pass) or bool(summary.get("source_bridge_quality_pass")),
    )
    add(
        "source_integration_audit_quality_pass",
        summary.get("source_integration_audit_quality_pass"),
        "is True",
        (not thresholds.require_source_integration_audit_quality_pass)
        or bool(summary.get("source_integration_audit_quality_pass")),
    )
    add(
        "exact_search_document_count",
        _int(summary, "exact_search_document_count"),
        f">= {thresholds.min_exact_search_documents}",
        _int(summary, "exact_search_document_count") >= thresholds.min_exact_search_documents,
    )
    add(
        "successful_smoke_query_count",
        _int(summary, "successful_smoke_query_count"),
        f">= {thresholds.min_successful_smoke_queries}",
        _int(summary, "successful_smoke_query_count") >= thresholds.min_successful_smoke_queries,
    )
    add(
        "total_smoke_match_count",
        _int(summary, "total_smoke_match_count"),
        f">= {thresholds.min_total_smoke_matches}",
        _int(summary, "total_smoke_match_count") >= thresholds.min_total_smoke_matches,
    )
    add(
        "bridge_record_count",
        _int(summary, "bridge_record_count"),
        f">= {thresholds.min_bridge_records}",
        _int(summary, "bridge_record_count") >= thresholds.min_bridge_records,
    )
    add(
        "ranking_available_bridge_record_count",
        _int(summary, "ranking_available_bridge_record_count"),
        f">= {thresholds.min_ranking_available_bridge_records}",
        _int(summary, "ranking_available_bridge_record_count") >= thresholds.min_ranking_available_bridge_records,
    )
    add(
        "page_with_ranking_signal_count",
        _int(summary, "page_with_ranking_signal_count"),
        f">= {thresholds.min_pages_with_ranking_signals}",
        _int(summary, "page_with_ranking_signal_count") >= thresholds.min_pages_with_ranking_signals,
    )
    add(
        "field_count",
        _int(summary, "field_count"),
        f">= {thresholds.min_field_count}",
        _int(summary, "field_count") >= thresholds.min_field_count,
    )
    add(
        "schema_missing_required_key_record_count",
        _int(summary, "schema_missing_required_key_record_count"),
        "== 0",
        _int(summary, "schema_missing_required_key_record_count") == 0,
    )
    add(
        "unsafe_total_count",
        _int(summary, "unsafe_total_count"),
        f"<= {thresholds.max_unsafe_records}",
        _int(summary, "unsafe_total_count") <= thresholds.max_unsafe_records,
    )
    add(
        "answer_permission_count",
        _int(summary, "answer_permission_count"),
        f"<= {thresholds.max_answer_permission_count}",
        _int(summary, "answer_permission_count") <= thresholds.max_answer_permission_count,
    )
    add(
        "source_truth_mutation_allowed_count",
        _int(summary, "source_truth_mutation_allowed_count"),
        f"<= {thresholds.max_source_truth_mutation_allowed}",
        _int(summary, "source_truth_mutation_allowed_count") <= thresholds.max_source_truth_mutation_allowed,
    )
    add(
        "can_answer_directly_count",
        _int(summary, "can_answer_directly_count"),
        "== 0",
        (not thresholds.require_no_answer_permission) or _int(summary, "can_answer_directly_count") == 0,
    )
    add(
        "can_prove_claims_count",
        _int(summary, "can_prove_claims_count"),
        "== 0",
        (not thresholds.require_no_answer_permission) or _int(summary, "can_prove_claims_count") == 0,
    )
    add("postgres_write_attempt_count", _int(summary, "postgres_write_attempt_count"), "== 0", _int(summary, "postgres_write_attempt_count") == 0)
    add("qdrant_write_attempt_count", _int(summary, "qdrant_write_attempt_count"), "== 0", _int(summary, "qdrant_write_attempt_count") == 0)
    add("opensearch_write_attempt_count", _int(summary, "opensearch_write_attempt_count"), "== 0", _int(summary, "opensearch_write_attempt_count") == 0)
    add("opensearch_upload_attempt_count", _int(summary, "opensearch_upload_attempt_count"), "== 0", _int(summary, "opensearch_upload_attempt_count") == 0)
    return checks


def build_readiness_report(
    *,
    table_exact_search_adapter_path: str | Path,
    table_exact_search_smoke_path: str | Path,
    table_hybrid_retrieval_bridge_path: str | Path,
    table_hybrid_retrieval_integration_audit_path: str | Path,
    output_dir: str | Path,
    thresholds: ReadinessThresholds | None = None,
) -> Dict[str, Any]:
    thresholds = thresholds or ReadinessThresholds()
    adapter = _read_json(table_exact_search_adapter_path)
    smoke = _read_json(table_exact_search_smoke_path)
    bridge = _read_json(table_hybrid_retrieval_bridge_path)
    integration = _read_json(table_hybrid_retrieval_integration_audit_path)

    adapter_summary = _summary(adapter)
    smoke_summary = _summary(smoke)
    bridge_summary = _summary(bridge)
    integration_summary = _summary(integration)
    safety = _aggregate_safety_counters([adapter_summary, smoke_summary, bridge_summary, integration_summary])

    field_counts = _field_counts(integration) or _field_counts(bridge) or _field_counts(adapter)

    summary: Dict[str, Any] = {
        "source_exact_search_adapter_path": str(table_exact_search_adapter_path),
        "source_exact_search_smoke_path": str(table_exact_search_smoke_path),
        "source_hybrid_bridge_path": str(table_hybrid_retrieval_bridge_path),
        "source_integration_audit_path": str(table_hybrid_retrieval_integration_audit_path),
        "source_exact_search_adapter_quality_pass": _bool_quality_pass(adapter),
        "source_exact_search_smoke_quality_pass": _bool_quality_pass(smoke),
        "source_bridge_quality_pass": _bool_quality_pass(bridge),
        "source_integration_audit_quality_pass": _bool_quality_pass(integration),
        "exact_search_document_count": _int(adapter_summary, "table_exact_search_document_count", "source_exact_search_document_count"),
        "successful_smoke_query_count": _int(smoke_summary, "successful_smoke_query_count"),
        "total_smoke_match_count": _int(smoke_summary, "total_match_count", "source_total_smoke_match_count"),
        "bridge_record_count": _int(bridge_summary, "table_hybrid_bridge_record_count", "source_bridge_record_count"),
        "query_bridge_group_count": _int(bridge_summary, "query_bridge_group_count", "source_query_bridge_group_count"),
        "successful_query_bridge_group_count": _int(bridge_summary, "successful_query_bridge_group_count"),
        "ranking_available_bridge_record_count": _int(integration_summary, "ranking_available_bridge_record_count"),
        "integration_audit_record_count": _int(integration_summary, "integration_audit_record_count"),
        "page_with_ranking_signal_count": _int(integration_summary, "page_with_ranking_signal_count"),
        "field_count": _int(integration_summary, "field_count") or len(field_counts),
        "schema_missing_required_key_record_count": _int(integration_summary, "schema_missing_required_key_record_count"),
        "field_counts": field_counts,
        "retrieval_permission": "ranking_only",
        "answer_authority": "blocked",
        "final_answer_authority": "none",
        "ready_for_live_opensearch_upload": False,
        "ready_for_hybrid_retrieval_ranking": True,
        **safety,
    }

    checks = evaluate_quality(summary, thresholds)
    quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    summary["retrieval_readiness_status"] = (
        "READY_FOR_RETRIEVAL_RANKING_ONLY" if quality_status == "PASS" else "NOT_READY_FOR_RETRIEVAL_RANKING"
    )

    report = {
        "module": "trace_net_table_route_retrieval_readiness_report_v1",
        "status": "TABLE_ROUTE_RETRIEVAL_READINESS_REPORT_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "quality_checks": checks,
        "readiness_contract": {
            "table_route_values_are_searchable": _int(summary, "exact_search_document_count") > 0,
            "table_route_values_are_ranking_signals": _int(summary, "ranking_available_bridge_record_count") > 0,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "writes_to_postgres": False,
            "writes_to_qdrant": False,
            "writes_to_opensearch": False,
            "uploads_to_opensearch": False,
        },
    }

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / REPORT_FILENAME
    inspect_md_path = out_dir / INSPECT_MD_FILENAME
    _write_json(report_path, report)
    inspect_md_path.write_text(render_inspect_markdown(report), encoding="utf-8")
    report["report_path"] = str(report_path)
    report["inspect_md_path"] = str(inspect_md_path)
    _write_json(report_path, report)
    return report


def render_inspect_markdown(report: Mapping[str, Any]) -> str:
    summary = _summary(report)
    checks = report.get("quality_checks") or []
    lines = [
        "# TRACE-Net Table Route Retrieval Readiness Report v1 Inspect",
        "",
        f"Quality status: **{report.get('quality_status', 'UNKNOWN')}**",
        "",
        "## Readiness status",
        f"- retrieval_readiness_status: {summary.get('retrieval_readiness_status')}",
        f"- retrieval_permission: {summary.get('retrieval_permission')}",
        f"- answer_authority: {summary.get('answer_authority')}",
        f"- ready_for_hybrid_retrieval_ranking: {summary.get('ready_for_hybrid_retrieval_ranking')}",
        f"- ready_for_live_opensearch_upload: {summary.get('ready_for_live_opensearch_upload')}",
        "",
        "## Main counters",
        f"- exact_search_document_count: {_int(summary, 'exact_search_document_count')}",
        f"- successful_smoke_query_count: {_int(summary, 'successful_smoke_query_count')}",
        f"- total_smoke_match_count: {_int(summary, 'total_smoke_match_count')}",
        f"- bridge_record_count: {_int(summary, 'bridge_record_count')}",
        f"- ranking_available_bridge_record_count: {_int(summary, 'ranking_available_bridge_record_count')}",
        f"- page_with_ranking_signal_count: {_int(summary, 'page_with_ranking_signal_count')}",
        f"- field_count: {_int(summary, 'field_count')}",
        f"- schema_missing_required_key_record_count: {_int(summary, 'schema_missing_required_key_record_count')}",
        "",
        "## Field counts",
    ]
    field_counts = summary.get("field_counts")
    if isinstance(field_counts, Mapping) and field_counts:
        for k in sorted(field_counts):
            lines.append(f"- {k}: {field_counts[k]}")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Safety/write counters",
            f"- unsafe_total_count: {_int(summary, 'unsafe_total_count')}",
            f"- answer_permission_count: {_int(summary, 'answer_permission_count')}",
            f"- can_answer_directly_count: {_int(summary, 'can_answer_directly_count')}",
            f"- can_prove_claims_count: {_int(summary, 'can_prove_claims_count')}",
            f"- source_truth_mutation_allowed_count: {_int(summary, 'source_truth_mutation_allowed_count')}",
            f"- postgres_write_attempt_count: {_int(summary, 'postgres_write_attempt_count')}",
            f"- qdrant_write_attempt_count: {_int(summary, 'qdrant_write_attempt_count')}",
            f"- opensearch_write_attempt_count: {_int(summary, 'opensearch_write_attempt_count')}",
            f"- opensearch_upload_attempt_count: {_int(summary, 'opensearch_upload_attempt_count')}",
            "",
            "## Quality checks",
        ]
    )
    for check in checks:
        mark = "PASS" if check.get("passed") else "FAIL"
        lines.append(f"- {mark} {check.get('name')}: observed={check.get('observed')} expected={check.get('expected')}")
    lines.append("")
    return "\n".join(lines)


def check_report_quality(report_path: str | Path, thresholds: ReadinessThresholds, write_json: bool = False) -> Dict[str, Any]:
    report = _read_json(report_path)
    summary = _summary(report)
    checks = evaluate_quality(summary, thresholds)
    quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    result = {
        "module": "trace_net_table_route_retrieval_readiness_report_v1_quality",
        "quality_status": quality_status,
        "report_path": str(report_path),
        "quality_checks": checks,
        "summary": dict(summary),
    }
    if write_json:
        _write_json(Path(report_path).with_name(CHECK_FILENAME), result)
    return result


def add_threshold_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-exact-search-documents", type=int, default=1000)
    parser.add_argument("--min-successful-smoke-queries", type=int, default=3)
    parser.add_argument("--min-total-smoke-matches", type=int, default=3)
    parser.add_argument("--min-bridge-records", type=int, default=1000)
    parser.add_argument("--min-ranking-available-bridge-records", type=int, default=1000)
    parser.add_argument("--min-pages-with-ranking-signals", type=int, default=1)
    parser.add_argument("--min-field-count", type=int, default=4)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-source-exact-search-adapter-quality-pass", action="store_true")
    parser.add_argument("--require-source-exact-search-smoke-quality-pass", action="store_true")
    parser.add_argument("--require-source-bridge-quality-pass", action="store_true")
    parser.add_argument("--require-source-integration-audit-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")


def thresholds_from_args(args: argparse.Namespace) -> ReadinessThresholds:
    return ReadinessThresholds(
        min_exact_search_documents=args.min_exact_search_documents,
        min_successful_smoke_queries=args.min_successful_smoke_queries,
        min_total_smoke_matches=args.min_total_smoke_matches,
        min_bridge_records=args.min_bridge_records,
        min_ranking_available_bridge_records=args.min_ranking_available_bridge_records,
        min_pages_with_ranking_signals=args.min_pages_with_ranking_signals,
        min_field_count=args.min_field_count,
        max_unsafe_records=args.max_unsafe_records,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_source_exact_search_adapter_quality_pass=args.require_source_exact_search_adapter_quality_pass,
        require_source_exact_search_smoke_quality_pass=args.require_source_exact_search_smoke_quality_pass,
        require_source_bridge_quality_pass=args.require_source_bridge_quality_pass,
        require_source_integration_audit_quality_pass=args.require_source_integration_audit_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )
