"""TRACE-Net route validator runner v1.

This module validates the simplified four-route operational resolver output:

    blank, plain_text, table, image

It does not require human review.  It turns validator-gated operational route
records into validated storage decisions using conservative route-specific
checks.  Pages that do not pass validation remain source-traceable but keep
``do_not_embed=true`` and are not eligible for Qdrant/OpenSearch indexing.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

MODULE = "trace_net_route_validator_runner_v1"
STATUS = "TRACE_NET_ROUTE_VALIDATOR_RUNNER_BUILT"
VERSION = "v1"

OPERATIONAL_ROUTES = ["blank", "plain_text", "table", "image"]

VALIDATOR_CONTRACTS = {
    "blank": "blank_candidate_confirmation_scan",
    "plain_text": "plain_text_ocr_context_validator",
    "table": "table_structure_and_part_evidence_validator",
    "image": "image_visual_sparse_label_validator",
}

WRITE_ZEROES = {
    "unsafe_record_count": 0,
    "answer_permission_count": 0,
    "can_answer_directly_count": 0,
    "can_prove_claims_count": 0,
    "source_truth_mutation_allowed_count": 0,
    "postgres_write_attempt_count": 0,
    "qdrant_write_attempt_count": 0,
    "opensearch_write_attempt_count": 0,
}


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _write_csv(path: Path, records: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "page_number",
        "page_id",
        "source_operational_route",
        "route_subtype",
        "validated_operational_route",
        "validation_decision",
        "validation_status",
        "validation_score",
        "validator_contracts_executed",
        "passed_validator_contracts",
        "failed_validator_contracts",
        "secondary_operational_routes",
        "route_confidence_band",
        "route_confidence_score",
        "source_validator_required",
        "source_multi_route_required",
        "final_do_not_embed",
        "qdrant_embedding_allowed",
        "opensearch_index_allowed",
        "ocr_text_word_count",
        "part_number_count",
        "validation_reasons",
        "source_member",
        "source_image_path",
        "ocr_text_path",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in records:
            out = dict(row)
            for key in [
                "validator_contracts_executed",
                "passed_validator_contracts",
                "failed_validator_contracts",
                "secondary_operational_routes",
                "validation_reasons",
            ]:
                if isinstance(out.get(key), (list, dict)):
                    out[key] = json.dumps(out[key], sort_keys=True)
            writer.writerow(out)


def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = payload.get("summary") or {}
    lines = [
        "# TRACE-Net Route Validator Runner v1",
        "",
        "This artifact validates four operational page routes: `blank`, `plain_text`, `table`, and `image`.",
        "Validator-gated pages that fail validation remain source-traceable but keep `do_not_embed=true`.",
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
        "No Postgres writes, no Qdrant writes, no OpenSearch writes, no source-truth mutation, and no answer permission.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _ensure_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, tuple):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return [str(v) for v in parsed if str(v).strip()]
        except json.JSONDecodeError:
            pass
        return [stripped]
    return [str(value)]


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _signal_bool(signals: Mapping[str, Any], key: str) -> bool:
    return bool(signals.get(key))


def _signal_int(signals: Mapping[str, Any], key: str) -> int:
    return _safe_int(signals.get(key))


def _route_candidates(record: Mapping[str, Any]) -> list[str]:
    candidates: list[str] = []
    primary = str(record.get("operational_route") or "").strip()
    if primary:
        candidates.append(primary)
    candidates.extend(_ensure_list(record.get("secondary_operational_routes")))
    out: list[str] = []
    seen: set[str] = set()
    for route in candidates:
        if route in OPERATIONAL_ROUTES and route not in seen:
            seen.add(route)
            out.append(route)
    return out or ["plain_text"]


def _validate_blank(record: Mapping[str, Any]) -> tuple[bool, float, list[str]]:
    words = _safe_int(record.get("ocr_text_word_count"))
    parts = _safe_int(record.get("part_number_count"))
    subtype = str(record.get("route_subtype") or "")
    reasons: list[str] = []
    score = 0.0
    if subtype == "blank_candidate":
        score += 50.0
        reasons.append("blank_subtype")
    if words <= 2:
        score += 35.0
        reasons.append("empty_or_near_empty_ocr")
    if parts == 0:
        score += 15.0
        reasons.append("no_part_number_tokens")
    passed = score >= 85.0 and words <= 2 and parts == 0
    return passed, min(score, 100.0), reasons


def _validate_plain_text(record: Mapping[str, Any]) -> tuple[bool, float, list[str]]:
    words = _safe_int(record.get("ocr_text_word_count"))
    parts = _safe_int(record.get("part_number_count"))
    signals = record.get("signal_counts") or {}
    subtype = str(record.get("route_subtype") or "")
    reasons: list[str] = []
    score = 0.0
    if subtype in {"normal_text", "procedure_or_description", "cover_or_title_page"}:
        score += 35.0
        reasons.append("plain_text_subtype")
    if words >= 40:
        score += 30.0
        reasons.append("meaningful_ocr_text")
    if parts <= 3:
        score += 15.0
        reasons.append("low_part_number_density")
    if not _signal_bool(signals, "has_row_structure"):
        score += 10.0
        reasons.append("no_strong_row_structure")
    if _signal_int(signals, "procedure_term_count") > 0 or subtype == "cover_or_title_page":
        score += 10.0
        reasons.append("text_context_terms")
    passed = score >= 70.0 and words >= 20 and not (parts >= 10 and _signal_bool(signals, "has_row_structure"))
    return passed, min(score, 100.0), reasons


def _validate_table(record: Mapping[str, Any]) -> tuple[bool, float, list[str]]:
    words = _safe_int(record.get("ocr_text_word_count"))
    parts = _safe_int(record.get("part_number_count"))
    signals = record.get("signal_counts") or {}
    subtype = str(record.get("route_subtype") or "")
    reasons: list[str] = []
    score = 0.0
    if subtype in {"detailed_parts_list", "table_or_index"}:
        score += 25.0
        reasons.append("table_subtype")
    if parts >= 8:
        score += 35.0
        reasons.append("strong_part_number_density")
    elif parts >= 3:
        score += 22.0
        reasons.append("moderate_part_number_density")
    if _signal_bool(signals, "has_row_structure"):
        score += 25.0
        reasons.append("row_structure_signal")
    if _signal_int(signals, "table_index_term_count") > 0 or _signal_int(signals, "detailed_parts_term_count") > 0:
        score += 20.0
        reasons.append("table_or_ipl_terms")
    if words >= 50:
        score += 5.0
        reasons.append("ocr_text_present")
    passed = score >= 60.0 and (parts >= 3 or _signal_bool(signals, "has_row_structure") or _signal_int(signals, "table_index_term_count") > 0)
    return passed, min(score, 100.0), reasons


def _validate_image(record: Mapping[str, Any]) -> tuple[bool, float, list[str]]:
    words = _safe_int(record.get("ocr_text_word_count"))
    parts = _safe_int(record.get("part_number_count"))
    signals = record.get("signal_counts") or {}
    subtype = str(record.get("route_subtype") or "")
    legacy = str(record.get("legacy_route") or "")
    reasons: list[str] = []
    score = 0.0
    if subtype in {"image_visual_diagram", "mixed_text_and_figure"}:
        score += 30.0
        reasons.append("image_subtype")
    if legacy == "image_visual":
        score += 30.0
        reasons.append("legacy_image_visual")
    if words <= 120:
        score += 15.0
        reasons.append("sparse_ocr_text")
    if _signal_int(signals, "concrete_visual_term_count") > 0 or _signal_bool(signals, "has_figure_caption"):
        score += 25.0
        reasons.append("concrete_visual_or_figure_signal")
    if parts <= 2 and not _signal_bool(signals, "has_row_structure"):
        score += 10.0
        reasons.append("not_table_like")
    blocker = bool(signals.get("ipl_visual_blocker")) or parts >= 5 or _signal_bool(signals, "has_row_structure")
    passed = score >= 75.0 and not blocker
    if blocker:
        reasons.append("blocked_by_table_or_ipl_signals")
    return passed, min(score, 100.0), reasons


VALIDATORS = {
    "blank": _validate_blank,
    "plain_text": _validate_plain_text,
    "table": _validate_table,
    "image": _validate_image,
}


def _storage_policy(route: str | None, *, passed: bool) -> dict[str, Any]:
    if not passed or route is None:
        return {
            "postgres_graph_record": True,
            "qdrant_embedding_allowed": False,
            "opensearch_index_allowed": False,
            "policy": "validator_failed_or_unresolved__do_not_embed",
        }
    if route == "blank":
        return {
            "postgres_graph_record": True,
            "qdrant_embedding_allowed": False,
            "opensearch_index_allowed": False,
            "policy": "blank_validated_graph_only_do_not_embed",
        }
    if route == "plain_text":
        return {
            "postgres_graph_record": True,
            "qdrant_embedding_allowed": True,
            "opensearch_index_allowed": False,
            "policy": "plain_text_validated_embed_ocr_chunks_and_page_context",
        }
    if route == "table":
        return {
            "postgres_graph_record": True,
            "qdrant_embedding_allowed": True,
            "opensearch_index_allowed": True,
            "policy": "table_validated_embed_evidence_and_exact_index_values",
        }
    if route == "image":
        return {
            "postgres_graph_record": True,
            "qdrant_embedding_allowed": True,
            "opensearch_index_allowed": False,
            "policy": "image_validated_embed_ocr_supported_visual_context_only",
        }
    raise ValueError(f"unknown route: {route}")


def _validate_record(record: Mapping[str, Any]) -> dict[str, Any]:
    candidates = _route_candidates(record)
    executed: list[str] = []
    passed_contracts: list[str] = []
    failed_contracts: list[str] = []
    candidate_results: list[dict[str, Any]] = []

    selected_route: str | None = None
    selected_score = 0.0
    selected_reasons: list[str] = []
    selected_decision = "validator_gated_unresolved"

    for route in candidates:
        validator = VALIDATORS[route]
        contract = VALIDATOR_CONTRACTS[route]
        executed.append(contract)
        passed, score, reasons = validator(record)
        candidate_results.append({
            "route": route,
            "validator_contract": contract,
            "passed": passed,
            "score": round(score, 3),
            "reasons": reasons,
        })
        if passed:
            passed_contracts.append(contract)
            if selected_route is None or score > selected_score:
                selected_route = route
                selected_score = score
                selected_reasons = reasons
        else:
            failed_contracts.append(contract)

    if selected_route is not None:
        selected_decision = "validated_secondary_route" if selected_route != candidates[0] else "validated_primary_route"
    storage = _storage_policy(selected_route, passed=selected_route is not None)
    final_do_not_embed = not bool(storage.get("qdrant_embedding_allowed"))

    page_number = record.get("canonical_page_number") or record.get("page_number")
    return {
        "module": MODULE,
        "version": VERSION,
        "page_number": page_number,
        "canonical_page_number": page_number,
        "page_id": record.get("page_id") or (f"page_{page_number}" if page_number is not None else None),
        "source_member": record.get("source_member"),
        "source_image_path": record.get("source_image_path"),
        "source_image_sha256": record.get("source_image_sha256"),
        "ocr_text_path": record.get("ocr_text_path"),
        "source_operational_route": record.get("operational_route"),
        "route_subtype": record.get("route_subtype"),
        "secondary_operational_routes": _ensure_list(record.get("secondary_operational_routes")),
        "candidate_operational_routes": candidates,
        "validated_operational_route": selected_route,
        "validation_decision": selected_decision,
        "validation_status": "PASS" if selected_route is not None else "VALIDATOR_GATED_UNRESOLVED",
        "validation_score": round(selected_score, 3),
        "validation_reasons": selected_reasons,
        "candidate_validation_results": candidate_results,
        "validator_contracts_executed": executed,
        "passed_validator_contracts": passed_contracts,
        "failed_validator_contracts": failed_contracts,
        "source_validator_required": bool(record.get("validator_required")),
        "source_multi_route_required": bool(record.get("multi_route_required")),
        "source_auto_resolved": bool(record.get("auto_resolved")),
        "route_confidence_band": record.get("route_confidence_band"),
        "route_confidence_score": record.get("route_confidence_score"),
        "source_do_not_embed": bool(record.get("do_not_embed")),
        "final_do_not_embed": final_do_not_embed,
        "storage_policy": storage,
        "qdrant_embedding_allowed": bool(storage.get("qdrant_embedding_allowed")),
        "opensearch_index_allowed": bool(storage.get("opensearch_index_allowed")),
        "ocr_text_word_count": record.get("ocr_text_word_count"),
        "part_number_count": record.get("part_number_count"),
        "part_number_tokens": record.get("part_number_tokens") or [],
        "route_reasons": record.get("route_reasons") or [],
        "signal_counts": record.get("signal_counts") or {},
        "human_review_required": False,
        "manual_review_required": False,
        "unsafe_record": False,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }


def build_route_validator_runner(
    *,
    four_route_resolver: str | Path,
    output_dir: str | Path,
    quality: bool = False,
) -> dict[str, Any]:
    source_path = Path(four_route_resolver)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    source_payload = _read_json(source_path)
    source_quality_status = source_payload.get("quality_status")
    source_records = source_payload.get("records") or []
    if not isinstance(source_records, list):
        raise ValueError("four-route resolver report must contain a records list")

    records = [_validate_record(record) for record in source_records]
    validated_records = [r for r in records if r["validated_operational_route"]]
    unresolved_records = [r for r in records if not r["validated_operational_route"]]

    validation_decision_counts = Counter(r["validation_decision"] for r in records)
    source_route_counts = Counter(r.get("source_operational_route") for r in records)
    validated_route_counts = Counter(r.get("validated_operational_route") for r in validated_records)
    validation_status_counts = Counter(r.get("validation_status") for r in records)
    final_do_not_embed_count = sum(1 for r in records if r["final_do_not_embed"])
    qdrant_allowed_count = sum(1 for r in records if r["qdrant_embedding_allowed"])
    opensearch_allowed_count = sum(1 for r in records if r["opensearch_index_allowed"])
    secondary_validated_count = validation_decision_counts.get("validated_secondary_route", 0)
    invalid_validated_route_count = sum(1 for r in validated_records if r.get("validated_operational_route") not in OPERATIONAL_ROUTES)

    summary = {
        "module": MODULE,
        "version": VERSION,
        "source_four_route_resolver": str(source_path),
        "source_four_route_resolver_quality_status": source_quality_status,
        "source_record_count": len(source_records),
        "validator_record_count": len(records),
        "validated_route_count": len(validated_records),
        "validator_gated_unresolved_count": len(unresolved_records),
        "validated_secondary_route_count": secondary_validated_count,
        "source_operational_route_counts": dict(sorted(source_route_counts.items())),
        "validated_operational_route_counts": dict(sorted(validated_route_counts.items())),
        "validation_decision_counts": dict(sorted(validation_decision_counts.items())),
        "validation_status_counts": dict(sorted(validation_status_counts.items())),
        "qdrant_embedding_allowed_count": qdrant_allowed_count,
        "opensearch_index_allowed_count": opensearch_allowed_count,
        "final_do_not_embed_count": final_do_not_embed_count,
        "invalid_validated_route_count": invalid_validated_route_count,
        "human_review_required_count": 0,
        "manual_review_required_count": 0,
        "ready_for_validated_storage": len(validated_records) > 0 and invalid_validated_route_count == 0,
        "ready_for_unresolved_retry_or_multi_route_probe": len(unresolved_records) > 0,
        **WRITE_ZEROES,
    }

    quality_status = "PASS"
    quality_failures: list[str] = []
    if source_quality_status not in {"PASS", None}:
        quality_status = "FAIL"
        quality_failures.append("source four-route resolver quality_status is not PASS")
    if len(records) != len(source_records):
        quality_status = "FAIL"
        quality_failures.append("validator record count does not match source record count")
    if invalid_validated_route_count:
        quality_status = "FAIL"
        quality_failures.append("invalid validated operational route found")
    if any(summary[k] for k in WRITE_ZEROES):
        quality_status = "FAIL"
        quality_failures.append("safety/write counters must remain zero")

    payload = {
        "module": MODULE,
        "version": VERSION,
        "status": STATUS,
        "quality_status": quality_status,
        "quality_failures": quality_failures,
        "summary": summary,
        "records": records,
        "validated_records": validated_records,
        "unresolved_records": unresolved_records,
    }

    report_path = output / "trace_net_route_validator_runner_v1.json"
    records_path = output / "trace_net_route_validator_runner_v1_records.jsonl"
    csv_path = output / "trace_net_route_validator_runner_v1_records.csv"
    validated_csv_path = output / "trace_net_route_validator_runner_v1_validated_records.csv"
    unresolved_csv_path = output / "trace_net_route_validator_runner_v1_unresolved_records.csv"
    summary_path = output / "trace_net_route_validator_runner_v1_summary.json"
    md_path = output / "README_trace_net_route_validator_runner_v1.md"

    _write_json(report_path, payload)
    _write_jsonl(records_path, records)
    _write_csv(csv_path, records)
    _write_csv(validated_csv_path, validated_records)
    _write_csv(unresolved_csv_path, unresolved_records)
    _write_json(summary_path, summary)
    _write_markdown(md_path, payload)

    if quality:
        _write_json(output / "trace_net_route_validator_runner_v1_quality_check.json", {"quality_status": quality_status, "summary": summary, "failures": quality_failures})

    print(f"Status: {STATUS}")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    return payload


def check_quality(
    *,
    report_path: str | Path,
    write_json: bool = False,
    min_records: int = 1,
    min_validated: int = 1,
    min_unresolved: int = 0,
    min_qdrant_allowed: int = 0,
    min_opensearch_allowed: int = 0,
    require_source_quality_pass: bool = False,
    require_no_human_review_required: bool = False,
    require_decision_files: bool = False,
    require_four_validated_routes_only: bool = False,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
    max_unsafe: int | None = None,
) -> dict[str, Any]:
    path = Path(report_path)
    payload = _read_json(path)
    summary = payload.get("summary") or {}
    failures: list[str] = []

    if payload.get("quality_status") != "PASS":
        failures.append("manifest quality_status is not PASS")
    if _safe_int(summary.get("validator_record_count")) < min_records:
        failures.append(f"validator_record_count below {min_records}")
    if _safe_int(summary.get("validated_route_count")) < min_validated:
        failures.append(f"validated_route_count below {min_validated}")
    if _safe_int(summary.get("validator_gated_unresolved_count")) < min_unresolved:
        failures.append(f"validator_gated_unresolved_count below {min_unresolved}")
    if _safe_int(summary.get("qdrant_embedding_allowed_count")) < min_qdrant_allowed:
        failures.append(f"qdrant_embedding_allowed_count below {min_qdrant_allowed}")
    if _safe_int(summary.get("opensearch_index_allowed_count")) < min_opensearch_allowed:
        failures.append(f"opensearch_index_allowed_count below {min_opensearch_allowed}")
    if require_source_quality_pass and summary.get("source_four_route_resolver_quality_status") != "PASS":
        failures.append("source four-route resolver quality_status is not PASS")
    if require_four_validated_routes_only and _safe_int(summary.get("invalid_validated_route_count")) != 0:
        failures.append("invalid validated operational routes found")
    if require_no_human_review_required:
        for key in ["human_review_required_count", "manual_review_required_count"]:
            if _safe_int(summary.get(key)) != 0:
                failures.append(f"{key} must be zero")
    if max_unsafe is not None and _safe_int(summary.get("unsafe_record_count")) > max_unsafe:
        failures.append("unsafe_record_count exceeds max")
    if require_no_answer_permission:
        for key in ["answer_permission_count", "can_answer_directly_count", "can_prove_claims_count"]:
            if _safe_int(summary.get(key)) != 0:
                failures.append(f"{key} must be zero")
    if require_no_source_truth_mutation and _safe_int(summary.get("source_truth_mutation_allowed_count")) != 0:
        failures.append("source_truth_mutation_allowed_count must be zero")
    if require_no_write_attempts:
        for key in ["postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"]:
            if _safe_int(summary.get(key)) != 0:
                failures.append(f"{key} must be zero")
    if require_decision_files:
        base = path.parent
        for filename in [
            "trace_net_route_validator_runner_v1_records.csv",
            "trace_net_route_validator_runner_v1_validated_records.csv",
            "trace_net_route_validator_runner_v1_unresolved_records.csv",
            "trace_net_route_validator_runner_v1_records.jsonl",
        ]:
            if not (base / filename).exists():
                failures.append(f"missing decision file: {filename}")

    quality_status = "PASS" if not failures else "FAIL"
    result = {"quality_status": quality_status, "summary": summary, "failures": failures}
    if write_json:
        out = path.with_name("trace_net_route_validator_runner_v1_quality_check.json")
        _write_json(out, result)
        print(f"Wrote: {out}")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures, indent=2))
    return result


def main_build(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Build TRACE-Net route validator runner v1")
    parser.add_argument("--four-route-resolver", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    return build_route_validator_runner(
        four_route_resolver=args.four_route_resolver,
        output_dir=args.output_dir,
        quality=args.quality,
    )


def main_check(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Check TRACE-Net route validator runner v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-validated", type=int, default=1)
    parser.add_argument("--min-unresolved", type=int, default=0)
    parser.add_argument("--min-qdrant-allowed", type=int, default=0)
    parser.add_argument("--min-opensearch-allowed", type=int, default=0)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-no-human-review-required", action="store_true")
    parser.add_argument("--require-decision-files", action="store_true")
    parser.add_argument("--require-four-validated-routes-only", action="store_true")
    parser.add_argument("--max-unsafe", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args(argv)
    return check_quality(
        report_path=args.report_path,
        write_json=args.write_json,
        min_records=args.min_records,
        min_validated=args.min_validated,
        min_unresolved=args.min_unresolved,
        min_qdrant_allowed=args.min_qdrant_allowed,
        min_opensearch_allowed=args.min_opensearch_allowed,
        require_source_quality_pass=args.require_source_quality_pass,
        require_no_human_review_required=args.require_no_human_review_required,
        require_decision_files=args.require_decision_files,
        require_four_validated_routes_only=args.require_four_validated_routes_only,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
    )


if __name__ == "__main__":  # pragma: no cover
    main_build()
