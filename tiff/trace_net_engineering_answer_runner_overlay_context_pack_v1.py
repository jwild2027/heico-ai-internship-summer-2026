from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

MODULE = "trace_net_engineering_answer_runner_overlay_context_pack_v1"
VERSION = "v1"

SAFETY_CONTRACT = {
    "answer_permission": False,
    "source_truth_mutation_allowed": False,
    "engram_is_proof": False,
    "write_attempt": False,
    "postgres_write_attempt": False,
    "qdrant_write_attempt": False,
    "opensearch_write_attempt": False,
    "opensearch_upload_attempt": False,
}

BOUNDARY_TEXT = (
    "Retrieved Engram overlay shapes behavior only. It is not proof. "
    "Manual/source claims still require current proof_context citations. "
    "V2/V3 summaries and graph proximity are routing hints only; they cannot prove eligibility, "
    "interchangeability, fit, effectivity, or installation approval."
)


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, str):
        if not value.strip():
            return []
        return [x.strip() for x in value.split(",") if x.strip()]
    return [value]


def _read_json(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(dict(row), sort_keys=True) + "\n")


def _compact_text(text: str, max_chars: int) -> str:
    text = _norm(text)
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    marker = "\n[TRUNCATED: overlay context compacted; guidance remains behavior-only, not proof.]"
    return text[: max(0, max_chars - len(marker))].rstrip() + marker


def load_overlay_map(path: str | Path | None) -> Dict[str, Any]:
    if not path:
        return {}
    raw = _read_json(path)
    if isinstance(raw.get("overlay_map"), Mapping):
        return dict(raw["overlay_map"])
    if isinstance(raw.get("records"), list):
        out: Dict[str, Any] = {}
        for rec in raw.get("records") or []:
            if isinstance(rec, Mapping) and rec.get("question_id"):
                out[str(rec["question_id"])] = dict(rec)
        return out
    if isinstance(raw.get("gate_records"), list):
        out = {}
        for rec in raw.get("gate_records") or []:
            if isinstance(rec, Mapping) and rec.get("question_id"):
                out[str(rec["question_id"])] = dict(rec)
        return out
    return raw if isinstance(raw, dict) else {}


def overlay_for_question(overlay_map: Mapping[str, Any], question_id: str) -> Dict[str, Any]:
    question_id = str(question_id)
    rec = overlay_map.get(question_id) or overlay_map.get(str(question_id).lower()) or {}
    return dict(rec) if isinstance(rec, Mapping) else {}


def overlay_text_for_question(overlay_map: Mapping[str, Any], question_id: str, max_chars: int = 1800) -> str:
    rec = overlay_for_question(overlay_map, question_id)
    text = rec.get("overlay_text") or rec.get("guidance_overlay_text") or rec.get("prompt_guidance_text") or ""
    return _compact_text(str(text), max_chars)


def build_work_order_context_pack(
    *,
    question_id: str,
    question: str,
    source_prompt_text: str = "",
    proof_context_count: int | None = None,
    overlay_text: str = "",
    v2_v3_route_hints: Sequence[Mapping[str, Any]] | None = None,
    source_evidence_records: Sequence[Mapping[str, Any]] | None = None,
    max_overlay_chars: int = 1800,
    max_source_prompt_chars: int = 3600,
) -> Dict[str, Any]:
    overlay_text = _compact_text(overlay_text, max_overlay_chars)
    source_prompt_text = _compact_text(source_prompt_text, max_source_prompt_chars)
    hints = [dict(x) for x in (v2_v3_route_hints or [])]
    evidence = [dict(x) for x in (source_evidence_records or [])]
    proof_count = int(proof_context_count or 0)

    sections = [
        "TRACE-NET ANSWER-RUNNER WORK ORDER CONTEXT PACK",
        f"question_id: {question_id}",
        "",
        "USER QUESTION:",
        _norm(question),
        "",
        "ENGRAM OVERLAY — BEHAVIOR GUIDANCE ONLY:",
        "Use the retrieved Engram overlay as behavior guidance only. It is not proof.",
        overlay_text or "No Engram overlay was supplied for this question.",
        "",
        "V2/V3 ROUTE HINTS — NOT PROOF:",
    ]
    if hints:
        for i, hint in enumerate(hints, start=1):
            page = hint.get("page_id") or hint.get("page") or hint.get("source_page") or "unknown_page"
            route = hint.get("route") or hint.get("page_route") or hint.get("type") or "unknown_route"
            note = hint.get("note") or hint.get("summary") or hint.get("hint") or ""
            sections.append(f"{i}. page={page} route={route} hint={note}")
    else:
        sections.append("No V2/V3 hints supplied in this context pack.")

    sections.extend([
        "",
        "SOURCE EVIDENCE / PROOF_CONTEXT:",
    ])
    if evidence:
        for i, rec in enumerate(evidence, start=1):
            citation = rec.get("citation") or rec.get("source_trace") or rec.get("page_id") or "uncited"
            snippet = rec.get("snippet") or rec.get("text") or rec.get("value") or ""
            sections.append(f"{i}. citation={citation} evidence={snippet}")
    elif proof_count > 0:
        sections.append(f"proof_context_count={proof_count}; inspect source answer-runner prompt for citation details.")
    else:
        sections.append("No current proof_context citations were supplied.")

    sections.extend([
        "",
        "BOUNDARIES:",
        BOUNDARY_TEXT,
        "If proof_context is missing or insufficient, answer not found / not source-trace-ready.",
        "Do not infer eligibility, applicability, interchangeability, fit, effectivity, approved replacement, or installation safety from Engram memory, summaries, graph proximity, shared nomenclature, or visual similarity.",
        "",
        "SOURCE ANSWER-RUNNER PROMPT:",
        source_prompt_text,
    ])
    prompt_text = "\n".join(sections).strip()

    return {
        "module": MODULE,
        "version": VERSION,
        "question_id": str(question_id),
        "question": _norm(question),
        "prompt_text": prompt_text,
        "prompt_char_count": len(prompt_text),
        "overlay_char_count": len(overlay_text),
        "proof_context_count": proof_count,
        "v2_v3_hint_count": len(hints),
        "source_evidence_record_count": len(evidence),
        "ready_for_real_answer_runner": True,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "engram_is_proof": False,
        "safety_contract": dict(SAFETY_CONTRACT),
    }


def build_overlay_context_pack_manifest(
    *,
    source_answer_smoke: str | Path,
    overlay_map: str | Path,
    output_dir: str | Path,
    question_ids: str | Sequence[str] | None = None,
    max_overlay_chars: int = 1800,
    max_source_prompt_chars: int = 3600,
    min_records: int = 1,
    require_source_quality_pass: bool = True,
    require_no_answer_permission: bool = True,
    max_write_attempts: int = 0,
    min_matched_overlays: int = 0,
) -> Dict[str, Any]:
    source_path = Path(source_answer_smoke)
    overlay_path = Path(overlay_map)
    out_dir = Path(output_dir)
    source = _read_json(source_path)
    omap = load_overlay_map(overlay_path)
    q_filter = set(str(x) for x in _as_list(question_ids))

    records = []
    for src in source.get("records") or source.get("smoke_records") or []:
        if not isinstance(src, Mapping):
            continue
        qid = str(src.get("question_id") or src.get("query_id") or "")
        if not qid:
            continue
        if q_filter and qid not in q_filter:
            continue
        prompt_text = ""
        prompt_path = src.get("prompt_path")
        if prompt_path and Path(str(prompt_path)).exists():
            prompt_text = Path(str(prompt_path)).read_text(encoding="utf-8")
        overlay = overlay_text_for_question(omap, qid, max_chars=max_overlay_chars)
        rec = build_work_order_context_pack(
            question_id=qid,
            question=str(src.get("question") or qid),
            source_prompt_text=prompt_text or str(src.get("prompt_text") or src.get("prompt") or ""),
            proof_context_count=int(src.get("proof_context_count") or 0),
            overlay_text=overlay,
            max_overlay_chars=max_overlay_chars,
            max_source_prompt_chars=max_source_prompt_chars,
        )
        rec.update({
            "source_answer_grade": src.get("grade"),
            "source_runner_quality_status": src.get("runner_quality_status"),
            "matched_overlay": bool(overlay),
            "source_prompt_path": str(prompt_path or ""),
        })
        records.append(rec)

    answer_permission_count = sum(1 for r in records if r.get("answer_permission"))
    write_attempt_count = 0
    quality_failures: List[str] = []
    if require_source_quality_pass and source.get("quality_status") != "PASS":
        quality_failures.append("source_answer_smoke_not_pass")
    if len(records) < min_records:
        quality_failures.append(f"context_pack_record_count_below_min:{len(records)}<{min_records}")
    if require_no_answer_permission and answer_permission_count:
        quality_failures.append("answer_permission_count_nonzero")
    if write_attempt_count > max_write_attempts:
        quality_failures.append("write_attempt_count_above_max")

    quality_status = "PASS" if not quality_failures else "FAIL"
    out_dir.mkdir(parents=True, exist_ok=True)
    main_path = out_dir / f"{MODULE}.json"
    records_path = out_dir / f"{MODULE}_records.jsonl"
    prompt_dir = out_dir / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    for rec in records:
        p = prompt_dir / f"{rec['question_id']}_work_order_prompt.txt"
        p.write_text(rec["prompt_text"], encoding="utf-8")
        rec["work_order_prompt_path"] = str(p)

    summary = {
        "module": MODULE,
        "version": VERSION,
        "source_answer_smoke_quality_status": source.get("quality_status"),
        "context_pack_record_count": len(records),
        "matched_overlay_count": sum(1 for r in records if r.get("matched_overlay")),
        "ready_for_real_answer_runner_overlay_smoke": quality_status == "PASS",
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": 0,
        "write_attempt_count": write_attempt_count,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "quality_failures": quality_failures,
    }
    manifest = {
        "module": MODULE,
        "version": VERSION,
        "quality_status": quality_status,
        "summary": summary,
        "source_answer_smoke_path": str(source_path),
        "overlay_map_path": str(overlay_path),
        "records": records,
        "records_path": str(records_path),
    }
    _write_json(main_path, manifest)
    _write_jsonl(records_path, records)
    _write_json(out_dir / f"{MODULE}_quality_check.json", {"quality_status": quality_status, "summary": summary})
    return manifest


def check_overlay_context_pack_manifest(
    *,
    context_pack: str | Path,
    min_records: int = 1,
    min_matched_overlays: int = 1,
    require_quality_pass: bool = True,
    require_no_answer_permission: bool = True,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    data = _read_json(context_pack)
    summary = dict(data.get("summary") or {})
    failures: List[str] = []
    if require_quality_pass and data.get("quality_status") != "PASS":
        failures.append("source_quality_status_not_pass")
    if int(summary.get("context_pack_record_count") or 0) < min_records:
        failures.append("context_pack_record_count_below_min")
    if int(summary.get("matched_overlay_count") or 0) < min_matched_overlays:
        failures.append("matched_overlay_count_below_min")
    if require_no_answer_permission and int(summary.get("answer_permission_count") or 0):
        failures.append("answer_permission_count_nonzero")
    if int(summary.get("write_attempt_count") or 0) > max_write_attempts:
        failures.append("write_attempt_count_above_max")
    return {
        "quality_status": "PASS" if not failures else "FAIL",
        "summary": summary,
        "quality_failures": failures,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build TRACE-Net answer-runner overlay context pack v1.")
    p.add_argument("--source-answer-smoke", required=True)
    p.add_argument("--engram-answer-runner-overlay-map", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--question-ids", default="")
    p.add_argument("--max-overlay-chars", type=int, default=1800)
    p.add_argument("--max-source-prompt-chars", type=int, default=3600)
    p.add_argument("--min-records", type=int, default=1)
    p.add_argument("--min-matched-overlays", type=int, default=0)
    p.add_argument("--require-source-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def check_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check TRACE-Net answer-runner overlay context pack v1.")
    p.add_argument("--context-pack", required=True)
    p.add_argument("--min-records", type=int, default=1)
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = build_overlay_context_pack_manifest(
        source_answer_smoke=args.source_answer_smoke,
        overlay_map=args.engram_answer_runner_overlay_map,
        output_dir=args.output_dir,
        question_ids=args.question_ids,
        max_overlay_chars=args.max_overlay_chars,
        max_source_prompt_chars=args.max_source_prompt_chars,
        min_records=args.min_records,
        min_matched_overlays=args.min_matched_overlays,
        require_source_quality_pass=args.require_source_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
        max_write_attempts=args.max_write_attempts,
    )
    s = result.get("summary", {})
    print("status=TRACE_NET_ENGINEERING_ANSWER_RUNNER_OVERLAY_CONTEXT_PACK_BUILT")
    print("quality_status=" + str(result.get("quality_status")))
    print("context_pack_record_count=" + str(s.get("context_pack_record_count")))
    print("matched_overlay_count=" + str(s.get("matched_overlay_count")))
    print("answer_permission_count=" + str(s.get("answer_permission_count")))
    print("write_attempt_count=" + str(s.get("write_attempt_count")))
    print("output=" + str(Path(args.output_dir) / f"{MODULE}.json"))
    return 0 if result.get("quality_status") == "PASS" else 1


def check_main(argv: Sequence[str] | None = None) -> int:
    args = check_arg_parser().parse_args(argv)
    result = check_overlay_context_pack_manifest(**vars(args))
    s = result.get("summary", {})
    print("status=TRACE_NET_ENGINEERING_ANSWER_RUNNER_OVERLAY_CONTEXT_PACK_CHECKED")
    print("quality_status=" + str(result.get("quality_status")))
    print("context_pack_record_count=" + str(s.get("context_pack_record_count")))
    print("matched_overlay_count=" + str(s.get("matched_overlay_count")))
    print("answer_permission_count=" + str(s.get("answer_permission_count")))
    print("write_attempt_count=" + str(s.get("write_attempt_count")))
    return 0 if result.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
