from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

MODULE = "trace_net_fast_chat_multi_route_quality_gate_v1"
VERSION = "v1"
SUPPORTED_IMPLEMENTED_QUERY_TYPES = {"exact_part_number", "figure_or_item", "part_family"}
PLANNED_QUERY_TYPES = {"image_or_diagram", "plain_text"}
FORBIDDEN_FAMILY_WORDS = [
    "interchangeable",
    "replacement",
    "substitute",
    "approved",
    "equivalent",
    "supersedes",
]


class MultiRouteQualityGateError(RuntimeError):
    pass


def _read_json(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    return json.loads(p.read_text(encoding="utf-8", errors="replace"))


def _write_json(path: str | Path, payload: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def _write_text(path: str | Path, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _write_csv(path: str | Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _num(summary: Dict[str, Any], key: str) -> int:
    try:
        return int(summary.get(key, 0) or 0)
    except Exception:
        return 0


def _bool(value: Any) -> bool:
    return bool(value)


def _answer_text(payload: Dict[str, Any], explicit: Optional[str | Path] = None) -> str:
    if explicit:
        p = Path(explicit)
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace")
    answer = payload.get("answer_text")
    if isinstance(answer, str):
        return answer
    return ""


def _citation_labels(answer: str) -> List[str]:
    return re.findall(r"\[(E\d+)\]", answer or "")


def _make_violation(severity: str, code: str, message: str, query_type: str | None = None) -> Dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "query_type": query_type,
    }


def _has_forbidden_family_claim(answer: str) -> bool:
    lower = (answer or "").lower()
    return any(word in lower for word in FORBIDDEN_FAMILY_WORDS)


def _route_records_and_violations(
    *,
    fast_chat_payload: Dict[str, Any],
    answer: str,
    min_exact_direct_records: int,
    min_figure_item_records: int,
    min_part_family_records: int,
    min_family_part_numbers: int,
    allow_planned_routes: bool,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    summary = fast_chat_payload.get("summary") or {}
    query_type = summary.get("query_type")
    query_route = summary.get("query_route")
    records: List[Dict[str, Any]] = []
    violations: List[Dict[str, Any]] = []

    def add_check(name: str, passed: bool, detail: str) -> None:
        records.append({
            "check_name": name,
            "status": "PASS" if passed else "FAIL",
            "query_type": query_type,
            "detail": detail,
        })
        if not passed:
            violations.append(_make_violation("high", name, detail, query_type=query_type))

    add_check("source_context_quality_pass", summary.get("source_context_quality_status") == "PASS", f"source_context_quality_status={summary.get('source_context_quality_status')}")
    add_check("no_invalid_citations", _num(summary, "invalid_answer_citation_count") == 0, f"invalid_answer_citation_count={_num(summary, 'invalid_answer_citation_count')}")
    add_check("no_violations_from_runner", _num(summary, "violation_record_count") == 0, f"runner_violation_record_count={_num(summary, 'violation_record_count')}")
    add_check("has_answer_citations", len(_citation_labels(answer)) > 0 or _num(summary, "valid_answer_citation_count") > 0, f"answer_citations={len(_citation_labels(answer))}; valid={_num(summary, 'valid_answer_citation_count')}")

    if query_type == "exact_part_number":
        add_check("exact_route_ready", summary.get("fast_chat_runner_ready") is True, f"fast_chat_runner_ready={summary.get('fast_chat_runner_ready')}")
        add_check("exact_answer_quality_gate_passed", summary.get("answer_quality_gate_passed") is True, f"answer_quality_gate_passed={summary.get('answer_quality_gate_passed')}")
        add_check("exact_direct_records_min", _num(summary, "direct_exact_answer_record_count") >= min_exact_direct_records, f"direct_exact_answer_record_count={_num(summary, 'direct_exact_answer_record_count')} min={min_exact_direct_records}")
        add_check("exact_has_part_number", _num(summary, "query_part_number_count") >= 1, f"query_part_number_count={_num(summary, 'query_part_number_count')}")
    elif query_type == "figure_or_item":
        add_check("figure_item_route_ready", summary.get("fast_chat_runner_ready") is True and summary.get("figure_item_fast_answer_ready") is True, f"fast_chat_runner_ready={summary.get('fast_chat_runner_ready')}; figure_item_fast_answer_ready={summary.get('figure_item_fast_answer_ready')}")
        add_check("figure_item_records_min", _num(summary, "figure_item_answer_record_count") >= min_figure_item_records, f"figure_item_answer_record_count={_num(summary, 'figure_item_answer_record_count')} min={min_figure_item_records}")
        add_check("figure_item_has_part_or_page", _num(summary, "figure_item_answer_page_count") >= 1 or bool(summary.get("figure_item_part_numbers")), f"figure_item_answer_page_count={_num(summary, 'figure_item_answer_page_count')}; figure_item_part_numbers={summary.get('figure_item_part_numbers')}")
    elif query_type == "part_family":
        add_check("part_family_route_ready", summary.get("fast_chat_runner_ready") is True and summary.get("part_family_fast_answer_ready") is True, f"fast_chat_runner_ready={summary.get('fast_chat_runner_ready')}; part_family_fast_answer_ready={summary.get('part_family_fast_answer_ready')}")
        add_check("part_family_records_min", _num(summary, "part_family_answer_record_count") >= min_part_family_records, f"part_family_answer_record_count={_num(summary, 'part_family_answer_record_count')} min={min_part_family_records}")
        add_check("part_family_number_count_min", _num(summary, "part_family_part_number_count") >= min_family_part_numbers, f"part_family_part_number_count={_num(summary, 'part_family_part_number_count')} min={min_family_part_numbers}")
        add_check("part_family_no_forbidden_equivalence_claim", not _has_forbidden_family_claim(answer), "answer avoids substitute/equivalence wording")
    elif query_type in PLANNED_QUERY_TYPES or str(query_route or "").startswith("planned_"):
        planned_ok = allow_planned_routes and summary.get("implemented_query_type") is False
        add_check("planned_route_safe_placeholder", planned_ok, f"allow_planned_routes={allow_planned_routes}; implemented_query_type={summary.get('implemented_query_type')}; query_route={query_route}")
    else:
        add_check("known_query_type", False, f"unknown query_type={query_type}")

    return records, violations


def build_fast_chat_multi_route_quality_gate(
    *,
    fast_chat_report: str | Path,
    output_dir: str | Path,
    answer_file: Optional[str | Path] = None,
    min_exact_direct_records: int = 1,
    min_figure_item_records: int = 1,
    min_part_family_records: int = 1,
    min_family_part_numbers: int = 2,
    allow_planned_routes: bool = True,
    require_runner_quality_pass: bool = True,
    quality: bool = False,
) -> Dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fast_payload = _read_json(fast_chat_report)
    fast_summary = fast_payload.get("summary") or {}
    answer = _answer_text(fast_payload, answer_file)
    records, violations = _route_records_and_violations(
        fast_chat_payload=fast_payload,
        answer=answer,
        min_exact_direct_records=min_exact_direct_records,
        min_figure_item_records=min_figure_item_records,
        min_part_family_records=min_part_family_records,
        min_family_part_numbers=min_family_part_numbers,
        allow_planned_routes=allow_planned_routes,
    )

    if require_runner_quality_pass and fast_payload.get("quality_status") != "PASS":
        violations.append(_make_violation("critical", "runner_quality_not_pass", f"fast chat runner quality_status={fast_payload.get('quality_status')}", query_type=fast_summary.get("query_type")))
        records.append({"check_name": "runner_quality_pass", "status": "FAIL", "query_type": fast_summary.get("query_type"), "detail": f"quality_status={fast_payload.get('quality_status')}"})
    else:
        records.append({"check_name": "runner_quality_pass", "status": "PASS", "query_type": fast_summary.get("query_type"), "detail": f"quality_status={fast_payload.get('quality_status')}"})

    severity_counts: Dict[str, int] = {}
    for violation in violations:
        sev = str(violation.get("severity") or "unknown")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    route_quality_status = "PASS" if not violations else "FAIL"
    query_type = fast_summary.get("query_type")
    implemented = bool(fast_summary.get("implemented_query_type"))
    planned_route = query_type in PLANNED_QUERY_TYPES or str(fast_summary.get("query_route") or "").startswith("planned_")
    webui_answer_ready = route_quality_status == "PASS" and implemented and not planned_route

    summary = {
        "module": MODULE,
        "version": VERSION,
        "source_fast_chat_report": str(fast_chat_report),
        "source_fast_chat_quality_status": fast_payload.get("quality_status"),
        "query_type": query_type,
        "query_route": fast_summary.get("query_route"),
        "implemented_query_type": implemented,
        "planned_route": planned_route,
        "webui_answer_ready": webui_answer_ready,
        "multi_route_quality_gate_passed": route_quality_status == "PASS",
        "route_quality_status": route_quality_status,
        "route_check_count": len(records),
        "route_check_fail_count": sum(1 for r in records if r.get("status") != "PASS"),
        "violation_record_count": len(violations),
        "violation_severity_counts": severity_counts,
        "answer_char_count": len(answer),
        "answer_citation_count": len(_citation_labels(answer)),
        "valid_answer_citation_count": _num(fast_summary, "valid_answer_citation_count"),
        "invalid_answer_citation_count": _num(fast_summary, "invalid_answer_citation_count"),
        "direct_exact_answer_record_count": _num(fast_summary, "direct_exact_answer_record_count"),
        "figure_item_answer_record_count": _num(fast_summary, "figure_item_answer_record_count"),
        "part_family_answer_record_count": _num(fast_summary, "part_family_answer_record_count"),
        "part_family_part_number_count": _num(fast_summary, "part_family_part_number_count"),
        "part_family_part_numbers": fast_summary.get("part_family_part_numbers", []),
        "answer_quality_gate_passed": bool(fast_summary.get("answer_quality_gate_passed")),
        "fast_chat_runner_ready": bool(fast_summary.get("fast_chat_runner_ready")),
        "human_review_required_count": 0,
        "manual_review_required_count": 0,
        "unsafe_record_count": 0,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "write_attempt_count": 0,
        "dry_run_only": True,
    }

    quality_status = "PASS" if route_quality_status == "PASS" else "FAIL"
    payload: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "quality_status": quality_status,
        "summary": summary,
        "answer_text": answer,
        "records": records,
        "violations": violations,
    }

    _write_json(out_dir / f"{MODULE}.json", payload)
    _write_json(out_dir / f"{MODULE}_summary.json", summary)
    _write_csv(out_dir / f"{MODULE}_records.csv", records, ["check_name", "status", "query_type", "detail"])
    _write_text(out_dir / f"{MODULE}.md", "# TRACE-Net Fast Chat Multi-Route Quality Gate v1\n\n" + json.dumps(summary, indent=2, sort_keys=True))

    if quality:
        quality_payload = check_fast_chat_multi_route_quality_gate_quality(report_path=out_dir / f"{MODULE}.json")
        _write_json(out_dir / f"{MODULE}_quality_check.json", quality_payload)
        print(f"Wrote: {out_dir / f'{MODULE}_quality_check.json'}")

    print("Status: TRACE_NET_FAST_CHAT_MULTI_ROUTE_QUALITY_GATE_BUILT")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    return payload


def check_fast_chat_multi_route_quality_gate_quality(
    *,
    report_path: str | Path,
    write_json: bool = False,
    min_checks: int = 1,
    max_violations: int = 0,
    require_multi_route_quality_pass: bool = False,
    require_webui_answer_ready: bool = False,
    require_exact_part_query: bool = False,
    require_figure_item_query: bool = False,
    require_part_family_query: bool = False,
    allow_planned_route: bool = False,
    require_no_human_review_required: bool = False,
    max_unsafe: Optional[int] = None,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
) -> Dict[str, Any]:
    path = Path(report_path)
    payload = _read_json(path)
    summary = payload.get("summary") or {}
    failures: List[str] = []

    if payload.get("quality_status") != "PASS":
        failures.append("report quality_status is not PASS")
    if _num(summary, "route_check_count") < min_checks:
        failures.append(f"route_check_count below {min_checks}")
    if _num(summary, "violation_record_count") > max_violations:
        failures.append(f"violation_record_count above {max_violations}")
    if require_multi_route_quality_pass and not summary.get("multi_route_quality_gate_passed"):
        failures.append("multi_route_quality_gate_passed is not true")
    if require_webui_answer_ready and not summary.get("webui_answer_ready"):
        failures.append("webui_answer_ready is not true")
    if require_exact_part_query and summary.get("query_type") != "exact_part_number":
        failures.append("query_type is not exact_part_number")
    if require_figure_item_query and summary.get("query_type") != "figure_or_item":
        failures.append("query_type is not figure_or_item")
    if require_part_family_query and summary.get("query_type") != "part_family":
        failures.append("query_type is not part_family")
    if not allow_planned_route and summary.get("planned_route") and require_webui_answer_ready:
        failures.append("planned route cannot be webui-answer-ready")
    if require_no_human_review_required and (_num(summary, "human_review_required_count") or _num(summary, "manual_review_required_count")):
        failures.append("human/manual review required count is nonzero")
    if max_unsafe is not None and _num(summary, "unsafe_record_count") > max_unsafe:
        failures.append(f"unsafe_record_count above {max_unsafe}")
    if require_no_answer_permission and _num(summary, "answer_permission_count") != 0:
        failures.append("answer_permission_count is nonzero")
    if require_no_source_truth_mutation and _num(summary, "source_truth_mutation_allowed_count") != 0:
        failures.append("source_truth_mutation_allowed_count is nonzero")
    if require_no_write_attempts and _num(summary, "write_attempt_count") != 0:
        failures.append("write_attempt_count is nonzero")

    result = {
        "module": f"{MODULE}_quality_check",
        "version": VERSION,
        "quality_status": "FAIL" if failures else "PASS",
        "summary": summary,
        "failures": failures,
    }
    if write_json:
        _write_json(path.with_name(f"{MODULE}_quality_check.json"), result)
        print(f"Wrote: {path.with_name(f'{MODULE}_quality_check.json')}")
    print(f"Quality status: {result['quality_status']}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures))
    return result


def main_build() -> None:
    parser = argparse.ArgumentParser(description="Build TRACE-Net fast chat multi-route quality gate from a fast chat runner report.")
    parser.add_argument("--fast-chat-report", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--answer-file")
    parser.add_argument("--min-exact-direct-records", type=int, default=1)
    parser.add_argument("--min-figure-item-records", type=int, default=1)
    parser.add_argument("--min-part-family-records", type=int, default=1)
    parser.add_argument("--min-family-part-numbers", type=int, default=2)
    parser.add_argument("--allow-planned-routes", action="store_true", default=True)
    parser.add_argument("--fail-planned-routes", action="store_true")
    parser.add_argument("--require-runner-quality-pass", action="store_true", default=True)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args()
    return build_fast_chat_multi_route_quality_gate(
        fast_chat_report=args.fast_chat_report,
        output_dir=args.output_dir,
        answer_file=args.answer_file,
        min_exact_direct_records=args.min_exact_direct_records,
        min_figure_item_records=args.min_figure_item_records,
        min_part_family_records=args.min_part_family_records,
        min_family_part_numbers=args.min_family_part_numbers,
        allow_planned_routes=not args.fail_planned_routes,
        require_runner_quality_pass=args.require_runner_quality_pass,
        quality=args.quality,
    )


def main_check() -> None:
    parser = argparse.ArgumentParser(description="Check TRACE-Net fast chat multi-route quality gate output.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-checks", type=int, default=1)
    parser.add_argument("--max-violations", type=int, default=0)
    parser.add_argument("--require-multi-route-quality-pass", action="store_true")
    parser.add_argument("--require-webui-answer-ready", action="store_true")
    parser.add_argument("--require-exact-part-query", action="store_true")
    parser.add_argument("--require-figure-item-query", action="store_true")
    parser.add_argument("--require-part-family-query", action="store_true")
    parser.add_argument("--allow-planned-route", action="store_true")
    parser.add_argument("--require-no-human-review-required", action="store_true")
    parser.add_argument("--max-unsafe", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args()
    return check_fast_chat_multi_route_quality_gate_quality(**vars(args))


if __name__ == "__main__":
    main_build()
