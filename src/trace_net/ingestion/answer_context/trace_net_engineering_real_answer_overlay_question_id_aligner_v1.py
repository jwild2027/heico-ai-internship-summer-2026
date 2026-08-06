from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

MODULE = "trace_net_engineering_real_answer_overlay_question_id_aligner_v1"
VERSION = "v1"
OUTPUT_NAME = "trace_net_engineering_real_answer_question_id_overlay_map_v1.json"
QUALITY_CHECK_NAME = f"{MODULE}_quality_check.json"
JSONL_NAME = f"{MODULE}.jsonl"


def _read_json(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(data), indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(dict(row), sort_keys=True) + "\n")


def _norm(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    return " ".join(str(value).split())


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _first_nonempty(record: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = _norm(record.get(key))
        if value:
            return value
    return ""


def _records_from_manifest(data: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Return the most likely record list from TRACE-Net-style manifests.

    Existing TRACE-Net builders have used slightly different top-level names across
    smoke artifacts. This adapter deliberately accepts the common names instead of
    assuming a single historical shape.
    """
    candidate_keys = (
        "records",
        "context_pack_records",
        "overlay_records",
        "answer_smoke_overlay_records",
        "answer_smoke_overlay_map_records",
        "smoke_records",
        "smoke_questions",
        "questions",
        "results",
    )
    for key in candidate_keys:
        rows = data.get(key)
        if isinstance(rows, list):
            return [dict(r) for r in rows if isinstance(r, Mapping)]

    # Some wrappers place the real answer smoke under a nested manifest/result key.
    for key in ("manifest", "result", "data"):
        nested = data.get(key)
        if isinstance(nested, Mapping):
            rows = _records_from_manifest(nested)
            if rows:
                return rows
    return []


def _question_id(record: Mapping[str, Any], index: int) -> str:
    value = _first_nonempty(record, ("question_id", "query_id", "smoke_question_id", "id"))
    return value or f"q{index + 1:02d}"


def _question_text(record: Mapping[str, Any]) -> str:
    return _first_nonempty(
        record,
        (
            "question",
            "user_question",
            "query",
            "question_text",
            "prompt_question",
            "input_question",
            "source_question",
        ),
    )


def _overlay_text(record: Mapping[str, Any]) -> str:
    keys = (
        "engram_overlay_text",
        "overlay_text",
        "work_order_prompt_text",
        "answer_preview",
        "answer_text",
        "answer",
        "prompt_text",
        "guidance_text",
        "selected_atom_text",
        "injected_prompt_text",
    )
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _index_overlay_records(records: Sequence[Mapping[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    by_qid: Dict[str, Dict[str, Any]] = {}
    by_question: Dict[str, Dict[str, Any]] = {}
    for i, record in enumerate(records):
        row = dict(record)
        qid = _question_id(row, i)
        question = _question_text(row).lower()
        if qid:
            by_qid.setdefault(qid, row)
        if question:
            by_question.setdefault(question, row)
    return by_qid, by_question


def _classify_question(question: str) -> Tuple[str, List[str]]:
    q = question.lower()
    hints: List[str] = []
    intent = "general_engineering_lookup"

    if "figure" in q or "fig." in q or "diagram" in q or "show" in q:
        intent = "visual_figure_identification"
        hints.extend(
            [
                "Use current proof_context citations from figure/caption/OCR/visual evidence.",
                "Do not infer part identity, applicability, fit, or approval from figure number alone.",
                "If the proof_context only identifies a page/figure but not the requested claim, answer as not source-trace-ready.",
            ]
        )
    if "eligib" in q or "applicab" in q or "effectiv" in q:
        intent = "eligibility_or_applicability_lookup"
        hints.extend(
            [
                "Eligibility/applicability requires explicit source authority, not mention-only evidence.",
                "Do not infer installation approval or interchangeability from shared nomenclature or graph proximity.",
            ]
        )
    if "part" in q or "pn" in q or "p/n" in q:
        hints.append("Part-number claims must be backed by current source-trace citations.")

    if not hints:
        hints.append("Use only current source-trace proof_context for factual claims; treat Engram as behavior guidance only.")

    return intent, hints


def _fallback_guidance(question_id: str, question: str) -> str:
    intent, hints = _classify_question(question)
    hint_text = "\n".join(f"- {h}" for h in hints)
    return (
        "TRACE-NET ENGRAM OVERLAY — QUESTION-ID ALIGNED GUIDANCE ONLY\n"
        f"question_id: {question_id}\n"
        f"question_intent: {intent}\n\n"
        "This overlay is aligned to the real-answer smoke question ID so the normal answer-runner path can receive Engram-channel guidance. "
        "It is not proof, is not source evidence, and cannot prove any manual claim.\n\n"
        "Behavior guidance:\n"
        f"{hint_text}\n\n"
        "Safety boundary: Engram guidance, V2/V3 summaries, graph proximity, visual similarity, and shared nomenclature are routing/context hints only. "
        "They do not grant answer permission and must not be used as proof."
    )


def _aligned_overlay_text(question_id: str, question: str, source_overlay: Optional[Mapping[str, Any]], match_reason: str) -> str:
    source_text = _overlay_text(source_overlay or {})
    header = (
        "TRACE-NET ENGRAM OVERLAY — QUESTION-ID ALIGNED GUIDANCE ONLY\n"
        f"question_id: {question_id}\n"
        f"match_reason: {match_reason}\n\n"
        "This overlay is behavior guidance only. It is not proof and grants no answer permission.\n\n"
    )
    if source_text:
        return header + "SOURCE OVERLAY GUIDANCE:\n" + source_text
    return _fallback_guidance(question_id, question)


def build_question_id_aligned_overlay_map(
    *,
    source_answer_smoke: str | Path,
    source_overlay_map: str | Path,
    output_dir: str | Path,
    max_questions: int = 0,
    min_records: int = 1,
    min_matched_question_ids: int = 1,
    require_no_answer_permission: bool = True,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    source_answer_data = _read_json(source_answer_smoke)
    source_overlay_data = _read_json(source_overlay_map)

    answer_records = _records_from_manifest(source_answer_data)
    overlay_records = _records_from_manifest(source_overlay_data)

    if max_questions and max_questions > 0:
        answer_records = answer_records[:max_questions]

    overlay_by_qid, overlay_by_question = _index_overlay_records(overlay_records)

    aligned: List[Dict[str, Any]] = []
    matched_question_id_count = 0
    copied_source_overlay_count = 0

    for index, answer_record in enumerate(answer_records):
        qid = _question_id(answer_record, index)
        question = _question_text(answer_record)
        source_overlay: Optional[Mapping[str, Any]] = None
        match_reason = "fallback_question_id_guidance"

        if qid in overlay_by_qid:
            source_overlay = overlay_by_qid[qid]
            match_reason = "source_overlay_same_question_id"
            copied_source_overlay_count += 1
        elif question and question.lower() in overlay_by_question:
            source_overlay = overlay_by_question[question.lower()]
            match_reason = "source_overlay_same_question_text"
            copied_source_overlay_count += 1

        guidance_text = _aligned_overlay_text(qid, question, source_overlay, match_reason)
        intent, hints = _classify_question(question)

        safety_contract = {
            "proof_role": "guidance_only",
            "answer_permission": False,
            "can_be_used_as_proof": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "opensearch_upload_attempt": False,
        }

        row: Dict[str, Any] = {
            "module": MODULE,
            "version": VERSION,
            "question_id": qid,
            "query_id": qid,
            "question": question,
            "user_question": question,
            "question_intent": intent,
            "question_guidance_hints": hints,
            "alignment_status": "question_id_aligned",
            "matched_real_answer_question_id": True,
            "matched_source_overlay": bool(source_overlay),
            "source_overlay_match_reason": match_reason,
            "source_overlay_question_id": _question_id(source_overlay or {}, 0) if source_overlay else "",
            "engram_overlay_text": guidance_text,
            "overlay_text": guidance_text,
            "prompt_text": guidance_text,
            "guidance_text": guidance_text,
            "answer_preview": guidance_text,
            "answer": guidance_text,
            "work_order_prompt_text": guidance_text,
            "memory_layer": "working_memory",
            "memory_type": "real_answer_question_id_aligned_guidance",
            "proof_role": "guidance_only",
            "engram_is_proof": False,
            "can_be_used_as_proof": False,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "safety_contract": safety_contract,
            "write_attempt_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "opensearch_upload_attempt_count": 0,
        }
        aligned.append(row)
        matched_question_id_count += 1

    answer_permission_count = sum(1 for r in aligned if _as_bool(r.get("answer_permission")))
    source_truth_mutation_allowed_count = sum(1 for r in aligned if _as_bool(r.get("source_truth_mutation_allowed")))
    postgres_write_attempt_count = sum(1 for r in aligned if _as_bool(r.get("postgres_write_attempt_count")))
    qdrant_write_attempt_count = sum(1 for r in aligned if _as_bool(r.get("qdrant_write_attempt_count")))
    opensearch_write_attempt_count = sum(1 for r in aligned if _as_bool(r.get("opensearch_write_attempt_count")))
    opensearch_upload_attempt_count = sum(1 for r in aligned if _as_bool(r.get("opensearch_upload_attempt_count")))
    write_attempt_count = (
        postgres_write_attempt_count
        + qdrant_write_attempt_count
        + opensearch_write_attempt_count
        + opensearch_upload_attempt_count
        + sum(1 for r in aligned if _as_bool(r.get("write_attempt_count")))
    )

    quality_failures: List[str] = []
    if len(aligned) < min_records:
        quality_failures.append(f"aligned_overlay_record_count_below_min:{len(aligned)}<{min_records}")
    if matched_question_id_count < min_matched_question_ids:
        quality_failures.append(f"matched_question_id_count_below_min:{matched_question_id_count}<{min_matched_question_ids}")
    if require_no_answer_permission and answer_permission_count:
        quality_failures.append(f"answer_permission_count_nonzero:{answer_permission_count}")
    if source_truth_mutation_allowed_count:
        quality_failures.append(f"source_truth_mutation_allowed_count_nonzero:{source_truth_mutation_allowed_count}")
    if write_attempt_count > max_write_attempts:
        quality_failures.append(f"write_attempt_count_above_max:{write_attempt_count}>{max_write_attempts}")

    quality_status = "PASS" if not quality_failures else "FAIL"
    summary: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "source_answer_smoke_quality_status": source_answer_data.get("quality_status"),
        "source_overlay_map_quality_status": source_overlay_data.get("quality_status"),
        "source_answer_record_count": len(answer_records),
        "source_overlay_record_count": len(overlay_records),
        "aligned_overlay_record_count": len(aligned),
        "matched_question_id_count": matched_question_id_count,
        "copied_source_overlay_count": copied_source_overlay_count,
        "fallback_question_id_guidance_count": len(aligned) - copied_source_overlay_count,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "postgres_write_attempt_count": postgres_write_attempt_count,
        "qdrant_write_attempt_count": qdrant_write_attempt_count,
        "opensearch_write_attempt_count": opensearch_write_attempt_count,
        "opensearch_upload_attempt_count": opensearch_upload_attempt_count,
        "write_attempt_count": write_attempt_count,
        "ready_for_real_answer_runner_overlay_smoke": quality_status == "PASS",
        "quality_failures": quality_failures,
    }

    out_dir = Path(output_dir)
    output_path = out_dir / OUTPUT_NAME
    quality_path = out_dir / QUALITY_CHECK_NAME
    jsonl_path = out_dir / JSONL_NAME

    manifest: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "quality_status": quality_status,
        "summary": summary,
        "records": aligned,
        "overlay_records": aligned,
        "output_path": str(output_path),
        "quality_check_path": str(quality_path),
        "jsonl_path": str(jsonl_path),
    }

    _write_json(output_path, manifest)
    _write_json(quality_path, {"quality_status": quality_status, "summary": summary})
    _write_jsonl(jsonl_path, aligned)
    return manifest


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build a question-id aligned Engram overlay map for real answer-smoke questions.")
    p.add_argument("--source-answer-smoke", required=True)
    p.add_argument("--source-overlay-map", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--max-questions", type=int, default=0)
    p.add_argument("--min-records", type=int, default=1)
    p.add_argument("--min-matched-question-ids", type=int, default=1)
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = build_question_id_aligned_overlay_map(
        source_answer_smoke=args.source_answer_smoke,
        source_overlay_map=args.source_overlay_map,
        output_dir=args.output_dir,
        max_questions=args.max_questions,
        min_records=args.min_records,
        min_matched_question_ids=args.min_matched_question_ids,
        require_no_answer_permission=args.require_no_answer_permission,
        max_write_attempts=args.max_write_attempts,
    )
    summary = result.get("summary", {})
    print(f"status={MODULE.upper()}_BUILT")
    print(f"quality_status={result.get('quality_status')}")
    print(f"aligned_overlay_record_count={summary.get('aligned_overlay_record_count')}")
    print(f"matched_question_id_count={summary.get('matched_question_id_count')}")
    print(f"fallback_question_id_guidance_count={summary.get('fallback_question_id_guidance_count')}")
    print(f"answer_permission_count={summary.get('answer_permission_count')}")
    print(f"write_attempt_count={summary.get('write_attempt_count')}")
    print(f"output={result.get('output_path')}")
    return 0 if result.get("quality_status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
