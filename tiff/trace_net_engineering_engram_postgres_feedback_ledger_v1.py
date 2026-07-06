from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

MODULE = "trace_net_engineering_engram_postgres_feedback_ledger_v1"
VERSION = "v1"

MEMORY_LAYERS = {"working_memory", "semantic_memory", "procedural_memory", "episodic_memory", "trait_memory", "critic_memory"}

SAFETY_CONTRACT = {
    "answer_permission": False,
    "source_truth_mutation_allowed": False,
    "postgres_write_attempt": False,
    "qdrant_write_attempt": False,
    "qdrant_read_attempt": False,
    "opensearch_write_attempt": False,
    "opensearch_upload_attempt": False,
    "write_attempt": False,
}

SCHEMA_SQL = """
-- TRACE-Net Engineering Engram feedback ledger v1
-- Safety: feedback rows are behavior memory only; they are not proof_context.
CREATE TABLE IF NOT EXISTS trace_net_engram_feedback_ledger_v1 (
    feedback_id TEXT PRIMARY KEY,
    source_question_id TEXT NOT NULL,
    feedback_source TEXT NOT NULL,
    rating TEXT NOT NULL,
    explanation TEXT NOT NULL,
    source_grade TEXT,
    critic_status TEXT,
    crag_status TEXT,
    recommended_memory_layer TEXT NOT NULL,
    recommended_memory_type TEXT NOT NULL,
    proof_role TEXT NOT NULL DEFAULT 'guidance_only',
    answer_permission BOOLEAN NOT NULL DEFAULT FALSE,
    source_truth_mutation_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS trace_net_engram_memory_candidate_v1 (
    candidate_id TEXT PRIMARY KEY,
    feedback_id TEXT NOT NULL REFERENCES trace_net_engram_feedback_ledger_v1(feedback_id),
    memory_layer TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    proof_role TEXT NOT NULL DEFAULT 'guidance_only',
    candidate_rule TEXT NOT NULL,
    candidate_trigger TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending_human_review',
    answer_permission BOOLEAN NOT NULL DEFAULT FALSE,
    source_truth_mutation_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
""".strip() + "\n"


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records), encoding="utf-8")


def _stable_id(prefix: str, *parts: Any) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8", errors="replace"))
        h.update(b"\x1f")
    return f"{prefix}_{h.hexdigest()[:24]}"


def _load_jsonl(path: str | Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _records_by_id(records: Iterable[Mapping[str, Any]], key: str = "question_id") -> dict[str, Mapping[str, Any]]:
    return {str(r.get(key) or ""): r for r in records if r.get(key)}


def _answer_records(answer_smoke: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list(answer_smoke.get("records") or answer_smoke.get("smoke_records") or [])


def _critic_records(critic: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list(critic.get("critic_records") or [])


def _crag_records(crag: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list(crag.get("crag_repair_records") or crag.get("repair_records") or [])


def _rating_for(answer: Mapping[str, Any], critic: Mapping[str, Any] | None, crag: Mapping[str, Any] | None) -> tuple[str, str, str, str]:
    qid = str(answer.get("question_id") or "")
    grade = str(answer.get("grade") or "UNKNOWN")
    critic_status = str((critic or {}).get("critic_status") or "UNKNOWN")
    expected_boundary = bool((critic or {}).get("expected_unknown_boundary_partial"))
    crag_status = str((crag or {}).get("crag_status") or "NO_CRAG_RECORD")

    if expected_boundary:
        return (
            "expected_boundary",
            "episodic_memory",
            "expected unknown/no-proof boundary was preserved safely; do not over-repair this case.",
            "unknown part; no proof_context; not source-trace-ready",
        )
    if grade == "GOOD" and critic_status == "PASS":
        return (
            "thumbs_up",
            "critic_memory" if "generic" in " ".join(map(str, (critic or {}).get("findings", []))).lower() else "episodic_memory",
            "answer passed critic checks; preserve this response pattern as behavior guidance.",
            "critic pass; citation safe; proof boundary preserved",
        )
    if critic_status in {"REVIEW", "REPAIR_RECOMMENDED"} or bool((critic or {}).get("repair_recommended")):
        return (
            "thumbs_down",
            "critic_memory",
            "critic recommended review/repair; retrieve this feedback before regenerating similar answers.",
            "repair recommended; self-rag review; crag repair",
        )
    return (
        "neutral_review",
        "episodic_memory",
        "record preserved as evaluation memory; do not treat as proof.",
        "evaluation memory; behavior guidance",
    )


def _normalize_feedback_records(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in records:
        qid = str(r.get("question_id") or r.get("source_question_id") or "manual_feedback")
        rating = str(r.get("rating") or r.get("feedback_rating") or "neutral_review")
        explanation = str(r.get("explanation") or r.get("feedback_text") or "Manual feedback record.")
        layer = str(r.get("recommended_memory_layer") or r.get("memory_layer") or ("critic_memory" if rating in {"thumbs_down", "negative"} else "episodic_memory"))
        if layer not in MEMORY_LAYERS:
            layer = "episodic_memory"
        out.append({
            "feedback_id": str(r.get("feedback_id") or _stable_id("fb", qid, rating, explanation)),
            "source_question_id": qid,
            "feedback_source": str(r.get("feedback_source") or "manual_feedback_jsonl"),
            "rating": rating,
            "explanation": explanation,
            "source_grade": str(r.get("source_grade") or "manual"),
            "critic_status": str(r.get("critic_status") or "manual"),
            "crag_status": str(r.get("crag_status") or "manual"),
            "recommended_memory_layer": layer,
            "recommended_memory_type": str(r.get("recommended_memory_type") or "feedback_memory"),
            "proof_role": "guidance_only",
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "payload": dict(r),
        })
    return out


def build_feedback_ledger_manifest(
    answer_smoke: str | Path,
    critic: str | Path,
    crag_repair: str | Path,
    output_dir: str | Path,
    feedback_jsonl: str | Path | None = None,
    postgres_dsn: str | None = None,
    enable_live_postgres_write: bool = False,
    min_feedback_records: int = 5,
    min_candidate_records: int = 5,
    require_source_quality_pass: bool = False,
    require_critic_quality_pass: bool = False,
    require_crag_quality_pass: bool = False,
    require_no_answer_permission: bool = False,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> dict[str, Any]:
    answer_manifest = _read_json(answer_smoke)
    critic_manifest = _read_json(critic)
    crag_manifest = _read_json(crag_repair)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    answers = _answer_records(answer_manifest)
    critics_by_qid = _records_by_id(_critic_records(critic_manifest))
    crag_by_qid = _records_by_id(_crag_records(crag_manifest))

    feedback_records: list[dict[str, Any]] = []
    for a in answers:
        qid = str(a.get("question_id") or "")
        c = critics_by_qid.get(qid)
        cr = crag_by_qid.get(qid)
        rating, layer, explanation, trigger = _rating_for(a, c, cr)
        feedback_id = _stable_id("fb", qid, rating, explanation, a.get("answer_preview") or a.get("answer_text") or "")
        feedback_records.append({
            "feedback_id": feedback_id,
            "source_question_id": qid,
            "feedback_source": "self_rag_crag_eval",
            "rating": rating,
            "explanation": explanation,
            "source_grade": str(a.get("grade") or "UNKNOWN"),
            "critic_status": str((c or {}).get("critic_status") or "UNKNOWN"),
            "crag_status": str((cr or {}).get("crag_status") or "NO_REPAIR"),
            "recommended_memory_layer": layer,
            "recommended_memory_type": "critic_memory" if layer == "critic_memory" else "episodic_memory",
            "proof_role": "guidance_only",
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "candidate_trigger": trigger,
            "payload": {
                "question": a.get("question"),
                "source_grade": a.get("grade"),
                "critic_findings": (c or {}).get("findings", []),
                "critic_repair_hints": (c or {}).get("repair_hints", []),
                "crag_status": (cr or {}).get("crag_status"),
            },
        })

    feedback_records.extend(_normalize_feedback_records(_load_jsonl(feedback_jsonl)))

    candidate_records: list[dict[str, Any]] = []
    for fb in feedback_records:
        layer = str(fb.get("recommended_memory_layer") or "episodic_memory")
        if layer not in MEMORY_LAYERS:
            layer = "episodic_memory"
        candidate_id = _stable_id("cand", fb["feedback_id"], layer, fb["explanation"])
        candidate_records.append({
            "candidate_id": candidate_id,
            "feedback_id": fb["feedback_id"],
            "source_question_id": fb["source_question_id"],
            "memory_layer": layer,
            "memory_type": fb.get("recommended_memory_type") or ("critic_memory" if layer == "critic_memory" else "episodic_memory"),
            "proof_role": "guidance_only",
            "candidate_rule": fb["explanation"],
            "candidate_trigger": fb.get("candidate_trigger") or fb["rating"],
            "status": "pending_human_review",
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "payload": {"feedback_id": fb["feedback_id"], "rating": fb["rating"], "feedback_source": fb["feedback_source"]},
        })

    postgres_write_attempt_count = 1 if enable_live_postgres_write else 0
    write_attempt_count = postgres_write_attempt_count
    unsafe_findings: list[str] = []

    if enable_live_postgres_write:
        unsafe_findings.append("live_postgres_write_requested_in_v1_adapter_not_executed")
        # This v1 ledger intentionally does not execute DB writes. H32 may wire an explicit executor.

    answer_permission_count = sum(1 for r in feedback_records + candidate_records if r.get("answer_permission"))
    source_truth_mutation_allowed_count = sum(1 for r in feedback_records + candidate_records if r.get("source_truth_mutation_allowed"))

    quality_failures: list[str] = []
    if require_source_quality_pass and answer_manifest.get("quality_status") != "PASS":
        quality_failures.append("source_answer_smoke_quality_status_not_pass")
    if require_critic_quality_pass and critic_manifest.get("quality_status") != "PASS":
        quality_failures.append("source_critic_quality_status_not_pass")
    if require_crag_quality_pass and crag_manifest.get("quality_status") != "PASS":
        quality_failures.append("source_crag_quality_status_not_pass")
    if len(feedback_records) < min_feedback_records:
        quality_failures.append(f"feedback_record_count_below_min:{len(feedback_records)}<{min_feedback_records}")
    if len(candidate_records) < min_candidate_records:
        quality_failures.append(f"candidate_record_count_below_min:{len(candidate_records)}<{min_candidate_records}")
    if require_no_answer_permission and answer_permission_count:
        quality_failures.append("answer_permission_count_above_zero")
    if source_truth_mutation_allowed_count:
        quality_failures.append("source_truth_mutation_allowed_count_above_zero")
    if len(unsafe_findings) > max_unsafe:
        quality_failures.append(f"unsafe_finding_count_above_max:{len(unsafe_findings)}>{max_unsafe}")
    if write_attempt_count > max_write_attempts:
        quality_failures.append(f"write_attempt_count_above_max:{write_attempt_count}>{max_write_attempts}")

    schema_path = output / "trace_net_engineering_engram_feedback_ledger_schema_v1.sql"
    feedback_path = output / "trace_net_engineering_engram_feedback_ledger_records_v1.jsonl"
    candidates_path = output / "trace_net_engineering_engram_feedback_to_memory_candidates_v1.jsonl"
    quality_path = output / "trace_net_engineering_engram_postgres_feedback_ledger_v1_quality_check.json"
    manifest_path = output / "trace_net_engineering_engram_postgres_feedback_ledger_v1.json"

    schema_path.write_text(SCHEMA_SQL, encoding="utf-8")
    _write_jsonl(feedback_path, feedback_records)
    _write_jsonl(candidates_path, candidate_records)

    summary = {
        "module": MODULE,
        "version": VERSION,
        "feedback_record_count": len(feedback_records),
        "candidate_record_count": len(candidate_records),
        "feedback_source_counts": _count(feedback_records, "feedback_source"),
        "candidate_memory_layer_counts": _count(candidate_records, "memory_layer"),
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "postgres_write_attempt_count": postgres_write_attempt_count,
        "qdrant_write_attempt_count": 0,
        "qdrant_read_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "write_attempt_count": write_attempt_count,
        "unsafe_finding_count": len(unsafe_findings),
        "unsafe_findings": unsafe_findings,
        "source_answer_smoke_quality_status": answer_manifest.get("quality_status"),
        "source_critic_quality_status": critic_manifest.get("quality_status"),
        "source_crag_quality_status": crag_manifest.get("quality_status"),
        "ready_for_postgres_feedback_table_creation": True,
        "ready_for_feedback_to_engram_review": not quality_failures,
        "quality_failures": quality_failures,
    }

    manifest = {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_POSTGRES_FEEDBACK_LEDGER_BUILT",
        "quality_status": "PASS" if not quality_failures else "FAIL",
        "summary": summary,
        "schema_path": str(schema_path),
        "feedback_records_path": str(feedback_path),
        "candidate_records_path": str(candidates_path),
        "quality_check_path": str(quality_path),
        "postgres_plan": {
            "postgres_dsn_configured": bool(postgres_dsn),
            "live_postgres_write_enabled": bool(enable_live_postgres_write),
            "live_postgres_write_attempted": bool(enable_live_postgres_write),
            "safety_note": "V1 emits schema and ledger rows. Live writes require explicit enable flag and are not executed by default.",
        },
        "ledger_policy": {
            "mode": "artifact_first_postgres_feedback_ledger",
            "proof_boundary": "Feedback and Engram memory candidates shape behavior only; factual manual claims still require proof_context citations.",
            "explicit_live_flags": ["--enable-live-postgres-write"],
            "forbidden": [
                "answer_permission_from_feedback",
                "source_truth_mutation_from_feedback",
                "feedback_or_engram_used_as_proof",
                "live_postgres_write_without_explicit_enable_flag",
            ],
        },
        "feedback_records": feedback_records,
        "candidate_records": candidate_records,
    }
    quality = {"quality_status": manifest["quality_status"], "summary": summary}
    _write_json(quality_path, quality)
    _write_json(manifest_path, manifest)
    return manifest


def _count(records: Iterable[Mapping[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in records:
        val = str(r.get(key) or "")
        if val:
            out[val] = out.get(val, 0) + 1
    return dict(sorted(out.items()))


def check_feedback_ledger_manifest(
    ledger: str | Path,
    min_feedback_records: int = 5,
    min_candidate_records: int = 5,
    require_quality_pass: bool = False,
    require_no_answer_permission: bool = False,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> dict[str, Any]:
    data = _read_json(ledger)
    summary = dict(data.get("summary") or {})
    quality_failures = list(summary.get("quality_failures") or [])
    if require_quality_pass and data.get("quality_status") != "PASS":
        quality_failures.append("source_quality_status_not_pass")
    if int(summary.get("feedback_record_count") or 0) < min_feedback_records:
        quality_failures.append("feedback_record_count_below_min")
    if int(summary.get("candidate_record_count") or 0) < min_candidate_records:
        quality_failures.append("candidate_record_count_below_min")
    if require_no_answer_permission and int(summary.get("answer_permission_count") or 0):
        quality_failures.append("answer_permission_count_above_zero")
    if int(summary.get("unsafe_finding_count") or 0) > max_unsafe:
        quality_failures.append("unsafe_finding_count_above_max")
    if int(summary.get("write_attempt_count") or 0) > max_write_attempts:
        quality_failures.append("write_attempt_count_above_max")
    return {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_POSTGRES_FEEDBACK_LEDGER_CHECKED",
        "quality_status": "PASS" if not quality_failures else "FAIL",
        "feedback_record_count": summary.get("feedback_record_count", 0),
        "candidate_record_count": summary.get("candidate_record_count", 0),
        "unsafe_finding_count": summary.get("unsafe_finding_count", 0),
        "answer_permission_count": summary.get("answer_permission_count", 0),
        "write_attempt_count": summary.get("write_attempt_count", 0),
        "quality_failures": quality_failures,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build TRACE-Net Engineering Engram Postgres feedback ledger v1")
    p.add_argument("--answer-smoke", required=True)
    p.add_argument("--critic", required=True)
    p.add_argument("--crag-repair", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--feedback-jsonl")
    p.add_argument("--postgres-dsn")
    p.add_argument("--enable-live-postgres-write", action="store_true")
    p.add_argument("--min-feedback-records", type=int, default=5)
    p.add_argument("--min-candidate-records", type=int, default=5)
    p.add_argument("--require-source-quality-pass", action="store_true")
    p.add_argument("--require-critic-quality-pass", action="store_true")
    p.add_argument("--require-crag-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    manifest = build_feedback_ledger_manifest(**vars(args))
    summary = manifest.get("summary", {})
    print("status=" + manifest.get("status", ""))
    print("quality_status=" + manifest.get("quality_status", ""))
    print("feedback_record_count=" + str(summary.get("feedback_record_count", 0)))
    print("candidate_record_count=" + str(summary.get("candidate_record_count", 0)))
    print("unsafe_finding_count=" + str(summary.get("unsafe_finding_count", 0)))
    print("answer_permission_count=" + str(summary.get("answer_permission_count", 0)))
    print("write_attempt_count=" + str(summary.get("write_attempt_count", 0)))
    print("output=" + str(Path(args.output_dir) / "trace_net_engineering_engram_postgres_feedback_ledger_v1.json"))
    return 0 if manifest.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
