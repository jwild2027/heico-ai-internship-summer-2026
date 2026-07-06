from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

MODULE = "trace_net_engineering_engram_qdrant_adapter_v1"
VERSION = "v1"

REQUIRED_LAYERS = {
    "working_memory",
    "semantic_memory",
    "procedural_memory",
    "episodic_memory",
    "trait_memory",
    "critic_memory",
}


def _read_json(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def _norm_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())


def _as_bool(value: Any) -> bool:
    return bool(value) if value is not None else False


def _point_id_from_atom(atom_id: str) -> str:
    return hashlib.sha256(atom_id.encode("utf-8")).hexdigest()


def _sanitize_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Keep only JSON-safe scalar/list/dict values and force safety counters false."""
    safe = json.loads(json.dumps(dict(payload), default=str))
    safe["answer_permission"] = False
    safe["source_truth_mutation_allowed"] = False
    safe["postgres_write_attempt"] = False
    safe["opensearch_write_attempt"] = False
    safe["opensearch_upload_attempt"] = False
    # This is a payload statement, not a runtime counter. Runtime write attempt is tracked elsewhere.
    safe["qdrant_write_attempt"] = False
    safe["engram_guidance_only"] = True
    safe["manual_claims_require_proof_context"] = True
    return safe


def normalize_qdrant_records(vector_loader: Mapping[str, Any], *, collection_name: str | None = None) -> List[Dict[str, Any]]:
    records = list(vector_loader.get("qdrant_ready_records") or [])
    out: List[Dict[str, Any]] = []
    for rec in records:
        atom_id = _norm_text(rec.get("atom_id")) or _norm_text(rec.get("id"))
        if not atom_id:
            atom_id = _point_id_from_atom(json.dumps(rec, sort_keys=True))[:24]
        vector = rec.get("vector") or rec.get("embedding") or rec.get("qdrant_vector")
        if not isinstance(vector, list):
            # Preserve adapter shape even if an older artifact stored dimension only.
            dim = int(rec.get("vector_dim") or vector_loader.get("summary", {}).get("vector_dim") or 64)
            vector = [0.0] * dim
        payload = _sanitize_payload(rec.get("qdrant_payload") or rec.get("payload") or rec)
        payload.update({
            "atom_id": atom_id,
            "memory_layer": rec.get("memory_layer") or payload.get("memory_layer"),
            "proof_role": rec.get("proof_role") or payload.get("proof_role"),
            "text_for_embedding": rec.get("text_for_embedding") or payload.get("text_for_embedding") or rec.get("text") or "",
        })
        point_id = rec.get("point_id") or _point_id_from_atom(atom_id)
        out.append({
            "id": point_id,
            "vector": [float(x) for x in vector],
            "payload": payload,
            "collection_name": collection_name,
            "atom_id": atom_id,
            "memory_layer": payload.get("memory_layer"),
            "proof_role": payload.get("proof_role"),
            "vector_dim": len(vector),
            "text_for_embedding": payload.get("text_for_embedding") or "",
        })
    return out


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _hash_embed(text: str, dim: int) -> List[float]:
    vec = [0.0] * dim
    for token in _norm_text(text).lower().split():
        h = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    if norm:
        vec = [v / norm for v in vec]
    return vec


def local_search(points: Sequence[Mapping[str, Any]], query: str, *, top_k: int = 5, vector_dim: int = 64) -> List[Dict[str, Any]]:
    qv = _hash_embed(query, vector_dim)
    rows: List[Dict[str, Any]] = []
    for pt in points:
        vector = pt.get("vector") or []
        score = _cosine(qv, vector) if vector else 0.0
        # Add a small lexical boost so tests and artifact previews are readable.
        text = _norm_text(pt.get("text_for_embedding") or pt.get("payload", {}).get("text_for_embedding") or "").lower()
        q_terms = set(_norm_text(query).lower().split())
        overlap = sum(1 for t in q_terms if t in text)
        score += min(0.25, overlap * 0.03)
        rows.append({
            "id": pt.get("id"),
            "atom_id": pt.get("atom_id"),
            "memory_layer": pt.get("memory_layer"),
            "proof_role": pt.get("proof_role"),
            "score": round(float(score), 6),
            "text_preview": _norm_text(text)[:260],
        })
    rows.sort(key=lambda r: r.get("score", 0.0), reverse=True)
    return rows[:top_k]


def _qdrant_request(method: str, url: str, payload: Mapping[str, Any] | None = None, timeout: int = 30) -> Dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {"status": "ok"}


def _create_collection(qdrant_url: str, collection_name: str, vector_dim: int, timeout: int) -> Dict[str, Any]:
    url = qdrant_url.rstrip("/") + f"/collections/{collection_name}"
    payload = {"vectors": {"size": vector_dim, "distance": "Cosine"}}
    try:
        return _qdrant_request("PUT", url, payload, timeout)
    except urllib.error.HTTPError as e:
        # Qdrant may return conflict/exists depending version. Treat as visible status, not hidden success.
        return {"status": "http_error", "code": e.code, "body": e.read().decode("utf-8", errors="replace")}


def _upsert_points(qdrant_url: str, collection_name: str, points: Sequence[Mapping[str, Any]], timeout: int) -> Dict[str, Any]:
    url = qdrant_url.rstrip("/") + f"/collections/{collection_name}/points?wait=true"
    qpoints = [{"id": p["id"], "vector": p["vector"], "payload": p["payload"]} for p in points]
    return _qdrant_request("PUT", url, {"points": qpoints}, timeout)


def _query_points(qdrant_url: str, collection_name: str, vector: Sequence[float], top_k: int, timeout: int) -> Dict[str, Any]:
    # Use the older /points/search endpoint for broad local Qdrant compatibility.
    url = qdrant_url.rstrip("/") + f"/collections/{collection_name}/points/search"
    payload = {"vector": list(vector), "limit": top_k, "with_payload": True}
    return _qdrant_request("POST", url, payload, timeout)


def build_qdrant_adapter_manifest(
    *,
    vector_loader: str | Path,
    output_dir: str | Path,
    collection_name: str = "trace_net_engineering_engram_memory_v1",
    qdrant_url: str = "http://127.0.0.1:6333",
    vector_dim: int = 64,
    top_k: int = 5,
    min_records: int = 1,
    min_local_queries: int = 3,
    require_all_layers: bool = False,
    require_source_quality_pass: bool = False,
    require_no_answer_permission: bool = False,
    enable_live_qdrant_write: bool = False,
    enable_live_qdrant_read: bool = False,
    qdrant_timeout_seconds: int = 30,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    vector_loader = Path(vector_loader)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source = _read_json(vector_loader)

    source_quality = source.get("quality_status") or source.get("summary", {}).get("quality_status")
    points = normalize_qdrant_records(source, collection_name=collection_name)
    layer_counts: Dict[str, int] = {}
    unsafe_findings: List[str] = []
    answer_permission_count = 0
    for p in points:
        layer = str(p.get("memory_layer") or "unknown")
        layer_counts[layer] = layer_counts.get(layer, 0) + 1
        payload = p.get("payload") or {}
        if payload.get("answer_permission") is True:
            answer_permission_count += 1
        if payload.get("engram_guidance_only") is not True:
            unsafe_findings.append(f"payload_not_guidance_only:{p.get('atom_id')}")
        if payload.get("manual_claims_require_proof_context") is not True:
            unsafe_findings.append(f"missing_proof_context_boundary:{p.get('atom_id')}")

    missing_layers = sorted(REQUIRED_LAYERS - set(layer_counts)) if require_all_layers else []
    if missing_layers:
        unsafe_findings.append("missing_layers:" + ",".join(missing_layers))

    # Local retrieval smoke, even when live Qdrant is disabled.
    default_queries = [
        {"query_id": "q_interchangeability", "query_text": "interchangeability requires explicit authority replacement approval"},
        {"query_id": "q_visual_ocr", "query_text": "visual figure link OCR nomenclature line text proof"},
        {"query_id": "q_unknown_part", "query_text": "unknown part no proof_context not source trace ready"},
        {"query_id": "q_safe_generic", "query_text": "safe but too generic repair critic CRAG"},
        {"query_id": "q_summary_limit", "query_text": "v2 summaries guidance only not proof"},
        {"query_id": "q_installation_limit", "query_text": "installation safety fit effectivity approval not proven"},
    ]
    local_queries = default_queries[: max(min_local_queries, 0)]
    local_records = []
    for q in local_queries:
        local_records.append({
            "query_id": q["query_id"],
            "query_text": q["query_text"],
            "results": local_search(points, q["query_text"], top_k=top_k, vector_dim=vector_dim),
        })

    qdrant_write_attempt_count = 0
    qdrant_read_attempt_count = 0
    qdrant_write_result: Dict[str, Any] | None = None
    qdrant_read_results: List[Dict[str, Any]] = []

    if enable_live_qdrant_write:
        qdrant_write_attempt_count += 1
        create_result = _create_collection(qdrant_url, collection_name, vector_dim, qdrant_timeout_seconds)
        upsert_result = _upsert_points(qdrant_url, collection_name, points, qdrant_timeout_seconds)
        qdrant_write_result = {"create_collection": create_result, "upsert_points": upsert_result}

    if enable_live_qdrant_read:
        for q in local_queries:
            qdrant_read_attempt_count += 1
            qv = _hash_embed(q["query_text"], vector_dim)
            try:
                live = _query_points(qdrant_url, collection_name, qv, top_k, qdrant_timeout_seconds)
            except Exception as e:  # visible failure in manifest
                live = {"status": "error", "error": repr(e)}
            qdrant_read_results.append({"query_id": q["query_id"], "query_text": q["query_text"], "live_qdrant_result": live})

    postgres_write_attempt_count = 0
    opensearch_write_attempt_count = 0
    opensearch_upload_attempt_count = 0
    source_truth_mutation_allowed_count = 0
    write_attempt_count = qdrant_write_attempt_count

    quality_failures: List[str] = []
    if require_source_quality_pass and source_quality != "PASS":
        quality_failures.append("source_vector_loader_quality_status_not_pass")
    if len(points) < min_records:
        quality_failures.append(f"record_count_below_min:{len(points)}<{min_records}")
    if require_no_answer_permission and answer_permission_count != 0:
        quality_failures.append("answer_permission_count_nonzero")
    if len(unsafe_findings) > max_unsafe:
        quality_failures.append(f"unsafe_finding_count_above_max:{len(unsafe_findings)}>{max_unsafe}")
    if write_attempt_count > max_write_attempts:
        quality_failures.append(f"write_attempt_count_above_max:{write_attempt_count}>{max_write_attempts}")
    if enable_live_qdrant_write and not qdrant_write_result:
        quality_failures.append("live_qdrant_write_enabled_but_no_result")
    if enable_live_qdrant_read and len(qdrant_read_results) < len(local_queries):
        quality_failures.append("live_qdrant_read_incomplete")

    quality_status = "PASS" if not quality_failures else "FAIL"

    points_jsonl = output_dir / "trace_net_engineering_engram_qdrant_points_v1.jsonl"
    local_jsonl = output_dir / "trace_net_engineering_engram_qdrant_local_retrieval_smoke_v1.jsonl"
    _write_jsonl(points_jsonl, points)
    _write_jsonl(local_jsonl, local_records)

    manifest = {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_QDRANT_ADAPTER_BUILT",
        "quality_status": quality_status,
        "module": MODULE,
        "version": VERSION,
        "source_vector_loader_path": str(vector_loader),
        "collection_plan": {
            "collection_name": collection_name,
            "qdrant_url": qdrant_url,
            "vector_dim": vector_dim,
            "distance": "Cosine",
            "encoder": source.get("collection_plan", {}).get("encoder", "trace_net_hashing_encoder_v1"),
            "live_qdrant_write_enabled": bool(enable_live_qdrant_write),
            "live_qdrant_read_enabled": bool(enable_live_qdrant_read),
            "live_qdrant_write_attempted": qdrant_write_attempt_count > 0,
            "live_qdrant_read_attempted": qdrant_read_attempt_count > 0,
            "safety_note": "Live Qdrant IO is disabled unless explicit enable flags are used.",
        },
        "summary": {
            "module": MODULE,
            "version": VERSION,
            "source_vector_loader_quality_status": source_quality,
            "qdrant_ready_record_count": len(points),
            "qdrant_point_record_count": len(points),
            "memory_layer_counts": layer_counts,
            "missing_layers": missing_layers,
            "local_retrieval_query_count": len(local_records),
            "qdrant_write_attempt_count": qdrant_write_attempt_count,
            "qdrant_read_attempt_count": qdrant_read_attempt_count,
            "postgres_write_attempt_count": postgres_write_attempt_count,
            "opensearch_write_attempt_count": opensearch_write_attempt_count,
            "opensearch_upload_attempt_count": opensearch_upload_attempt_count,
            "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
            "answer_permission_count": answer_permission_count,
            "write_attempt_count": write_attempt_count,
            "unsafe_finding_count": len(unsafe_findings),
            "unsafe_findings": unsafe_findings,
            "quality_failures": quality_failures,
            "ready_for_live_qdrant_write": quality_status == "PASS" and not enable_live_qdrant_write,
            "ready_for_live_qdrant_search": quality_status == "PASS",
        },
        "qdrant_point_records_path": str(points_jsonl),
        "local_retrieval_smoke_path": str(local_jsonl),
        "local_retrieval_records": local_records,
        "live_qdrant_write_result": qdrant_write_result,
        "live_qdrant_read_results": qdrant_read_results,
        "adapter_policy": {
            "mode": "artifact_first_qdrant_adapter",
            "proof_boundary": "Engram vectors retrieve behavior guidance only; factual manual claims still require proof_context citations.",
            "forbidden": [
                "answer_permission_from_engram_vector",
                "source_truth_mutation_from_engram_vector",
                "summary_or_engram_used_as_proof",
                "live_qdrant_io_without_explicit_enable_flags",
            ],
            "explicit_live_flags": ["--enable-live-qdrant-write", "--enable-live-qdrant-read"],
        },
    }

    manifest_path = output_dir / "trace_net_engineering_engram_qdrant_adapter_v1.json"
    _write_json(manifest_path, manifest)
    check_path = output_dir / "trace_net_engineering_engram_qdrant_adapter_v1_quality_check.json"
    _write_json(check_path, {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_QDRANT_ADAPTER_CHECKED",
        "quality_status": quality_status,
        "summary": manifest["summary"],
    })
    return manifest


def check_qdrant_adapter_manifest(
    *,
    qdrant_adapter: str | Path,
    min_records: int = 1,
    min_local_queries: int = 0,
    require_quality_pass: bool = False,
    require_all_layers: bool = False,
    require_no_answer_permission: bool = False,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    data = _read_json(qdrant_adapter)
    summary = data.get("summary", {})
    quality_failures: List[str] = []
    if require_quality_pass and data.get("quality_status") != "PASS":
        quality_failures.append("source_quality_status_not_pass")
    if int(summary.get("qdrant_point_record_count") or 0) < min_records:
        quality_failures.append("record_count_below_min")
    if int(summary.get("local_retrieval_query_count") or 0) < min_local_queries:
        quality_failures.append("local_query_count_below_min")
    if require_all_layers and summary.get("missing_layers"):
        quality_failures.append("missing_required_layers")
    if require_no_answer_permission and int(summary.get("answer_permission_count") or 0) != 0:
        quality_failures.append("answer_permission_count_nonzero")
    if int(summary.get("unsafe_finding_count") or 0) > max_unsafe:
        quality_failures.append("unsafe_finding_count_above_max")
    if int(summary.get("write_attempt_count") or 0) > max_write_attempts:
        quality_failures.append("write_attempt_count_above_max")
    quality_status = "PASS" if not quality_failures else "FAIL"
    result = {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_QDRANT_ADAPTER_CHECKED",
        "quality_status": quality_status,
        "qdrant_point_record_count": int(summary.get("qdrant_point_record_count") or 0),
        "local_retrieval_query_count": int(summary.get("local_retrieval_query_count") or 0),
        "memory_layer_counts": summary.get("memory_layer_counts", {}),
        "qdrant_write_attempt_count": int(summary.get("qdrant_write_attempt_count") or 0),
        "qdrant_read_attempt_count": int(summary.get("qdrant_read_attempt_count") or 0),
        "answer_permission_count": int(summary.get("answer_permission_count") or 0),
        "unsafe_finding_count": int(summary.get("unsafe_finding_count") or 0),
        "write_attempt_count": int(summary.get("write_attempt_count") or 0),
        "quality_failures": quality_failures,
    }
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build TRACE-Net Engineering Engram Qdrant adapter artifact.")
    p.add_argument("--vector-loader", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--collection-name", default="trace_net_engineering_engram_memory_v1")
    p.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    p.add_argument("--vector-dim", type=int, default=64)
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--min-records", type=int, default=1)
    p.add_argument("--min-local-queries", type=int, default=3)
    p.add_argument("--require-all-layers", action="store_true")
    p.add_argument("--require-source-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--enable-live-qdrant-write", action="store_true")
    p.add_argument("--enable-live-qdrant-read", action="store_true")
    p.add_argument("--qdrant-timeout-seconds", type=int, default=30)
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    manifest = build_qdrant_adapter_manifest(**vars(args))
    s = manifest.get("summary", {})
    print("status=" + str(manifest.get("status")))
    print("quality_status=" + str(manifest.get("quality_status")))
    print("qdrant_point_record_count=" + str(s.get("qdrant_point_record_count")))
    print("local_retrieval_query_count=" + str(s.get("local_retrieval_query_count")))
    print("qdrant_write_attempt_count=" + str(s.get("qdrant_write_attempt_count")))
    print("qdrant_read_attempt_count=" + str(s.get("qdrant_read_attempt_count")))
    print("unsafe_finding_count=" + str(s.get("unsafe_finding_count")))
    print("answer_permission_count=" + str(s.get("answer_permission_count")))
    print("write_attempt_count=" + str(s.get("write_attempt_count")))
    print("output=" + str(Path(args.output_dir) / "trace_net_engineering_engram_qdrant_adapter_v1.json"))
    return 0 if manifest.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
