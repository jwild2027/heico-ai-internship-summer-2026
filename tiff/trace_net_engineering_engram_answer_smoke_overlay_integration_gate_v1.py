"""TRACE-Net Engineering Engram Answer-Smoke Overlay Integration Gate v1.

Artifact-only integration gate for carrying H24/H25 retrieved Engram overlays toward the
real engineering LLM answer smoke builder without making the full 30-question path the
default debug loop.

Safety contract:
- no live LLM calls
- no Postgres writes
- no Qdrant reads/writes
- no OpenSearch reads/writes/uploads
- no source-truth mutation
- no answer permission
- Engram overlays are behavior guidance only, never proof
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

MODULE = "trace_net_engineering_engram_answer_smoke_overlay_integration_gate_v1"
VERSION = "v1"

SAFETY_CONTRACT = {
    "answer_permission": False,
    "source_truth_mutation_allowed": False,
    "postgres_write_attempt": False,
    "qdrant_read_attempt": False,
    "qdrant_write_attempt": False,
    "opensearch_write_attempt": False,
    "opensearch_upload_attempt": False,
    "write_attempt": False,
    "llm_call_attempt": False,
}

DEFAULT_TARGET_QUESTION_IDS = ["q12", "q16", "q18", "q25", "q29"]


def _read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def _split_ids(value: str | None) -> list[str]:
    if not value:
        return list(DEFAULT_TARGET_QUESTION_IDS)
    out: list[str] = []
    for part in value.replace(";", ",").split(","):
        clean = part.strip()
        if clean and clean not in out:
            out.append(clean)
    return out


def _summary_count(summary: Mapping[str, Any], key: str) -> int:
    try:
        return int(summary.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _by_question_id(records: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    by_id: dict[str, Mapping[str, Any]] = {}
    for rec in records:
        qid = str(rec.get("question_id") or "").strip()
        if qid:
            by_id[qid] = rec
    return by_id


def _overlay_records_by_question(overlay_smoke: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return _by_question_id(overlay_smoke.get("overlay_records", []) or [])


def _h25_records_by_question(h25_smoke: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return _by_question_id(h25_smoke.get("smoke_records", []) or [])


def _source_records_by_question(source_answer_smoke: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return _by_question_id(source_answer_smoke.get("records", []) or source_answer_smoke.get("smoke_records", []) or [])


def _safe_bool(rec: Mapping[str, Any], key: str) -> bool:
    return bool(rec.get(key, False))


def build_overlay_integration_gate(
    *,
    overlay_smoke: str | Path,
    overlay_llm_smoke: str | Path,
    source_answer_smoke: str | Path,
    output_dir: str | Path,
    question_ids: str | None = None,
    max_overlay_chars: int = 1800,
    min_gate_records: int = 5,
    min_h25_good_answers: int = 4,
    require_h24_quality_pass: bool = False,
    require_h25_quality_pass: bool = False,
    require_source_answer_smoke_quality_pass: bool = False,
    require_no_answer_permission: bool = False,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> dict[str, Any]:
    overlay_manifest = _read_json(overlay_smoke)
    h25_manifest = _read_json(overlay_llm_smoke)
    source_manifest = _read_json(source_answer_smoke)

    target_ids = _split_ids(question_ids)
    overlay_by_q = _overlay_records_by_question(overlay_manifest)
    h25_by_q = _h25_records_by_question(h25_manifest)
    source_by_q = _source_records_by_question(source_manifest)

    overlay_summary = overlay_manifest.get("summary", {}) or {}
    h25_summary = h25_manifest.get("summary", {}) or {}
    source_summary = source_manifest.get("summary", {}) or {}

    gate_records: list[dict[str, Any]] = []
    unsafe_findings: list[str] = []
    answer_permission_count = 0
    write_attempt_count = 0

    for qid in target_ids:
        overlay_rec = overlay_by_q.get(qid, {})
        h25_rec = h25_by_q.get(qid, {})
        source_rec = source_by_q.get(qid, {})
        overlay_text = str(overlay_rec.get("overlay_text") or "")[:max_overlay_chars]
        missing: list[str] = []
        if not overlay_rec:
            missing.append("h24_overlay_record")
        if not h25_rec:
            missing.append("h25_llm_smoke_record")
        if not source_rec:
            missing.append("source_answer_smoke_record")

        rec_answer_permission = any(
            _safe_bool(r, "answer_permission") for r in (overlay_rec, h25_rec, source_rec) if isinstance(r, Mapping)
        )
        rec_write_attempt = any(
            _safe_bool(r, "write_attempt") or _safe_bool(r, "write_attempt_count")
            for r in (overlay_rec, h25_rec, source_rec)
            if isinstance(r, Mapping)
        )
        rec_unsafe = bool(missing) or any(
            _safe_bool(r, "unsafe") for r in (overlay_rec, h25_rec, source_rec) if isinstance(r, Mapping)
        )
        boundary_text = overlay_text.lower()
        required_boundaries = [
            "behavior guidance only",
            "not proof",
            "proof_context citations",
        ]
        missing_boundaries = [b for b in required_boundaries if b not in boundary_text]
        if missing_boundaries:
            rec_unsafe = True
            missing.extend([f"missing_boundary:{b}" for b in missing_boundaries])

        if rec_answer_permission:
            answer_permission_count += 1
        if rec_write_attempt:
            write_attempt_count += 1
        if rec_unsafe:
            unsafe_findings.append(qid + ":" + ",".join(missing or ["unsafe_record"]))

        gate_records.append({
            "question_id": qid,
            "question": source_rec.get("question") or overlay_rec.get("source_question") or h25_rec.get("question"),
            "source_answer_grade": source_rec.get("grade") or overlay_rec.get("source_grade"),
            "h25_overlay_grade": h25_rec.get("grade"),
            "matched_bridge_query_ids": overlay_rec.get("matched_bridge_query_ids", []),
            "matched_bridge_task_types": overlay_rec.get("matched_bridge_task_types", []),
            "selected_layers": overlay_rec.get("selected_layers", []),
            "selected_proof_roles": overlay_rec.get("selected_proof_roles", []),
            "overlay_char_count": len(overlay_text),
            "overlay_map_ready": bool(overlay_rec and overlay_text),
            "real_answer_smoke_overlay_enabled": False,
            "requires_explicit_cli_flag": True,
            "recommended_cli_flag": "--engram-answer-runner-overlay-map",
            "recommended_overlay_map_key": qid,
            "answer_permission": rec_answer_permission,
            "write_attempt": rec_write_attempt,
            "unsafe": rec_unsafe,
            "missing_requirements": missing,
            "overlay_text_preview": overlay_text[:900],
        })

    quality_failures: list[str] = []
    if require_h24_quality_pass and overlay_manifest.get("quality_status") != "PASS":
        quality_failures.append("h24_overlay_smoke_not_pass")
    if require_h25_quality_pass and h25_manifest.get("quality_status") != "PASS":
        quality_failures.append("h25_overlay_llm_smoke_not_pass")
    if require_source_answer_smoke_quality_pass and source_manifest.get("quality_status") != "PASS":
        quality_failures.append("source_answer_smoke_not_pass")
    if len(gate_records) < min_gate_records:
        quality_failures.append(f"gate_record_count_below_min:{len(gate_records)}<{min_gate_records}")
    h25_good = _summary_count(h25_summary, "good_answer_count")
    if h25_good < min_h25_good_answers:
        quality_failures.append(f"h25_good_answer_count_below_min:{h25_good}<{min_h25_good_answers}")
    if require_no_answer_permission and answer_permission_count:
        quality_failures.append("answer_permission_present")
    if len(unsafe_findings) > max_unsafe:
        quality_failures.append(f"unsafe_finding_count_above_max:{len(unsafe_findings)}>{max_unsafe}")
    if write_attempt_count > max_write_attempts:
        quality_failures.append(f"write_attempt_count_above_max:{write_attempt_count}>{max_write_attempts}")

    out_dir = Path(output_dir)
    overlay_map_path = out_dir / "trace_net_engineering_engram_answer_smoke_overlay_map_v1.json"
    records_path = out_dir / "trace_net_engineering_engram_answer_smoke_overlay_integration_gate_v1_records.jsonl"
    quality_path = out_dir / "trace_net_engineering_engram_answer_smoke_overlay_integration_gate_v1_quality_check.json"
    manifest_path = out_dir / "trace_net_engineering_engram_answer_smoke_overlay_integration_gate_v1.json"

    overlay_map = {
        rec["question_id"]: {
            "overlay_text": overlay_by_q.get(rec["question_id"], {}).get("overlay_text", "")[:max_overlay_chars],
            "matched_bridge_query_ids": rec["matched_bridge_query_ids"],
            "matched_bridge_task_types": rec["matched_bridge_task_types"],
            "selected_layers": rec["selected_layers"],
            "selected_proof_roles": rec["selected_proof_roles"],
            "proof_boundary": "Engram overlay is behavior guidance only; factual claims require current proof_context citations.",
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        }
        for rec in gate_records
        if not rec["unsafe"]
    }

    summary = {
        "module": MODULE,
        "version": VERSION,
        "gate_record_count": len(gate_records),
        "target_question_count": len(target_ids),
        "target_question_ids": target_ids,
        "overlay_map_record_count": len(overlay_map),
        "h24_quality_status": overlay_manifest.get("quality_status"),
        "h25_quality_status": h25_manifest.get("quality_status"),
        "source_answer_smoke_quality_status": source_manifest.get("quality_status"),
        "h25_good_answer_count": h25_good,
        "h25_bad_answer_count": _summary_count(h25_summary, "bad_answer_count"),
        "h25_unsupported_claim_count": _summary_count(h25_summary, "unsupported_claim_count"),
        "ready_for_real_answer_smoke_overlay_flag_patch": not quality_failures,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_read_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "write_attempt_count": write_attempt_count,
        "unsafe_finding_count": len(unsafe_findings),
        "unsafe_findings": unsafe_findings,
        "quality_failures": quality_failures,
    }

    manifest = {
        "module": MODULE,
        "version": VERSION,
        "status": "TRACE_NET_ENGINEERING_ENGRAM_ANSWER_SMOKE_OVERLAY_INTEGRATION_GATE_BUILT",
        "quality_status": "PASS" if not quality_failures else "FAIL",
        "summary": summary,
        "integration_policy": {
            "mode": "artifact_only_real_answer_smoke_overlay_gate",
            "next_patch": "add explicit --engram-answer-runner-overlay-map support to the real answer-smoke builder",
            "forbidden": [
                "default_full_30_question_rerun_as_debug_loop",
                "answer_permission_from_engram",
                "source_truth_mutation_from_engram",
                "summary_or_engram_used_as_proof",
                "live_db_or_qdrant_io_without_explicit_gate",
            ],
            "required_runtime_gate": "overlay injection must be behind explicit CLI flag and targeted question set first",
            "proof_boundary": "Retrieved Engram overlays shape answer behavior only; factual manual claims require current proof_context citations.",
            "safety_contract": SAFETY_CONTRACT,
        },
        "recommended_real_smoke_flags": {
            "overlay_map_flag": "--engram-answer-runner-overlay-map",
            "overlay_map_path": str(overlay_map_path),
            "targeted_question_ids": ",".join(target_ids),
            "required_target_first": True,
        },
        "paths": {
            "overlay_map": str(overlay_map_path),
            "records_jsonl": str(records_path),
            "quality_check": str(quality_path),
        },
        "gate_records": gate_records,
    }

    _write_json(overlay_map_path, overlay_map)
    _write_jsonl(records_path, gate_records)
    _write_json(quality_path, {"quality_status": manifest["quality_status"], "summary": summary})
    _write_json(manifest_path, manifest)
    return manifest


def check_overlay_integration_gate(
    *,
    integration_gate: str | Path,
    min_gate_records: int = 5,
    min_overlay_map_records: int = 5,
    require_quality_pass: bool = False,
    require_no_answer_permission: bool = False,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> dict[str, Any]:
    manifest = _read_json(integration_gate)
    summary = manifest.get("summary", {}) or {}
    failures: list[str] = []
    gate_count = _summary_count(summary, "gate_record_count")
    overlay_count = _summary_count(summary, "overlay_map_record_count")
    unsafe_count = _summary_count(summary, "unsafe_finding_count")
    write_count = _summary_count(summary, "write_attempt_count")
    answer_permission_count = _summary_count(summary, "answer_permission_count")
    if require_quality_pass and manifest.get("quality_status") != "PASS":
        failures.append("quality_status_not_pass")
    if gate_count < min_gate_records:
        failures.append(f"gate_record_count_below_min:{gate_count}<{min_gate_records}")
    if overlay_count < min_overlay_map_records:
        failures.append(f"overlay_map_record_count_below_min:{overlay_count}<{min_overlay_map_records}")
    if require_no_answer_permission and answer_permission_count:
        failures.append("answer_permission_present")
    if unsafe_count > max_unsafe:
        failures.append(f"unsafe_finding_count_above_max:{unsafe_count}>{max_unsafe}")
    if write_count > max_write_attempts:
        failures.append(f"write_attempt_count_above_max:{write_count}>{max_write_attempts}")

    checked = dict(manifest)
    checked["status"] = "TRACE_NET_ENGINEERING_ENGRAM_ANSWER_SMOKE_OVERLAY_INTEGRATION_GATE_CHECKED"
    checked["quality_status"] = "PASS" if not failures else "FAIL"
    checked["quality_failures"] = failures
    return checked


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=MODULE)
    p.add_argument("--overlay-smoke", required=True)
    p.add_argument("--overlay-llm-smoke", required=True)
    p.add_argument("--source-answer-smoke", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--question-ids", default=",".join(DEFAULT_TARGET_QUESTION_IDS))
    p.add_argument("--max-overlay-chars", type=int, default=1800)
    p.add_argument("--min-gate-records", type=int, default=5)
    p.add_argument("--min-h25-good-answers", type=int, default=4)
    p.add_argument("--require-h24-quality-pass", action="store_true")
    p.add_argument("--require-h25-quality-pass", action="store_true")
    p.add_argument("--require-source-answer-smoke-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def check_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=MODULE + " check")
    p.add_argument("--integration-gate", required=True)
    p.add_argument("--min-gate-records", type=int, default=5)
    p.add_argument("--min-overlay-map-records", type=int, default=5)
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = build_overlay_integration_gate(**vars(args))
    summary = result.get("summary", {})
    print("status=" + result.get("status", ""))
    print("quality_status=" + result.get("quality_status", ""))
    print("gate_record_count=" + str(summary.get("gate_record_count")))
    print("overlay_map_record_count=" + str(summary.get("overlay_map_record_count")))
    print("unsafe_finding_count=" + str(summary.get("unsafe_finding_count")))
    print("answer_permission_count=" + str(summary.get("answer_permission_count")))
    print("write_attempt_count=" + str(summary.get("write_attempt_count")))
    print("output=" + str(Path(args.output_dir) / "trace_net_engineering_engram_answer_smoke_overlay_integration_gate_v1.json"))
    return 0 if result.get("quality_status") == "PASS" else 1


def check_main(argv: list[str] | None = None) -> int:
    args = check_arg_parser().parse_args(argv)
    result = check_overlay_integration_gate(**vars(args))
    summary = result.get("summary", {})
    print("status=" + result.get("status", ""))
    print("quality_status=" + result.get("quality_status", ""))
    print("gate_record_count=" + str(summary.get("gate_record_count")))
    print("overlay_map_record_count=" + str(summary.get("overlay_map_record_count")))
    print("unsafe_finding_count=" + str(summary.get("unsafe_finding_count")))
    print("answer_permission_count=" + str(summary.get("answer_permission_count")))
    print("write_attempt_count=" + str(summary.get("write_attempt_count")))
    if result.get("quality_failures"):
        print("quality_failures=" + json.dumps(result.get("quality_failures")))
    return 0 if result.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
