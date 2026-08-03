from __future__ import annotations

import argparse
import json
import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

MODULE = "trace_net_engineering_engram_crag_repair_v1"
VERSION = "v1"

REPAIR_STATUSES = {"REVIEW", "REPAIR_RECOMMENDED", "FAIL", "CRITIC_REPAIR_RECOMMENDED"}
PASS_STATUSES = {"PASS", "EXPECTED_BOUNDARY", "NO_REPAIR_REQUIRED", "REPAIRED_ARTIFACT"}


def _read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: str | Path, rows: Sequence[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def _norm(value: Any) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())


def _preview(value: Any, limit: int = 1200) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _record_question_id(record: Mapping[str, Any]) -> str:
    return _norm(record.get("question_id") or record.get("target_question_id") or record.get("id"))


def _answer_text(record: Mapping[str, Any]) -> str:
    return str(record.get("answer_text") or record.get("answer_preview") or "")


def _critic_records(critic: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = critic.get("critic_records") or critic.get("records") or []
    return [dict(r) for r in rows if isinstance(r, Mapping)]


def _answer_records(answer_smoke: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = answer_smoke.get("records") or answer_smoke.get("smoke_records") or []
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        if not isinstance(r, Mapping):
            continue
        qid = _record_question_id(r)
        if qid:
            out[qid] = dict(r)
    return out


def critic_recommends_repair(record: Mapping[str, Any]) -> bool:
    if bool(record.get("repair_recommended")):
        return True
    status = _norm(record.get("critic_status")).upper()
    return status in REPAIR_STATUSES


def is_expected_boundary(record: Mapping[str, Any]) -> bool:
    status = _norm(record.get("critic_status")).upper()
    return bool(record.get("expected_unknown_boundary_partial")) or status == "EXPECTED_BOUNDARY"


def build_artifact_repair_answer(*, question: str, original_answer: str, repair_hints: Sequence[Any]) -> str:
    hints = [f"- {_norm(h)}" for h in repair_hints if _norm(h)]
    hint_text = "\n".join(hints) if hints else "- Preserve proof boundaries and cite only current proof_context labels."
    original = _preview(original_answer, 1600)
    return (
        "Answer:\n"
        "CRAG artifact repair candidate prepared for reviewer-approved regeneration. This candidate does not add new proof and must remain bounded by current proof_context citations.\n\n"
        "Evidence:\n"
        "- The original answer and Self-RAG critic record were used as behavior guidance only, not as manual/source proof.\n\n"
        "Repair guidance:\n"
        f"{hint_text}\n\n"
        "Original answer preview:\n"
        f"{original}\n\n"
        "Engineering confidence:\n"
        "LOW until the repaired answer is rerun through the answer-smoke citation and unsupported-claim gates.\n\n"
        "Limits:\n"
        "This CRAG artifact cannot prove factual manual claims, grant answer permission, or mutate source truth."
    )


def build_crag_repair_manifest(
    *,
    critic_path: str | Path,
    answer_smoke_path: str | Path,
    output_dir: str | Path,
    llm_mode: str = "artifact",
    min_records: int = 1,
    min_crag_pass_or_no_repair: int = 1,
    max_repair_attempts: int = 0,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
    require_source_quality_pass: bool = False,
    require_critic_quality_pass: bool = False,
    require_no_answer_permission: bool = False,
) -> dict[str, Any]:
    critic_path = Path(critic_path)
    answer_smoke_path = Path(answer_smoke_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    critic = _read_json(critic_path)
    answer_smoke = _read_json(answer_smoke_path)
    c_records = _critic_records(critic)
    a_records = _answer_records(answer_smoke)

    repair_records: list[dict[str, Any]] = []
    repair_candidates: list[dict[str, Any]] = []

    repair_attempt_count = 0
    repair_recommended_count = 0
    no_repair_required_count = 0
    expected_boundary_preserved_count = 0
    unsafe_finding_count = 0
    answer_permission_count = 0

    for c in c_records:
        qid = _record_question_id(c)
        answer = a_records.get(qid, {})
        question = _norm(answer.get("question") or c.get("question") or qid)
        critic_status = _norm(c.get("critic_status") or "UNKNOWN")
        source_grade = _norm(c.get("source_grade") or answer.get("grade"))
        repair_recommended = critic_recommends_repair(c)
        expected_boundary = is_expected_boundary(c)
        repair_hints = list(c.get("repair_hints") or [])

        crag_status = "NO_REPAIR_REQUIRED"
        repair_attempted = False
        repaired_answer_text = ""
        findings: list[str] = []

        if expected_boundary and not repair_recommended:
            crag_status = "EXPECTED_BOUNDARY_PRESERVED"
            expected_boundary_preserved_count += 1
            findings.append("expected_boundary_preserved_no_repair")
        elif repair_recommended:
            repair_recommended_count += 1
            findings.append("critic_recommended_repair")
            if repair_attempt_count < max_repair_attempts:
                repair_attempted = True
                repair_attempt_count += 1
                crag_status = "REPAIRED_ARTIFACT" if llm_mode == "artifact" else "REPAIR_PLANNED"
                repaired_answer_text = build_artifact_repair_answer(
                    question=question,
                    original_answer=_answer_text(answer),
                    repair_hints=repair_hints,
                )
            else:
                crag_status = "REPAIR_BLOCKED_BY_MAX_ATTEMPTS"
                findings.append("repair_blocked_by_max_attempts")
        else:
            no_repair_required_count += 1
            findings.append("critic_passed_no_repair_required")

        unsafe = bool(c.get("unsafe")) or bool(answer.get("unsafe"))
        answer_permission = bool(c.get("answer_permission")) or bool(answer.get("answer_permission")) or bool(answer.get("can_answer_directly"))
        if unsafe:
            unsafe_finding_count += 1
        if answer_permission:
            answer_permission_count += 1

        rec = {
            "question_id": qid,
            "question": question,
            "source_grade": source_grade,
            "critic_status": critic_status,
            "expected_unknown_boundary_partial": expected_boundary,
            "repair_recommended": repair_recommended,
            "repair_attempted": repair_attempted,
            "crag_status": crag_status,
            "repair_hints": repair_hints,
            "findings": findings,
            "unsafe": unsafe,
            "answer_permission": answer_permission,
            "source_answer_sha256": _sha(_answer_text(answer)),
            "source_answer_preview": _preview(_answer_text(answer), 900),
            "repaired_answer_sha256": _sha(repaired_answer_text) if repaired_answer_text else "",
            "repaired_answer_preview": _preview(repaired_answer_text, 900),
        }
        repair_records.append(rec)
        if repair_recommended:
            repair_candidates.append(rec)

    crag_pass_or_no_repair_count = sum(
        1 for r in repair_records if str(r.get("crag_status")) in {"NO_REPAIR_REQUIRED", "EXPECTED_BOUNDARY_PRESERVED", "REPAIRED_ARTIFACT", "REPAIR_PLANNED"}
    )

    write_attempt_count = 0
    postgres_write_attempt_count = 0
    qdrant_write_attempt_count = 0
    qdrant_read_attempt_count = 0
    opensearch_write_attempt_count = 0
    opensearch_upload_attempt_count = 0
    source_truth_mutation_allowed_count = 0

    quality_failures: list[str] = []
    source_quality = answer_smoke.get("quality_status")
    critic_quality = critic.get("quality_status")
    if require_source_quality_pass and source_quality != "PASS":
        quality_failures.append("source_answer_smoke_quality_status_not_pass")
    if require_critic_quality_pass and critic_quality != "PASS":
        quality_failures.append("source_critic_quality_status_not_pass")
    if len(repair_records) < min_records:
        quality_failures.append(f"critic_record_count_below_min:{len(repair_records)}<{min_records}")
    if crag_pass_or_no_repair_count < min_crag_pass_or_no_repair:
        quality_failures.append(f"crag_pass_or_no_repair_below_min:{crag_pass_or_no_repair_count}<{min_crag_pass_or_no_repair}")
    if repair_attempt_count > max_repair_attempts:
        quality_failures.append(f"repair_attempt_count_above_max:{repair_attempt_count}>{max_repair_attempts}")
    if unsafe_finding_count > max_unsafe:
        quality_failures.append(f"unsafe_finding_count_above_max:{unsafe_finding_count}>{max_unsafe}")
    if require_no_answer_permission and answer_permission_count:
        quality_failures.append("answer_permission_present")
    if write_attempt_count > max_write_attempts:
        quality_failures.append(f"write_attempt_count_above_max:{write_attempt_count}>{max_write_attempts}")

    quality_status = "PASS" if not quality_failures else "FAIL"

    records_path = output_dir / "trace_net_engineering_engram_crag_repair_records_v1.jsonl"
    candidates_path = output_dir / "trace_net_engineering_engram_crag_repair_candidates_v1.jsonl"
    check_path = output_dir / "trace_net_engineering_engram_crag_repair_v1_quality_check.json"
    manifest_path = output_dir / "trace_net_engineering_engram_crag_repair_v1.json"

    summary = {
        "module": MODULE,
        "version": VERSION,
        "critic_record_count": len(repair_records),
        "crag_pass_or_no_repair_count": crag_pass_or_no_repair_count,
        "no_repair_required_count": no_repair_required_count,
        "expected_boundary_preserved_count": expected_boundary_preserved_count,
        "repair_recommended_count": repair_recommended_count,
        "repair_attempt_count": repair_attempt_count,
        "repair_candidate_count": len(repair_candidates),
        "source_answer_smoke_quality_status": source_quality,
        "source_critic_quality_status": critic_quality,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "postgres_write_attempt_count": postgres_write_attempt_count,
        "qdrant_read_attempt_count": qdrant_read_attempt_count,
        "qdrant_write_attempt_count": qdrant_write_attempt_count,
        "opensearch_write_attempt_count": opensearch_write_attempt_count,
        "opensearch_upload_attempt_count": opensearch_upload_attempt_count,
        "write_attempt_count": write_attempt_count,
        "unsafe_finding_count": unsafe_finding_count,
        "quality_failures": quality_failures,
        "ready_for_qdrant_engram_adapter": quality_status == "PASS",
        "ready_for_postgres_feedback_ledger": quality_status == "PASS",
    }

    manifest = {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_CRAG_REPAIR_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "crag_policy": {
            "mode": "artifact_only_crag_engram_repair",
            "repair_rule": "Only records marked REVIEW/REPAIR_RECOMMENDED by the Self-RAG critic are eligible for repair.",
            "expected_boundary_rule": "Expected unknown/no-proof partials are preserved and not repaired.",
            "proof_boundary": "CRAG may repair answer behavior, formatting, and citation discipline; it cannot create proof or use Engram memory as source evidence.",
            "forbidden": [
                "answer_permission_from_crag",
                "source_truth_mutation_from_crag",
                "summary_or_engram_used_as_proof",
                "live_db_or_qdrant_io_without_explicit_gate",
            ],
            "next_patch": "Live Qdrant Engram vector adapter behind explicit gates.",
        },
        "inputs": {
            "critic": str(critic_path),
            "answer_smoke": str(answer_smoke_path),
        },
        "outputs": {
            "records_jsonl": str(records_path),
            "repair_candidates_jsonl": str(candidates_path),
            "quality_check": str(check_path),
            "manifest": str(manifest_path),
        },
        "crag_repair_records": repair_records,
        "repair_candidate_records": repair_candidates,
    }

    _write_jsonl(records_path, repair_records)
    _write_jsonl(candidates_path, repair_candidates)
    _write_json(check_path, {"quality_status": quality_status, "summary": summary})
    _write_json(manifest_path, manifest)
    return manifest


def check_crag_repair_manifest(
    *,
    crag_repair: str | Path,
    min_records: int = 1,
    min_crag_pass_or_no_repair: int = 1,
    require_quality_pass: bool = False,
    require_no_answer_permission: bool = False,
    max_repair_attempts: int = 0,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> dict[str, Any]:
    data = _read_json(crag_repair)
    summary = dict(data.get("summary") or {})
    quality_failures = list(summary.get("quality_failures") or [])

    if require_quality_pass and data.get("quality_status") != "PASS":
        quality_failures.append("source_quality_status_not_pass")
    if int(summary.get("critic_record_count") or 0) < min_records:
        quality_failures.append("critic_record_count_below_min")
    if int(summary.get("crag_pass_or_no_repair_count") or 0) < min_crag_pass_or_no_repair:
        quality_failures.append("crag_pass_or_no_repair_below_min")
    if int(summary.get("repair_attempt_count") or 0) > max_repair_attempts:
        quality_failures.append("repair_attempt_count_above_max")
    if require_no_answer_permission and int(summary.get("answer_permission_count") or 0):
        quality_failures.append("answer_permission_present")
    if int(summary.get("unsafe_finding_count") or 0) > max_unsafe:
        quality_failures.append("unsafe_finding_count_above_max")
    if int(summary.get("write_attempt_count") or 0) > max_write_attempts:
        quality_failures.append("write_attempt_count_above_max")

    quality_status = "PASS" if not quality_failures else "FAIL"
    return {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_CRAG_REPAIR_CHECKED",
        "quality_status": quality_status,
        "critic_record_count": int(summary.get("critic_record_count") or 0),
        "crag_pass_or_no_repair_count": int(summary.get("crag_pass_or_no_repair_count") or 0),
        "repair_recommended_count": int(summary.get("repair_recommended_count") or 0),
        "repair_attempt_count": int(summary.get("repair_attempt_count") or 0),
        "unsafe_finding_count": int(summary.get("unsafe_finding_count") or 0),
        "answer_permission_count": int(summary.get("answer_permission_count") or 0),
        "write_attempt_count": int(summary.get("write_attempt_count") or 0),
        "quality_failures": quality_failures,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Engineering Engram CRAG repair artifact v1")
    parser.add_argument("--critic", required=True)
    parser.add_argument("--answer-smoke", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--llm-mode", default="artifact", choices=["artifact", "planned"])
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-crag-pass-or-no-repair", type=int, default=1)
    parser.add_argument("--max-repair-attempts", type=int, default=0)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-critic-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--max-write-attempts", type=int, default=0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    kwargs = vars(args).copy()

    # H29 CLI compatibility: argparse uses concise CLI names such as
    # --critic and --answer-smoke, while the artifact builder may use
    # more explicit internal parameter names.  Map aliases based on the
    # actual build_crag_repair_manifest signature, then pass only accepted
    # keyword arguments.
    import inspect

    sig = inspect.signature(build_crag_repair_manifest)
    params = set(sig.parameters)

    alias_candidates = {
        "critic": (
            "critic",
            "critic_path",
            "critic_manifest",
            "critic_manifest_path",
            "self_rag_critic",
            "self_rag_critic_path",
        ),
        "answer_smoke": (
            "answer_smoke",
            "answer_smoke_path",
            "answer_smoke_manifest",
            "answer_smoke_manifest_path",
            "source_answer_smoke",
            "source_answer_smoke_path",
        ),
    }

    for cli_name, candidates in alias_candidates.items():
        if cli_name not in kwargs:
            continue
        if cli_name in params:
            continue
        value = kwargs.pop(cli_name)
        for candidate in candidates:
            if candidate in params:
                kwargs[candidate] = value
                break
        else:
            # Leave a clear error instead of silently ignoring a required input.
            kwargs[cli_name] = value

    kwargs = {k: v for k, v in kwargs.items() if k in params}
    manifest = build_crag_repair_manifest(**kwargs)
    s = manifest.get("summary", {})
    print("status=" + str(manifest.get("status")))
    print("quality_status=" + str(manifest.get("quality_status")))
    print("critic_record_count=" + str(s.get("critic_record_count")))
    print("crag_pass_or_no_repair_count=" + str(s.get("crag_pass_or_no_repair_count")))
    print("repair_recommended_count=" + str(s.get("repair_recommended_count")))
    print("repair_attempt_count=" + str(s.get("repair_attempt_count")))
    print("unsafe_finding_count=" + str(s.get("unsafe_finding_count")))
    print("answer_permission_count=" + str(s.get("answer_permission_count")))
    print("write_attempt_count=" + str(s.get("write_attempt_count")))
    print("output=" + str(manifest.get("outputs", {}).get("manifest")))
    return 0 if manifest.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
