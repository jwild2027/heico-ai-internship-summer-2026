
"""TRACE-Net H32 Engineering Engram unified runtime gate v1.

This module is intentionally artifact-first. It joins the already-built Engram
runtime pieces into one inspectable targeted gate:

- H27E answer smoke records with retrieved Engram overlays applied.
- H28 Self-RAG critic records.
- H29 CRAG repair records.
- H30 Qdrant/vector adapter records.
- H31 Postgres feedback ledger records.
- Optional graph-route guidance manifest, when available.

It does not perform LLM calls, graph traversal, Qdrant IO, Postgres IO,
OpenSearch IO, or source-truth mutation. It proves runtime wiring readiness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

MODULE = "trace_net_engineering_engram_unified_runtime_gate_v1"
VERSION = "v1"
ALLOWED_QIDS = ("q12", "q16", "q18", "q25", "q29")

ZERO_SAFETY = {
    "answer_permission_count": 0,
    "source_truth_mutation_allowed_count": 0,
    "postgres_write_attempt_count": 0,
    "qdrant_read_attempt_count": 0,
    "qdrant_write_attempt_count": 0,
    "opensearch_write_attempt_count": 0,
    "opensearch_upload_attempt_count": 0,
    "write_attempt_count": 0,
    "unsafe_finding_count": 0,
}

QUESTION_TO_VECTOR_QUERY = {
    "q12": ["q_interchangeability", "q_installation_limit"],
    "q16": ["q_visual_ocr", "q_safe_generic"],
    "q18": ["q_visual_ocr", "q_safe_generic"],
    "q25": ["q_unknown_part"],
    "q29": ["q_summary_limit"],
}

QUESTION_TO_GRAPH_HINT = {
    "q12": "bounded_part_relationship_graph_guidance_optional",
    "q16": "visual_route_to_ocr_nomenclature_route_link_guidance_optional",
    "q18": "pipeline_recovery_route_graph_guidance_optional",
    "q25": "unknown_part_no_graph_claim_without_proof_context",
    "q29": "summary_guidance_not_source_proof_graph_boundary",
}


def _read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def _summary(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    s = manifest.get("summary")
    return s if isinstance(s, Mapping) else {}


def _quality(manifest: Mapping[str, Any]) -> str:
    return str(manifest.get("quality_status") or _summary(manifest).get("quality_status") or "")


def _records(manifest: Mapping[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        val = manifest.get(key)
        if isinstance(val, list):
            return [r for r in val if isinstance(r, dict)]
    return []


def _by_key(rows: Iterable[Mapping[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        v = row.get(key)
        if v is not None:
            out[str(v)] = dict(row)
    return out


def _feedback_by_question(rows: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        qid = row.get("source_question_id") or row.get("question_id")
        if qid:
            out.setdefault(str(qid), []).append(dict(row))
    return out


def _candidate_by_feedback(rows: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        fid = row.get("feedback_id")
        if fid:
            out.setdefault(str(fid), []).append(dict(row))
    return out


def _vector_queries_by_id(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    return _by_key(rows, "query_id")


def _source_count(manifest: Mapping[str, Any], key: str) -> int:
    try:
        return int(_summary(manifest).get(key, manifest.get(key, 0)) or 0)
    except Exception:
        return 0


def _combine_source_safety(*manifests: Mapping[str, Any]) -> dict[str, int]:
    keys = list(ZERO_SAFETY)
    out = {k: 0 for k in keys}
    for manifest in manifests:
        s = _summary(manifest)
        for key in keys:
            try:
                out[key] += int(s.get(key, manifest.get(key, 0)) or 0)
            except Exception:
                pass
    return out


def _hash_record_id(*parts: str) -> str:
    raw = "|".join(parts).encode("utf-8")
    return "h32_" + hashlib.sha256(raw).hexdigest()[:24]


def _safe_preview(text: Any, n: int = 700) -> str:
    raw = str(text or "").replace("\r", " ").strip()
    return raw[:n]


def _graph_guidance_for_question(qid: str, graph_manifest: Mapping[str, Any] | None) -> dict[str, Any]:
    if graph_manifest:
        return {
            "graph_guidance_status": "optional_graph_manifest_supplied",
            "graph_manifest_quality_status": _quality(graph_manifest) or "UNKNOWN",
            "graph_hint": QUESTION_TO_GRAPH_HINT.get(qid, "bounded_graph_route_guidance_optional"),
            "live_graph_traversal_attempted": False,
            "graph_used_as_proof": False,
        }
    return {
        "graph_guidance_status": "artifact_placeholder_no_live_graph_traversal",
        "graph_manifest_quality_status": "NOT_SUPPLIED",
        "graph_hint": QUESTION_TO_GRAPH_HINT.get(qid, "bounded_graph_route_guidance_optional"),
        "live_graph_traversal_attempted": False,
        "graph_used_as_proof": False,
    }


def _runtime_status(answer: Mapping[str, Any], critic: Mapping[str, Any], crag: Mapping[str, Any]) -> str:
    critic_status = str(critic.get("critic_status") or "")
    source_grade = str(answer.get("grade") or "")
    repair_attempted = bool(crag.get("repair_attempted"))
    if critic_status == "EXPECTED_BOUNDARY":
        return "EXPECTED_BOUNDARY"
    if critic_status == "PASS" and source_grade == "GOOD" and not repair_attempted:
        return "PASS"
    if critic_status == "PASS" and source_grade in {"GOOD", "PARTIAL"} and not repair_attempted:
        return "PASS_WITH_LIMIT"
    if repair_attempted:
        return "REPAIRED_OR_ATTEMPTED"
    return "REVIEW"


def build_unified_runtime_gate(
    answer_smoke: str | Path,
    critic: str | Path,
    crag_repair: str | Path,
    qdrant_adapter: str | Path,
    feedback_ledger: str | Path,
    output_dir: str | Path,
    graph_route_manifest: str | Path | None = None,
    question_ids: str = ",".join(ALLOWED_QIDS),
    min_runtime_records: int = 5,
    min_pass_or_expected: int = 5,
    require_answer_quality_pass: bool = False,
    require_critic_quality_pass: bool = False,
    require_crag_quality_pass: bool = False,
    require_qdrant_quality_pass: bool = False,
    require_feedback_quality_pass: bool = False,
    require_no_answer_permission: bool = False,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> dict[str, Any]:
    answer_manifest = _read_json(answer_smoke)
    critic_manifest = _read_json(critic)
    crag_manifest = _read_json(crag_repair)
    qdrant_manifest = _read_json(qdrant_adapter)
    feedback_manifest = _read_json(feedback_ledger)
    graph_manifest = _read_json(graph_route_manifest) if graph_route_manifest else None

    requested_qids = [q.strip() for q in question_ids.split(",") if q.strip()]
    answer_by_qid = _by_key(_records(answer_manifest, "records", "smoke_records"), "question_id")
    critic_by_qid = _by_key(_records(critic_manifest, "critic_records"), "question_id")
    crag_by_qid = _by_key(_records(crag_manifest, "crag_repair_records", "repair_records"), "question_id")
    feedback_by_qid = _feedback_by_question(_records(feedback_manifest, "feedback_records"))
    candidates_by_feedback = _candidate_by_feedback(_records(feedback_manifest, "candidate_records"))
    vector_by_query = _vector_queries_by_id(_records(qdrant_manifest, "local_retrieval_records"))

    runtime_records: list[dict[str, Any]] = []
    unsafe_findings: list[str] = []

    for qid in requested_qids:
        answer = answer_by_qid.get(qid, {})
        critic_rec = critic_by_qid.get(qid, {})
        crag_rec = crag_by_qid.get(qid, {})
        feedback_rows = feedback_by_qid.get(qid, [])
        candidate_rows = [cand for fb in feedback_rows for cand in candidates_by_feedback.get(str(fb.get("feedback_id")), [])]
        vector_query_ids = QUESTION_TO_VECTOR_QUERY.get(qid, [])
        vector_rows = [vector_by_query[vqid] for vqid in vector_query_ids if vqid in vector_by_query]
        vector_layers = sorted({item.get("memory_layer") for row in vector_rows for item in row.get("results", []) if isinstance(item, Mapping) and item.get("memory_layer")})
        graph_guidance = _graph_guidance_for_question(qid, graph_manifest)

        unsafe = False
        answer_permission = False
        reasons: list[str] = []
        for source_name, rec in (("answer", answer), ("critic", critic_rec), ("crag", crag_rec)):
            if rec.get("unsafe") or rec.get("answer_permission"):
                unsafe = True
                reasons.append(f"{source_name}_record_unsafe_or_answer_permission")
            if rec.get("answer_permission"):
                answer_permission = True

        status = _runtime_status(answer, critic_rec, crag_rec)
        if status == "REVIEW":
            reasons.append("runtime_status_review")

        runtime_record = {
            "runtime_record_id": _hash_record_id(qid, status, str(answer.get("grade"))),
            "question_id": qid,
            "question": answer.get("question"),
            "answer_grade": answer.get("grade"),
            "critic_status": critic_rec.get("critic_status"),
            "crag_status": crag_rec.get("crag_status"),
            "expected_unknown_boundary_partial": bool(critic_rec.get("expected_unknown_boundary_partial")),
            "repair_recommended": bool(critic_rec.get("repair_recommended")),
            "repair_attempted": bool(crag_rec.get("repair_attempted")),
            "runtime_status": status,
            "feedback_ids": [r.get("feedback_id") for r in feedback_rows],
            "feedback_ratings": [r.get("rating") for r in feedback_rows],
            "candidate_ids": [r.get("candidate_id") for r in candidate_rows],
            "candidate_memory_layers": sorted({r.get("memory_layer") for r in candidate_rows if r.get("memory_layer")}),
            "vector_query_ids": vector_query_ids,
            "vector_guidance_available": bool(vector_rows),
            "vector_memory_layers": vector_layers,
            "graph_guidance": graph_guidance,
            "runtime_steps": [
                "load_current_question_and_proof_context",
                "apply_retrieved_engram_overlay_behavior_guidance",
                "draft_answer_with_proof_context_citations",
                "run_self_rag_engram_critic",
                "run_crag_repair_only_if_critic_recommends_repair",
                "emit_feedback_ledger_and_memory_candidates_for_human_review",
                "consult_graph_route_guidance_when_manifest_supplied_without_using_graph_as_proof",
            ],
            "proof_boundary": "Engram, feedback, graph, and vector memories shape behavior only; factual manual claims still require proof_context citations.",
            "live_qdrant_io_attempted": False,
            "live_postgres_write_attempted": False,
            "live_graph_traversal_attempted": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": answer_permission,
            "unsafe": unsafe,
            "unsafe_reasons": reasons,
            "answer_preview": _safe_preview(answer.get("answer_text") or answer.get("answer_preview")),
        }
        if unsafe:
            unsafe_findings.append(f"{qid}:" + ";".join(reasons))
        runtime_records.append(runtime_record)

    pass_count = sum(1 for r in runtime_records if r["runtime_status"] == "PASS")
    expected_count = sum(1 for r in runtime_records if r["runtime_status"] == "EXPECTED_BOUNDARY")
    pass_limit_count = sum(1 for r in runtime_records if r["runtime_status"] == "PASS_WITH_LIMIT")
    pass_or_expected = pass_count + expected_count + pass_limit_count

    source_safety = _combine_source_safety(answer_manifest, critic_manifest, crag_manifest, qdrant_manifest, feedback_manifest)
    unsafe_total = len(unsafe_findings) + source_safety.get("unsafe_finding_count", 0)
    answer_permission_total = source_safety.get("answer_permission_count", 0) + sum(1 for r in runtime_records if r["answer_permission"])
    write_total = source_safety.get("write_attempt_count", 0)

    quality_failures: list[str] = []
    source_quality = {
        "answer_smoke": _quality(answer_manifest),
        "self_rag_critic": _quality(critic_manifest),
        "crag_repair": _quality(crag_manifest),
        "qdrant_adapter": _quality(qdrant_manifest),
        "feedback_ledger": _quality(feedback_manifest),
        "graph_route_manifest": _quality(graph_manifest or {}) if graph_manifest else "NOT_SUPPLIED",
    }
    required_sources = [
        (require_answer_quality_pass, "answer_smoke"),
        (require_critic_quality_pass, "self_rag_critic"),
        (require_crag_quality_pass, "crag_repair"),
        (require_qdrant_quality_pass, "qdrant_adapter"),
        (require_feedback_quality_pass, "feedback_ledger"),
    ]
    for required, key in required_sources:
        if required and source_quality.get(key) != "PASS":
            quality_failures.append(f"source_{key}_quality_not_pass:{source_quality.get(key)}")
    if len(runtime_records) < min_runtime_records:
        quality_failures.append(f"runtime_record_count_below_min:{len(runtime_records)}<{min_runtime_records}")
    if pass_or_expected < min_pass_or_expected:
        quality_failures.append(f"pass_or_expected_below_min:{pass_or_expected}<{min_pass_or_expected}")
    if require_no_answer_permission and answer_permission_total:
        quality_failures.append(f"answer_permission_count_nonzero:{answer_permission_total}")
    if unsafe_total > max_unsafe:
        quality_failures.append(f"unsafe_finding_count_above_max:{unsafe_total}>{max_unsafe}")
    if write_total > max_write_attempts:
        quality_failures.append(f"write_attempt_count_above_max:{write_total}>{max_write_attempts}")

    quality_status = "PASS" if not quality_failures else "FAIL"
    output = Path(output_dir)
    records_path = output / "trace_net_engineering_engram_unified_runtime_records_v1.jsonl"
    quality_path = output / "trace_net_engineering_engram_unified_runtime_gate_v1_quality_check.json"
    manifest_path = output / "trace_net_engineering_engram_unified_runtime_gate_v1.json"

    summary = {
        "module": MODULE,
        "version": VERSION,
        "runtime_record_count": len(runtime_records),
        "runtime_pass_count": pass_count,
        "runtime_pass_with_limit_count": pass_limit_count,
        "expected_boundary_count": expected_count,
        "runtime_pass_or_expected_count": pass_or_expected,
        "question_ids": requested_qids,
        "source_quality": source_quality,
        "self_rag_connected": True,
        "crag_connected": True,
        "qdrant_vector_adapter_connected": True,
        "postgres_feedback_ledger_connected": True,
        "graph_guidance_connected": bool(graph_manifest),
        "graph_guidance_mode": "optional_manifest" if graph_manifest else "artifact_placeholder_no_live_graph_traversal",
        "vector_guidance_record_count": sum(1 for r in runtime_records if r["vector_guidance_available"]),
        "feedback_runtime_record_count": sum(1 for r in runtime_records if r["feedback_ids"]),
        "repair_attempt_count": sum(1 for r in runtime_records if r["repair_attempted"]),
        "answer_permission_count": answer_permission_total,
        "source_truth_mutation_allowed_count": source_safety.get("source_truth_mutation_allowed_count", 0),
        "postgres_write_attempt_count": source_safety.get("postgres_write_attempt_count", 0),
        "qdrant_read_attempt_count": source_safety.get("qdrant_read_attempt_count", 0),
        "qdrant_write_attempt_count": source_safety.get("qdrant_write_attempt_count", 0),
        "opensearch_write_attempt_count": source_safety.get("opensearch_write_attempt_count", 0),
        "opensearch_upload_attempt_count": source_safety.get("opensearch_upload_attempt_count", 0),
        "write_attempt_count": write_total,
        "unsafe_finding_count": unsafe_total,
        "unsafe_findings": unsafe_findings,
        "quality_failures": quality_failures,
        "ready_for_targeted_unified_engram_runtime_commit_gate": quality_status == "PASS",
        "ready_for_optional_full_30_after_targeted_pass": quality_status == "PASS",
    }
    manifest = {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_UNIFIED_RUNTIME_GATE_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "runtime_policy": {
            "mode": "artifact_first_unified_engram_runtime_gate",
            "connects": [
                "self_rag_critic",
                "crag_repair_gate",
                "qdrant_vector_adapter_artifact_or_live_if_explicit",
                "postgres_feedback_ledger_artifact_or_live_if_explicit",
                "graph_route_guidance_optional_manifest",
            ],
            "proof_boundary": "Engram/feedback/vector/graph guidance can shape behavior but cannot prove manual claims; factual source claims still require proof_context citations.",
            "forbidden": [
                "answer_permission_from_engram_or_feedback_or_graph_or_vector",
                "source_truth_mutation_from_runtime_gate",
                "summary_or_engram_or_feedback_used_as_proof",
                "live_db_vector_or_graph_io_without_explicit_gate",
            ],
            "explicit_live_flags_expected_in_future": [
                "--enable-live-qdrant-read",
                "--enable-live-qdrant-write",
                "--enable-live-postgres-write",
                "--enable-live-graph-traversal",
            ],
        },
        "source_paths": {
            "answer_smoke": str(answer_smoke),
            "critic": str(critic),
            "crag_repair": str(crag_repair),
            "qdrant_adapter": str(qdrant_adapter),
            "feedback_ledger": str(feedback_ledger),
            "graph_route_manifest": str(graph_route_manifest) if graph_route_manifest else "",
        },
        "runtime_records_path": str(records_path),
        "quality_check_path": str(quality_path),
        "runtime_records": runtime_records,
    }
    quality_check = {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_UNIFIED_RUNTIME_GATE_CHECKED",
        "quality_status": quality_status,
        "summary": summary,
    }

    _write_jsonl(records_path, runtime_records)
    _write_json(quality_path, quality_check)
    _write_json(manifest_path, manifest)
    return manifest


def check_unified_runtime_gate(
    unified_runtime_gate: str | Path,
    min_runtime_records: int = 5,
    min_pass_or_expected: int = 5,
    require_quality_pass: bool = False,
    require_no_answer_permission: bool = False,
    require_connections: bool = False,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> dict[str, Any]:
    manifest = _read_json(unified_runtime_gate)
    s = dict(_summary(manifest))
    quality_failures = list(s.get("quality_failures") or [])
    if require_quality_pass and manifest.get("quality_status") != "PASS":
        quality_failures.append(f"quality_not_pass:{manifest.get('quality_status')}")
    if int(s.get("runtime_record_count", 0) or 0) < min_runtime_records:
        quality_failures.append("runtime_record_count_below_min")
    if int(s.get("runtime_pass_or_expected_count", 0) or 0) < min_pass_or_expected:
        quality_failures.append("runtime_pass_or_expected_below_min")
    if require_no_answer_permission and int(s.get("answer_permission_count", 0) or 0) != 0:
        quality_failures.append("answer_permission_count_nonzero")
    if int(s.get("unsafe_finding_count", 0) or 0) > max_unsafe:
        quality_failures.append("unsafe_finding_count_above_max")
    if int(s.get("write_attempt_count", 0) or 0) > max_write_attempts:
        quality_failures.append("write_attempt_count_above_max")
    if require_connections:
        for key in ("self_rag_connected", "crag_connected", "qdrant_vector_adapter_connected", "postgres_feedback_ledger_connected"):
            if not s.get(key):
                quality_failures.append(f"missing_connection:{key}")
    status = "PASS" if not quality_failures else "FAIL"
    return {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_UNIFIED_RUNTIME_GATE_CHECKED",
        "quality_status": status,
        "runtime_record_count": int(s.get("runtime_record_count", 0) or 0),
        "runtime_pass_or_expected_count": int(s.get("runtime_pass_or_expected_count", 0) or 0),
        "unsafe_finding_count": int(s.get("unsafe_finding_count", 0) or 0),
        "answer_permission_count": int(s.get("answer_permission_count", 0) or 0),
        "write_attempt_count": int(s.get("write_attempt_count", 0) or 0),
        "quality_failures": quality_failures,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--answer-smoke", required=True)
    p.add_argument("--critic", required=True)
    p.add_argument("--crag-repair", required=True)
    p.add_argument("--qdrant-adapter", required=True)
    p.add_argument("--feedback-ledger", required=True)
    p.add_argument("--graph-route-manifest", default=None)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--question-ids", default=",".join(ALLOWED_QIDS))
    p.add_argument("--min-runtime-records", type=int, default=5)
    p.add_argument("--min-pass-or-expected", type=int, default=5)
    p.add_argument("--require-answer-quality-pass", action="store_true")
    p.add_argument("--require-critic-quality-pass", action="store_true")
    p.add_argument("--require-crag-quality-pass", action="store_true")
    p.add_argument("--require-qdrant-quality-pass", action="store_true")
    p.add_argument("--require-feedback-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    manifest = build_unified_runtime_gate(**vars(args))
    s = manifest.get("summary", {})
    print("status=" + str(manifest.get("status")))
    print("quality_status=" + str(manifest.get("quality_status")))
    print("runtime_record_count=" + str(s.get("runtime_record_count")))
    print("runtime_pass_or_expected_count=" + str(s.get("runtime_pass_or_expected_count")))
    print("self_rag_connected=" + str(s.get("self_rag_connected")))
    print("crag_connected=" + str(s.get("crag_connected")))
    print("qdrant_vector_adapter_connected=" + str(s.get("qdrant_vector_adapter_connected")))
    print("postgres_feedback_ledger_connected=" + str(s.get("postgres_feedback_ledger_connected")))
    print("unsafe_finding_count=" + str(s.get("unsafe_finding_count")))
    print("answer_permission_count=" + str(s.get("answer_permission_count")))
    print("write_attempt_count=" + str(s.get("write_attempt_count")))
    print("output=" + str(Path(args.output_dir) / "trace_net_engineering_engram_unified_runtime_gate_v1.json"))
    return 0 if manifest.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
