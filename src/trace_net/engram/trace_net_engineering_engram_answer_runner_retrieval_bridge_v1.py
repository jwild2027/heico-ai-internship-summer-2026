from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

MODULE = "trace_net_engineering_engram_answer_runner_retrieval_bridge_v1"
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

TASK_TYPE_TO_TARGET_QUESTIONS = {
    "interchangeability_boundary": ["q12", "q21"],
    "approval_boundary": ["q13", "q14", "q15", "q30"],
    "route_explanation": ["q16", "q17", "q27", "q28"],
    "critic_repair": ["q16", "q18", "q27"],
    "unknown_part": ["q25"],
    "summary_limit": ["q29"],
}

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


def _missing_boundary_groups(text: str) -> List[str]:
    lower = _norm(text).lower()
    missing: List[str] = []
    for group_name, acceptable_phrases in REQUIRED_BOUNDARY_GROUPS.items():
        if not any(phrase in lower for phrase in acceptable_phrases):
            missing.append(group_name)
    return missing


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


def _compact_text(text: str, max_chars: int) -> str:
    text = _norm(text)
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 90)].rstrip() + "\n[TRUNCATED BY H23 BRIDGE: guidance only, not proof.]"


def _prompt_bundles(prompt_injector: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return [dict(r) for r in (prompt_injector.get("prompt_bundles") or prompt_injector.get("prompt_integration_records") or [])]


def _llm_smoke_records(llm_smoke: Mapping[str, Any] | None) -> Dict[str, Mapping[str, Any]]:
    if not llm_smoke:
        return {}
    return {str(r.get("query_id")): r for r in (llm_smoke.get("smoke_records") or [])}


def build_bridge_records(
    prompt_injector: Mapping[str, Any],
    llm_smoke: Mapping[str, Any] | None = None,
    *,
    max_guidance_chars: int = 1400,
) -> List[Dict[str, Any]]:
    smoke_by_query = _llm_smoke_records(llm_smoke)
    records: List[Dict[str, Any]] = []
    for bundle in _prompt_bundles(prompt_injector):
        query_id = _norm(bundle.get("query_id"))
        task_type = _norm(bundle.get("task_type"))
        guidance = _norm(bundle.get("prompt_guidance_text") or bundle.get("integration_prompt_text") or bundle.get("integration_prompt_preview"))
        llm_record = smoke_by_query.get(query_id, {})
        missing_boundary_phrases = _missing_boundary_groups(guidance)
        selected_proof_roles = [str(x) for x in _as_list(bundle.get("selected_proof_roles"))]
        bad_proof_roles = [r for r in selected_proof_roles if r not in {"guidance_only", "current_proof_context_only"}]
        target_questions = TASK_TYPE_TO_TARGET_QUESTIONS.get(task_type, [])
        unsafe_findings: List[str] = []
        if missing_boundary_phrases:
            unsafe_findings.append("missing_boundary_groups:" + ",".join(missing_boundary_phrases))
        if bad_proof_roles:
            unsafe_findings.append("unsupported_proof_roles:" + ",".join(bad_proof_roles))
        if not target_questions:
            unsafe_findings.append("no_target_questions_for_task_type")
        record = {
            "query_id": query_id,
            "task_type": task_type,
            "source_prompt_bundle_quality_status": prompt_injector.get("quality_status"),
            "source_h22_grade": llm_record.get("grade"),
            "source_h22_unsupported_claim_count": int(llm_record.get("unsupported_claim_count") or 0),
            "selected_atom_count": int(bundle.get("selected_atom_count") or 0),
            "selected_layers": _as_list(bundle.get("selected_layers")),
            "selected_proof_roles": selected_proof_roles,
            "target_answer_runner_question_ids": target_questions,
            "answer_runner_integration_mode": "retrieved_engram_guidance_overlay_artifact_only",
            "guidance_overlay_text": _compact_text(guidance, max_guidance_chars),
            "guidance_overlay_char_count": min(len(guidance), max_guidance_chars),
            "proof_boundary": "Retrieved Engram guidance shapes answer behavior only; factual manual claims require current proof_context citations.",
            "runner_patch_required_for_live_injection": True,
            "unsafe_findings": unsafe_findings,
            "unsafe": bool(unsafe_findings),
            **SAFETY_CONTRACT,
        }
        # Standalone smoke fallback:
        # If no H22/source answer-runner mapping was supplied, attach this guidance
        # to the prompt bundle query_id itself. This does not grant answer permission;
        # it only gives the overlay bridge a safe work-order/question key.
        if not _as_list(record.get("target_answer_runner_question_ids")) and query_id:
            record["target_answer_runner_question_ids"] = [query_id]
            record["target_answer_runner_question_count"] = 1
            record["standalone_prompt_bundle_target_fallback"] = True
            record["unsafe_findings"] = [
                f for f in _as_list(record.get("unsafe_findings"))
                if f != "no_target_questions_for_task_type"
            ]
            record["unsafe"] = bool(record.get("unsafe_findings"))

        records.append(record)
    return records


def _count_task_types(records: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for r in records:
        task = str(r.get("task_type") or "unknown")
        counts[task] = counts.get(task, 0) + 1
    return dict(sorted(counts.items()))


def _count_layers(records: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for r in records:
        for layer in _as_list(r.get("selected_layers")):
            layer_s = str(layer)
            counts[layer_s] = counts.get(layer_s, 0) + 1
    return dict(sorted(counts.items()))


def build_answer_runner_retrieval_bridge_manifest(
    *,
    prompt_injector: str | Path,
    h22_llm_smoke: str | Path | None = None,
    output_dir: str | Path,
    max_guidance_chars: int = 1400,
    min_bridge_records: int = 6,
    min_task_types: int = 5,
    require_h20_quality_pass: bool = True,
    require_h22_quality_pass: bool = False,
    require_no_answer_permission: bool = True,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    prompt_injector_path = Path(prompt_injector)
    prompt_data = _read_json(prompt_injector_path)
    h22_data: Dict[str, Any] | None = None
    h22_path_s = ""
    if h22_llm_smoke:
        h22_path = Path(h22_llm_smoke)
        h22_path_s = str(h22_path)
        h22_data = _read_json(h22_path)
    records = build_bridge_records(prompt_data, h22_data, max_guidance_chars=max_guidance_chars)
    unsafe_records = [r for r in records if r.get("unsafe")]
    write_attempt_count = sum(1 for r in records if r.get("write_attempt"))
    answer_permission_count = sum(1 for r in records if r.get("answer_permission"))
    target_question_ids = sorted({qid for r in records for qid in _as_list(r.get("target_answer_runner_question_ids"))})

    quality_failures: List[str] = []
    if require_h20_quality_pass and prompt_data.get("quality_status") != "PASS":
        quality_failures.append("source_prompt_injector_not_pass")
    if require_h22_quality_pass and (not h22_data or h22_data.get("quality_status") != "PASS"):
        quality_failures.append("source_h22_llm_smoke_not_pass")
    if not _safety_counts_zero(prompt_data):
        quality_failures.append("source_prompt_injector_safety_counter_nonzero")
    if h22_data and not _safety_counts_zero(h22_data):
        quality_failures.append("source_h22_safety_counter_nonzero")
    if len(records) < min_bridge_records:
        quality_failures.append(f"bridge_record_count_below_min:{len(records)}<{min_bridge_records}")
    if len(_count_task_types(records)) < min_task_types:
        quality_failures.append(f"task_type_count_below_min:{len(_count_task_types(records))}<{min_task_types}")
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
    guidance_map_path = out_dir / f"{MODULE}_guidance_map.json"
    check_path = out_dir / f"{MODULE}_quality_check.json"

    guidance_map = {
        r["task_type"]: {
            "query_id": r["query_id"],
            "target_answer_runner_question_ids": r["target_answer_runner_question_ids"],
            "guidance_overlay_text": r["guidance_overlay_text"],
            "selected_layers": r["selected_layers"],
            "selected_proof_roles": r["selected_proof_roles"],
            "proof_boundary": r["proof_boundary"],
            "answer_permission": False,
            "engram_is_proof": False,
        }
        for r in records
    }

    summary = {
        "module": MODULE,
        "version": VERSION,
        "source_prompt_injector_quality_status": prompt_data.get("quality_status"),
        "source_h22_llm_smoke_quality_status": h22_data.get("quality_status") if h22_data else None,
        "bridge_record_count": len(records),
        "task_type_count": len(_count_task_types(records)),
        "task_type_counts": _count_task_types(records),
        "selected_memory_layer_counts": _count_layers(records),
        "target_answer_runner_question_count": len(target_question_ids),
        "target_answer_runner_question_ids": target_question_ids,
        "ready_for_answer_runner_prompt_overlay_patch": quality_status == "PASS",
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
        "status": "TRACE_NET_ENGINEERING_ENGRAM_ANSWER_RUNNER_RETRIEVAL_BRIDGE_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "quality_failures": quality_failures,
        "source_prompt_injector_path": str(prompt_injector_path),
        "source_h22_llm_smoke_path": h22_path_s,
        "safety_contract": dict(SAFETY_CONTRACT),
        "integration_policy": {
            "mode": "artifact_only_answer_runner_guidance_bridge",
            "proof_boundary": "Retrieved Engram guidance shapes behavior only; factual manual claims require current proof_context citations.",
            "forbidden": [
                "answer_permission_from_engram",
                "source_truth_mutation_from_engram",
                "summary_or_engram_used_as_proof",
                "live_db_or_qdrant_io_without_explicit_gate",
            ],
            "next_patch": "wire guidance_map into a targeted answer-runner smoke behind an explicit CLI flag",
        },
        "bridge_records": records,
        "guidance_map_path": str(guidance_map_path),
        "records_path": str(records_path),
        "quality_check_path": str(check_path),
    }
    _write_json(manifest_path, manifest)
    _write_jsonl(records_path, records)
    _write_json(guidance_map_path, guidance_map)
    _write_json(check_path, {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_ANSWER_RUNNER_RETRIEVAL_BRIDGE_CHECKED",
        "quality_status": quality_status,
        "summary": summary,
        "quality_failures": quality_failures,
    })
    manifest["output_path"] = str(manifest_path)
    _write_json(manifest_path, manifest)
    return manifest


def check_answer_runner_retrieval_bridge_manifest(
    *,
    bridge: str | Path,
    min_bridge_records: int = 6,
    min_task_types: int = 5,
    require_quality_pass: bool = True,
    require_no_answer_permission: bool = True,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    data = _read_json(bridge)
    summary = dict(data.get("summary") or {})
    failures: List[str] = []
    if require_quality_pass and data.get("quality_status") != "PASS":
        failures.append("source_quality_status_not_pass")
    if int(summary.get("bridge_record_count") or 0) < min_bridge_records:
        failures.append("bridge_record_count_below_min")
    if int(summary.get("task_type_count") or 0) < min_task_types:
        failures.append("task_type_count_below_min")
    if require_no_answer_permission and int(summary.get("answer_permission_count") or 0) != 0:
        failures.append("answer_permission_count_nonzero")
    if int(summary.get("unsafe_finding_count") or 0) > max_unsafe:
        failures.append("unsafe_finding_count_above_max")
    if int(summary.get("write_attempt_count") or 0) > max_write_attempts:
        failures.append("write_attempt_count_above_max")
    quality_status = "PASS" if not failures else "FAIL"
    result = {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_ANSWER_RUNNER_RETRIEVAL_BRIDGE_CHECKED",
        "quality_status": quality_status,
        "summary": summary,
        "quality_failures": failures,
    }
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build TRACE-Net H23 Engram answer-runner retrieval bridge.")
    p.add_argument("--prompt-injector", required=True)
    p.add_argument("--h22-llm-smoke", default="")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--max-guidance-chars", type=int, default=1400)
    p.add_argument("--min-bridge-records", type=int, default=6)
    p.add_argument("--min-task-types", type=int, default=5)
    p.add_argument("--require-h20-quality-pass", action="store_true")
    p.add_argument("--require-h22-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = build_answer_runner_retrieval_bridge_manifest(
        prompt_injector=args.prompt_injector,
        h22_llm_smoke=args.h22_llm_smoke or None,
        output_dir=args.output_dir,
        max_guidance_chars=args.max_guidance_chars,
        min_bridge_records=args.min_bridge_records,
        min_task_types=args.min_task_types,
        require_h20_quality_pass=args.require_h20_quality_pass,
        require_h22_quality_pass=args.require_h22_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
        max_unsafe=args.max_unsafe,
        max_write_attempts=args.max_write_attempts,
    )
    s = result.get("summary", {})
    print("status=" + str(result.get("status")))
    print("quality_status=" + str(result.get("quality_status")))
    print("bridge_record_count=" + str(s.get("bridge_record_count")))
    print("task_type_count=" + str(s.get("task_type_count")))
    print("target_answer_runner_question_count=" + str(s.get("target_answer_runner_question_count")))
    print("unsafe_finding_count=" + str(s.get("unsafe_finding_count")))
    print("answer_permission_count=" + str(s.get("answer_permission_count")))
    print("write_attempt_count=" + str(s.get("write_attempt_count")))
    print("output=" + str(Path(args.output_dir) / f"{MODULE}.json"))
    return 0 if result.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
