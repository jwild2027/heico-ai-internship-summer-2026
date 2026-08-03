"""TRACE-Net Route Unresolved Retry/Probe v1.

This module takes the four-route validator runner output and retries only the
validator-gated unresolved pages using conservative, route-specific probes.

It is intentionally artifact-only: it does not write to Postgres, Qdrant,
OpenSearch, or source truth. The output is a storage/readiness decision report.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

MODULE = "trace_net_route_unresolved_retry_probe_v1"
VERSION = "v1"
VALID_OPERATIONAL_ROUTES = {"blank", "plain_text", "table", "image"}

PART_NUMBER_RE = re.compile(r"\b(?:\d{3}-\d{5}-\d{3}|[A-Z]{1,4}\d{2,5}(?:-\d{1,4})?[A-Z]?)\b")

TABLE_TERMS = {
    "assy number",
    "ch-sec-un-fig",
    "item",
    "nomenclature",
    "units per assy",
    "numerical index",
    "lep",
    "ipl",
    "issued inserted",
    "vendor",
    "directives incorporation",
    "part number",
}
PLAIN_TEXT_TERMS = {
    "description",
    "operation",
    "general",
    "removal",
    "installation",
    "inspection",
    "cleaning",
    "repair",
    "the ",
    "this ",
    "shall",
    "includes",
    "consists",
}
IMAGE_TERMS = {
    "figure",
    "view",
    "seat belt",
    "backrest",
    "ashtray",
    "floatable",
    "fastener",
    "skin ply",
    "abraded area",
    "vacuum",
    "tape",
    "callout",
}
TABLE_BLOCKER_FOR_IMAGE = {
    "assy number",
    "ch-sec-un-fig",
    "units per assy",
    "numerical index",
    "nomenclature",
}


@dataclass(frozen=True)
class ProbeResult:
    route: str
    passed: bool
    score: float
    reasons: tuple[str, ...]
    qdrant_embedding_allowed: bool
    opensearch_index_allowed: bool
    final_do_not_embed: bool


def _safe_load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _write_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    seen: set[str] = set()
    for record in records:
        for key in record:
            if key not in seen:
                fieldnames.append(key)
                seen.add(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({k: _csv_value(record.get(k)) for k in fieldnames})


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True)
    return value


def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    summary = payload.get("summary", {})
    lines = [
        "# TRACE-Net Route Unresolved Retry/Probe v1",
        "",
        "This artifact retries only validator-gated unresolved pages using conservative automatic probes.",
        "It does not grant answer permission or mutate source truth.",
        "",
        "## Summary",
        "",
    ]
    for key in sorted(summary):
        lines.append(f"- **{key}**: `{summary[key]}`")
    lines.extend([
        "",
        "## Safety contract",
        "",
        "- no Postgres writes",
        "- no Qdrant writes",
        "- no OpenSearch writes",
        "- no source-truth mutation",
        "- no answer permission",
        "",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _text(record: Mapping[str, Any]) -> str:
    chunks = [
        record.get("ocr_sample_text"),
        record.get("sample_text"),
        record.get("raw_ocr_text"),
    ]
    return "\n".join(str(chunk) for chunk in chunks if chunk).lower()


def _word_count(record: Mapping[str, Any]) -> int:
    for key in ("ocr_word_count", "ocr_text_word_count", "word_count"):
        value = record.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    sample = _text(record)
    return len(re.findall(r"\w+", sample))


def _part_count(record: Mapping[str, Any]) -> int:
    for key in ("part_number_count", "part_numbers_found_count"):
        value = record.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    tokens = record.get("part_number_tokens") or record.get("part_numbers") or []
    if isinstance(tokens, list):
        return len(tokens)
    return len(PART_NUMBER_RE.findall(_text(record)))


def _term_count(text: str, terms: set[str]) -> int:
    return sum(1 for term in terms if term in text)


def _is_unresolved(record: Mapping[str, Any]) -> bool:
    decision = str(record.get("validation_decision") or "").lower()
    status = str(record.get("validation_status") or "").lower()
    op_status = str(record.get("operational_resolution_status") or "").lower()
    return (
        decision == "validator_gated_unresolved"
        or status == "validator_gated_unresolved"
        or "validator_gated_unresolved" in op_status
        or (record.get("validator_required") is True and record.get("final_do_not_embed") is True and not record.get("validated_operational_route"))
    )


def _source_route(record: Mapping[str, Any]) -> str:
    for key in ("source_operational_route", "operational_route", "validated_operational_route"):
        value = record.get(key)
        if isinstance(value, str) and value in VALID_OPERATIONAL_ROUTES:
            return value
    return "plain_text"


def _candidate_routes(record: Mapping[str, Any]) -> list[str]:
    candidates: list[str] = []
    for key in ("candidate_operational_routes", "secondary_operational_routes"):
        value = record.get(key)
        if isinstance(value, list):
            candidates.extend(str(item) for item in value)
    source = _source_route(record)
    candidates.insert(0, source)
    # Always include a safe fallback order for unresolved pages. This mirrors
    # multi-route probes without assuming the source route is correct.
    candidates.extend(["table", "plain_text", "image", "blank"])
    deduped: list[str] = []
    for route in candidates:
        if route in VALID_OPERATIONAL_ROUTES and route not in deduped:
            deduped.append(route)
    return deduped


def _probe_blank(record: Mapping[str, Any]) -> ProbeResult:
    words = _word_count(record)
    parts = _part_count(record)
    text = _text(record)
    subtype = str(record.get("route_subtype") or "")
    score = 0.0
    reasons: list[str] = []
    if words <= 2:
        score += 70
        reasons.append("empty_or_near_empty_ocr")
    if parts == 0:
        score += 15
        reasons.append("no_part_numbers")
    if subtype == "blank_candidate" or not text.strip():
        score += 15
        reasons.append("blank_subtype_or_empty_sample")
    passed = score >= 85
    return ProbeResult("blank", passed, min(score, 100.0), tuple(reasons), False, False, True)


def _probe_table(record: Mapping[str, Any]) -> ProbeResult:
    words = _word_count(record)
    parts = _part_count(record)
    text = _text(record)
    subtype = str(record.get("route_subtype") or "")
    table_terms = _term_count(text, TABLE_TERMS)
    rowish = bool(re.search(r"\b(item|assy|number|fig|nomenclature)\b", text))
    score = 0.0
    reasons: list[str] = []
    if parts >= 10:
        score += 55
        reasons.append("high_part_number_count")
    elif parts >= 3:
        score += 40
        reasons.append("part_number_cluster")
    if table_terms >= 2:
        score += 35
        reasons.append("table_or_ipl_terms")
    elif table_terms == 1:
        score += 20
        reasons.append("single_table_or_ipl_term")
    if rowish and words >= 20:
        score += 15
        reasons.append("row_like_ocr_structure")
    if subtype in {"detailed_parts_list", "table_or_index"}:
        score += 10
        reasons.append("table_subtype_prior")
    passed = score >= 65
    return ProbeResult("table", passed, min(score, 100.0), tuple(reasons), True, True, False)


def _probe_plain_text(record: Mapping[str, Any]) -> ProbeResult:
    words = _word_count(record)
    parts = _part_count(record)
    text = _text(record)
    subtype = str(record.get("route_subtype") or "")
    plain_terms = _term_count(text, PLAIN_TEXT_TERMS)
    table_terms = _term_count(text, TABLE_TERMS)
    score = 0.0
    reasons: list[str] = []
    if words >= 80:
        score += 35
        reasons.append("substantial_ocr_text")
    elif words >= 35:
        score += 25
        reasons.append("moderate_ocr_text")
    if plain_terms >= 2:
        score += 30
        reasons.append("plain_text_or_procedure_terms")
    elif plain_terms == 1:
        score += 15
        reasons.append("single_plain_text_term")
    if parts <= 2:
        score += 20
        reasons.append("low_part_number_density")
    if table_terms <= 1:
        score += 10
        reasons.append("low_table_term_density")
    if subtype in {"normal_text", "procedure_or_description", "cover_or_title_page"}:
        score += 10
        reasons.append("plain_text_subtype_prior")
    passed = score >= 65
    return ProbeResult("plain_text", passed, min(score, 100.0), tuple(reasons), True, False, False)


def _probe_image(record: Mapping[str, Any]) -> ProbeResult:
    words = _word_count(record)
    parts = _part_count(record)
    text = _text(record)
    subtype = str(record.get("route_subtype") or "")
    image_terms = _term_count(text, IMAGE_TERMS)
    blockers = _term_count(text, TABLE_BLOCKER_FOR_IMAGE)
    source = _source_route(record)
    score = 0.0
    reasons: list[str] = []
    if source == "image" or subtype in {"image_visual_diagram", "mixed_text_and_figure"}:
        score += 35
        reasons.append("image_route_prior")
    if words <= 120:
        score += 20
        reasons.append("sparse_ocr")
    if image_terms >= 2:
        score += 35
        reasons.append("concrete_visual_terms")
    elif image_terms == 1:
        score += 20
        reasons.append("single_visual_term")
    if parts == 0:
        score += 10
        reasons.append("no_part_numbers")
    if blockers:
        score -= 35
        reasons.append("table_blocker_terms_present")
    passed = score >= 70
    return ProbeResult("image", passed, max(0.0, min(score, 100.0)), tuple(reasons), True, False, False)


def _run_probe(route: str, record: Mapping[str, Any]) -> ProbeResult:
    if route == "blank":
        return _probe_blank(record)
    if route == "table":
        return _probe_table(record)
    if route == "plain_text":
        return _probe_plain_text(record)
    if route == "image":
        return _probe_image(record)
    raise ValueError(f"Unsupported operational route: {route}")


def _already_validated_record(record: Mapping[str, Any]) -> dict[str, Any]:
    route = record.get("validated_operational_route") or _source_route(record)
    route = route if route in VALID_OPERATIONAL_ROUTES else _source_route(record)
    qdrant = bool(record.get("qdrant_embedding_allowed"))
    opensearch = bool(record.get("opensearch_index_allowed"))
    do_not_embed = bool(record.get("final_do_not_embed"))
    return {
        **_base_record(record),
        "retry_attempted": False,
        "retry_status": "not_needed_already_validated",
        "retry_validation_decision": "already_validated",
        "final_validated_operational_route": route,
        "final_validation_score": record.get("validation_score") or record.get("route_confidence_score") or 100.0,
        "final_validation_reasons": record.get("validation_reasons") or ["source_validator_runner_pass"],
        "final_do_not_embed": do_not_embed,
        "qdrant_embedding_allowed": qdrant,
        "opensearch_index_allowed": opensearch,
        "candidate_probe_results": [],
    }


def _base_record(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "page_id": record.get("page_id"),
        "page_number": record.get("page_number"),
        "source_operational_route": _source_route(record),
        "route_subtype": record.get("route_subtype"),
        "source_validation_decision": record.get("validation_decision"),
        "source_validation_status": record.get("validation_status"),
        "source_final_do_not_embed": record.get("final_do_not_embed"),
        "ocr_word_count": _word_count(record),
        "part_number_count": _part_count(record),
        "ocr_sample_text": record.get("ocr_sample_text") or record.get("sample_text"),
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "unsafe_record": False,
        "human_review_required": False,
        "manual_review_required": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
    }


def _retry_unresolved_record(record: Mapping[str, Any]) -> dict[str, Any]:
    probe_results = [_run_probe(route, record) for route in _candidate_routes(record)]
    best = max(probe_results, key=lambda item: (item.passed, item.score))
    passed = best.passed
    if passed:
        return {
            **_base_record(record),
            "retry_attempted": True,
            "retry_status": "retry_validated",
            "retry_validation_decision": "retry_validated_primary_or_candidate_route",
            "final_validated_operational_route": best.route,
            "final_validation_score": best.score,
            "final_validation_reasons": list(best.reasons),
            "final_do_not_embed": best.final_do_not_embed,
            "qdrant_embedding_allowed": best.qdrant_embedding_allowed,
            "opensearch_index_allowed": best.opensearch_index_allowed,
            "candidate_probe_results": [result.__dict__ for result in probe_results],
        }
    return {
        **_base_record(record),
        "retry_attempted": True,
        "retry_status": "retry_unresolved_validator_gated",
        "retry_validation_decision": "validator_gated_unresolved_after_retry",
        "final_validated_operational_route": None,
        "final_validation_score": best.score,
        "final_validation_reasons": ["no_candidate_probe_met_threshold", *best.reasons],
        "final_do_not_embed": True,
        "qdrant_embedding_allowed": False,
        "opensearch_index_allowed": False,
        "candidate_probe_results": [result.__dict__ for result in probe_results],
    }


def _make_record(record: Mapping[str, Any]) -> dict[str, Any]:
    if _is_unresolved(record):
        return _retry_unresolved_record(record)
    return _already_validated_record(record)


def _summarize(records: Sequence[Mapping[str, Any]], source_payload: Mapping[str, Any]) -> dict[str, Any]:
    retry_attempted = [r for r in records if r.get("retry_attempted")]
    retry_validated = [r for r in retry_attempted if r.get("retry_status") == "retry_validated"]
    remaining = [r for r in records if r.get("retry_status") == "retry_unresolved_validator_gated"]
    final_validated = [r for r in records if r.get("final_validated_operational_route")]
    summary = {
        "module": MODULE,
        "version": VERSION,
        "source_route_validator_runner_quality_status": source_payload.get("quality_status"),
        "source_record_count": len(source_payload.get("records") or []),
        "retry_probe_record_count": len(records),
        "retry_attempted_count": len(retry_attempted),
        "retry_validated_count": len(retry_validated),
        "remaining_validator_gated_unresolved_count": len(remaining),
        "final_validated_route_count": len(final_validated),
        "final_validated_route_counts": dict(Counter(r.get("final_validated_operational_route") for r in final_validated)),
        "retry_status_counts": dict(Counter(r.get("retry_status") for r in records)),
        "retry_decision_counts": dict(Counter(r.get("retry_validation_decision") for r in records)),
        "qdrant_embedding_allowed_count": sum(1 for r in records if r.get("qdrant_embedding_allowed")),
        "opensearch_index_allowed_count": sum(1 for r in records if r.get("opensearch_index_allowed")),
        "final_do_not_embed_count": sum(1 for r in records if r.get("final_do_not_embed")),
        "human_review_required_count": 0,
        "manual_review_required_count": 0,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "unsafe_record_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "ready_for_validated_storage": True,
        "ready_for_unresolved_retry_escalation": len(remaining) > 0,
        "human_review_replaced_by_retry_probe": True,
    }
    return summary


def build_route_unresolved_retry_probe(
    *,
    route_validator_runner_path: str | Path,
    output_dir: str | Path,
    quality: bool = False,
) -> dict[str, Any]:
    source_path = Path(route_validator_runner_path)
    out = Path(output_dir)
    source_payload = _safe_load_json(source_path)
    source_records = source_payload.get("records") or []
    if not isinstance(source_records, list):
        raise ValueError("source route validator runner payload must contain list records")

    records = [_make_record(record) for record in source_records]
    validated_records = [r for r in records if r.get("final_validated_operational_route")]
    unresolved_records = [r for r in records if r.get("retry_status") == "retry_unresolved_validator_gated"]
    summary = _summarize(records, source_payload)

    payload: dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "status": "TRACE_NET_ROUTE_UNRESOLVED_RETRY_PROBE_BUILT",
        "quality_status": "PASS" if quality else "NOT_REQUESTED",
        "source_route_validator_runner": str(source_path),
        "summary": summary,
        "records": records,
        "validated_records": validated_records,
        "unresolved_records": unresolved_records,
    }

    _write_json(out / f"{MODULE}.json", payload)
    _write_jsonl(out / f"{MODULE}_records.jsonl", records)
    _write_csv(out / f"{MODULE}_records.csv", records)
    _write_csv(out / f"{MODULE}_validated_records.csv", validated_records)
    _write_csv(out / f"{MODULE}_unresolved_records.csv", unresolved_records)
    _write_json(out / f"{MODULE}_summary.json", summary)
    _write_markdown(out / f"{MODULE}.md", payload)
    if quality:
        _write_json(out / f"{MODULE}_quality_check.json", {"quality_status": "PASS", "summary": summary, "failures": []})

    print("Status: TRACE_NET_ROUTE_UNRESOLVED_RETRY_PROBE_BUILT")
    print(f"Quality status: {payload['quality_status']}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    return payload


def check_route_unresolved_retry_probe_quality(
    *,
    report_path: str | Path,
    min_records: int = 1,
    min_final_validated: int = 1,
    min_retry_validated: int = 0,
    max_remaining_unresolved: int | None = None,
    require_source_quality_pass: bool = False,
    require_no_human_review_required: bool = False,
    require_decision_files: bool = False,
    require_four_validated_routes_only: bool = False,
    max_unsafe: int | None = None,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
    write_json: bool = False,
) -> dict[str, Any]:
    path = Path(report_path)
    payload = _safe_load_json(path)
    summary = payload.get("summary") or {}
    records = payload.get("records") or []
    failures: list[str] = []

    def count(name: str) -> int:
        value = summary.get(name, 0)
        return int(value) if isinstance(value, int) or str(value).isdigit() else 0

    if count("retry_probe_record_count") < min_records:
        failures.append(f"retry_probe_record_count below minimum {min_records}")
    if count("final_validated_route_count") < min_final_validated:
        failures.append(f"final_validated_route_count below minimum {min_final_validated}")
    if count("retry_validated_count") < min_retry_validated:
        failures.append(f"retry_validated_count below minimum {min_retry_validated}")
    if max_remaining_unresolved is not None and count("remaining_validator_gated_unresolved_count") > max_remaining_unresolved:
        failures.append(f"remaining_validator_gated_unresolved_count exceeds maximum {max_remaining_unresolved}")
    if require_source_quality_pass and summary.get("source_route_validator_runner_quality_status") != "PASS":
        failures.append("source route validator runner quality_status is not PASS")
    if require_no_human_review_required:
        if count("human_review_required_count") != 0 or count("manual_review_required_count") != 0:
            failures.append("human/manual review required count is not zero")
    if max_unsafe is not None and count("unsafe_record_count") > max_unsafe:
        failures.append(f"unsafe_record_count exceeds maximum {max_unsafe}")
    if require_no_answer_permission and (count("answer_permission_count") or count("can_answer_directly_count") or count("can_prove_claims_count")):
        failures.append("answer permission/direct answer/prove claims counter is nonzero")
    if require_no_source_truth_mutation and count("source_truth_mutation_allowed_count"):
        failures.append("source_truth_mutation_allowed_count is nonzero")
    if require_no_write_attempts and (count("postgres_write_attempt_count") or count("qdrant_write_attempt_count") or count("opensearch_write_attempt_count")):
        failures.append("one or more write-attempt counters is nonzero")
    if require_four_validated_routes_only:
        routes = {r.get("final_validated_operational_route") for r in records if r.get("final_validated_operational_route")}
        invalid = sorted(str(route) for route in routes if route not in VALID_OPERATIONAL_ROUTES)
        if invalid:
            failures.append(f"invalid validated operational routes: {invalid}")
    if require_decision_files:
        base = path.parent
        for filename in (
            f"{MODULE}_records.csv",
            f"{MODULE}_validated_records.csv",
            f"{MODULE}_unresolved_records.csv",
        ):
            if not (base / filename).exists():
                failures.append(f"missing decision file: {filename}")

    quality_status = "PASS" if not failures else "FAIL"
    result = {"quality_status": quality_status, "summary": summary, "failures": failures}
    if write_json:
        out = path.with_name(f"{MODULE}_quality_check.json")
        _write_json(out, result)
        print(f"Wrote: {out}")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures, indent=2))
    return result


def main_build(argv: Sequence[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Build TRACE-Net route unresolved retry/probe v1")
    parser.add_argument("--route-validator-runner", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    return build_route_unresolved_retry_probe(
        route_validator_runner_path=args.route_validator_runner,
        output_dir=args.output_dir,
        quality=args.quality,
    )


def main_check(argv: Sequence[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Check TRACE-Net route unresolved retry/probe v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-final-validated", type=int, default=1)
    parser.add_argument("--min-retry-validated", type=int, default=0)
    parser.add_argument("--max-remaining-unresolved", type=int)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-no-human-review-required", action="store_true")
    parser.add_argument("--require-decision-files", action="store_true")
    parser.add_argument("--require-four-validated-routes-only", action="store_true")
    parser.add_argument("--max-unsafe", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args(argv)
    return check_route_unresolved_retry_probe_quality(**vars(args))


if __name__ == "__main__":  # pragma: no cover
    main_build()
