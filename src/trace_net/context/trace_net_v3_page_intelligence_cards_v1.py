#!/usr/bin/env python3
"""
TRACE-Net V3 Page Intelligence Cards v1.

Builds a lightweight V3 page-intelligence layer from:
- Fishnet OCR grid page cards.
- Accepted V2 page_context_v2 records from Gemma.
- Deferred V2 page IDs.

V3 does not rerun the LLM. It enriches page-level routing/retrieval metadata and
keeps proof boundaries explicit. V3 is guidance, not source truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "trace_net_v3_page_intelligence_cards_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/v3_page_intelligence")
DEFAULT_MANIFEST = "trace_net_v3_page_intelligence_cards_v1.json"
DEFAULT_JSONL = "trace_net_v3_page_intelligence_cards_v1.jsonl"
DEFAULT_NODES = "trace_net_v3_page_intelligence_graph_nodes.json"
DEFAULT_EDGES = "trace_net_v3_page_intelligence_graph_edges.json"
DEFAULT_QUALITY = "trace_net_v3_page_intelligence_cards_v1_quality.json"

SAFETY_CONTRACT = {
    "v3_cards_are_source_truth": False,
    "v3_cards_can_answer_directly": False,
    "v3_cards_can_prove_claims": False,
    "requires_source_check": True,
    "requires_citation": True,
    "source_truth_mutation_allowed": False,
    "postgres_write_attempt_count": 0,
    "qdrant_write_attempt_count": 0,
    "opensearch_write_attempt_count": 0,
}


def norm_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def stable_hash(*parts: Any, length: int = 20) -> str:
    raw = "|".join(norm_text(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def page_id_from_number(page_number: int, *, prefix: str = "t_p_120_1176") -> str:
    return f"{prefix}_p{int(page_number):06d}"


def page_number_from_page_id(page_id: str) -> int | None:
    m = re.search(r"_p(\d{6})$", norm_text(page_id))
    return int(m.group(1)) if m else None


def as_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("records", "cards", "items", "graph_nodes", "nodes"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def load_fishnet_records(path: Path) -> list[dict[str, Any]]:
    records = as_records(read_json(path))
    if not records:
        raise ValueError(f"No fishnet records found in {path}")
    return records


def load_v2_records(path: Path) -> list[dict[str, Any]]:
    records = as_records(read_json(path))
    if not records:
        raise ValueError(f"No V2 records found in {path}")
    return records


def load_deferred_page_ids(path: Path | None, *, fallback: Iterable[str] = ()) -> list[str]:
    ids: list[str] = []
    if path and path.exists():
        payload = read_json(path)
        if isinstance(payload, list):
            ids = [norm_text(x) for x in payload if norm_text(x)]
        elif isinstance(payload, dict):
            for key in ("deferred_page_ids", "missing_page_ids", "page_ids"):
                value = payload.get(key)
                if isinstance(value, list):
                    ids = [norm_text(x) for x in value if norm_text(x)]
                    break
    if not ids:
        ids = [norm_text(x) for x in fallback if norm_text(x)]
    return sorted(dict.fromkeys(ids))


def v2_page_id(record: Mapping[str, Any]) -> str:
    return norm_text(
        record.get("page_id")
        or record.get("source_page_id")
        or record.get("canonical_page_id")
        or record.get("original_gemma_record", {}).get("page_id")
    )


def safe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def summarize_route(fishnet: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "recommended_route_candidate": fishnet.get("recommended_route_candidate"),
        "best_route_candidate_before_review": fishnet.get("best_route_candidate_before_review"),
        "route_confidence": fishnet.get("route_confidence"),
        "review_required": bool(fishnet.get("review_required", False)),
        "route_review_reason_codes": safe_list(fishnet.get("route_review_reason_codes")),
        "route_scores": fishnet.get("route_scores") or {},
        "route_adjusted_scores": fishnet.get("route_adjusted_scores") or {},
        "reason_counts": fishnet.get("reason_counts") or {},
    }


def build_retrieval_text(*, page_id: str, fishnet: Mapping[str, Any], v2: Mapping[str, Any] | None) -> str:
    ocr_features = fishnet.get("page_ocr_features") or {}
    parts = [
        f"TRACE-Net V3 page intelligence for {page_id}.",
        f"Route: {fishnet.get('recommended_route_candidate') or 'unknown'}; review_required={bool(fishnet.get('review_required', False))}.",
    ]
    if v2:
        parts.extend(
            [
                f"V2 role: {v2.get('role') or v2.get('original_gemma_record', {}).get('role') or 'unknown'}.",
                f"V2 subrole: {v2.get('subrole') or v2.get('original_gemma_record', {}).get('subrole') or 'unknown'}.",
                norm_text(first_present(v2.get("retrieval_summary"), v2.get("original_gemma_record", {}).get("retrieval_summary"))),
                norm_text(first_present(v2.get("short_summary"), v2.get("original_gemma_record", {}).get("short_summary"))),
                "Entities: " + ", ".join(map(str, safe_list(v2.get("important_entities") or v2.get("original_gemma_record", {}).get("important_entities"))[:12])),
                "Parts: " + ", ".join(map(str, safe_list(v2.get("important_parts") or v2.get("original_gemma_record", {}).get("important_parts"))[:12])),
            ]
        )
    else:
        parts.append("V2 context is missing or deferred for this page.")
    sample_text = norm_text(ocr_features.get("sample_text"))
    if sample_text:
        parts.append("OCR sample: " + sample_text[:700])
    return "\n".join([p for p in parts if norm_text(p)])


def build_v3_record(
    *,
    fishnet: Mapping[str, Any],
    v2: Mapping[str, Any] | None,
    deferred_ids: set[str],
    canonical_prefix: str,
) -> dict[str, Any]:
    page_number = fishnet.get("page_number")
    page_id = page_id_from_number(int(page_number), prefix=canonical_prefix) if page_number else norm_text(fishnet.get("page_id"))
    fishnet_page_id = norm_text(fishnet.get("page_id"))
    ocr_features = fishnet.get("page_ocr_features") or {}
    ink_features = fishnet.get("page_ink_features") or {}
    route = summarize_route(fishnet)

    v2_available = v2 is not None
    if v2_available:
        v2_status = "available"
    elif page_id in deferred_ids:
        v2_status = "missing_deferred"
    else:
        v2_status = "missing_not_generated"

    original = v2.get("original_gemma_record", {}) if isinstance(v2, Mapping) else {}

    role = first_present(v2.get("role") if v2 else None, original.get("role"), "unknown")
    subrole = first_present(v2.get("subrole") if v2 else None, original.get("subrole"), "unknown")
    confidence = first_present(v2.get("confidence") if v2 else None, original.get("confidence"), "unknown")

    v3_id = f"v3_page_intelligence::{page_id}"
    page_node_id = f"page::{page_id}"

    record = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "v3_page_intelligence_card",
        "id": v3_id,
        "v3_id": v3_id,
        "page_id": page_id,
        "page_number": page_number,
        "source_page_id": fishnet_page_id,
        "source_path": fishnet.get("source_path"),
        "file_name": fishnet.get("file_name"),
        "graph_node_id": v3_id,
        "graph_edge_type": "HAS_V3_PAGE_INTELLIGENCE",
        "source_page_node_id": page_node_id,
        "v2_context_available": v2_available,
        "v2_context_status": v2_status,
        "v2_context_id": v2.get("context_id") if v2 else None,
        "v2_generation_model": v2.get("generation_model") if v2 else None,
        "v2_role": role,
        "v2_subrole": subrole,
        "v2_confidence": confidence,
        "v2_retrieval_summary": first_present(v2.get("retrieval_summary") if v2 else None, original.get("retrieval_summary")),
        "v2_short_summary": first_present(v2.get("short_summary") if v2 else None, original.get("short_summary")),
        "v2_retrieval_cues": safe_list(first_present(v2.get("retrieval_cues") if v2 else None, original.get("retrieval_cues"))),
        "important_entities": safe_list(first_present(v2.get("important_entities") if v2 else None, original.get("important_entities"))),
        "important_parts": safe_list(first_present(v2.get("important_parts") if v2 else None, original.get("important_parts"))),
        "answerable_questions": safe_list(first_present(v2.get("answerable_questions") if v2 else None, original.get("answerable_questions"))),
        "ocr": {
            "status": fishnet.get("page_ocr_status") or fishnet.get("ocr_engine_status"),
            "engine_status": fishnet.get("ocr_engine_status"),
            "char_count": ocr_features.get("ocr_char_count"),
            "word_count": ocr_features.get("ocr_word_count"),
            "line_count": ocr_features.get("ocr_line_count"),
            "part_number_token_count": ocr_features.get("part_number_token_count"),
            "numeric_token_count": ocr_features.get("numeric_token_count"),
            "callout_hint_count": ocr_features.get("callout_hint_count"),
            "table_keyword_count": ocr_features.get("table_keyword_count"),
            "visual_keyword_count": ocr_features.get("visual_keyword_count"),
            "ocr_word_box_count": ocr_features.get("ocr_word_box_count"),
            "ocr_mean_confidence": ocr_features.get("ocr_mean_confidence"),
            "sample_text": ocr_features.get("sample_text"),
        },
        "ink": {
            "ink_pixel_count": ink_features.get("ink_pixel_count"),
            "total_pixel_count": ink_features.get("total_pixel_count"),
            "ink_ratio": ink_features.get("ink_ratio"),
            "mean_darkness": ink_features.get("mean_darkness"),
        },
        "route": route,
        "retrieval_profile": {
            "embedding_candidate_recommended": True,
            "text": build_retrieval_text(page_id=page_id, fishnet=fishnet, v2=v2),
            "preferred_uses": ["retrieve", "rank", "route", "candidate_discovery"],
            "proof_boundary": "V3 page intelligence is retrieval/routing guidance only; verify claims against source OCR/table/visual/source_trace evidence.",
        },
        "proof_policy": {
            "guidance_only": True,
            "canonical_source_truth": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "requires_source_check": True,
            "requires_citation": True,
            "source_truth_mutation_allowed": False,
        },
        "guidance_only": True,
        "canonical_source_truth": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "deferred_reason": "Gemma V2 invalid JSON" if v2_status == "missing_deferred" else None,
    }
    return record


def make_graph_node(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": record["graph_node_id"],
        "node_id": record["graph_node_id"],
        "type": "V3PageIntelligence",
        "node_type": "V3PageIntelligence",
        "label": f"V3 Page Intelligence {record['page_id']}",
        "page_id": record["page_id"],
        "payload": {
            "schema_version": SCHEMA_VERSION,
            "record_type": "v3_page_intelligence_card",
            "v2_context_status": record.get("v2_context_status"),
            "recommended_route_candidate": (record.get("route") or {}).get("recommended_route_candidate"),
            "guidance_only": True,
            "canonical_source_truth": False,
            "can_answer_directly": False,
            "source_truth_mutation_allowed": False,
        },
        "guidance_only": True,
        "canonical_source_truth": False,
        "can_answer_directly": False,
        "source_truth_mutation_allowed": False,
    }


def make_graph_edge(record: Mapping[str, Any]) -> dict[str, Any]:
    edge_id = f"edge:{stable_hash('HAS_V3_PAGE_INTELLIGENCE', record['source_page_node_id'], record['graph_node_id'])}"
    return {
        "id": edge_id,
        "edge_id": edge_id,
        "type": "HAS_V3_PAGE_INTELLIGENCE",
        "edge_type": "HAS_V3_PAGE_INTELLIGENCE",
        "source": record["source_page_node_id"],
        "source_id": record["source_page_node_id"],
        "source_node_id": record["source_page_node_id"],
        "target": record["graph_node_id"],
        "target_id": record["graph_node_id"],
        "target_node_id": record["graph_node_id"],
        "page_id": record["page_id"],
        "payload": {
            "schema_version": SCHEMA_VERSION,
            "relationship": "page_has_v3_page_intelligence",
            "proof_boundary": "HAS_V3_PAGE_INTELLIGENCE exposes retrieval/routing guidance only",
            "v2_context_status": record.get("v2_context_status"),
        },
        "guidance_only": True,
        "canonical_source_truth": False,
        "can_answer_directly": False,
        "source_truth_mutation_allowed": False,
    }


def summarize(records: list[dict[str, Any]], nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    v2_status_counts = Counter(r.get("v2_context_status") for r in records)
    route_counts = Counter((r.get("route") or {}).get("recommended_route_candidate") for r in records)
    ocr_status_counts = Counter((r.get("ocr") or {}).get("status") for r in records)
    return {
        "schema_version": SCHEMA_VERSION,
        "record_count": len(records),
        "unique_page_count": len({r.get("page_id") for r in records}),
        "graph_node_count": len(nodes),
        "graph_edge_count": len(edges),
        "v3_page_intelligence_node_count": sum(1 for n in nodes if (n.get("node_type") or n.get("type")) == "V3PageIntelligence"),
        "has_v3_page_intelligence_edge_count": sum(1 for e in edges if (e.get("edge_type") or e.get("type")) == "HAS_V3_PAGE_INTELLIGENCE"),
        "v2_context_available_count": sum(1 for r in records if r.get("v2_context_available")),
        "v2_context_missing_count": sum(1 for r in records if not r.get("v2_context_available")),
        "v2_context_status_counts": dict(sorted(v2_status_counts.items(), key=lambda kv: str(kv[0]))),
        "route_counts": dict(sorted(route_counts.items(), key=lambda kv: str(kv[0]))),
        "ocr_status_counts": dict(sorted(ocr_status_counts.items(), key=lambda kv: str(kv[0]))),
        "guidance_only_count": sum(1 for r in records if r.get("guidance_only") is True),
        "canonical_source_truth_count": sum(1 for r in records if r.get("canonical_source_truth") is True),
        "answer_permission_count": sum(1 for r in records if r.get("answer_permission") is True),
        "can_answer_directly_count": sum(1 for r in records if r.get("can_answer_directly") is True),
        "can_prove_claims_count": sum(1 for r in records if r.get("can_prove_claims") is True),
        "source_truth_mutation_allowed_count": sum(1 for r in records if r.get("source_truth_mutation_allowed") is True),
        "postgres_write_attempt_count": sum(int(r.get("postgres_write_attempt_count") or 0) for r in records),
        "qdrant_write_attempt_count": sum(int(r.get("qdrant_write_attempt_count") or 0) for r in records),
        "opensearch_write_attempt_count": sum(int(r.get("opensearch_write_attempt_count") or 0) for r in records),
        "unsafe_record_count": sum(
            1
            for r in records
            if r.get("canonical_source_truth")
            or r.get("can_answer_directly")
            or r.get("can_prove_claims")
            or r.get("source_truth_mutation_allowed")
        ),
    }


def evaluate_quality(
    summary: Mapping[str, Any],
    *,
    min_records: int,
    expected_records: int | None,
    max_missing_v2: int,
    require_full_fishnet_coverage: bool,
    require_no_answer_permission: bool,
    require_no_source_truth_mutation: bool,
    max_unsafe: int,
) -> tuple[str, list[str]]:
    failures: list[str] = []
    if int(summary.get("record_count") or 0) < min_records:
        failures.append(f"record_count_below_min:{summary.get('record_count')}<{min_records}")
    if expected_records is not None and int(summary.get("record_count") or 0) != expected_records:
        failures.append(f"record_count_not_expected:{summary.get('record_count')}!={expected_records}")
    if require_full_fishnet_coverage and int(summary.get("unique_page_count") or 0) != int(summary.get("record_count") or 0):
        failures.append("unique_page_count_mismatch")
    if int(summary.get("v2_context_missing_count") or 0) > max_missing_v2:
        failures.append(f"v2_context_missing_count_too_high:{summary.get('v2_context_missing_count')}>{max_missing_v2}")
    if int(summary.get("graph_node_count") or 0) != int(summary.get("record_count") or 0):
        failures.append("graph_node_count_mismatch")
    if int(summary.get("graph_edge_count") or 0) != int(summary.get("record_count") or 0):
        failures.append("graph_edge_count_mismatch")
    if int(summary.get("has_v3_page_intelligence_edge_count") or 0) != int(summary.get("record_count") or 0):
        failures.append("has_v3_page_intelligence_edge_count_mismatch")
    if require_no_answer_permission and int(summary.get("answer_permission_count") or 0) != 0:
        failures.append("answer_permission_count_nonzero")
    if require_no_source_truth_mutation and int(summary.get("source_truth_mutation_allowed_count") or 0) != 0:
        failures.append("source_truth_mutation_allowed_count_nonzero")
    if int(summary.get("unsafe_record_count") or 0) > max_unsafe:
        failures.append(f"unsafe_record_count_too_high:{summary.get('unsafe_record_count')}>{max_unsafe}")
    for key in ("postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"):
        if int(summary.get(key) or 0) != 0:
            failures.append(f"{key}_nonzero")
    return ("PASS" if not failures else "FAIL"), failures


def build_v3_bundle(
    *,
    fishnet_path: Path,
    page_context_v2_path: Path,
    deferred_page_ids_path: Path | None = None,
    canonical_prefix: str = "t_p_120_1176",
    min_records: int = 509,
    expected_records: int | None = 509,
    max_missing_v2: int = 3,
    require_full_fishnet_coverage: bool = True,
    require_no_answer_permission: bool = True,
    require_no_source_truth_mutation: bool = True,
    max_unsafe: int = 0,
) -> dict[str, Any]:
    fishnet_records = load_fishnet_records(fishnet_path)
    v2_records = load_v2_records(page_context_v2_path)
    v2_by_page = {v2_page_id(r): r for r in v2_records if v2_page_id(r)}
    deferred_ids = set(load_deferred_page_ids(deferred_page_ids_path, fallback=[
        "t_p_120_1176_p000282",
        "t_p_120_1176_p000337",
        "t_p_120_1176_p000441",
    ]))

    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for fishnet in sorted(fishnet_records, key=lambda r: int(r.get("page_number") or 10**9)):
        try:
            page_id = page_id_from_number(int(fishnet.get("page_number")), prefix=canonical_prefix)
            record = build_v3_record(
                fishnet=fishnet,
                v2=v2_by_page.get(page_id),
                deferred_ids=deferred_ids,
                canonical_prefix=canonical_prefix,
            )
            records.append(record)
        except Exception as exc:
            errors.append({
                "source_page_id": fishnet.get("page_id"),
                "page_number": fishnet.get("page_number"),
                "error_type": type(exc).__name__,
                "error": str(exc)[:700],
            })

    nodes = [make_graph_node(r) for r in records]
    edges = [make_graph_edge(r) for r in records]
    summary = summarize(records, nodes, edges)
    summary.update({
        "fishnet_path": str(fishnet_path),
        "page_context_v2_path": str(page_context_v2_path),
        "deferred_page_ids_path": str(deferred_page_ids_path or ""),
        "deferred_page_ids": sorted(deferred_ids),
        "build_error_count": len(errors),
    })
    quality_status, failure_reasons = evaluate_quality(
        summary,
        min_records=min_records,
        expected_records=expected_records,
        max_missing_v2=max_missing_v2,
        require_full_fishnet_coverage=require_full_fishnet_coverage,
        require_no_answer_permission=require_no_answer_permission,
        require_no_source_truth_mutation=require_no_source_truth_mutation,
        max_unsafe=max_unsafe,
    )
    if errors:
        quality_status = "FAIL"
        failure_reasons.append("build_error_count_nonzero")

    return {
        "module": SCHEMA_VERSION,
        "version": "v1",
        "status": "V3_PAGE_INTELLIGENCE_CARDS_BUILT",
        "quality_status": quality_status,
        "failure_reasons": failure_reasons,
        "summary": summary,
        "safety_contract": SAFETY_CONTRACT,
        "errors": errors,
        "records": records,
        "graph_nodes": nodes,
        "graph_edges": edges,
    }


def write_bundle(bundle: Mapping[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = output_dir / DEFAULT_MANIFEST
    jsonl = output_dir / DEFAULT_JSONL
    nodes = output_dir / DEFAULT_NODES
    edges = output_dir / DEFAULT_EDGES
    quality = output_dir / DEFAULT_QUALITY

    write_json(manifest, dict(bundle))
    with jsonl.open("w", encoding="utf-8") as f:
        for rec in bundle.get("records", []):
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    write_json(nodes, bundle.get("graph_nodes", []))
    write_json(edges, bundle.get("graph_edges", []))
    write_json(quality, {
        "quality_status": bundle.get("quality_status"),
        "failure_reasons": bundle.get("failure_reasons", []),
        "summary": bundle.get("summary", {}),
        "safety_contract": bundle.get("safety_contract", {}),
    })
    return {
        "manifest": manifest,
        "jsonl": jsonl,
        "nodes": nodes,
        "edges": edges,
        "quality": quality,
    }


def check_manifest_quality(
    manifest_path: Path,
    *,
    min_records: int,
    expected_records: int | None,
    max_missing_v2: int,
    require_quality_pass: bool,
    require_v3_graph_contract: bool,
    require_no_answer_permission: bool,
    require_no_source_truth_mutation: bool,
    max_unsafe: int,
) -> dict[str, Any]:
    bundle = read_json(manifest_path)
    records = as_records(bundle)
    nodes = bundle.get("graph_nodes", []) if isinstance(bundle, dict) else []
    edges = bundle.get("graph_edges", []) if isinstance(bundle, dict) else []
    summary = summarize(records, nodes, edges)
    # Preserve path/status fields if already present.
    if isinstance(bundle, dict):
        summary.update({
            "source_quality_status": bundle.get("quality_status"),
            "source_failure_reasons": bundle.get("failure_reasons", []),
        })

    status, failures = evaluate_quality(
        summary,
        min_records=min_records,
        expected_records=expected_records,
        max_missing_v2=max_missing_v2,
        require_full_fishnet_coverage=True,
        require_no_answer_permission=require_no_answer_permission,
        require_no_source_truth_mutation=require_no_source_truth_mutation,
        max_unsafe=max_unsafe,
    )
    if require_quality_pass and isinstance(bundle, dict) and bundle.get("quality_status") != "PASS":
        status = "FAIL"
        failures.append("source_manifest_quality_status_not_pass")
    if require_v3_graph_contract:
        bad_edges = [
            e for e in edges
            if (e.get("edge_type") or e.get("type")) != "HAS_V3_PAGE_INTELLIGENCE"
            or not norm_text(e.get("source_node_id") or e.get("source") or "").startswith("page::")
            or not norm_text(e.get("target_node_id") or e.get("target") or "").startswith("v3_page_intelligence::")
        ]
        if bad_edges:
            status = "FAIL"
            failures.append(f"v3_graph_contract_bad_edge_count:{len(bad_edges)}")
    return {
        "quality_status": "PASS" if status == "PASS" and not failures else "FAIL",
        "failure_reasons": failures,
        "summary": summary,
    }


def build_cli_main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build TRACE-Net V3 page intelligence cards v1.")
    p.add_argument("--fishnet-report", type=Path, required=True)
    p.add_argument("--page-context-v2", type=Path, required=True)
    p.add_argument("--deferred-page-ids", type=Path)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--canonical-prefix", default="t_p_120_1176")
    p.add_argument("--min-records", type=int, default=509)
    p.add_argument("--expected-records", type=int, default=509)
    p.add_argument("--max-missing-v2", type=int, default=3)
    p.add_argument("--require-quality-pass", action="store_true")
    args = p.parse_args(argv)

    bundle = build_v3_bundle(
        fishnet_path=args.fishnet_report,
        page_context_v2_path=args.page_context_v2,
        deferred_page_ids_path=args.deferred_page_ids,
        canonical_prefix=args.canonical_prefix,
        min_records=args.min_records,
        expected_records=args.expected_records,
        max_missing_v2=args.max_missing_v2,
    )
    paths = write_bundle(bundle, args.output_dir)

    print(f"Status: {bundle['status']}")
    print(f"Quality status: {bundle['quality_status']}")
    print("Summary:", json.dumps(bundle["summary"], ensure_ascii=False, sort_keys=True))
    for path in paths.values():
        print("Wrote:", path)

    if args.require_quality_pass and bundle["quality_status"] != "PASS":
        return 2
    return 0 if bundle["quality_status"] == "PASS" else 2


def check_cli_main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Check TRACE-Net V3 page intelligence cards v1 quality.")
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path)
    p.add_argument("--write-json", action="store_true")
    p.add_argument("--min-records", type=int, default=509)
    p.add_argument("--expected-records", type=int, default=509)
    p.add_argument("--max-missing-v2", type=int, default=3)
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--require-v3-graph-contract", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--require-no-source-truth-mutation", action="store_true")
    p.add_argument("--max-unsafe", type=int, default=0)
    args = p.parse_args(argv)

    result = check_manifest_quality(
        args.manifest,
        min_records=args.min_records,
        expected_records=args.expected_records,
        max_missing_v2=args.max_missing_v2,
        require_quality_pass=args.require_quality_pass,
        require_v3_graph_contract=args.require_v3_graph_contract,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        max_unsafe=args.max_unsafe,
    )

    print("Quality status:", result["quality_status"])
    print("Summary:", json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))
    if result["failure_reasons"]:
        print("Failure reasons:", result["failure_reasons"])

    if args.write_json or args.output:
        out = args.output or (args.manifest.parent / DEFAULT_QUALITY)
        write_json(out, result)
        print("Wrote:", out)

    return 0 if result["quality_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(build_cli_main())
