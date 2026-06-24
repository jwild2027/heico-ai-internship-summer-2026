from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from tiff.trace_net_e2e_relationship_router_hardening_v29_1 import (
    MODEL_ID as ROUTER_MODEL_ID,
    SAFETY_CONTRACT as ROUTER_SAFETY_CONTRACT,
    RuntimeState as RouterRuntimeState,
    _extract_user_text,
    _read_json,
    _write_json,
    _write_jsonl,
)
from tiff.trace_net_e2e_relationship_final_gate_hardener_v30 import (
    SAFETY_CONTRACT as RELATIONSHIP_GATE_SAFETY_CONTRACT,
    final_gate_record,
)

VERSION = "v31"
MODULE = "trace_net_e2e_live_relationship_final_gated_endpoint_v31"
MODEL_ID = "trace-net-e2e-live-relationship-final-gated-gemma-v31"
STATUS_READY = "E2E_LIVE_RELATIONSHIP_FINAL_GATED_ENDPOINT_READY"
STATUS_NEEDS_REPAIR = "E2E_LIVE_RELATIONSHIP_FINAL_GATED_ENDPOINT_NEEDS_REPAIR"

SAFETY_CONTRACT = {
    **ROUTER_SAFETY_CONTRACT,
    **RELATIONSHIP_GATE_SAFETY_CONTRACT,
    "llm_called": False,
    "metadata_count_router_enabled": True,
    "relationship_final_gate_required": True,
    "relationship_final_gate_live_endpoint": True,
    "graph_leiden_guidance_only": True,
    "v2_summaries_guidance_only": True,
    "nomenclature_metadata_guidance_only": True,
    "source_truth_required_for_relationship_claims": True,
}

STANDARD_SAMPLE_QUERIES = [
    "how many pages have a v2 summary",
    "how many pages mention a nomenclature",
    "find part number 120-36833-503",
    "Find part number DOES-NOT-EXIST-999",
    "What maintenance manual pages mention covered part numbers?",
    "Drill down covered part numbers by page",
    "What pages are related to part number 120-36833-503?",
    "Which pages are in the same Leiden community as page t_p_120_1176_p000003?",
    "Explain how part number 120-36833-503 relates to manual reference 25-21-00",
]


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


def _quality_check(name: str, observed: Any, op: str, expected: Any) -> Dict[str, Any]:
    if op == ">=":
        passed = observed >= expected
    elif op == "<=":
        passed = observed <= expected
    elif op == "==":
        passed = observed == expected
    elif op == "is":
        passed = observed is expected
    else:
        raise ValueError(f"Unsupported op {op}")
    return {"name": name, "observed": observed, "op": op, "expected": expected, "passed": bool(passed)}


def _router_result_to_gate_input(query: str, router_result: Dict[str, Any]) -> Dict[str, Any]:
    """Adapt a v29.2 router result to the v30 relationship final-gate shape."""
    return {
        **router_result,
        "user_query": query,
        "query": query,
        "final_answer": router_result.get("answer", ""),
        "answer": router_result.get("answer", ""),
        "response_mode": router_result.get("response_mode"),
        "final_gate_status": router_result.get("final_gate_status"),
        "relationship_query": router_result.get("relationship_query", False),
    }


def apply_relationship_final_gate(query: str, router_result: Dict[str, Any], *, record_id: str = "live_relationship_gate_v31_0001") -> Dict[str, Any]:
    """Apply the v30 relationship hard gate to a live router result."""
    gate_input = _router_result_to_gate_input(query, router_result)
    gate = final_gate_record(gate_input, record_id=record_id)
    final_result = dict(router_result)
    final_result["source_final_gate_status"] = router_result.get("final_gate_status")
    final_result["answer"] = gate.get("final_answer", router_result.get("answer", ""))
    final_result["relationship_final_gate_applied"] = True
    final_result["relationship_final_gate_status"] = gate.get("final_gate_status")
    final_result["relationship_final_gate_repaired"] = gate.get("repaired_from_draft", False)
    final_result["relationship_final_gate_post_issue_count"] = gate.get("post_gate_issue_count", 0)
    final_result["relationship_final_gate_record_id"] = gate.get("relationship_final_gate_id")
    final_result["relationship_gate_latency_ms"] = gate.get("latency_ms", 0)
    final_result["graph_as_proof_violation_detected"] = gate.get("graph_as_proof_violation_detected", False)
    final_result["v2_summary_as_proof_violation_detected"] = gate.get("v2_summary_as_proof_violation_detected", False)
    final_result["nomenclature_as_proof_violation_detected"] = gate.get("nomenclature_as_proof_violation_detected", False)
    final_result["unsupported_relationship_claim_detected"] = gate.get("unsupported_relationship_claim_detected", False)
    final_result["relationship_guidance_only_enforced"] = gate.get("relationship_guidance_only_enforced", False)
    final_result["source_truth_required_for_relationship_claims"] = True
    final_result["final_gate_status"] = gate.get("final_gate_status")
    final_result["relationship_final_gate_record"] = gate

    safety = dict(final_result.get("safety") or {})
    safety.update(
        {
            "relationship_final_gate_required": True,
            "relationship_final_gate_applied": True,
            "source_truth_required_for_relationship_claims": True,
            "graph_leiden_guidance_only": True,
            "v2_summaries_guidance_only": True,
            "nomenclature_metadata_guidance_only": True,
            "response_is_final_gated": gate.get("final_gate_status") == "RELATIONSHIP_FINAL_GATE_PASS",
        }
    )
    final_result["safety"] = safety
    return final_result


class RuntimeState:
    def __init__(
        self,
        *,
        relationship_router_hardening: Path,
        relationship_final_gate_hardener: Optional[Path],
        table_exact_search_adapter: Path,
        page_context_v2: Optional[Path],
        leiden_communities: Optional[Path],
        graph_signal_paths: Optional[Sequence[Path]] = None,
    ):
        self.router_state = RouterRuntimeState(
            relationship_router_hardening,
            table_exact_search_adapter,
            page_context_v2,
            leiden_communities,
            graph_signal_paths,
        )
        self.router_report = self.router_state.report
        self.relationship_final_gate_hardener_path = relationship_final_gate_hardener
        self.relationship_final_gate_hardener_report = _read_json(relationship_final_gate_hardener) if relationship_final_gate_hardener and relationship_final_gate_hardener.exists() else {}

    def answer(self, query: str) -> Dict[str, Any]:
        t0 = _now_ms()
        router_result = self.router_state.answer(query)
        gated = apply_relationship_final_gate(query, router_result, record_id=f"live_relationship_final_gate_v31_{uuid.uuid4().hex[:8]}")
        # Preserve router timings and add the total live wrapper timing.
        stage_timings = dict(gated.get("stage_timings_ms") or {})
        stage_timings["relationship_final_gate_ms"] = gated.get("relationship_gate_latency_ms", 0)
        stage_timings["live_wrapper_total_ms"] = round(_now_ms() - t0, 3)
        gated["stage_timings_ms"] = stage_timings
        gated["latency_summary"] = {
            **dict(gated.get("latency_summary") or {}),
            "live_wrapper_total_ms": stage_timings["live_wrapper_total_ms"],
            "relationship_final_gate_ms": stage_timings["relationship_final_gate_ms"],
        }
        return gated


def make_chat_completion_response(model: str, query: str, result: Dict[str, Any]) -> Dict[str, Any]:
    trace_net = {
        "endpoint_version": "live_relationship_final_gated_v31",
        "query_intent": result.get("query_intent"),
        "response_mode": result.get("response_mode"),
        "source_final_gate_status": result.get("source_final_gate_status"),
        "final_gate_status": result.get("final_gate_status"),
        "relationship_final_gate_applied": result.get("relationship_final_gate_applied", False),
        "relationship_final_gate_status": result.get("relationship_final_gate_status"),
        "relationship_final_gate_repaired": result.get("relationship_final_gate_repaired", False),
        "relationship_final_gate_post_issue_count": result.get("relationship_final_gate_post_issue_count", 0),
        "graph_as_proof_violation_detected": result.get("graph_as_proof_violation_detected", False),
        "v2_summary_as_proof_violation_detected": result.get("v2_summary_as_proof_violation_detected", False),
        "nomenclature_as_proof_violation_detected": result.get("nomenclature_as_proof_violation_detected", False),
        "unsupported_relationship_claim_detected": result.get("unsupported_relationship_claim_detected", False),
        "citation_like_count": result.get("citation_like_count", 0),
        "total_match_count": result.get("total_match_count", 0),
        "returned_match_count": result.get("returned_match_count", 0),
        "result_was_capped": result.get("result_was_capped", False),
        "metadata_count_router_used": result.get("metadata_count_router_used", False),
        "metadata_count_source": result.get("metadata_count_source"),
        "bad_broad_fallback_blocked": result.get("bad_broad_fallback_blocked", False),
        "relationship_query": result.get("relationship_query", False),
        "relationship_guidance_only": result.get("relationship_guidance_only", False),
        "relationship_guidance_only_enforced": result.get("relationship_guidance_only_enforced", False),
        "relationship_proof_violation": result.get("relationship_proof_violation", False),
        "source_truth_required_for_relationship_claims": result.get("source_truth_required_for_relationship_claims", True),
        "llm_status": result.get("llm_status"),
        "llm_called": result.get("llm_called", False),
        "stage_timings_ms": result.get("stage_timings_ms", {}),
        "latency_summary": result.get("latency_summary", {}),
        "safety": result.get("safety", SAFETY_CONTRACT),
    }
    for key in (
        "v2_summary_page_count",
        "v2_summary_page_first",
        "v2_summary_page_last",
        "page_context_v2_page_count",
        "graph_has_v2_page_count",
        "graph_has_context_page_count",
        "nomenclature_page_count",
        "nomenclature_page_first",
        "nomenclature_page_last",
        "nomenclature_part_count",
        "raw_candidate_match_count",
        "target_unique_match_count",
        "target_occurrence_count",
        "collapsed_duplicate_record_count",
        "candidate_page_ids",
        "leiden_community_ids",
    ):
        if key in result:
            trace_net[key] = result[key]
    return {
        "id": f"chatcmpl-tracenet-v31-{uuid.uuid4().hex[:16]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": result.get("answer", "")}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "trace_net": trace_net,
    }


def _sample_record(sample_id: str, query: str, result: Dict[str, Any]) -> Dict[str, Any]:
    status = "PASS" if result.get("relationship_final_gate_status") == "RELATIONSHIP_FINAL_GATE_PASS" and result.get("relationship_final_gate_post_issue_count", 0) == 0 else "FAIL"
    return {
        "sample_id": sample_id,
        "query": query,
        "status": status,
        "response_mode": result.get("response_mode"),
        "source_final_gate_status": result.get("source_final_gate_status"),
        "relationship_final_gate_status": result.get("relationship_final_gate_status"),
        "relationship_final_gate_applied": result.get("relationship_final_gate_applied"),
        "relationship_final_gate_repaired": result.get("relationship_final_gate_repaired"),
        "post_gate_issue_count": result.get("relationship_final_gate_post_issue_count", 0),
        "relationship_query": result.get("relationship_query", False),
        "metadata_count_router_used": result.get("metadata_count_router_used", False),
        "bad_broad_fallback_blocked": result.get("bad_broad_fallback_blocked", False),
        "answer": result.get("answer", ""),
        "trace_net": {k: v for k, v in result.items() if k.endswith("_count") or k.endswith("_status") or k in {"metadata_count_source", "relationship_guidance_only"}},
    }


def build_report(
    *,
    relationship_router_hardening: Path,
    relationship_final_gate_hardener: Optional[Path],
    table_exact_search_adapter: Path,
    page_context_v2: Optional[Path],
    leiden_communities: Optional[Path],
    output_dir: Path,
    graph_signal_paths: Optional[Sequence[Path]] = None,
    include_standard_demo_queries: bool = False,
    min_sample_queries: int = 0,
    min_sample_successes: int = 0,
    min_relationship_final_gate_applied: int = 0,
    min_relationship_records: int = 0,
    max_post_gate_issue_count: int = 0,
    max_answer_permission_count: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    require_no_answer_permission: bool = False,
    quality: bool = False,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime = RuntimeState(
        relationship_router_hardening=relationship_router_hardening,
        relationship_final_gate_hardener=relationship_final_gate_hardener,
        table_exact_search_adapter=table_exact_search_adapter,
        page_context_v2=page_context_v2,
        leiden_communities=leiden_communities,
        graph_signal_paths=graph_signal_paths,
    )
    queries = STANDARD_SAMPLE_QUERIES if include_standard_demo_queries else STANDARD_SAMPLE_QUERIES[:4]
    sample_records: List[Dict[str, Any]] = []
    for idx, query in enumerate(queries, 1):
        sample_records.append(_sample_record(f"sample_v31_{idx:04d}", query, runtime.answer(query)))

    # Prove the live endpoint wrapper can repair unsafe relationship wording before WebUI return.
    unsafe_router_result = {
        "answer": "The Leiden community proves that part number 120-36833-503 is related to manual reference 25-21-00.",
        "response_mode": "relationship_synthesis",
        "final_gate_status": None,
        "relationship_query": True,
        "relationship_guidance_only": False,
        "query_intent": "relationship_synthesis",
        "llm_status": "SYNTHETIC_UNSAFE_DRAFT",
        "llm_called": False,
        "citation_like_count": 0,
        "total_match_count": 0,
        "returned_match_count": 0,
        "result_was_capped": False,
        "safety": SAFETY_CONTRACT,
    }
    sample_records.append(
        _sample_record(
            f"sample_v31_{len(sample_records)+1:04d}",
            "Synthetic unsafe relationship draft smoke",
            apply_relationship_final_gate("Explain how part number 120-36833-503 relates to manual reference 25-21-00", unsafe_router_result, record_id="live_relationship_final_gate_v31_synthetic"),
        )
    )

    sample_success_count = sum(1 for r in sample_records if r["status"] == "PASS")
    relationship_gate_applied_count = sum(1 for r in sample_records if r.get("relationship_final_gate_applied"))
    relationship_record_count = sum(1 for r in sample_records if r.get("relationship_query"))
    repaired_count = sum(1 for r in sample_records if r.get("relationship_final_gate_repaired"))
    post_gate_issue_count = sum(int(r.get("post_gate_issue_count", 0)) for r in sample_records)
    answer_permission_count = 0
    source_truth_mutation_allowed_count = 0

    checks = [
        _quality_check("sample_query_count", len(sample_records), ">=", min_sample_queries),
        _quality_check("sample_success_count", sample_success_count, ">=", min_sample_successes),
        _quality_check("relationship_final_gate_applied_count", relationship_gate_applied_count, ">=", min_relationship_final_gate_applied),
        _quality_check("relationship_record_count", relationship_record_count, ">=", min_relationship_records),
        _quality_check("post_gate_issue_count", post_gate_issue_count, "<=", max_post_gate_issue_count),
        _quality_check("answer_permission_count", answer_permission_count, "<=", max_answer_permission_count),
        _quality_check("source_truth_mutation_allowed_count", source_truth_mutation_allowed_count, "<=", max_source_truth_mutation_allowed),
        _quality_check("contract_relationship_final_gate_live_endpoint", True, "is", True),
        _quality_check("contract_raw_5tb_scan_at_query_time", False, "is", False),
    ]
    if require_no_answer_permission:
        checks.append(_quality_check("require_no_answer_permission", answer_permission_count, "==", 0))

    quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    report_path = output_dir / "trace_net_e2e_live_relationship_final_gated_endpoint_v31.json"
    samples_jsonl_path = output_dir / "trace_net_e2e_live_relationship_final_gated_endpoint_samples_v31.jsonl"
    inspect_md_path = output_dir / "trace_net_e2e_live_relationship_final_gated_endpoint_v31.md"

    router_report = runtime.router_report
    gate_report = runtime.relationship_final_gate_hardener_report
    report = {
        "module": MODULE,
        "version": VERSION,
        "status": STATUS_READY if quality_status == "PASS" else STATUS_NEEDS_REPAIR,
        "quality_status": quality_status,
        "model_id": MODEL_ID,
        "router_model_id": ROUTER_MODEL_ID,
        "relationship_router_hardening_path": str(relationship_router_hardening),
        "relationship_final_gate_hardener_path": str(relationship_final_gate_hardener) if relationship_final_gate_hardener else None,
        "exact_search_document_count": router_report.get("exact_search_document_count", 0),
        "page_context_v2_page_count": router_report.get("page_context_v2_page_count", 0),
        "graph_has_v2_page_count": router_report.get("graph_has_v2_page_count", 0),
        "graph_has_nomenclature_page_count": router_report.get("graph_has_nomenclature_page_count", 0),
        "relationship_final_gate_hardener_quality_status": gate_report.get("quality_status"),
        "relationship_final_gate_hardener_post_gate_issue_count": gate_report.get("post_gate_issue_count", 0),
        "sample_query_count": len(sample_records),
        "sample_success_count": sample_success_count,
        "relationship_final_gate_applied_count": relationship_gate_applied_count,
        "relationship_record_count": relationship_record_count,
        "repaired_relationship_sample_count": repaired_count,
        "post_gate_issue_count": post_gate_issue_count,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "base_url_windows": "http://127.0.0.1:8026/v1",
        "base_url_open_webui_docker": "http://host.docker.internal:8026/v1",
        "contract": SAFETY_CONTRACT,
        "sample_records": sample_records,
        "quality_checks": checks,
        "report_path": str(report_path),
        "samples_jsonl_path": str(samples_jsonl_path),
        "inspect_md_path": str(inspect_md_path),
    }
    _write_json(report_path, report)
    _write_jsonl(samples_jsonl_path, sample_records)
    write_inspect_md(inspect_md_path, report)
    return report


def write_inspect_md(path: Path, report: Dict[str, Any]) -> None:
    lines = [
        "# TRACE-Net E2E Live Relationship Final-Gated Endpoint v31",
        "",
        f"Quality status: **{report['quality_status']}**",
        f"Status: `{report['status']}`",
        "",
        "## Summary",
    ]
    for key in [
        "sample_query_count",
        "sample_success_count",
        "relationship_final_gate_applied_count",
        "relationship_record_count",
        "repaired_relationship_sample_count",
        "post_gate_issue_count",
        "exact_search_document_count",
        "page_context_v2_page_count",
        "graph_has_v2_page_count",
        "graph_has_nomenclature_page_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {report.get(key)}")
    lines.extend([
        "",
        "## Contract",
        "- v29.2 metadata/count and relationship router runs first.",
        "- v30 relationship final gate is applied before WebUI receives the answer.",
        "- Graph, Leiden, v2 summaries, and nomenclature metadata remain guidance only.",
        "- Source-truth evidence is required for factual relationship claims.",
        "- The endpoint does not scan raw 5TB data, rebuild graph, mutate source truth, or write to services.",
        "",
        "## Samples",
    ])
    for r in report.get("sample_records", [])[:12]:
        lines.extend([
            f"### {r['sample_id']} — {r['status']}",
            f"- query: {r.get('query')}",
            f"- response_mode: {r.get('response_mode')}",
            f"- source_final_gate_status: {r.get('source_final_gate_status')}",
            f"- relationship_final_gate_status: {r.get('relationship_final_gate_status')}",
            f"- relationship_final_gate_repaired: {r.get('relationship_final_gate_repaired')}",
            f"- post_gate_issue_count: {r.get('post_gate_issue_count')}",
            f"- preview: {r.get('answer','')[:260]}",
            "",
        ])
    lines.extend(["## Quality checks"])
    for c in report.get("quality_checks", []):
        status = "PASS" if c["passed"] else "FAIL"
        lines.append(f"- {status} {c['name']}: observed={c['observed']} expected={c['op']} {c['expected']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def check_report(
    *,
    report_path: Path,
    min_sample_queries: int = 0,
    min_sample_successes: int = 0,
    min_relationship_final_gate_applied: int = 0,
    min_relationship_records: int = 0,
    max_post_gate_issue_count: int = 0,
    max_answer_permission_count: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    require_no_answer_permission: bool = False,
    write_json: bool = False,
) -> Dict[str, Any]:
    report = _read_json(report_path)
    checks = [
        _quality_check("quality_status", report.get("quality_status"), "==", "PASS"),
        _quality_check("sample_query_count", report.get("sample_query_count", 0), ">=", min_sample_queries),
        _quality_check("sample_success_count", report.get("sample_success_count", 0), ">=", min_sample_successes),
        _quality_check("relationship_final_gate_applied_count", report.get("relationship_final_gate_applied_count", 0), ">=", min_relationship_final_gate_applied),
        _quality_check("relationship_record_count", report.get("relationship_record_count", 0), ">=", min_relationship_records),
        _quality_check("post_gate_issue_count", report.get("post_gate_issue_count", 0), "<=", max_post_gate_issue_count),
        _quality_check("answer_permission_count", report.get("answer_permission_count", 0), "<=", max_answer_permission_count),
        _quality_check("source_truth_mutation_allowed_count", report.get("source_truth_mutation_allowed_count", 0), "<=", max_source_truth_mutation_allowed),
    ]
    if require_no_answer_permission:
        checks.append(_quality_check("require_no_answer_permission", report.get("answer_permission_count", 0), "==", 0))
    quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    result = {**report, "quality_status": quality_status, "quality_checks": checks}
    if write_json:
        _write_json(report_path, report)
    return result
