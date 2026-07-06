from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

MODULE = "trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1"
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
    "live_qdrant_io_attempted": False,
    "engram_is_proof": False,
}

DEFAULT_TARGET_QUESTION_IDS = ["q12", "q16", "q18", "q25", "q29"]
ALLOWED_PROOF_ROLES = {"guidance_only", "current_proof_context_only"}

REQUIRED_BOUNDARY_GROUPS = {
    "behavior_guidance_boundary": [
        "behavior guidance only",
        "behavior only",
        "answer behavior only",
        "shape answer behavior only",
        "shapes answer behavior only",
    ],
    "not_proof_boundary": [
        "not proof",
        "not manual evidence",
        "do not use engram memory as manual evidence",
        "engram memory as manual evidence",
        "not used as proof",
    ],
    "proof_context_boundary": [
        "proof_context",
        "current proof context",
        "current proof_context citations",
    ],
}


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _read_json(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, sort_keys=True) + "\n")


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _parse_question_ids(value: str | Sequence[str] | None) -> List[str]:
    if value is None or value == "":
        return list(DEFAULT_TARGET_QUESTION_IDS)
    if isinstance(value, str):
        parts: List[str] = []
        for chunk in value.split(","):
            cleaned = chunk.strip()
            if cleaned:
                parts.append(cleaned)
        return parts or list(DEFAULT_TARGET_QUESTION_IDS)
    return [str(v).strip() for v in value if str(v).strip()]


def _compact_text(text: str, max_chars: int) -> str:
    text = _norm(text)
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 92)].rstrip() + "\n[TRUNCATED BY H24 OVERLAY SMOKE: guidance only, not proof.]"


def _missing_boundary_groups(text: str) -> List[str]:
    lower = _norm(text).lower()
    missing: List[str] = []
    for group_name, phrases in REQUIRED_BOUNDARY_GROUPS.items():
        if not any(phrase in lower for phrase in phrases):
            missing.append(group_name)
    return missing


def _records_by_question_id(source_answer_smoke: Mapping[str, Any] | None) -> Dict[str, Mapping[str, Any]]:
    if not source_answer_smoke:
        return {}
    return {str(r.get("question_id")): r for r in (source_answer_smoke.get("records") or source_answer_smoke.get("smoke_records") or [])}


def _bridge_records(bridge: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return [dict(r) for r in (bridge.get("bridge_records") or [])]


def _bridge_records_for_question(bridge: Mapping[str, Any], question_id: str) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    for rec in _bridge_records(bridge):
        if question_id in [str(x) for x in _as_list(rec.get("target_answer_runner_question_ids"))]:
            matches.append(rec)
    return matches


def _combine_layers(records: Sequence[Mapping[str, Any]]) -> List[str]:
    return sorted({str(layer) for rec in records for layer in _as_list(rec.get("selected_layers"))})


def _combine_proof_roles(records: Sequence[Mapping[str, Any]]) -> List[str]:
    return sorted({str(role) for rec in records for role in _as_list(rec.get("selected_proof_roles"))})


def build_overlay_text(question_id: str, bridge_records: Sequence[Mapping[str, Any]], max_overlay_chars: int = 1800) -> str:
    chunks: List[str] = [
        "TRACE-NET H24 ANSWER-RUNNER RETRIEVED ENGRAM OVERLAY",
        "Use this overlay as behavior guidance only. It is not proof.",
        "Manual/source claims still require current proof_context citations.",
        "Do not let Engram guidance grant answer permission, mutate source truth, or replace proof_context.",
        f"target_question_id: {question_id}",
        "",
    ]
    for rec in bridge_records:
        guidance = _norm(rec.get("guidance_overlay_text"))
        task = _norm(rec.get("task_type"))
        query_id = _norm(rec.get("query_id"))
        chunks.append(f"--- retrieved_guidance query_id={query_id} task_type={task} ---")
        chunks.append(guidance)
        chunks.append("")
    chunks.append("Required response discipline: answer from current proof_context only; use retrieved Engram overlay only to shape wording, boundaries, route awareness, and repair behavior.")
    return _compact_text("\n".join(chunks).strip(), max_overlay_chars)


def build_overlay_records(
    bridge: Mapping[str, Any],
    source_answer_smoke: Mapping[str, Any] | None = None,
    *,
    question_ids: str | Sequence[str] | None = None,
    max_overlay_chars: int = 1800,
) -> List[Dict[str, Any]]:
    qids = _parse_question_ids(question_ids)
    source_by_qid = _records_by_question_id(source_answer_smoke)
    records: List[Dict[str, Any]] = []
    for qid in qids:
        matches = _bridge_records_for_question(bridge, qid)
        source = source_by_qid.get(qid, {})
        overlay = build_overlay_text(qid, matches, max_overlay_chars=max_overlay_chars) if matches else ""
        selected_proof_roles = _combine_proof_roles(matches)
        selected_layers = _combine_layers(matches)
        bad_proof_roles = [r for r in selected_proof_roles if r not in ALLOWED_PROOF_ROLES]
        missing_boundary_groups = _missing_boundary_groups(overlay) if overlay else ["no_overlay_text"]
        unsafe_findings: List[str] = []
        if not matches:
            unsafe_findings.append("no_bridge_guidance_for_question")
        if missing_boundary_groups:
            unsafe_findings.append("missing_boundary_groups:" + ",".join(missing_boundary_groups))
        if bad_proof_roles:
            unsafe_findings.append("unsupported_proof_roles:" + ",".join(bad_proof_roles))
        if any(bool(rec.get("answer_permission")) for rec in matches):
            unsafe_findings.append("bridge_record_answer_permission_true")
        if any(bool(rec.get("write_attempt")) for rec in matches):
            unsafe_findings.append("bridge_record_write_attempt_true")
        record = {
            "question_id": qid,
            "source_question": source.get("question", ""),
            "source_category": source.get("category", ""),
            "source_task_type": source.get("task_type", ""),
            "source_grade": source.get("grade", ""),
            "source_runner_quality_status": source.get("runner_quality_status", ""),
            "source_proof_context_count": int(source.get("proof_context_count") or 0),
            "matched_bridge_record_count": len(matches),
            "matched_bridge_query_ids": [m.get("query_id") for m in matches],
            "matched_bridge_task_types": [m.get("task_type") for m in matches],
            "selected_layers": selected_layers,
            "selected_proof_roles": selected_proof_roles,
            "overlay_text": overlay,
            "overlay_char_count": len(overlay),
            "answer_runner_overlay_mode": "artifact_only_prompt_overlay_smoke",
            "ready_for_targeted_llm_overlay_smoke": bool(matches) and not unsafe_findings,
            "unsafe_findings": unsafe_findings,
            "unsafe": bool(unsafe_findings),
            **SAFETY_CONTRACT,
        }
        records.append(record)
    return records


def _count_layers(records: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for rec in records:
        for layer in _as_list(rec.get("selected_layers")):
            layer_s = str(layer)
            counts[layer_s] = counts.get(layer_s, 0) + 1
    return dict(sorted(counts.items()))


def _count_matched_task_types(records: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for rec in records:
        for task in _as_list(rec.get("matched_bridge_task_types")):
            task_s = str(task)
            counts[task_s] = counts.get(task_s, 0) + 1
    return dict(sorted(counts.items()))


def _safety_counts_zero(data: Mapping[str, Any]) -> bool:
    summary = data.get("summary") or {}
    keys = [
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_read_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "opensearch_upload_attempt_count",
        "write_attempt_count",
        "unsafe_finding_count",
    ]
    return all(int(summary.get(k) or 0) == 0 for k in keys)


def build_answer_runner_prompt_overlay_smoke_manifest(
    *,
    bridge: str | Path,
    source_answer_smoke: str | Path | None = None,
    output_dir: str | Path,
    question_ids: str | Sequence[str] | None = None,
    max_overlay_chars: int = 1800,
    min_overlay_records: int = 5,
    min_matched_bridge_records: int = 5,
    require_h23_quality_pass: bool = True,
    require_source_answer_smoke_quality_pass: bool = False,
    require_no_answer_permission: bool = True,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    bridge_path = Path(bridge)
    bridge_data = _read_json(bridge_path)
    source_data: Dict[str, Any] | None = None
    source_path_s = ""
    if source_answer_smoke:
        source_path = Path(source_answer_smoke)
        source_path_s = str(source_path)
        source_data = _read_json(source_path)
    records = build_overlay_records(bridge_data, source_data, question_ids=question_ids, max_overlay_chars=max_overlay_chars)
    unsafe_records = [r for r in records if r.get("unsafe")]
    matched_bridge_record_count = sum(int(r.get("matched_bridge_record_count") or 0) for r in records)
    answer_permission_count = sum(1 for r in records if r.get("answer_permission"))
    write_attempt_count = sum(1 for r in records if r.get("write_attempt"))
    qids = [str(r.get("question_id")) for r in records]

    quality_failures: List[str] = []
    if require_h23_quality_pass and bridge_data.get("quality_status") != "PASS":
        quality_failures.append("source_bridge_not_pass")
    if not _safety_counts_zero(bridge_data):
        quality_failures.append("source_bridge_safety_counter_nonzero")
    if require_source_answer_smoke_quality_pass and (not source_data or source_data.get("quality_status") != "PASS"):
        quality_failures.append("source_answer_smoke_not_pass")
    if len(records) < min_overlay_records:
        quality_failures.append(f"overlay_record_count_below_min:{len(records)}<{min_overlay_records}")
    if matched_bridge_record_count < min_matched_bridge_records:
        quality_failures.append(f"matched_bridge_record_count_below_min:{matched_bridge_record_count}<{min_matched_bridge_records}")
    if require_no_answer_permission and answer_permission_count:
        quality_failures.append("answer_permission_count_nonzero")
    if len(unsafe_records) > max_unsafe:
        quality_failures.append(f"unsafe_finding_count_above_max:{len(unsafe_records)}>{max_unsafe}")
    if write_attempt_count > max_write_attempts:
        quality_failures.append(f"write_attempt_count_above_max:{write_attempt_count}>{max_write_attempts}")
    quality_status = "PASS" if not quality_failures else "FAIL"

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / f"{MODULE}.json"
    records_path = out_dir / f"{MODULE}_records.jsonl"
    overlay_map_path = out_dir / f"{MODULE}_overlay_map.json"
    check_path = out_dir / f"{MODULE}_quality_check.json"

    overlay_map = {
        r["question_id"]: {
            "overlay_text": r["overlay_text"],
            "matched_bridge_query_ids": r["matched_bridge_query_ids"],
            "matched_bridge_task_types": r["matched_bridge_task_types"],
            "selected_layers": r["selected_layers"],
            "selected_proof_roles": r["selected_proof_roles"],
            "answer_permission": False,
            "engram_is_proof": False,
        }
        for r in records
    }
    summary = {
        "module": MODULE,
        "version": VERSION,
        "source_bridge_quality_status": bridge_data.get("quality_status"),
        "source_answer_smoke_quality_status": source_data.get("quality_status") if source_data else None,
        "overlay_record_count": len(records),
        "target_question_count": len(qids),
        "target_question_ids": qids,
        "matched_bridge_record_count": matched_bridge_record_count,
        "matched_bridge_task_type_counts": _count_matched_task_types(records),
        "selected_memory_layer_counts": _count_layers(records),
        "ready_for_targeted_llm_overlay_smoke": quality_status == "PASS",
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_read_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "write_attempt_count": write_attempt_count,
        "unsafe_finding_count": len(unsafe_records),
        "quality_failures": quality_failures,
    }
    manifest = {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_ANSWER_RUNNER_PROMPT_OVERLAY_SMOKE_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "quality_failures": quality_failures,
        "source_bridge_path": str(bridge_path),
        "source_answer_smoke_path": source_path_s,
        "safety_contract": dict(SAFETY_CONTRACT),
        "integration_policy": {
            "mode": "artifact_only_answer_runner_prompt_overlay_smoke",
            "proof_boundary": "Retrieved Engram overlays shape answer behavior only; factual manual claims require current proof_context citations.",
            "forbidden": [
                "answer_permission_from_engram",
                "source_truth_mutation_from_engram",
                "summary_or_engram_used_as_proof",
                "live_db_or_qdrant_io_without_explicit_gate",
                "full_30_question_rerun_as_default_debug_loop",
            ],
            "next_patch": "targeted LLM answer-runner overlay smoke behind explicit CLI flag",
        },
        "overlay_records": records,
        "records_path": str(records_path),
        "overlay_map_path": str(overlay_map_path),
        "quality_check_path": str(check_path),
    }
    _write_json(manifest_path, manifest)
    _write_jsonl(records_path, records)
    _write_json(overlay_map_path, overlay_map)
    _write_json(check_path, {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_ANSWER_RUNNER_PROMPT_OVERLAY_SMOKE_CHECKED",
        "quality_status": quality_status,
        "summary": summary,
        "quality_failures": quality_failures,
    })
    manifest["output_path"] = str(manifest_path)
    _write_json(manifest_path, manifest)
    return manifest


def check_answer_runner_prompt_overlay_smoke_manifest(
    *,
    overlay_smoke: str | Path,
    min_overlay_records: int = 5,
    min_matched_bridge_records: int = 5,
    require_quality_pass: bool = True,
    require_no_answer_permission: bool = True,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    data = _read_json(overlay_smoke)
    summary = dict(data.get("summary") or {})
    failures: List[str] = []
    if require_quality_pass and data.get("quality_status") != "PASS":
        failures.append("source_quality_status_not_pass")
    if int(summary.get("overlay_record_count") or 0) < min_overlay_records:
        failures.append("overlay_record_count_below_min")
    if int(summary.get("matched_bridge_record_count") or 0) < min_matched_bridge_records:
        failures.append("matched_bridge_record_count_below_min")
    if require_no_answer_permission and int(summary.get("answer_permission_count") or 0) != 0:
        failures.append("answer_permission_count_nonzero")
    if int(summary.get("unsafe_finding_count") or 0) > max_unsafe:
        failures.append("unsafe_finding_count_above_max")
    if int(summary.get("write_attempt_count") or 0) > max_write_attempts:
        failures.append("write_attempt_count_above_max")
    quality_status = "PASS" if not failures else "FAIL"
    return {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_ANSWER_RUNNER_PROMPT_OVERLAY_SMOKE_CHECKED",
        "quality_status": quality_status,
        "summary": summary,
        "quality_failures": failures,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build TRACE-Net H24 Engram answer-runner prompt overlay smoke.")
    p.add_argument("--bridge", required=True)
    p.add_argument("--source-answer-smoke", default="")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--question-ids", default=",".join(DEFAULT_TARGET_QUESTION_IDS))
    p.add_argument("--max-overlay-chars", type=int, default=1800)
    p.add_argument("--min-overlay-records", type=int, default=5)
    p.add_argument("--min-matched-bridge-records", type=int, default=5)
    p.add_argument("--require-h23-quality-pass", action="store_true")
    p.add_argument("--require-source-answer-smoke-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = build_answer_runner_prompt_overlay_smoke_manifest(
        bridge=args.bridge,
        source_answer_smoke=args.source_answer_smoke or None,
        output_dir=args.output_dir,
        question_ids=args.question_ids,
        max_overlay_chars=args.max_overlay_chars,
        min_overlay_records=args.min_overlay_records,
        min_matched_bridge_records=args.min_matched_bridge_records,
        require_h23_quality_pass=args.require_h23_quality_pass,
        require_source_answer_smoke_quality_pass=args.require_source_answer_smoke_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
        max_unsafe=args.max_unsafe,
        max_write_attempts=args.max_write_attempts,
    )
    s = result.get("summary", {})
    print("status=" + str(result.get("status")))
    print("quality_status=" + str(result.get("quality_status")))
    print("overlay_record_count=" + str(s.get("overlay_record_count")))
    print("target_question_count=" + str(s.get("target_question_count")))
    print("matched_bridge_record_count=" + str(s.get("matched_bridge_record_count")))
    print("unsafe_finding_count=" + str(s.get("unsafe_finding_count")))
    print("answer_permission_count=" + str(s.get("answer_permission_count")))
    print("write_attempt_count=" + str(s.get("write_attempt_count")))
    print("output=" + str(Path(args.output_dir) / f"{MODULE}.json"))
    return 0 if result.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
