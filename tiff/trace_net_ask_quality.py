"""Quality checks for TRACE-Net ask orchestration with feedback mode."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

DEFAULT_ASK_SUMMARY = Path("local_data/organization/trace_net/ask/trace_net_ask_summary.json")
DEFAULT_QUALITY = Path("local_data/organization/trace_net/ask/trace_net_ask_quality.json")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(value) if isinstance(value, dict) else {}


def _num(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _check(name: str, ok: bool, detail: str) -> Dict[str, Any]:
    return {"name": name, "status": "OK" if ok else "FAIL", "detail": detail}


def evaluate_trace_net_ask_quality(
    summary_path: Path = DEFAULT_ASK_SUMMARY,
    *,
    min_answer_pages: int = 1,
    min_evidence_records: int = 1,
    max_unsafe_answer_groups: int = 0,
    require_all_stages_ok: bool = True,
    require_feedback_mode: Optional[str] = None,
    require_feedback_simulation: bool = False,
    min_feedback_signals_used: int = 0,
    min_feedback_groups_adjusted: int = 0,
    min_feedback_rank_changed_records: int = 0,
    max_feedback_unsafe_groups: int = 0,
    max_feedback_context_warning_signals_used: int = 0,
    require_feedback_answer_changed: bool = False,
) -> Dict[str, Any]:
    report = _load_json(summary_path)
    stages = report.get("stages") or []
    ask_summary = report.get("summary") or {}
    artifacts = report.get("artifacts") or {}
    options = report.get("options") or {}
    stage_failures = [s for s in stages if s.get("status") != "OK"]
    stage_names = [s.get("name") for s in stages]
    answer_pages = ask_summary.get("answer_page_records")
    evidence_records = ask_summary.get("answer_evidence_records")
    unsafe_groups = ask_summary.get("unsafe_answer_groups")
    feedback_mode = options.get("feedback_mode", "off")
    feedback_stages = [s for s in stages if str(s.get("name", "")).startswith("feedback_")]
    feedback_ask_status = ask_summary.get("feedback_ask_status")
    feedback_signals_used = _num(ask_summary.get("feedback_ask_feedback_signals_used"), 0)
    feedback_groups_adjusted = _num(ask_summary.get("feedback_ask_groups_adjusted"), 0)
    feedback_rank_changed = _num(ask_summary.get("feedback_ask_rank_changed_records"), 0)
    feedback_unsafe = _num(ask_summary.get("feedback_ask_unsafe_groups"), 0)
    feedback_context_warning = _num(ask_summary.get("feedback_ask_context_warning_signals_used"), 0)
    feedback_answer_changed = bool(ask_summary.get("feedback_ask_answer_changed"))

    checks: List[Dict[str, Any]] = []
    checks.append(_check("ask_summary_present", bool(report), f"summary_path={summary_path}; present={bool(report)}"))
    checks.append(_check("ask_status", report.get("status") == "OK", f"status={report.get('status')}"))
    checks.append(_check("ask_stages_present", len(stages) >= 4, f"stages={len(stages)}"))
    checks.append(_check("ask_stages_ok", (not stage_failures) if require_all_stages_ok else True, f"stage_failures={len(stage_failures)}"))
    checks.append(_check("answer_pages", isinstance(answer_pages, int) and answer_pages >= min_answer_pages, f"answer_page_records={answer_pages}; minimum={min_answer_pages}"))
    checks.append(_check("evidence_records", isinstance(evidence_records, int) and evidence_records >= min_evidence_records, f"answer_evidence_records={evidence_records}; minimum={min_evidence_records}"))
    checks.append(_check("unsafe_answer_groups", (unsafe_groups or 0) <= max_unsafe_answer_groups, f"unsafe_answer_groups={unsafe_groups}; max={max_unsafe_answer_groups}"))
    checks.append(_check("answer_artifacts", bool(artifacts.get("answer_md") or artifacts.get("answer_html")), f"answer_md={artifacts.get('answer_md')}; answer_html={artifacts.get('answer_html')}"))

    if require_feedback_mode:
        checks.append(_check("feedback_mode", feedback_mode == require_feedback_mode, f"feedback_mode={feedback_mode}; expected={require_feedback_mode}"))
    if require_feedback_simulation:
        checks.append(_check("feedback_simulation_stages_present", len(feedback_stages) >= 2 and "feedback_search_simulation" in stage_names and "feedback_ask_simulation" in stage_names, f"feedback_stages={stage_names}"))
        checks.append(_check("feedback_ask_status", feedback_ask_status == "OK", f"feedback_ask_status={feedback_ask_status}"))
        checks.append(_check("feedback_signals_used", feedback_signals_used >= min_feedback_signals_used, f"signals_used={feedback_signals_used}; minimum={min_feedback_signals_used}"))
        checks.append(_check("feedback_groups_adjusted", feedback_groups_adjusted >= min_feedback_groups_adjusted, f"groups_adjusted={feedback_groups_adjusted}; minimum={min_feedback_groups_adjusted}"))
        checks.append(_check("feedback_rank_changed", feedback_rank_changed >= min_feedback_rank_changed_records, f"rank_changed={feedback_rank_changed}; minimum={min_feedback_rank_changed_records}"))
        checks.append(_check("feedback_unsafe_groups", feedback_unsafe <= max_feedback_unsafe_groups, f"unsafe={feedback_unsafe}; max={max_feedback_unsafe_groups}"))
        checks.append(_check("feedback_context_warning_signals_ignored", feedback_context_warning <= max_feedback_context_warning_signals_used, f"context_warning_signals_used={feedback_context_warning}; max={max_feedback_context_warning_signals_used}"))
        checks.append(_check("feedback_artifacts", bool(artifacts.get("feedback_ask_simulation_md") or artifacts.get("feedback_ask_simulation_html")), f"feedback_md={artifacts.get('feedback_ask_simulation_md')}; feedback_html={artifacts.get('feedback_ask_simulation_html')}"))
        if require_feedback_answer_changed:
            checks.append(_check("feedback_answer_changed", feedback_answer_changed, f"answer_changed={feedback_answer_changed}"))

    status = "OK" if all(c["status"] == "OK" for c in checks) else "FAIL"
    return {
        "status": status,
        "summary_path": str(summary_path),
        "ask_status": report.get("status"),
        "ask_version": report.get("version"),
        "ask_query": report.get("effective_query"),
        "ask_feedback_mode": feedback_mode,
        "ask_stage_count": len(stages),
        "ask_stage_failures": len(stage_failures),
        "ask_answer_page_records": answer_pages,
        "ask_answer_evidence_records": evidence_records,
        "ask_unsafe_answer_groups": unsafe_groups,
        "ask_feedback_stage_count": len(feedback_stages),
        "ask_feedback_ask_status": feedback_ask_status,
        "ask_feedback_signals_used": feedback_signals_used,
        "ask_feedback_groups_adjusted": feedback_groups_adjusted,
        "ask_feedback_rank_changed_records": feedback_rank_changed,
        "ask_feedback_answer_changed": feedback_answer_changed,
        "ask_feedback_unsafe_groups": feedback_unsafe,
        "ask_feedback_context_warning_signals_used": feedback_context_warning,
        "checks": checks,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Quality gate for TRACE-Net ask output.")
    p.add_argument("--summary", default=str(DEFAULT_ASK_SUMMARY))
    p.add_argument("--quality", default=str(DEFAULT_QUALITY))
    p.add_argument("--min-answer-pages", type=int, default=1)
    p.add_argument("--min-evidence-records", type=int, default=1)
    p.add_argument("--max-unsafe-answer-groups", type=int, default=0)
    p.add_argument("--require-feedback-mode", choices=["off", "simulate", "apply"], default=None)
    p.add_argument("--require-feedback-simulation", action="store_true")
    p.add_argument("--min-feedback-signals-used", type=int, default=0)
    p.add_argument("--min-feedback-groups-adjusted", type=int, default=0)
    p.add_argument("--min-feedback-rank-changed-records", type=int, default=0)
    p.add_argument("--max-feedback-unsafe-groups", type=int, default=0)
    p.add_argument("--max-feedback-context-warning-signals-used", type=int, default=0)
    p.add_argument("--require-feedback-answer-changed", action="store_true")
    p.add_argument("--write-json", action="store_true")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = evaluate_trace_net_ask_quality(
        Path(args.summary),
        min_answer_pages=args.min_answer_pages,
        min_evidence_records=args.min_evidence_records,
        max_unsafe_answer_groups=args.max_unsafe_answer_groups,
        require_feedback_mode=args.require_feedback_mode,
        require_feedback_simulation=args.require_feedback_simulation,
        min_feedback_signals_used=args.min_feedback_signals_used,
        min_feedback_groups_adjusted=args.min_feedback_groups_adjusted,
        min_feedback_rank_changed_records=args.min_feedback_rank_changed_records,
        max_feedback_unsafe_groups=args.max_feedback_unsafe_groups,
        max_feedback_context_warning_signals_used=args.max_feedback_context_warning_signals_used,
        require_feedback_answer_changed=args.require_feedback_answer_changed,
    )
    print("TRACE-Net ask quality gate")
    print(f"  Status: {report['status']}")
    print("  Summary:")
    for key in [
        "ask_status",
        "ask_version",
        "ask_query",
        "ask_feedback_mode",
        "ask_stage_count",
        "ask_stage_failures",
        "ask_answer_page_records",
        "ask_answer_evidence_records",
        "ask_unsafe_answer_groups",
        "ask_feedback_stage_count",
        "ask_feedback_ask_status",
        "ask_feedback_signals_used",
        "ask_feedback_groups_adjusted",
        "ask_feedback_rank_changed_records",
        "ask_feedback_answer_changed",
        "ask_feedback_unsafe_groups",
        "ask_feedback_context_warning_signals_used",
    ]:
        print(f"    {key}: {report.get(key)}")
    print("  Checks:")
    for check in report["checks"]:
        print(f"    {check['status']} {check['name']}: {check['detail']}")
    if args.write_json:
        path = Path(args.quality)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        print(f"\nJSON: {path}")
    return 0 if report["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
