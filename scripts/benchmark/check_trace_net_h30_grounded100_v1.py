#!/usr/bin/env python3
"""Check a completed TRACE-Net H30 Phase 5 Grounded-100 benchmark run."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from scripts.benchmark.run_trace_net_h30_grounded100_v1 import summarize_records
from scripts.benchmark.trace_net_h30_phase5_question_bank_v1 import (
    CONTRACT_ID,
    EXPECTED_TOTAL,
    validate_phase5_bank,
)

MODULE = "check_trace_net_h30_grounded100_v1"
STATUS = "TRACE_NET_H30_PHASE5_GROUNDED100_CHECK_V1"


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def default_contract_path(repo_root: Path) -> Path:
    return repo_root / "tests/fixtures/trace_net_h30_phase5_grounded100_contract_v1.json"


def inspect_run(run_dir: Path, contract: Mapping[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    bank_path = run_dir / "question_bank.json"
    if not bank_path.exists():
        return {
            "module": MODULE,
            "status": STATUS,
            "contract_id": contract.get("contract_id") or CONTRACT_ID,
            "quality_status": "FAIL",
            "failures": ["question_bank_missing"],
            "record_count": 0,
        }
    bank_doc = _mapping(load_json(bank_path))
    bank = [dict(row) for row in bank_doc.get("questions") or [] if isinstance(row, Mapping)]
    bank_validation = validate_phase5_bank(bank)
    if not bank_validation.get("accepted"):
        failures.extend(f"bank:{value}" for value in bank_validation.get("failures") or [])

    expected_count = int(contract.get("expected_question_count") or EXPECTED_TOTAL)
    record_files = sorted(run_dir.glob("[0-9][0-9][0-9]_q[0-9][0-9][0-9]_*.json"))
    records: list[dict[str, Any]] = []
    raw_records: list[dict[str, Any]] = []
    for path in record_files:
        payload = _mapping(load_json(path))
        evaluation = _mapping(payload.get("evaluation"))
        raw_records.append(payload)
        if not evaluation:
            failures.append(f"record_missing_evaluation:{path.name}")
            continue
        records.append(evaluation)

    ids = [str(row.get("question_id") or "") for row in records]
    expected_ids = [f"q{index:03d}" for index in range(1, expected_count + 1)]
    if len(record_files) != expected_count:
        failures.append(f"record_file_count:{len(record_files)}")
    if len(records) != expected_count:
        failures.append(f"record_count:{len(records)}")
    if sorted(ids) != expected_ids:
        missing = sorted(set(expected_ids) - set(ids))
        unexpected = sorted(set(ids) - set(expected_ids))
        if missing:
            failures.append("missing_question_ids:" + ",".join(missing))
        if unexpected:
            failures.append("unexpected_question_ids:" + ",".join(unexpected))
        if len(ids) != len(set(ids)):
            failures.append("duplicate_question_ids")

    category_counts = Counter(str(row.get("category") or "") for row in records)
    expected_categories = {
        str(key): int(value)
        for key, value in _mapping(contract.get("category_counts")).items()
    }
    if dict(category_counts) != expected_categories:
        failures.append("category_distribution_mismatch")

    summary = summarize_records(
        records,
        selected_count=expected_count,
        full_bank_count=expected_count,
        category_counts_expected=expected_categories,
        route_match_threshold=float(_mapping(contract.get("thresholds")).get("route_match_rate") or 0.90),
        identifier_recovery_threshold=float(_mapping(contract.get("thresholds")).get("identifier_recovery_rate") or 0.75),
        page_recovery_threshold=float(_mapping(contract.get("thresholds")).get("page_recovery_rate") or 0.70),
    )
    thresholds = _mapping(contract.get("thresholds"))

    def require_rate(name: str, numerator_key: str, denominator: int, threshold_key: str) -> None:
        threshold = float(thresholds.get(threshold_key) or 0.0)
        numerator = int(summary.get(numerator_key) or 0)
        rate = numerator / denominator if denominator else 0.0
        if rate + 1e-12 < threshold:
            failures.append(f"{name}_below_threshold:{rate:.6f}<{threshold:.6f}")

    require_rate("http_200_rate", "http_200_count", expected_count, "http_200_rate")
    require_rate("nonempty_answer_rate", "nonempty_answer_count", expected_count, "nonempty_answer_rate")
    require_rate("post_validation_accept_rate", "post_validation_accepted_count", expected_count, "post_validation_accept_rate")
    require_rate("public_contract_rate", "public_contract_pass_count", expected_count, "public_contract_rate")

    route_threshold = float(thresholds.get("route_match_rate") or 0.0)
    if float(summary.get("route_match_rate") or 0.0) + 1e-12 < route_threshold:
        failures.append("route_match_rate_below_threshold")
    id_threshold = float(thresholds.get("identifier_recovery_rate") or 0.0)
    if summary.get("identifier_question_count") and float(summary.get("identifier_recovery_rate") or 0.0) + 1e-12 < id_threshold:
        failures.append("identifier_recovery_rate_below_threshold")
    page_threshold = float(thresholds.get("page_recovery_rate") or 0.0)
    if summary.get("page_question_count") and float(summary.get("page_recovery_rate") or 0.0) + 1e-12 < page_threshold:
        failures.append("page_recovery_rate_below_threshold")

    maxima = (
        ("unknown_citation_id_count", "maximum_unknown_citations"),
        ("negative_control_fabricated_count", "maximum_negative_fabrications"),
        ("duplicate_candidate_total", "maximum_duplicate_candidates"),
        ("public_internal_leak_count", "maximum_public_internal_leaks"),
        ("public_output_anomaly_count", "maximum_public_output_anomalies"),
        ("unsafe_authority_assertion_count", "maximum_unsafe_authority_assertions"),
        ("required_citation_missing_count", "maximum_required_citation_missing"),
    )
    for summary_key, threshold_key in maxima:
        maximum = int(thresholds.get(threshold_key) or 0)
        value = int(summary.get(summary_key) or 0)
        if value > maximum:
            failures.append(f"{summary_key}:{value}>{maximum}")

    maximum_latency = float(thresholds.get("maximum_latency_ms") or 0.0)
    if maximum_latency > 0 and float(summary.get("maximum_latency_ms") or 0.0) > maximum_latency:
        failures.append("maximum_latency_exceeded")
    maximum_calls = int(thresholds.get("maximum_constrained_calls_per_record") or 1)
    if int(summary.get("maximum_constrained_calls_per_record") or 0) > maximum_calls:
        failures.append("constrained_call_maximum_exceeded")
    minimum_accepted = int(thresholds.get("minimum_constrained_writer_accepted") or 0)
    if int(summary.get("constrained_writer_accepted_count") or 0) < minimum_accepted:
        failures.append("no_constrained_writer_output_accepted")
    maximum_record_hard = int(thresholds.get("maximum_record_hard_failures") or 0)
    hard_count = sum(len(row.get("hard_failures") or []) for row in records)
    if hard_count > maximum_record_hard:
        failures.append(f"record_hard_failure_total:{hard_count}>{maximum_record_hard}")

    summary_path = run_dir / "summary.json"
    stored_summary = _mapping(load_json(summary_path)) if summary_path.exists() else {}
    stored_inner = _mapping(stored_summary.get("summary"))
    if not summary_path.exists():
        failures.append("summary_missing")
    elif str(stored_inner.get("quality_status") or stored_summary.get("quality_status") or "") != str(summary.get("quality_status")):
        failures.append("stored_summary_quality_mismatch")

    unique_failures = list(dict.fromkeys(failures))
    return {
        "module": MODULE,
        "status": STATUS,
        "contract_id": contract.get("contract_id") or CONTRACT_ID,
        "quality_status": "PASS" if not unique_failures else "FAIL",
        "record_count": len(records),
        "expected_record_count": expected_count,
        "passed_record_count": sum(not row.get("hard_failures") for row in records),
        "failed_record_count": sum(bool(row.get("hard_failures")) for row in records),
        "question_bank_quality_status": bank_validation.get("quality_status"),
        "question_bank_sha256": bank_validation.get("bank_sha256"),
        "category_counts": dict(category_counts),
        "summary": summary,
        "failure_count": len(unique_failures),
        "failures": unique_failures,
        "safety_contract": {
            "evaluation_only": True,
            "retrieval_changed": False,
            "ranking_changed": False,
            "route_changed": False,
            "answer_writer_changed": False,
            "source_truth_mutation_allowed": False,
            "database_write_attempt_count": 0,
        },
    }


def write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    summary = _mapping(report.get("summary"))
    lines = [
        "# TRACE-Net H30 Phase 5 Grounded-100 Acceptance",
        "",
        f"Status: **{report.get('quality_status')}**",
        "",
        f"Records: {report.get('record_count')}/{report.get('expected_record_count')}",
        f"Routes matched: {summary.get('route_match_count')}/{summary.get('question_count')}",
        f"HTTP 200: {summary.get('http_200_count')}",
        f"Post-validation accepted: {summary.get('post_validation_accepted_count')}",
        f"Identifier recovery rate: {summary.get('identifier_recovery_rate')}",
        f"Page recovery rate: {summary.get('page_recovery_rate')}",
        f"Maximum latency ms: {summary.get('maximum_latency_ms')}",
        f"Constrained outputs accepted: {summary.get('constrained_writer_accepted_count')}",
        f"Phase 3 fallbacks: {summary.get('constrained_writer_fallback_count')}",
        "",
        "## Failures",
        "",
    ]
    failures = list(report.get("failures") or [])
    lines.extend(f"- {value}" for value in failures)
    if not failures:
        lines.append("- None")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--contract", default="")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo_root).resolve()
    run_dir = Path(args.run_dir).resolve()
    contract_path = Path(args.contract).resolve() if args.contract else default_contract_path(repo)
    output_dir = Path(args.output_dir).resolve() if args.output_dir else run_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    contract = _mapping(load_json(contract_path))
    report = inspect_run(run_dir, contract)
    json_path = output_dir / "phase5_grounded100_acceptance.json"
    md_path = output_dir / "phase5_grounded100_acceptance.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(md_path, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"phase5_acceptance_json={json_path}")
    print(f"phase5_acceptance_markdown={md_path}")
    return 1 if args.strict and report.get("quality_status") != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
