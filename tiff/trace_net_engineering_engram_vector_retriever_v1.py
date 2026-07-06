"""TRACE-Net Engineering Engram Vector Retriever v1.

Artifact-only local retriever for H18 Engram vector-loader records.

This module intentionally does not contact Qdrant or any live service.  It uses the
same style of deterministic hashing-vector scoring as the H18 local loader so the
retrieval behavior is reproducible in tests and git artifacts.  A later live
adapter can use the same payload contract after explicit write gates are added.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

MODULE = "trace_net_engineering_engram_vector_retriever_v1"
VERSION = "v1"

SAFETY_CONTRACT = {
    "answer_permission": False,
    "source_truth_mutation_allowed": False,
    "postgres_write_attempt": False,
    "qdrant_write_attempt": False,
    "opensearch_write_attempt": False,
    "opensearch_upload_attempt": False,
    "live_qdrant_read_attempted": False,
    "live_qdrant_write_attempted": False,
}

REQUIRED_LAYERS = [
    "working_memory",
    "semantic_memory",
    "procedural_memory",
    "episodic_memory",
    "trait_memory",
    "critic_memory",
]

DEFAULT_RETRIEVAL_QUERIES = [
    {
        "query_id": "h19_q_interchangeability_boundary",
        "text": "Is part 120-50645-005 interchangeable with 120-50645-011 or an approved replacement? Require explicit source authority.",
        "expected_layers": ["procedural_memory", "trait_memory"],
        "task_type": "interchangeability_boundary",
    },
    {
        "query_id": "h19_q_visual_ocr_route_behavior",
        "text": "Why does the visual route need OCR nomenclature evidence for Figure 69 and part names?",
        "expected_layers": ["semantic_memory", "critic_memory"],
        "task_type": "route_explanation",
    },
    {
        "query_id": "h19_q_unknown_part_not_source_trace_ready",
        "text": "Find part number 999-99999-999 and cite a source when no proof_context exists.",
        "expected_layers": ["working_memory", "procedural_memory"],
        "task_type": "unknown_part",
    },
    {
        "query_id": "h19_q_safe_but_too_generic_repair",
        "text": "The answer was safe but too generic. Retrieve repair behavior before regenerating.",
        "expected_layers": ["critic_memory", "episodic_memory", "trait_memory"],
        "task_type": "critic_repair",
    },
    {
        "query_id": "h19_q_summary_only_limit",
        "text": "Can v2 summaries alone prove Figure 69 part identity or source claims?",
        "expected_layers": ["working_memory", "procedural_memory"],
        "task_type": "summary_limit",
    },
    {
        "query_id": "h19_q_installation_fit_effectivity_limit",
        "text": "Does a figure or part identification prove installation safety, fit approval, aircraft effectivity, or replacement approval?",
        "expected_layers": ["procedural_memory", "semantic_memory"],
        "task_type": "approval_boundary",
    },
]

_TOKEN_RE = re.compile(r"[A-Za-z0-9_./:-]+")


def _stable_id(text: str, prefix: str = "h19") -> str:
    return prefix + "_" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def tokenize(text: str) -> List[str]:
    return [m.group(0).lower() for m in _TOKEN_RE.finditer(text or "")]


def hashing_vector(text: str, dim: int = 64) -> List[float]:
    """Deterministic signed hashing vector with L2 normalization."""
    dim = max(8, int(dim or 64))
    vec = [0.0] * dim
    tokens = tokenize(text)
    if not tokens:
        return vec
    for tok in tokens:
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        # Mildly reward exact engineering identifiers and long route terms.
        weight = 1.0
        if any(ch.isdigit() for ch in tok):
            weight += 0.25
        if "_" in tok or "-" in tok:
            weight += 0.15
        vec[idx] += sign * weight
    norm = math.sqrt(sum(x * x for x in vec))
    if norm <= 0.0:
        return vec
    return [round(x / norm, 10) for x in vec]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(float(a[i]) * float(b[i]) for i in range(n))
    na = math.sqrt(sum(float(x) * float(x) for x in a[:n]))
    nb = math.sqrt(sum(float(x) * float(x) for x in b[:n]))
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (na * nb)


def keyword_overlap_score(query_text: str, candidate_text: str) -> float:
    q = set(tokenize(query_text))
    c = set(tokenize(candidate_text))
    if not q or not c:
        return 0.0
    overlap = q & c
    # Jaccard-style score with a small exact-overlap boost.
    return len(overlap) / max(1, len(q))


def _coerce_vector(value: Any, dim: int, text_fallback: str) -> List[float]:
    if isinstance(value, list) and value and all(isinstance(x, (int, float)) for x in value):
        out = [float(x) for x in value]
        if len(out) == dim:
            return out
    return hashing_vector(text_fallback, dim=dim)


def _record_text(record: Mapping[str, Any]) -> str:
    parts = []
    for key in ("text_for_embedding", "rule", "title", "atom_id", "memory_layer", "proof_role"):
        val = record.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val.strip())
    payload = record.get("qdrant_payload")
    if isinstance(payload, Mapping):
        for key in ("title", "rule", "trigger", "memory_type", "memory_layer", "proof_role"):
            val = payload.get(key)
            if isinstance(val, str) and val.strip():
                parts.append(val.strip())
            elif isinstance(val, list):
                parts.extend(str(x) for x in val if str(x).strip())
    return " | ".join(parts)


def normalize_qdrant_ready_record(record: Mapping[str, Any], vector_dim: int) -> Dict[str, Any]:
    payload = record.get("qdrant_payload")
    if not isinstance(payload, Mapping):
        payload = {}
    atom_id = str(record.get("atom_id") or payload.get("atom_id") or _stable_id(json.dumps(record, sort_keys=True), "atom"))
    memory_layer = str(record.get("memory_layer") or payload.get("memory_layer") or "unknown")
    proof_role = str(record.get("proof_role") or payload.get("proof_role") or "guidance_only")
    text = _record_text(record)
    vector = _coerce_vector(record.get("vector") or record.get("embedding"), vector_dim, text)
    point_id = str(record.get("point_id") or payload.get("point_id") or hashlib.sha256(atom_id.encode("utf-8")).hexdigest())
    return {
        "atom_id": atom_id,
        "point_id": point_id,
        "memory_layer": memory_layer,
        "proof_role": proof_role,
        "memory_type": str(record.get("memory_type") or payload.get("memory_type") or ""),
        "title": str(record.get("title") or payload.get("title") or atom_id),
        "text_for_embedding": text,
        "vector": vector,
        "vector_dim": len(vector),
        "qdrant_payload": dict(payload),
        "answer_permission": bool(payload.get("answer_permission") or record.get("answer_permission") or False),
        "source_truth_mutation_allowed": bool(payload.get("source_truth_mutation_allowed") or record.get("source_truth_mutation_allowed") or False),
        "qdrant_write_attempt": bool(payload.get("qdrant_write_attempt") or record.get("qdrant_write_attempt") or False),
    }


def load_vector_loader(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def load_queries(path: Optional[str | Path] = None, inline_queries: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    queries: List[Dict[str, Any]] = []
    if path:
        for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            obj = json.loads(line)
            if isinstance(obj, str):
                obj = {"text": obj}
            if "query_id" not in obj:
                obj["query_id"] = _stable_id(f"{path}:{line_no}:{obj.get('text','')}", "query")
            queries.append(obj)
    if inline_queries:
        for i, text in enumerate(inline_queries, start=1):
            queries.append({"query_id": _stable_id(f"inline:{i}:{text}", "query"), "text": text, "expected_layers": []})
    if not queries:
        queries = [dict(q) for q in DEFAULT_RETRIEVAL_QUERIES]
    for q in queries:
        q.setdefault("query_id", _stable_id(q.get("text", ""), "query"))
        q.setdefault("expected_layers", [])
        q.setdefault("task_type", "engram_memory_retrieval")
    return queries


def retrieve_for_query(
    query: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    *,
    top_k: int = 5,
    vector_dim: int = 64,
) -> Dict[str, Any]:
    query_text = str(query.get("text") or query.get("query") or "")
    query_vec = hashing_vector(query_text, dim=vector_dim)
    scored: List[Dict[str, Any]] = []
    for rec in records:
        rec_text = str(rec.get("text_for_embedding") or "")
        sim = cosine_similarity(query_vec, rec.get("vector") or [])
        overlap = keyword_overlap_score(query_text, rec_text)
        expected_layers = set(query.get("expected_layers") or [])
        layer_bonus = 0.05 if rec.get("memory_layer") in expected_layers else 0.0
        final = (0.72 * sim) + (0.23 * overlap) + layer_bonus
        scored.append({
            "rank": 0,
            "atom_id": rec.get("atom_id"),
            "point_id": rec.get("point_id"),
            "memory_layer": rec.get("memory_layer"),
            "proof_role": rec.get("proof_role"),
            "title": rec.get("title"),
            "similarity_score": round(sim, 6),
            "keyword_overlap_score": round(overlap, 6),
            "layer_bonus": round(layer_bonus, 6),
            "retrieval_score": round(final, 6),
            "text_preview": rec_text[:700],
            "answer_permission": bool(rec.get("answer_permission")),
            "source_truth_mutation_allowed": bool(rec.get("source_truth_mutation_allowed")),
            "qdrant_write_attempt": bool(rec.get("qdrant_write_attempt")),
        })
    scored.sort(key=lambda x: (x["retrieval_score"], x["similarity_score"]), reverse=True)
    top = scored[: max(1, int(top_k or 5))]
    for i, item in enumerate(top, start=1):
        item["rank"] = i
    return {
        "query_id": query.get("query_id"),
        "task_type": query.get("task_type"),
        "query_text": query_text,
        "expected_layers": list(query.get("expected_layers") or []),
        "top_k": top_k,
        "result_count": len(top),
        "covered_layers": sorted({str(x.get("memory_layer")) for x in top if x.get("memory_layer")}),
        "results": top,
    }


def _counter(values: Iterable[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for value in values:
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items()))


def _write_json(path: Path, obj: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records), encoding="utf-8")


def build_vector_retriever_manifest(
    *,
    vector_loader_path: str | Path,
    output_dir: str | Path,
    queries_path: Optional[str | Path] = None,
    inline_queries: Optional[Sequence[str]] = None,
    top_k: int = 5,
    min_queries: int = 1,
    min_results_per_query: int = 1,
    require_all_layers: bool = False,
    require_no_answer_permission: bool = True,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    loader = load_vector_loader(vector_loader_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    collection_plan = loader.get("collection_plan") if isinstance(loader.get("collection_plan"), Mapping) else {}
    summary = loader.get("summary") if isinstance(loader.get("summary"), Mapping) else {}
    vector_dim = int(collection_plan.get("vector_dim") or summary.get("vector_dim") or 64)
    raw_records = loader.get("qdrant_ready_records") or []
    if not isinstance(raw_records, list):
        raw_records = []
    records = [normalize_qdrant_ready_record(r, vector_dim=vector_dim) for r in raw_records if isinstance(r, Mapping)]
    queries = load_queries(queries_path, inline_queries)

    retrieval_records = [
        retrieve_for_query(q, records, top_k=top_k, vector_dim=vector_dim)
        for q in queries[:]
    ]

    all_result_items = [item for rr in retrieval_records for item in rr.get("results", [])]
    result_layer_counts = _counter(str(item.get("memory_layer")) for item in all_result_items if item.get("memory_layer"))
    indexed_layer_counts = _counter(str(r.get("memory_layer")) for r in records if r.get("memory_layer"))
    missing_indexed_layers = [layer for layer in REQUIRED_LAYERS if indexed_layer_counts.get(layer, 0) <= 0]
    missing_retrieved_layers = [layer for layer in REQUIRED_LAYERS if result_layer_counts.get(layer, 0) <= 0]

    answer_permission_count = sum(1 for r in records if r.get("answer_permission")) + sum(1 for item in all_result_items if item.get("answer_permission"))
    source_truth_mutation_allowed_count = sum(1 for r in records if r.get("source_truth_mutation_allowed")) + sum(1 for item in all_result_items if item.get("source_truth_mutation_allowed"))
    qdrant_write_attempt_count = sum(1 for r in records if r.get("qdrant_write_attempt")) + sum(1 for item in all_result_items if item.get("qdrant_write_attempt"))
    write_attempt_count = qdrant_write_attempt_count

    unsafe_findings: List[str] = []
    if len(queries) < min_queries:
        unsafe_findings.append(f"query_count_below_min:{len(queries)}<{min_queries}")
    for rr in retrieval_records:
        if rr.get("result_count", 0) < min_results_per_query:
            unsafe_findings.append(f"query_result_count_below_min:{rr.get('query_id')}:{rr.get('result_count')}<{min_results_per_query}")
    if require_all_layers and missing_indexed_layers:
        unsafe_findings.append("missing_indexed_layers:" + ",".join(missing_indexed_layers))
    if require_all_layers and missing_retrieved_layers:
        unsafe_findings.append("missing_retrieved_layers:" + ",".join(missing_retrieved_layers))
    if require_no_answer_permission and answer_permission_count:
        unsafe_findings.append(f"answer_permission_count:{answer_permission_count}")
    if source_truth_mutation_allowed_count:
        unsafe_findings.append(f"source_truth_mutation_allowed_count:{source_truth_mutation_allowed_count}")
    if write_attempt_count > max_write_attempts:
        unsafe_findings.append(f"write_attempt_count:{write_attempt_count}>{max_write_attempts}")

    unsafe_finding_count = len(unsafe_findings)
    quality_status = "PASS" if unsafe_finding_count <= max_unsafe else "FAIL"

    manifest = {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_VECTOR_RETRIEVER_BUILT",
        "quality_status": quality_status,
        "module": MODULE,
        "version": VERSION,
        "source_vector_loader_path": str(vector_loader_path),
        "collection_plan": {
            "collection_name": collection_plan.get("collection_name", "trace_net_engineering_engram_memory_v1"),
            "distance": collection_plan.get("distance", "Cosine"),
            "encoder": collection_plan.get("encoder", "trace_net_hashing_encoder_v1"),
            "retriever": "trace_net_local_hashing_retriever_v1",
            "vector_dim": vector_dim,
            "live_qdrant_read_attempted": False,
            "live_qdrant_write_attempted": False,
            "note": "Artifact-only local retrieval over Qdrant-ready Engram records; no live Qdrant IO.",
        },
        "retrieval_queries": queries,
        "retrieval_records": retrieval_records,
        "summary": {
            "module": MODULE,
            "version": VERSION,
            "query_count": len(queries),
            "qdrant_ready_record_count": len(records),
            "retrieval_record_count": len(retrieval_records),
            "total_retrieved_item_count": len(all_result_items),
            "top_k": top_k,
            "vector_dim": vector_dim,
            "indexed_memory_layer_counts": indexed_layer_counts,
            "retrieved_memory_layer_counts": result_layer_counts,
            "missing_indexed_layers": missing_indexed_layers,
            "missing_retrieved_layers": missing_retrieved_layers,
            "answer_permission_count": answer_permission_count,
            "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": qdrant_write_attempt_count,
            "opensearch_write_attempt_count": 0,
            "opensearch_upload_attempt_count": 0,
            "write_attempt_count": write_attempt_count,
            "unsafe_finding_count": unsafe_finding_count,
            "unsafe_findings": unsafe_findings,
            "ready_for_engram_prompt_retrieval": quality_status == "PASS",
        },
        "safety_contract": dict(SAFETY_CONTRACT),
    }

    manifest_path = output / f"{MODULE}.json"
    records_path = output / f"{MODULE}_retrieval_records.jsonl"
    check_path = output / f"{MODULE}_quality_check.json"
    _write_json(manifest_path, manifest)
    _write_jsonl(records_path, retrieval_records)
    _write_json(check_path, {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_VECTOR_RETRIEVER_CHECKED",
        "quality_status": quality_status,
        "summary": manifest["summary"],
        "safety_contract": manifest["safety_contract"],
    })
    manifest["output_path"] = str(manifest_path)
    manifest["retrieval_records_path"] = str(records_path)
    manifest["quality_check_path"] = str(check_path)
    _write_json(manifest_path, manifest)
    return manifest


def check_vector_retriever_manifest(
    *,
    vector_retriever_path: str | Path,
    min_queries: int = 1,
    min_results_per_query: int = 1,
    require_all_layers: bool = False,
    require_quality_pass: bool = False,
    require_no_answer_permission: bool = True,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    data = json.loads(Path(vector_retriever_path).read_text(encoding="utf-8"))
    summary = data.get("summary") if isinstance(data.get("summary"), Mapping) else {}
    failures: List[str] = []
    if require_quality_pass and data.get("quality_status") != "PASS":
        failures.append("quality_status_not_pass")
    if int(summary.get("query_count") or 0) < min_queries:
        failures.append("query_count_below_min")
    for rr in data.get("retrieval_records", []) or []:
        if int(rr.get("result_count") or 0) < min_results_per_query:
            failures.append(f"query_result_count_below_min:{rr.get('query_id')}")
    if require_all_layers:
        missing = summary.get("missing_indexed_layers") or []
        if missing:
            failures.append("missing_indexed_layers:" + ",".join(missing))
        missing_retrieved = summary.get("missing_retrieved_layers") or []
        if missing_retrieved:
            failures.append("missing_retrieved_layers:" + ",".join(missing_retrieved))
    if require_no_answer_permission and int(summary.get("answer_permission_count") or 0) != 0:
        failures.append("answer_permission_count_nonzero")
    if int(summary.get("write_attempt_count") or 0) > max_write_attempts:
        failures.append("write_attempt_count_exceeds_max")
    if int(summary.get("unsafe_finding_count") or 0) > max_unsafe:
        failures.append("unsafe_finding_count_exceeds_max")

    quality_status = "PASS" if not failures else "FAIL"
    result = {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_VECTOR_RETRIEVER_CHECKED",
        "quality_status": quality_status,
        "module": MODULE,
        "version": VERSION,
        "query_count": int(summary.get("query_count") or 0),
        "retrieval_record_count": int(summary.get("retrieval_record_count") or 0),
        "total_retrieved_item_count": int(summary.get("total_retrieved_item_count") or 0),
        "indexed_memory_layer_counts": summary.get("indexed_memory_layer_counts") or {},
        "retrieved_memory_layer_counts": summary.get("retrieved_memory_layer_counts") or {},
        "unsafe_finding_count": int(summary.get("unsafe_finding_count") or 0),
        "answer_permission_count": int(summary.get("answer_permission_count") or 0),
        "write_attempt_count": int(summary.get("write_attempt_count") or 0),
        "failures": failures,
    }
    out = Path(vector_retriever_path).with_name(f"{MODULE}_external_quality_check.json")
    _write_json(out, result)
    result["output_path"] = str(out)
    return result
