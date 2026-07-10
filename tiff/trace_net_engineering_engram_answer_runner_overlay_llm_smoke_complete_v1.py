from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

MODULE = "trace_net_engineering_engram_answer_runner_overlay_llm_smoke_complete_v1"
VERSION = "v1"

REQUIRED_BOUNDARY_PHRASES = [
    "proof_context",
    "source-trace-ready",
]


def _read_json(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _answer_text(record: Mapping[str, Any]) -> str:
    for key in ["answer", "llm_answer", "artifact_answer", "answer_text", "answer_preview"]:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value
    p = record.get("answer_path")
    if p and Path(str(p)).exists():
        return Path(str(p)).read_text(encoding="utf-8")
    return ""


def check_overlay_llm_smoke_complete(
    *,
    overlay_llm_smoke: str | Path,
    min_records: int = 1,
    min_answer_chars: int = 240,
    require_good: bool = True,
    require_boundary_language: bool = True,
    require_no_answer_permission: bool = True,
    max_unsupported_claims: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    data = _read_json(overlay_llm_smoke)
    records = list(data.get("smoke_records") or data.get("records") or [])
    checked = []
    failures: List[str] = []

    for rec in records:
        if not isinstance(rec, Mapping):
            continue
        answer = _answer_text(rec)
        lower = answer.lower()
        reasons = []
        if len(answer.strip()) < min_answer_chars:
            reasons.append("answer_too_short")
        if require_good and rec.get("grade") != "GOOD":
            reasons.append("grade_not_good")
        if require_boundary_language and not all(p in lower for p in REQUIRED_BOUNDARY_PHRASES):
            reasons.append("boundary_language_missing")
        if int(rec.get("unsupported_claim_count") or 0) > max_unsupported_claims:
            reasons.append("unsupported_claim_count_above_max")
        if require_no_answer_permission and bool(rec.get("answer_permission")):
            reasons.append("answer_permission_true")
        checked.append({
            "question_id": rec.get("question_id"),
            "grade": rec.get("grade"),
            "answer_char_count": len(answer),
            "unsupported_claim_count": int(rec.get("unsupported_claim_count") or 0),
            "answer_permission": bool(rec.get("answer_permission")),
            "complete": not reasons,
            "completion_failures": reasons,
        })

    if len(checked) < min_records:
        failures.append(f"record_count_below_min:{len(checked)}<{min_records}")
    failures.extend(f"{r['question_id']}:{','.join(r['completion_failures'])}" for r in checked if r["completion_failures"])

    summary = {
        "module": MODULE,
        "version": VERSION,
        "source_quality_status": data.get("quality_status"),
        "checked_record_count": len(checked),
        "complete_record_count": sum(1 for r in checked if r["complete"]),
        "min_answer_chars": min_answer_chars,
        "answer_permission_count": sum(1 for r in checked if r["answer_permission"]),
        "unsupported_claim_count": sum(int(r.get("unsupported_claim_count") or 0) for r in checked),
        "write_attempt_count": int((data.get("summary") or {}).get("write_attempt_count") or 0),
        "quality_failures": failures,
    }
    if summary["write_attempt_count"] > max_write_attempts:
        failures.append("write_attempt_count_above_max")
    return {
        "module": MODULE,
        "version": VERSION,
        "quality_status": "PASS" if not failures else "FAIL",
        "summary": summary,
        "checked_records": checked,
    }


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Check H25 overlay LLM smoke for complete guarded answers.")
    p.add_argument("--overlay-llm-smoke", required=True)
    p.add_argument("--min-records", type=int, default=1)
    p.add_argument("--min-answer-chars", type=int, default=240)
    p.add_argument("--require-good", action="store_true")
    p.add_argument("--require-boundary-language", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--max-unsupported-claims", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    p.add_argument("--output-dir", default="")
    args = p.parse_args(argv)
    result = check_overlay_llm_smoke_complete(
        overlay_llm_smoke=args.overlay_llm_smoke,
        min_records=args.min_records,
        min_answer_chars=args.min_answer_chars,
        require_good=args.require_good,
        require_boundary_language=args.require_boundary_language,
        require_no_answer_permission=args.require_no_answer_permission,
        max_unsupported_claims=args.max_unsupported_claims,
        max_write_attempts=args.max_write_attempts,
    )
    if args.output_dir:
        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{MODULE}.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    s = result["summary"]
    print("status=TRACE_NET_ENGINEERING_ENGRAM_OVERLAY_LLM_SMOKE_COMPLETENESS_CHECKED")
    print("quality_status=" + result["quality_status"])
    print("checked_record_count=" + str(s["checked_record_count"]))
    print("complete_record_count=" + str(s["complete_record_count"]))
    print("answer_permission_count=" + str(s["answer_permission_count"]))
    print("unsupported_claim_count=" + str(s["unsupported_claim_count"]))
    print("write_attempt_count=" + str(s["write_attempt_count"]))
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
