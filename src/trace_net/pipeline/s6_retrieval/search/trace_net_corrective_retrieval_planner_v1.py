"""TRACE-Net Corrective Retrieval Planner v1.

A read-only CRAG-style planner for TRACE-Net artifacts.

The planner does not retrieve, index, write to external services, or answer. It
reads existing retrieval/evidence/audit artifacts and emits corrective routing
records such as exact-search expansion, graph-path expansion, reranking, visual
review, or final-gate use.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

SCHEMA_VERSION = "trace_net_corrective_retrieval_planner_v1"
STATUS_BUILT = "CORRECTIVE_RETRIEVAL_PLAN_BUILT"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"
QUALITY_UNKNOWN = "UNKNOWN"

ANSWER_FORBIDDEN_FIELDS = (
    "can_answer_directly",
    "can_prove_claims",
    "answer_capable",
    "claim_proof_allowed",
    "source_truth_mutation_allowed",
)

SAFE_BASE_CONTRACT = {
    "retrieval_only": True,
    "can_answer_directly": False,
    "can_prove_claims": False,
    "source_truth_mutation_allowed": False,
    "postgres_write_attempt": False,
    "qdrant_write_attempt": False,
    "opensearch_write_attempt": False,
}

HARD_ZERO_SUMMARY_FIELDS = (
    "unsafe_correction_record_count",
    "answer_permission_count",
    "source_truth_mutation_allowed_count",
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
    "opensearch_write_attempt_count",
    "can_answer_directly_count",
    "can_prove_claims_count",
    "retrieval_only_answer_allowed_count",
    "community_as_proof_count",
    "category_as_proof_count",
)


@dataclass(frozen=True)
class Thresholds:
    min_correction_records: int = 0
    min_diagnostic_records: int = 0
    min_safe_action_records: int = 0
    min_review_routed_records: int = 0
    max_unsafe_correction_records: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_no_answer_permission: bool = False
    require_page_eval_quality_pass: bool = False
    require_ai_trace_quality_pass: bool = False
    require_graph_enrichment_quality_pass: bool = False
    require_opensearch_loader_quality_pass: bool = False
    require_qdrant_quality_pass: bool = False
    require_tiff_audit_quality_pass: bool = False


def load_json(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing JSON input: {p}")
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str | Path, payload: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: str | Path, records: Iterable[Dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


def get_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("summary") if isinstance(payload.get("summary"), dict) else {}


def _upper_status(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    status = value.strip().upper()
    return status or None


def _explicit_quality(value: Any) -> Optional[str]:
    status = _upper_status(value)
    if status in {QUALITY_PASS, QUALITY_FAIL, QUALITY_UNKNOWN}:
        return status
    return None


def _number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _lookup(payload: Dict[str, Any], key: str) -> Any:
    if key in payload:
        return payload.get(key)
    summary = get_summary(payload)
    return summary.get(key)


def _summary_counter_zero(payload: Dict[str, Any], *keys: str) -> bool:
    for key in keys:
        value = _lookup(payload, key)
        n = _number(value)
        if n is not None and n != 0:
            return False
    return True


def normalize_qdrant_page_profile_quality(payload: Dict[str, Any]) -> str:
    """Normalize old and new Qdrant page-profile quality artifact shapes.

    Historical Qdrant page-profile artifacts in this repo have appeared as
    quality reports, manifests, and summary-only JSON objects. Some old shapes
    carried a non-quality status such as a build/manifest status while the PASS
    signal lived under `summary`, `profile_quality_status`, or in coherent point
    counts. This normalizer intentionally accepts those safe PASS shapes while
    still failing explicit FAILs or unsafe/nonzero counters.
    """
    summary = get_summary(payload)

    # Explicit FAIL always wins when it appears in quality-bearing fields.
    for key in (
        "quality_status",
        "qdrant_quality_status",
        "profile_quality_status",
        "page_profile_quality_status",
        "adapter_quality_status",
    ):
        for container in (payload, summary):
            explicit = _explicit_quality(container.get(key))
            if explicit == QUALITY_FAIL:
                return QUALITY_FAIL

    # Top-level/summary `status` may be a literal PASS/FAIL in older reports.
    for container in (payload, summary):
        explicit = _explicit_quality(container.get("status"))
        if explicit == QUALITY_FAIL:
            return QUALITY_FAIL

    if not _summary_counter_zero(
        payload,
        "unsafe_point_count",
        "unsafe_payload_count",
        "unsafe_record_count",
        "rejected_count",
        "source_truth_mutation_allowed_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "retrieval_only_answer_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        return QUALITY_FAIL

    # Any explicit PASS in quality-bearing fields is enough once unsafe counters
    # are clean. This handles newer quality JSONs and summary-only reports.
    for key in (
        "quality_status",
        "qdrant_quality_status",
        "profile_quality_status",
        "page_profile_quality_status",
        "adapter_quality_status",
        "status",
    ):
        for container in (payload, summary):
            explicit = _explicit_quality(container.get(key))
            if explicit == QUALITY_PASS:
                return QUALITY_PASS

    # Count-based fallback for manifest-like Qdrant reports.
    loaded = (
        _number(_lookup(payload, "loaded_point_count"))
        or _number(_lookup(payload, "point_count"))
        or _number(_lookup(payload, "points_loaded"))
    )
    qdrant_count = _number(_lookup(payload, "qdrant_count"))
    page_count = _number(_lookup(payload, "page_count")) or _number(_lookup(payload, "pages_with_points"))
    source_trace_count = _number(_lookup(payload, "source_trace_point_count"))
    context_count = _number(_lookup(payload, "context_v2_point_count"))

    if loaded and loaded > 0:
        counts_match = True
        if qdrant_count is not None:
            counts_match = counts_match and qdrant_count == loaded
        if page_count is not None:
            counts_match = counts_match and page_count > 0
        if source_trace_count is not None:
            counts_match = counts_match and source_trace_count > 0
        if context_count is not None:
            counts_match = counts_match and context_count >= 0
        if counts_match:
            return QUALITY_PASS

    return QUALITY_UNKNOWN


def get_quality_status(payload: Dict[str, Any], *, artifact_name: Optional[str] = None) -> str:
    if artifact_name == "qdrant_page_profile_quality":
        return normalize_qdrant_page_profile_quality(payload)

    status = _explicit_quality(payload.get("quality_status"))
    if status:
        return status
    summary = get_summary(payload)
    status = _explicit_quality(summary.get("quality_status")) or _explicit_quality(summary.get("status"))
    return status if status else QUALITY_UNKNOWN


def get_status(payload: Dict[str, Any]) -> str:
    status = payload.get("status")
    if isinstance(status, str):
        return status
    summary = get_summary(payload)
    status = summary.get("status")
    return status if isinstance(status, str) else QUALITY_UNKNOWN


def norm_id(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[^a-zA-Z0-9_.:-]+", "_", str(value)).strip("_")[:180]


def safe_bool(value: Any) -> bool:
    return bool(value) if value is not None else False


def maybe_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def contract() -> Dict[str, Any]:
    return dict(SAFE_BASE_CONTRACT)


def make_record(
    *,
    source_module: str,
    source_record_id: str,
    issue_type: str,
    severity: str,
    recommended_actions: Sequence[str],
    rationale: str,
    query_id: Optional[str] = None,
    query: Optional[str] = None,
    page_id: Optional[str] = None,
    channels: Optional[Sequence[str]] = None,
    review_reason_codes: Optional[Sequence[str]] = None,
    source_status: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    actions = list(dict.fromkeys(str(a) for a in recommended_actions if a))
    review_reasons = list(dict.fromkeys(str(a) for a in (review_reason_codes or []) if a))
    record_id = "::".join(
        [
            "corrective_retrieval",
            norm_id(source_module),
            norm_id(query_id or page_id or source_record_id or issue_type),
            norm_id(issue_type),
        ]
    )
    is_review = any("review" in a or "audit" in a for a in actions + review_reasons)
    return {
        "record_id": record_id,
        "schema_version": SCHEMA_VERSION,
        "source_module": source_module,
        "source_record_id": source_record_id,
        "source_status": source_status,
        "query_id": query_id,
        "query": query,
        "page_id": page_id,
        "issue_type": issue_type,
        "severity": severity,
        "correction_status": "CORRECTION_ROUTED_TO_REVIEW" if is_review else "CORRECTION_ROUTED",
        "recommended_actions": actions,
        "recommended_primary_action": actions[0] if actions else None,
        "review_reason_codes": review_reasons,
        "evidence_channels": list(channels or []),
        "rationale": rationale,
        "metadata": metadata or {},
        "safety_contract": contract(),
        "retrieval_only": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }


def collect_from_page_eval(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    records = payload.get("query_records") or payload.get("records") or []
    if not isinstance(records, list):
        records = []
    out: List[Dict[str, Any]] = []
    source_status = get_quality_status(payload)
    for r in records:
        if not isinstance(r, dict):
            continue
        evaluated = safe_bool(r.get("evaluated"))
        page_id = r.get("page_id")
        query_id = r.get("query_id") or page_id
        query = r.get("semantic_retrieval_query") or r.get("llm_question") or r.get("query")
        blank_expected = safe_bool(r.get("blank_expected"))
        target_rank = r.get("target_rank")
        target_hit_at_k = safe_bool(r.get("target_hit_at_k"))
        target_hit_at_1 = bool(target_rank == 1)
        query_type = r.get("query_type")
        route = r.get("retrieval_route")
        graph_path_resolved = r.get("graph_path_resolved")
        if evaluated and not target_hit_at_k:
            out.append(
                make_record(
                    source_module="page_retrieval_large_eval_v2",
                    source_record_id=str(r.get("record_id") or query_id),
                    query_id=str(query_id) if query_id else None,
                    query=str(query) if query else None,
                    page_id=str(page_id) if page_id else None,
                    issue_type="semantic_page_target_miss",
                    severity="HIGH",
                    recommended_actions=[
                        "rerank_with_graph_page_anchor",
                        "expand_graph_source_path",
                        "run_opensearch_exact_if_identifier_present",
                        "mark_result_audit_required_until_corrected",
                    ],
                    rationale="BGE-M3 semantic retrieval did not return the target page in top-k; use graph/source anchors and exact search correction before downstream answering.",
                    channels=["qdrant_bge_m3", "graph_path"],
                    review_reason_codes=["semantic_page_target_miss"],
                    source_status=source_status,
                    metadata={
                        "target_rank": target_rank,
                        "top_k": len(r.get("top_hits") or []),
                        "query_type": query_type,
                        "retrieval_route": route,
                        "graph_path_resolved": graph_path_resolved,
                    },
                )
            )
        elif evaluated and not target_hit_at_1 and target_rank is not None and int(target_rank) > 5:
            actions = ["apply_graph_anchor_rerank", "retain_top_k_for_review"]
            if blank_expected:
                actions.insert(0, "apply_blank_page_exact_page_rerank")
            out.append(
                make_record(
                    source_module="page_retrieval_large_eval_v2",
                    source_record_id=str(r.get("record_id") or query_id),
                    query_id=str(query_id) if query_id else None,
                    query=str(query) if query else None,
                    page_id=str(page_id) if page_id else None,
                    issue_type="target_page_low_rank",
                    severity="MEDIUM",
                    recommended_actions=actions,
                    rationale="Target page was found but ranked low; correct with page/source path anchoring before presenting ranked evidence.",
                    channels=["qdrant_bge_m3", "graph_path"],
                    review_reason_codes=["low_rank_semantic_hit"],
                    source_status=source_status,
                    metadata={
                        "target_rank": target_rank,
                        "blank_expected": blank_expected,
                        "query_type": query_type,
                        "retrieval_route": route,
                    },
                )
            )
    return out


def collect_from_ai_trace(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    packs = payload.get("trace_pack_records") or payload.get("records") or []
    if not isinstance(packs, list):
        packs = []
    out: List[Dict[str, Any]] = []
    source_status = get_quality_status(payload)
    for p in packs:
        if not isinstance(p, dict):
            continue
        needs_review = safe_bool(p.get("needs_review")) or str(p.get("trace_status", "")).endswith("REVIEW_RECOMMENDED")
        query_id = p.get("query_id")
        query = p.get("query")
        trace_status = p.get("trace_status")
        reason_codes = [str(x) for x in maybe_list(p.get("review_reason_codes"))]
        channels: List[str] = []
        graph_summary = p.get("graph_trace_summary") or {}
        if isinstance(graph_summary, dict):
            channels.extend((graph_summary.get("channel_counts") or {}).keys())
        retrieval_summary = p.get("retrieval_summary") or {}
        if isinstance(retrieval_summary, dict) and retrieval_summary.get("hybrid_query_present"):
            channels.append("hybrid_v2")
        if p.get("source_trace_summary"):
            channels.append("dublin_core_source_identity")
        if p.get("leiden_navigation_summary"):
            channels.append("leiden_navigation")
        if p.get("claim_evidence_summary"):
            channels.append("claim_evidence_entailment")
        if needs_review:
            actions: List[str] = []
            if "retrieval_critic_audit" in reason_codes:
                actions.extend(["run_corrective_retrieval_expansion", "compare_semantic_vs_exact_channels"])
            if "claim_evidence_review" in reason_codes or "page_alignment_review" in reason_codes:
                actions.extend(["run_claim_evidence_alignment_review", "require_human_review_before_final_answer"])
            if "graph_evidence_review_flags" in reason_codes:
                actions.append("expand_graph_evidence_enrichment")
            if not actions:
                actions.append("route_to_human_review")
            out.append(
                make_record(
                    source_module="ai_trace_pack",
                    source_record_id=str(p.get("trace_pack_id") or query_id),
                    query_id=str(query_id) if query_id else None,
                    query=str(query) if query else None,
                    issue_type="trace_pack_review_recommended",
                    severity="HIGH" if any("claim" in x or "alignment" in x for x in reason_codes) else "MEDIUM",
                    recommended_actions=actions,
                    rationale="AI trace pack requires review; apply corrective retrieval/evidence routing before final return.",
                    channels=list(dict.fromkeys(str(c) for c in channels)),
                    review_reason_codes=reason_codes,
                    source_status=source_status,
                    metadata={
                        "trace_status": trace_status,
                        "page_ids": p.get("page_ids") or [],
                        "critic_summary": p.get("critic_summary") or {},
                        "claim_evidence_summary": p.get("claim_evidence_summary") or {},
                    },
                )
            )
        elif trace_status == "TRACE_PACK_FINAL_GATE_AUTHORIZED_NO_REVIEW_FLAGS":
            out.append(
                make_record(
                    source_module="ai_trace_pack",
                    source_record_id=str(p.get("trace_pack_id") or query_id),
                    query_id=str(query_id) if query_id else None,
                    query=str(query) if query else None,
                    issue_type="trace_pack_safe_to_use_final_gate_path",
                    severity="INFO",
                    recommended_actions=["use_final_gate_authorized_answer_path"],
                    rationale="Trace pack is already final-gate authorized with no review flags; no corrective retrieval needed.",
                    channels=list(dict.fromkeys(str(c) for c in channels)),
                    source_status=source_status,
                    metadata={"trace_status": trace_status, "page_ids": p.get("page_ids") or []},
                )
            )
    return out


def collect_from_graph_enrichment(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    reviews = payload.get("review_records") or []
    if not isinstance(reviews, list):
        reviews = []
    out: List[Dict[str, Any]] = []
    source_status = get_quality_status(payload)
    for idx, r in enumerate(reviews):
        if not isinstance(r, dict):
            continue
        query_id = r.get("query_id") or r.get("plan_id")
        page_id = r.get("page_id")
        reason_codes = [str(x) for x in maybe_list(r.get("reason_codes") or r.get("review_reason_codes") or r.get("flags"))]
        out.append(
            make_record(
                source_module="graph_query_evidence_enrichment",
                source_record_id=str(r.get("record_id") or f"review_{idx:04d}"),
                query_id=str(query_id) if query_id else None,
                page_id=str(page_id) if page_id else None,
                issue_type="graph_evidence_review_flag",
                severity="MEDIUM",
                recommended_actions=["expand_bounded_graph_path", "verify_dublin_core_source_identity", "route_to_review_if_still_flagged"],
                rationale="Graph enrichment emitted a review flag; use bounded graph expansion and source identity verification before final answer use.",
                channels=["graph_query_evidence_enrichment"],
                review_reason_codes=reason_codes,
                source_status=source_status,
                metadata={"review_record": r},
            )
        )
    return out


def collect_from_tiff_audit(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    records = payload.get("content_audit_records") or []
    if not isinstance(records, list):
        records = []
    out: List[Dict[str, Any]] = []
    source_status = get_quality_status(payload)
    for r in records:
        if not isinstance(r, dict):
            continue
        status = r.get("content_audit_status")
        if status == QUALITY_PASS:
            continue
        page_id = r.get("page_id")
        reason_codes = [str(x) for x in maybe_list(r.get("heuristic_flags") or r.get("vision_flags") or r.get("validation_flags"))]
        severity = "HIGH" if status == QUALITY_FAIL else "MEDIUM"
        actions = ["route_to_tiff_content_review", "run_or_expand_vision_audit_sample"]
        if r.get("blank_expected"):
            actions.insert(0, "verify_blank_page_with_image_metrics")
        out.append(
            make_record(
                source_module="page_query_response_tiff_content_audit",
                source_record_id=str(r.get("record_id") or page_id),
                page_id=str(page_id) if page_id else None,
                query=str(r.get("question")) if r.get("question") else None,
                issue_type="tiff_content_audit_review",
                severity=severity,
                recommended_actions=actions,
                rationale="TIFF content audit recommended review; do not promote this response until visual/content review clears.",
                channels=["tiff_image_heuristic", "ollama_vision" if r.get("vision_evaluated") else "image_metrics"],
                review_reason_codes=reason_codes,
                source_status=source_status,
                metadata={
                    "content_audit_status": status,
                    "vision_verdict": r.get("vision_verdict"),
                    "heuristic_content_status": r.get("heuristic_content_status"),
                    "source_entry": r.get("source_entry_name_used"),
                },
            )
        )
    return out


def make_source_artifact_record(name: str, path: Optional[str], payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if payload is None:
        return {"name": name, "path": path, "loaded": False, "quality_status": None, "status": None}
    return {
        "name": name,
        "path": path,
        "loaded": True,
        "quality_status": get_quality_status(payload, artifact_name=name),
        "status": get_status(payload),
        "summary": get_summary(payload),
    }


def validate_record_safety(record: Dict[str, Any]) -> List[str]:
    flags: List[str] = []
    for field in ANSWER_FORBIDDEN_FIELDS:
        if safe_bool(record.get(field)):
            flags.append(f"unsafe_field:{field}")
    sc = record.get("safety_contract") or {}
    if isinstance(sc, dict):
        for field in ("can_answer_directly", "can_prove_claims", "source_truth_mutation_allowed"):
            if safe_bool(sc.get(field)):
                flags.append(f"unsafe_contract:{field}")
    for action in record.get("recommended_actions") or []:
        action_l = str(action).lower()
        if "direct_answer" in action_l or "prove_claim" in action_l or "mutate_source" in action_l:
            flags.append(f"unsafe_action:{action}")
    return flags


def compute_summary(records: List[Dict[str, Any]], source_artifacts: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    action_counter: Counter[str] = Counter()
    issue_counter: Counter[str] = Counter()
    severity_counter: Counter[str] = Counter()
    source_counter: Counter[str] = Counter()
    review_routed_count = 0
    unsafe_count = 0
    answer_permission_count = 0
    source_truth_mutation_allowed_count = 0
    safe_action_records = 0
    for record in records:
        actions = [str(a) for a in (record.get("recommended_actions") or [])]
        action_counter.update(actions)
        issue_counter[record.get("issue_type") or "unknown"] += 1
        severity_counter[record.get("severity") or "unknown"] += 1
        source_counter[record.get("source_module") or "unknown"] += 1
        if any("review" in a or "audit" in a for a in actions + [str(x) for x in (record.get("review_reason_codes") or [])]):
            review_routed_count += 1
        if actions:
            safe_action_records += 1
        flags = validate_record_safety(record)
        if flags:
            unsafe_count += 1
        if safe_bool(record.get("can_answer_directly")) or safe_bool(record.get("can_prove_claims")):
            answer_permission_count += 1
        if safe_bool(record.get("source_truth_mutation_allowed")):
            source_truth_mutation_allowed_count += 1
    loaded_source_quality = {
        name: artifact.get("quality_status") for name, artifact in source_artifacts.items() if artifact.get("loaded")
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "correction_record_count": len(records),
        "diagnostic_record_count": len(records),
        "safe_action_record_count": safe_action_records,
        "review_routed_record_count": review_routed_count,
        "unsafe_correction_record_count": unsafe_count,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "issue_type_counts": dict(sorted(issue_counter.items())),
        "severity_counts": dict(sorted(severity_counter.items())),
        "source_module_counts": dict(sorted(source_counter.items())),
        "recommended_action_counts": dict(sorted(action_counter.items())),
        "source_quality_statuses": loaded_source_quality,
        "source_artifact_count": len([a for a in source_artifacts.values() if a.get("loaded")]),
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "retrieval_only_answer_allowed_count": 0,
        "community_as_proof_count": 0,
        "category_as_proof_count": 0,
    }


def build_quality_checks(summary: Dict[str, Any], source_artifacts: Dict[str, Dict[str, Any]], thresholds: Thresholds) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"check_name": name, "passed": bool(ok), "detail": detail})

    add("correction_record_count", summary.get("correction_record_count", 0) >= thresholds.min_correction_records, f"records={summary.get('correction_record_count', 0)}; minimum={thresholds.min_correction_records}")
    add("diagnostic_record_count", summary.get("diagnostic_record_count", 0) >= thresholds.min_diagnostic_records, f"records={summary.get('diagnostic_record_count', 0)}; minimum={thresholds.min_diagnostic_records}")
    add("safe_action_record_count", summary.get("safe_action_record_count", 0) >= thresholds.min_safe_action_records, f"records={summary.get('safe_action_record_count', 0)}; minimum={thresholds.min_safe_action_records}")
    add("review_routed_record_count", summary.get("review_routed_record_count", 0) >= thresholds.min_review_routed_records, f"records={summary.get('review_routed_record_count', 0)}; minimum={thresholds.min_review_routed_records}")
    add("unsafe_correction_record_count", summary.get("unsafe_correction_record_count", 0) <= thresholds.max_unsafe_correction_records, f"unsafe={summary.get('unsafe_correction_record_count', 0)}; max={thresholds.max_unsafe_correction_records}")
    add("answer_permission_count", summary.get("answer_permission_count", 0) <= thresholds.max_answer_permission_count, f"answer_permission={summary.get('answer_permission_count', 0)}; max={thresholds.max_answer_permission_count}")
    add("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count", 0) <= thresholds.max_source_truth_mutation_allowed, f"mutations={summary.get('source_truth_mutation_allowed_count', 0)}; max={thresholds.max_source_truth_mutation_allowed}")
    add("write_attempts", summary.get("postgres_write_attempt_count", 0) == 0 and summary.get("qdrant_write_attempt_count", 0) == 0 and summary.get("opensearch_write_attempt_count", 0) == 0, "postgres/qdrant/opensearch write attempts must all be 0")
    if thresholds.require_no_answer_permission:
        add("no_answer_permission", summary.get("can_answer_directly_count", 0) == 0 and summary.get("can_prove_claims_count", 0) == 0 and summary.get("retrieval_only_answer_allowed_count", 0) == 0, "planner must not grant direct answer/proof/retrieval-only answer permission")
    source_requirements = {
        "page_retrieval_large_eval_v2": thresholds.require_page_eval_quality_pass,
        "ai_trace_pack": thresholds.require_ai_trace_quality_pass,
        "graph_query_evidence_enrichment": thresholds.require_graph_enrichment_quality_pass,
        "opensearch_loader_smoke": thresholds.require_opensearch_loader_quality_pass,
        "qdrant_page_profile_quality": thresholds.require_qdrant_quality_pass,
        "page_query_response_tiff_content_audit": thresholds.require_tiff_audit_quality_pass,
    }
    for name, required in source_requirements.items():
        if required:
            artifact = source_artifacts.get(name) or {}
            ok = artifact.get("loaded") and artifact.get("quality_status") == QUALITY_PASS
            add(f"{name}_quality_pass", ok, f"loaded={artifact.get('loaded')}; quality_status={artifact.get('quality_status')}")
    return checks


def quality_status_from_checks(checks: Sequence[Dict[str, Any]]) -> str:
    return QUALITY_PASS if all(c.get("passed") for c in checks) else QUALITY_FAIL


def build_corrective_retrieval_plan(
    *,
    output_dir: str | Path,
    thresholds: Thresholds,
    page_retrieval_large_eval_v2: Optional[str] = None,
    ai_trace_pack: Optional[str] = None,
    graph_query_evidence_enrichment: Optional[str] = None,
    opensearch_loader_smoke: Optional[str] = None,
    qdrant_page_profile_quality: Optional[str] = None,
    page_query_response_tiff_content_audit: Optional[str] = None,
    write_outputs: bool = True,
) -> Dict[str, Any]:
    output = Path(output_dir)
    source_artifacts: Dict[str, Dict[str, Any]] = {}
    all_records: List[Dict[str, Any]] = []

    def read_optional(name: str, path: Optional[str]) -> Optional[Dict[str, Any]]:
        if not path:
            source_artifacts[name] = make_source_artifact_record(name, None, None)
            return None
        payload = load_json(path)
        source_artifacts[name] = make_source_artifact_record(name, path, payload)
        return payload

    page_eval = read_optional("page_retrieval_large_eval_v2", page_retrieval_large_eval_v2)
    if page_eval:
        all_records.extend(collect_from_page_eval(page_eval))
    ai_trace = read_optional("ai_trace_pack", ai_trace_pack)
    if ai_trace:
        all_records.extend(collect_from_ai_trace(ai_trace))
    graph_enrichment = read_optional("graph_query_evidence_enrichment", graph_query_evidence_enrichment)
    if graph_enrichment:
        all_records.extend(collect_from_graph_enrichment(graph_enrichment))

    opensearch_payload = read_optional("opensearch_loader_smoke", opensearch_loader_smoke)
    if opensearch_payload:
        os_summary = get_summary(opensearch_payload)
        os_quality = get_quality_status(opensearch_payload)
        if os_quality == QUALITY_PASS:
            all_records.append(
                make_record(
                    source_module="opensearch_loader_smoke",
                    source_record_id="opensearch_exact_search_available",
                    issue_type="exact_search_channel_available",
                    severity="INFO",
                    recommended_actions=["use_opensearch_exact_for_identifiers", "use_opensearch_table_cell_for_part_cells"],
                    rationale="OpenSearch loader smoke is ready; CRAG correction can route exact identifiers and table cells to this exact-search channel.",
                    channels=["opensearch_exact"],
                    source_status=os_quality,
                    metadata={"opensearch_document_count": os_summary.get("opensearch_document_count"), "query_plan_count": os_summary.get("query_plan_count")},
                )
            )
        else:
            all_records.append(
                make_record(
                    source_module="opensearch_loader_smoke",
                    source_record_id="opensearch_exact_search_unavailable",
                    issue_type="exact_search_channel_unavailable",
                    severity="HIGH",
                    recommended_actions=["do_not_route_exact_queries_to_opensearch", "repair_opensearch_loader_before_exact_correction"],
                    rationale="OpenSearch exact-search channel did not pass quality; CRAG correction must not rely on it yet.",
                    channels=["opensearch_exact"],
                    review_reason_codes=["opensearch_quality_not_pass"],
                    source_status=os_quality,
                )
            )

    qdrant_payload = read_optional("qdrant_page_profile_quality", qdrant_page_profile_quality)
    if qdrant_payload:
        q_summary = get_summary(qdrant_payload)
        q_quality = get_quality_status(qdrant_payload, artifact_name="qdrant_page_profile_quality")
        if q_quality == QUALITY_PASS:
            all_records.append(
                make_record(
                    source_module="qdrant_page_profile_quality",
                    source_record_id="semantic_search_channel_available",
                    issue_type="semantic_search_channel_available",
                    severity="INFO",
                    recommended_actions=["use_qdrant_bge_m3_for_semantic_candidates", "rerank_with_graph_source_anchors"],
                    rationale="Qdrant BGE-M3 page-profile collection passed quality; use it for semantic candidates but still source-resolve and final-gate results.",
                    channels=["qdrant_bge_m3"],
                    source_status=q_quality,
                    metadata={
                        "point_count": q_summary.get("point_count") or q_summary.get("loaded_point_count") or qdrant_payload.get("loaded_point_count") or qdrant_payload.get("point_count"),
                        "context_v2_point_count": q_summary.get("context_v2_point_count") or qdrant_payload.get("context_v2_point_count"),
                    },
                )
            )

    tiff_audit = read_optional("page_query_response_tiff_content_audit", page_query_response_tiff_content_audit)
    if tiff_audit:
        all_records.extend(collect_from_tiff_audit(tiff_audit))

    seen = set()
    records: List[Dict[str, Any]] = []
    for record in all_records:
        rid = record.get("record_id")
        if rid in seen:
            continue
        seen.add(rid)
        records.append(record)

    summary = compute_summary(records, source_artifacts)
    checks = build_quality_checks(summary, source_artifacts, thresholds)
    quality_status = quality_status_from_checks(checks)
    summary["quality_status"] = quality_status
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "summary": summary,
        "source_artifacts": source_artifacts,
        "quality_checks": checks,
        "corrective_retrieval_records": records,
        "diagnostic_records": records,
    }
    if write_outputs:
        output.mkdir(parents=True, exist_ok=True)
        report_path = output / "trace_net_corrective_retrieval_planner_v1.json"
        quality_path = output / "trace_net_corrective_retrieval_planner_v1_quality.json"
        records_path = output / "trace_net_corrective_retrieval_planner_v1_records.jsonl"
        summary_md_path = output / "trace_net_corrective_retrieval_planner_v1_summary.md"
        payload["report_path"] = str(report_path)
        payload["quality_path"] = str(quality_path)
        payload["records_path"] = str(records_path)
        payload["summary_markdown_path"] = str(summary_md_path)
        write_json(report_path, payload)
        write_json(quality_path, {k: payload[k] for k in ["schema_version", "status", "quality_status", "summary", "quality_checks"]})
        write_jsonl(records_path, records)
        summary_md_path.write_text(render_markdown_summary(payload), encoding="utf-8")
    return payload


def render_markdown_summary(payload: Dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "# TRACE-Net Corrective Retrieval Planner v1",
        "",
        f"Status: `{payload.get('status')}`",
        f"Quality status: `{payload.get('quality_status')}`",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "correction_record_count",
        "safe_action_record_count",
        "review_routed_record_count",
        "unsafe_correction_record_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        lines.append(f"- {key}: `{summary.get(key)}`")
    lines.extend(["", "## Recommended action counts", ""])
    for action, count in (summary.get("recommended_action_counts") or {}).items():
        lines.append(f"- {action}: `{count}`")
    lines.extend([
        "",
        "## Safety contract",
        "",
        "This artifact is read-only and retrieval-only. It does not grant final answer permission, does not prove claims, and does not mutate source truth.",
    ])
    return "\n".join(lines) + "\n"


def check_corrective_retrieval_plan_quality(
    *,
    report_path: str | Path,
    thresholds: Thresholds,
    write_json_report: bool = False,
) -> Dict[str, Any]:
    report = load_json(report_path)
    records = report.get("corrective_retrieval_records") or report.get("records") or report.get("diagnostic_records") or []
    if not isinstance(records, list):
        records = []
    source_artifacts = report.get("source_artifacts") if isinstance(report.get("source_artifacts"), dict) else {}
    summary = compute_summary(records, source_artifacts)
    checks = build_quality_checks(summary, source_artifacts, thresholds)
    quality_status = quality_status_from_checks(checks)
    summary["quality_status"] = quality_status
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": report.get("status") or STATUS_BUILT,
        "quality_status": quality_status,
        "summary": summary,
        "quality_checks": checks,
    }
    if write_json_report:
        out_path = Path(report_path).parent / "trace_net_corrective_retrieval_planner_v1_quality.json"
        write_json(out_path, result)
        result["quality_path"] = str(out_path)
    return result


def _add_threshold_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-correction-records", type=int, default=0)
    parser.add_argument("--min-diagnostic-records", type=int, default=0)
    parser.add_argument("--min-safe-action-records", type=int, default=0)
    parser.add_argument("--min-review-routed-records", type=int, default=0)
    parser.add_argument("--max-unsafe-correction-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-page-eval-quality-pass", action="store_true")
    parser.add_argument("--require-ai-trace-quality-pass", action="store_true")
    parser.add_argument("--require-graph-enrichment-quality-pass", action="store_true")
    parser.add_argument("--require-opensearch-loader-quality-pass", action="store_true")
    parser.add_argument("--require-qdrant-quality-pass", action="store_true")
    parser.add_argument("--require-tiff-audit-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")


def _thresholds_from_args(args: argparse.Namespace) -> Thresholds:
    return Thresholds(
        min_correction_records=args.min_correction_records,
        min_diagnostic_records=args.min_diagnostic_records,
        min_safe_action_records=args.min_safe_action_records,
        min_review_routed_records=args.min_review_routed_records,
        max_unsafe_correction_records=args.max_unsafe_correction_records,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
        require_page_eval_quality_pass=args.require_page_eval_quality_pass,
        require_ai_trace_quality_pass=args.require_ai_trace_quality_pass,
        require_graph_enrichment_quality_pass=args.require_graph_enrichment_quality_pass,
        require_opensearch_loader_quality_pass=args.require_opensearch_loader_quality_pass,
        require_qdrant_quality_pass=args.require_qdrant_quality_pass,
        require_tiff_audit_quality_pass=args.require_tiff_audit_quality_pass,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Corrective Retrieval Planner v1.")
    parser.add_argument("--page-retrieval-large-eval-v2")
    parser.add_argument("--ai-trace-pack")
    parser.add_argument("--graph-query-evidence-enrichment")
    parser.add_argument("--opensearch-loader-smoke")
    parser.add_argument("--qdrant-page-profile-quality")
    parser.add_argument("--page-query-response-tiff-content-audit")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", action="store_true")
    _add_threshold_args(parser)
    args = parser.parse_args(argv)
    payload = build_corrective_retrieval_plan(
        output_dir=args.output_dir,
        thresholds=_thresholds_from_args(args),
        page_retrieval_large_eval_v2=args.page_retrieval_large_eval_v2,
        ai_trace_pack=args.ai_trace_pack,
        graph_query_evidence_enrichment=args.graph_query_evidence_enrichment,
        opensearch_loader_smoke=args.opensearch_loader_smoke,
        qdrant_page_profile_quality=args.qdrant_page_profile_quality,
        page_query_response_tiff_content_audit=args.page_query_response_tiff_content_audit,
        write_outputs=True,
    )
    print(json.dumps({"quality_status": payload["quality_status"], "summary": payload["summary"]}, indent=2, sort_keys=True))
    return 0 if (not args.quality or payload["quality_status"] == QUALITY_PASS) else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Corrective Retrieval Planner v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    _add_threshold_args(parser)
    args = parser.parse_args(argv)
    payload = check_corrective_retrieval_plan_quality(
        report_path=args.report_path,
        thresholds=_thresholds_from_args(args),
        write_json_report=args.write_json,
    )
    print(json.dumps({"quality_status": payload["quality_status"], "summary": payload["summary"]}, indent=2, sort_keys=True))
    return 0 if payload["quality_status"] == QUALITY_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
