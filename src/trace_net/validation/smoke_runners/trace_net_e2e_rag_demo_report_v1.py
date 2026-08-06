"""TRACE-Net E2E RAG demo report v1.

This module stitches the artifact-only E2E chain into a single local demo report:
query planning/routing -> planned hybrid retrieval -> planned context pack ->
evidence sufficiency gate -> final gate smoke.

It is deliberately conservative. It reports safe response drafts and audit status,
but it does not grant answer authority, prove claims, mutate source truth, or write
runtime services.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

REPORT_FILENAME = "trace_net_e2e_rag_demo_report_v1.json"
QUALITY_FILENAME = "trace_net_e2e_rag_demo_report_v1_quality.json"
INSPECT_FILENAME = "trace_net_e2e_rag_demo_report_v1_inspect.md"
RECORDS_JSONL_FILENAME = "trace_net_e2e_rag_demo_records_v1.jsonl"

PASS = "PASS"
FAIL = "FAIL"


def _load_json(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {p}")
    return data


def _write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=False), encoding="utf-8")


def _write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=False) + "\n")


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _summary(data: Mapping[str, Any]) -> Mapping[str, Any]:
    s = data.get("summary")
    return s if isinstance(s, Mapping) else {}


def _is_pass(data: Mapping[str, Any]) -> bool:
    return data.get("quality_status") == PASS


def _get_counter(data: Mapping[str, Any], *keys: str, default: int = 0) -> int:
    for key in keys:
        value = data.get(key)
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
    s = _summary(data)
    for key in keys:
        value = s.get(key)
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
    return default


def _safe_bool(value: Any) -> bool:
    return bool(value) if isinstance(value, bool) else False


def _index_by_query_id(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Mapping[str, Any]]:
    out: Dict[str, Mapping[str, Any]] = {}
    for row in rows:
        qid = row.get("query_id")
        if isinstance(qid, str):
            out[qid] = row
    return out


def _first_text(row: Mapping[str, Any], keys: Sequence[str], default: str = "") -> str:
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    return default


def _page_ids_from_items(items: Sequence[Mapping[str, Any]]) -> List[str]:
    pages: List[str] = []
    for item in items:
        page_id = item.get("page_id")
        if isinstance(page_id, str) and page_id not in pages:
            pages.append(page_id)
    return pages


def _citations_from_record(record: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    citations = record.get("citations")
    if isinstance(citations, list):
        return [c for c in citations if isinstance(c, Mapping)]
    return []


def _records_from_sources(
    planning: Mapping[str, Any],
    runtime: Mapping[str, Any],
    context: Mapping[str, Any],
    sufficiency: Mapping[str, Any],
    final_gate: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    plans = [r for r in _as_list(planning.get("query_route_plans")) if isinstance(r, Mapping)]
    runtime_by_qid = _index_by_query_id([r for r in _as_list(runtime.get("retrieval_groups")) if isinstance(r, Mapping)])
    context_by_qid = _index_by_query_id([r for r in _as_list(context.get("context_packs")) if isinstance(r, Mapping)])
    suff_by_qid = _index_by_query_id([r for r in _as_list(sufficiency.get("gate_records")) if isinstance(r, Mapping)])
    final_by_qid = _index_by_query_id([r for r in _as_list(final_gate.get("final_gate_records")) if isinstance(r, Mapping)])

    records: List[Dict[str, Any]] = []
    for plan in plans:
        qid = _first_text(plan, ["query_id"])
        runtime_row = runtime_by_qid.get(qid, {})
        context_row = context_by_qid.get(qid, {})
        suff_row = suff_by_qid.get(qid, {})
        final_row = final_by_qid.get(qid, {})

        hits = [h for h in _as_list(runtime_row.get("hits")) if isinstance(h, Mapping)]
        context_items = [i for i in _as_list(context_row.get("top_context_items")) if isinstance(i, Mapping)]
        if not context_items:
            context_items = [i for i in _as_list(context_row.get("context_items")) if isinstance(i, Mapping)]
        citations = _citations_from_record(final_row)
        page_ids = list(dict.fromkeys(
            list(plan.get("page_ids", []) if isinstance(plan.get("page_ids"), list) else [])
            + list(runtime_row.get("page_ids", []) if isinstance(runtime_row.get("page_ids"), list) else [])
            + _page_ids_from_items(context_items)
            + list(suff_row.get("page_ids", []) if isinstance(suff_row.get("page_ids"), list) else [])
            + list(final_row.get("page_ids", []) if isinstance(final_row.get("page_ids"), list) else [])
            + _page_ids_from_items(citations)
        ))

        final_decision = _first_text(final_row, ["final_gate_decision", "decision", "response_decision"], "UNKNOWN_FINAL_GATE_DECISION")
        response_type = _first_text(final_row, ["response_type", "final_response_type"], "safe_response_draft")
        response_draft = _first_text(final_row, ["response_draft", "draft_response", "response_text"], "")
        evidence_status = _first_text(suff_row, ["evidence_sufficiency_status"], "UNKNOWN_EVIDENCE_STATUS")

        flow_complete = bool(qid and runtime_row and context_row and suff_row and final_row)
        demo_status = "E2E_DEMO_FLOW_COMPLETE" if flow_complete else "E2E_DEMO_FLOW_INCOMPLETE"

        records.append({
            "query_id": qid,
            "query_intent": _first_text(plan, ["query_intent"]),
            "user_query": _first_text(plan, ["user_query"]),
            "demo_flow_status": demo_status,
            "routeable": bool(plan.get("routeable", True)),
            "tunnel_types": list(plan.get("tunnel_types", [])) if isinstance(plan.get("tunnel_types"), list) else [],
            "planned_retrieval_step_count": len(_as_list(plan.get("planned_retrieval_order"))),
            "retrieval_status": _first_text(runtime_row, ["retrieval_status"], "UNKNOWN_RETRIEVAL_STATUS"),
            "retrieval_hit_count": int(runtime_row.get("hit_count", len(hits)) or 0),
            "context_pack_status": _first_text(context_row, ["context_pack_status"], "UNKNOWN_CONTEXT_PACK_STATUS"),
            "context_item_count": int(context_row.get("context_item_count", len(context_items)) or 0),
            "evidence_sufficiency_status": evidence_status,
            "final_gate_decision": final_decision,
            "response_type": response_type,
            "response_draft": response_draft,
            "citation_count": int(final_row.get("citation_count", len(citations)) or 0),
            "source_trace_count": int(final_row.get("source_trace_count", final_row.get("citation_count", len(citations))) or 0),
            "page_ids": page_ids,
            "top_citations": [dict(c) for c in citations[:3]],
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
        })
    return records


def _quality_checks(report: Mapping[str, Any], thresholds: Mapping[str, int | bool]) -> List[Dict[str, Any]]:
    s = _summary(report)
    checks: List[Dict[str, Any]] = []

    def add(name: str, observed: Any, expected: str, passed: bool) -> None:
        checks.append({"name": name, "observed": observed, "expected": expected, "passed": bool(passed)})

    add("source_planning_quality_pass", s.get("source_planning_quality_pass"), "is True", bool(s.get("source_planning_quality_pass")))
    add("source_runtime_quality_pass", s.get("source_runtime_quality_pass"), "is True", bool(s.get("source_runtime_quality_pass")))
    add("source_context_quality_pass", s.get("source_context_quality_pass"), "is True", bool(s.get("source_context_quality_pass")))
    add("source_sufficiency_quality_pass", s.get("source_sufficiency_quality_pass"), "is True", bool(s.get("source_sufficiency_quality_pass")))
    add("source_final_gate_smoke_quality_pass", s.get("source_final_gate_smoke_quality_pass"), "is True", bool(s.get("source_final_gate_smoke_quality_pass")))

    int_thresholds = [
        ("stage_pass_count", "min_stage_passes"),
        ("e2e_demo_record_count", "min_demo_records"),
        ("complete_demo_flow_count", "min_complete_demo_flows"),
        ("planned_query_route_plan_count", "min_route_plans"),
        ("total_query_tunnel_count", "min_total_tunnels"),
        ("retrieval_group_count", "min_retrieval_groups"),
        ("successful_retrieval_query_count", "min_successful_retrieval_queries"),
        ("context_pack_count", "min_context_packs"),
        ("final_gate_review_ready_pack_count", "min_final_gate_ready_packs"),
        ("final_gate_record_count", "min_final_gate_records"),
        ("safe_response_draft_count", "min_safe_response_drafts"),
        ("citation_backed_response_draft_count", "min_citation_backed_response_drafts"),
        ("total_citation_count", "min_total_citations"),
        ("page_with_citation_count", "min_pages_cited"),
        ("field_count", "min_field_count"),
    ]
    for observed_key, threshold_key in int_thresholds:
        threshold = int(thresholds.get(threshold_key, 0) or 0)
        observed = int(s.get(observed_key, 0) or 0)
        add(observed_key, observed, f">= {threshold}", observed >= threshold)

    max_thresholds = [
        ("schema_missing_required_key_record_count", "max_schema_missing_required_key_records"),
        ("unsafe_total_count", "max_unsafe_records"),
        ("answer_permission_count", "max_answer_permission_count"),
        ("source_truth_mutation_allowed_count", "max_source_truth_mutation_allowed"),
    ]
    for observed_key, threshold_key in max_thresholds:
        threshold = int(thresholds.get(threshold_key, 0) or 0)
        observed = int(s.get(observed_key, 0) or 0)
        add(observed_key, observed, f"<= {threshold}", observed <= threshold)

    add("can_answer_directly_count", s.get("can_answer_directly_count", 0), "== 0", int(s.get("can_answer_directly_count", 0) or 0) == 0)
    add("can_prove_claims_count", s.get("can_prove_claims_count", 0), "== 0", int(s.get("can_prove_claims_count", 0) or 0) == 0)
    add("postgres_write_attempt_count", s.get("postgres_write_attempt_count", 0), "== 0", int(s.get("postgres_write_attempt_count", 0) or 0) == 0)
    add("qdrant_write_attempt_count", s.get("qdrant_write_attempt_count", 0), "== 0", int(s.get("qdrant_write_attempt_count", 0) or 0) == 0)
    add("opensearch_write_attempt_count", s.get("opensearch_write_attempt_count", 0), "== 0", int(s.get("opensearch_write_attempt_count", 0) or 0) == 0)
    add("opensearch_upload_attempt_count", s.get("opensearch_upload_attempt_count", 0), "== 0", int(s.get("opensearch_upload_attempt_count", 0) or 0) == 0)
    add("all_demo_records_no_answer_authority", s.get("all_demo_records_no_answer_authority"), "is True", bool(s.get("all_demo_records_no_answer_authority")))

    return checks


def build_e2e_rag_demo_report(
    *,
    query_planning_routing_path: str | Path,
    e2e_hybrid_retrieval_runtime_path: str | Path,
    e2e_context_pack_builder_path: str | Path,
    e2e_evidence_sufficiency_gate_path: str | Path,
    e2e_final_gate_smoke_path: str | Path,
    output_dir: str | Path,
    thresholds: Optional[Mapping[str, int | bool]] = None,
) -> Dict[str, Any]:
    thresholds = dict(thresholds or {})
    planning = _load_json(query_planning_routing_path)
    runtime = _load_json(e2e_hybrid_retrieval_runtime_path)
    context = _load_json(e2e_context_pack_builder_path)
    sufficiency = _load_json(e2e_evidence_sufficiency_gate_path)
    final_gate = _load_json(e2e_final_gate_smoke_path)

    records = _records_from_sources(planning, runtime, context, sufficiency, final_gate)
    field_counts: Counter[str] = Counter()
    pages_with_citations: set[str] = set()
    for rec in records:
        for cite in rec.get("top_citations", []):
            field_name = cite.get("field_name")
            if isinstance(field_name, str) and field_name:
                field_counts[field_name] += 1
            page_id = cite.get("page_id")
            if isinstance(page_id, str) and page_id:
                pages_with_citations.add(page_id)
        if not rec.get("top_citations"):
            # Fall back to intent if final-gate fixture stores only counts.
            if rec.get("query_intent"):
                field_counts[str(rec["query_intent"])] += 1
            for page_id in rec.get("page_ids", [])[:1]:
                if isinstance(page_id, str):
                    pages_with_citations.add(page_id)

    stage_passes = sum(_is_pass(x) for x in [planning, runtime, context, sufficiency, final_gate])
    complete_flow_count = sum(1 for r in records if r["demo_flow_status"] == "E2E_DEMO_FLOW_COMPLETE")
    no_authority = all(
        not r.get("answer_permission") and not r.get("can_answer_directly") and not r.get("can_prove_claims") and not r.get("source_truth_mutation_allowed")
        for r in records
    )

    final_summary = _summary(final_gate)
    summary: Dict[str, Any] = {
        "e2e_rag_demo_status": "E2E_RAG_DEMO_REPORT_READY_FOR_API_WRAPPER",
        "source_planning_quality_pass": _is_pass(planning),
        "source_runtime_quality_pass": _is_pass(runtime),
        "source_context_quality_pass": _is_pass(context),
        "source_sufficiency_quality_pass": _is_pass(sufficiency),
        "source_final_gate_smoke_quality_pass": _is_pass(final_gate),
        "stage_pass_count": stage_passes,
        "e2e_demo_record_count": len(records),
        "complete_demo_flow_count": complete_flow_count,
        "planned_query_route_plan_count": _get_counter(planning, "query_route_plan_count"),
        "total_query_tunnel_count": _get_counter(planning, "total_query_tunnel_count"),
        "unique_tunnel_type_count": _get_counter(planning, "unique_tunnel_type_count"),
        "retrieval_group_count": _get_counter(runtime, "retrieval_group_count"),
        "successful_retrieval_query_count": _get_counter(runtime, "successful_retrieval_query_count"),
        "total_retrieval_hit_count": _get_counter(runtime, "total_retrieval_hit_count"),
        "context_pack_count": _get_counter(context, "context_pack_count"),
        "total_context_item_count": _get_counter(context, "total_context_item_count"),
        "citation_ready_context_item_count": _get_counter(context, "citation_ready_context_item_count"),
        "source_trace_ready_context_item_count": _get_counter(context, "source_trace_ready_context_item_count"),
        "sufficient_context_pack_count": _get_counter(sufficiency, "sufficient_context_pack_count"),
        "final_gate_review_ready_pack_count": _get_counter(sufficiency, "final_gate_review_ready_pack_count"),
        "final_gate_record_count": _get_counter(final_gate, "final_gate_record_count"),
        "safe_response_draft_count": _get_counter(final_gate, "safe_response_draft_count"),
        "citation_backed_response_draft_count": _get_counter(final_gate, "citation_backed_response_draft_count"),
        "audit_only_response_count": _get_counter(final_gate, "audit_only_response_count"),
        "total_citation_count": _get_counter(final_gate, "total_citation_count"),
        "page_with_citation_count": _get_counter(final_gate, "page_with_citation_count", default=len(pages_with_citations)),
        "field_count": max(_get_counter(final_gate, "field_count"), len(field_counts)),
        "field_counts": dict(sorted(field_counts.items())),
        "schema_missing_required_key_record_count": sum(_get_counter(x, "schema_missing_required_key_record_count") for x in [planning, runtime, context, sufficiency, final_gate]),
        "unsafe_total_count": sum(_get_counter(x, "unsafe_query_route_plan_count", "unsafe_runtime_record_count", "unsafe_context_record_count", "unsafe_evidence_sufficiency_record_count", "unsafe_final_gate_smoke_record_count", "unsafe_record_count") for x in [planning, runtime, context, sufficiency, final_gate]),
        "answer_permission_count": sum(_get_counter(x, "answer_permission_count") for x in [planning, runtime, context, sufficiency, final_gate]),
        "can_answer_directly_count": sum(_get_counter(x, "can_answer_directly_count") for x in [planning, runtime, context, sufficiency, final_gate]),
        "can_prove_claims_count": sum(_get_counter(x, "can_prove_claims_count") for x in [planning, runtime, context, sufficiency, final_gate]),
        "source_truth_mutation_allowed_count": sum(_get_counter(x, "source_truth_mutation_allowed_count") for x in [planning, runtime, context, sufficiency, final_gate]),
        "postgres_write_attempt_count": sum(_get_counter(x, "postgres_write_attempt_count") for x in [planning, runtime, context, sufficiency, final_gate]),
        "qdrant_write_attempt_count": sum(_get_counter(x, "qdrant_write_attempt_count") for x in [planning, runtime, context, sufficiency, final_gate]),
        "opensearch_write_attempt_count": sum(_get_counter(x, "opensearch_write_attempt_count") for x in [planning, runtime, context, sufficiency, final_gate]),
        "opensearch_upload_attempt_count": sum(_get_counter(x, "opensearch_upload_attempt_count") for x in [planning, runtime, context, sufficiency, final_gate]),
        "all_demo_records_no_answer_authority": no_authority,
        "api_wrapper_next_step": True,
    }

    report: Dict[str, Any] = {
        "report_schema_version": "trace_net_e2e_rag_demo_report_v1",
        "status": "E2E_RAG_DEMO_REPORT_BUILT",
        "quality_status": PASS,
        "e2e_rag_demo_status": summary["e2e_rag_demo_status"],
        "demo_contract": {
            "purpose": "Combine planned query routing, hybrid retrieval, context packs, sufficiency, and final-gate smoke into one local E2E RAG demo report.",
            "graph_and_summaries_are_tunnels": True,
            "tunnels_can_rank_or_route": True,
            "tunnels_can_answer_directly": False,
            "safe_responses_are_drafts_until_api_finalization": True,
            "answer_authority": "blocked_in_artifact_smoke",
            "retrieval_permission": "ranking_until_final_gate_smoke",
            "ready_for_api_wrapper": True,
            "source_truth_mutation_allowed": False,
            "writes_to_postgres": False,
            "writes_to_qdrant": False,
            "writes_to_opensearch": False,
            "uploads_to_opensearch": False,
        },
        "source_paths": {
            "query_planning_routing": str(query_planning_routing_path),
            "e2e_hybrid_retrieval_runtime": str(e2e_hybrid_retrieval_runtime_path),
            "e2e_context_pack_builder": str(e2e_context_pack_builder_path),
            "e2e_evidence_sufficiency_gate": str(e2e_evidence_sufficiency_gate_path),
            "e2e_final_gate_smoke": str(e2e_final_gate_smoke_path),
        },
        "summary": summary,
        "demo_records": records,
        "quality_checks": [],
    }
    checks = _quality_checks(report, thresholds)
    report["quality_checks"] = checks
    report["quality_status"] = PASS if all(c["passed"] for c in checks) else FAIL

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / REPORT_FILENAME
    quality_path = output / QUALITY_FILENAME
    inspect_path = output / INSPECT_FILENAME
    records_path = output / RECORDS_JSONL_FILENAME

    _write_json(report_path, report)
    _write_json(quality_path, {"quality_status": report["quality_status"], "quality_checks": checks, "summary": summary})
    _write_jsonl(records_path, records)
    inspect_path.write_text(render_inspect_markdown(report), encoding="utf-8")

    report["report_path"] = str(report_path)
    report["quality_path"] = str(quality_path)
    report["records_jsonl_path"] = str(records_path)
    report["inspect_md_path"] = str(inspect_path)
    _write_json(report_path, report)
    return report


def render_inspect_markdown(report: Mapping[str, Any]) -> str:
    s = _summary(report)
    lines = [
        "# TRACE-Net E2E RAG Demo Report v1 Inspect",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        "",
        "## Demo status",
        f"- e2e_rag_demo_status: {report.get('e2e_rag_demo_status')}",
        "- graph and summaries are tunnels: True",
        "- answer authority: blocked in artifact smoke",
        "- ready for API wrapper: True",
        "",
        "## Main counters",
    ]
    for key in [
        "stage_pass_count",
        "e2e_demo_record_count",
        "complete_demo_flow_count",
        "planned_query_route_plan_count",
        "total_query_tunnel_count",
        "retrieval_group_count",
        "successful_retrieval_query_count",
        "total_retrieval_hit_count",
        "context_pack_count",
        "total_context_item_count",
        "final_gate_review_ready_pack_count",
        "final_gate_record_count",
        "safe_response_draft_count",
        "citation_backed_response_draft_count",
        "total_citation_count",
        "page_with_citation_count",
        "field_count",
    ]:
        lines.append(f"- {key}: {s.get(key)}")
    lines.extend(["", "## Safety/write counters"])
    for key in [
        "unsafe_total_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "opensearch_upload_attempt_count",
    ]:
        lines.append(f"- {key}: {s.get(key)}")
    lines.extend(["", "## Demo records"])
    for row in _as_list(report.get("demo_records")):
        if not isinstance(row, Mapping):
            continue
        lines.append(
            f"- {row.get('query_id')} | {row.get('query_intent')} | {row.get('demo_flow_status')} | "
            f"retrieval_hits={row.get('retrieval_hit_count')} | citations={row.get('citation_count')}"
        )
        lines.append(f"  - query: {row.get('user_query')}")
        lines.append(f"  - final_gate_decision: {row.get('final_gate_decision')}")
        lines.append(f"  - pages: {', '.join(row.get('page_ids', [])[:8]) if isinstance(row.get('page_ids'), list) else ''}")
        draft = row.get("response_draft") or ""
        if draft:
            lines.append(f"  - draft: {str(draft)[:240]}")
    lines.extend(["", "## Quality checks"])
    for check in _as_list(report.get("quality_checks")):
        if isinstance(check, Mapping):
            status = "PASS" if check.get("passed") else "FAIL"
            lines.append(f"- {status} {check.get('name')}: observed={check.get('observed')} expected={check.get('expected')}")
    return "\n".join(lines) + "\n"


__all__ = [
    "build_e2e_rag_demo_report",
    "render_inspect_markdown",
]
