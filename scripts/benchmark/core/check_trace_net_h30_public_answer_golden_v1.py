#!/usr/bin/env python3
"""Validate a TRACE-Net grounded-20 ``summary.json`` against the public-answer golden contract."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from src.trace_net.writing.trace_net_h30_public_answer_contract_v1 import (
    parse_public_answer,
    validate_public_answer_contract,
)

MODULE = "check_trace_net_h30_public_answer_golden_v1"
STATUS = "TRACE_NET_H30_PUBLIC_ANSWER_GOLDEN_V1"

CITATION_RE = re.compile(r"\[(\d{1,3})\]")
PART_RE = re.compile(r"\b(?:\d{2,4}-\d{4,6}(?:-\d{3})?(?:/\d{3})?|[A-Z]{2,}\d{4,}(?:[-./][A-Z0-9]+)*)\b", re.I)
PAGE_RE = re.compile(r"\bt_p_[A-Za-z0-9_]+\b", re.I)
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")


def _rows(value: Any) -> List[Dict[str, Any]]:
    return [dict(row) for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def _headings(text: str) -> List[str]:
    parsed = parse_public_answer(text)
    return [f"## {name}" for name in parsed["heading_order"]]


def _section_lines(text: str, target: str) -> List[str]:
    parsed = parse_public_answer(text)
    canonical = {"answer": "Answer", "evidence": "Evidence", "limits": "Limits"}.get(target.casefold(), target)
    return list(parsed["sections"].get(canonical, []))


def _normalized_line(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"^[-*]\s*", "", value)).strip().casefold()


def _contains(text: str, value: str) -> bool:
    return value.casefold() in text.casefold()


def _identifier_line_requires_citation(line: str) -> bool:
    low = line.casefold()
    if any(token in low for token in ("not found", "no indexed match", "no matching indexed", "does not establish", "does not prove", "no explicit")):
        return False
    return bool(PART_RE.search(line) or PAGE_RE.search(line) or ATA_RE.search(line) or re.search(r"\bfigure\s+\d+", line, re.I))


def validate_contract(summary_payload: Mapping[str, Any], contract: Mapping[str, Any]) -> Dict[str, Any]:
    records = _rows(summary_payload.get("records"))
    by_id = {str(row.get("question_id") or ""): row for row in records}
    expected = _rows(contract.get("questions"))
    expected_ids = [str(row.get("question_id") or "") for row in expected]
    expected_set = set(expected_ids)
    actual_set = set(by_id)
    global_rules = contract.get("global") if isinstance(contract.get("global"), Mapping) else {}

    results: List[Dict[str, Any]] = []
    global_forbidden_hits = 0
    unrelated_nomenclature_hits = 0
    raw_internal_hits = 0
    runtime_contract_failure_count = 0

    for rule in expected:
        qid = str(rule.get("question_id") or "")
        row = by_id.get(qid)
        failures: List[str] = []
        if row is None:
            results.append({"question_id": qid, "passed": False, "failures": ["missing_record"]})
            continue

        answer = str(row.get("answer") or "")
        question = str(row.get("question") or "")
        headings = _headings(answer)
        if str(rule.get("question") or "") != question:
            failures.append("question_changed")
        if str(rule.get("category") or "") != str(row.get("category") or ""):
            failures.append("category_changed")
        if bool(global_rules.get("require_post_validation_accepted", True)) and not row.get("post_validation_accepted"):
            failures.append("post_validation_rejected")

        runtime_contract = validate_public_answer_contract(
            answer,
            route=str(row.get("actual_route") or row.get("expected_route") or ""),
        )
        for failure in runtime_contract.get("failures") or []:
            failures.append(f"public_contract:{failure}")
            runtime_contract_failure_count += 1

        required_headings = list(rule.get("required_headings") or global_rules.get("required_headings") or [])
        for heading in required_headings:
            if heading not in headings:
                failures.append(f"missing_heading:{heading}")
        allowed_headings = set(global_rules.get("allowed_headings") or [])
        for heading in headings:
            if allowed_headings and heading not in allowed_headings:
                failures.append(f"unexpected_heading:{heading}")

        require_limits = rule.get("require_limits")
        if require_limits is True and "## Limits" not in headings:
            failures.append("limits_required")
        if require_limits is False and "## Limits" in headings:
            failures.append("limits_should_be_omitted")

        for value in rule.get("required_text") or []:
            if not _contains(answer, str(value)):
                failures.append(f"missing_text:{value}")
        for group in rule.get("any_of") or []:
            if isinstance(group, list) and group and not any(_contains(answer, str(value)) for value in group):
                failures.append("missing_any_of:" + "|".join(map(str, group)))

        forbidden = list(global_rules.get("forbidden_text") or []) + list(rule.get("forbidden_text") or [])
        forbidden_identifiers = list(rule.get("forbidden_identifiers") or [])
        for value in forbidden:
            if _contains(answer, str(value)):
                failures.append(f"forbidden_text:{value}")
                global_forbidden_hits += 1
                if str(value).casefold() in {x.casefold() for x in global_rules.get("raw_internal_labels") or []}:
                    raw_internal_hits += 1
        for value in forbidden_identifiers:
            if _contains(answer, str(value)):
                failures.append(f"unrelated_identifier:{value}")
                unrelated_nomenclature_hits += 1

        evidence_lines = _section_lines(answer, "Evidence")
        normalized = [_normalized_line(line) for line in evidence_lines]
        duplicates = sum(count - 1 for count in Counter(normalized).values() if count > 1)
        if duplicates:
            failures.append(f"duplicate_evidence_lines:{duplicates}")

        if rule.get("require_answer_citation"):
            answer_lines = _section_lines(answer, "Answer")
            if answer_lines and not CITATION_RE.search(answer_lines[0]):
                failures.append("answer_citation_required")
        if rule.get("require_identifier_lines_cited", True):
            for line in _section_lines(answer, "Answer") + evidence_lines:
                if _identifier_line_requires_citation(line) and not CITATION_RE.search(line):
                    failures.append("uncited_identifier_line")
                    break

        results.append({
            "question_id": qid,
            "passed": not failures,
            "failures": list(dict.fromkeys(failures)),
        })

    missing = sorted(expected_set - actual_set)
    unexpected = sorted(actual_set - expected_set)
    passed_count = sum(bool(row.get("passed")) for row in results)
    failure_count = len(results) - passed_count + len(missing) + len(unexpected)
    status = "PASS" if failure_count == 0 else "FAIL"
    return {
        "module": MODULE,
        "status": STATUS,
        "quality_status": status,
        "contract_id": contract.get("contract_id"),
        "question_count": len(records),
        "contract_question_count": len(expected),
        "passed_question_count": passed_count,
        "failed_question_count": len(results) - passed_count,
        "missing_question_ids": missing,
        "unexpected_question_ids": unexpected,
        "global_forbidden_hit_count": global_forbidden_hits,
        "unrelated_nomenclature_result_count": unrelated_nomenclature_hits,
        "raw_internal_label_count": raw_internal_hits,
        "runtime_contract_failure_count": runtime_contract_failure_count,
        "post_validation_rejected_count": sum(
            1 for row in records if not bool(row.get("post_validation_accepted"))
        ),
        "results": results,
    }


def write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    lines = [
        "# TRACE-Net H30 Public Answer Golden Contract",
        "",
        f"Status: **{report.get('quality_status')}**",
        "",
        f"Questions passed: {report.get('passed_question_count')}/{report.get('contract_question_count')}",
        f"Post-validation rejected: {report.get('post_validation_rejected_count')}",
        f"Runtime contract failures: {report.get('runtime_contract_failure_count')}",
        f"Unrelated nomenclature results: {report.get('unrelated_nomenclature_result_count')}",
        f"Raw internal labels: {report.get('raw_internal_label_count')}",
        "",
        "| Question | Status | Failures |",
        "|---|---|---|",
    ]
    for row in report.get("results") or []:
        failures = ", ".join(row.get("failures") or []) or "—"
        lines.append(f"| {row.get('question_id')} | {'PASS' if row.get('passed') else 'FAIL'} | {failures} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True)
    parser.add_argument(
        "--contract",
        default="tests/fixtures/trace_net_h30_tiff_grounded20_public_answer_golden_v1.json",
    )
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary_path = Path(args.summary).resolve()
    contract_path = Path(args.contract).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else summary_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    report = validate_contract(summary, contract)
    json_path = output_dir / "public_answer_golden_report.json"
    md_path = output_dir / "public_answer_golden_report.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(md_path, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"golden_report_json={json_path}")
    print(f"golden_report_markdown={md_path}")
    return 1 if args.strict and report.get("quality_status") != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
