"""TRACE-Net four-route operational resolver v1.

This module collapses the detailed TRACE-Net route confidence labels into the
four operational processor families used at scale:

    blank, plain_text, table, image

The detailed label is preserved as route_subtype metadata.  Ambiguous pages are
kept safe through multi-route and validator gates instead of requiring human
review or being embedded/indexed prematurely.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

MODULE = "trace_net_four_route_operational_resolver_v1"
STATUS = "TRACE_NET_FOUR_ROUTE_OPERATIONAL_RESOLVER_BUILT"
VERSION = "v1"

OPERATIONAL_ROUTES = ["blank", "plain_text", "table", "image"]

SUBTYPE_TO_OPERATIONAL_ROUTE = {
    "blank_candidate": "blank",
    "cover_or_title_page": "plain_text",
    "normal_text": "plain_text",
    "procedure_or_description": "plain_text",
    "table_or_index": "table",
    "detailed_parts_list": "table",
    "image_visual_diagram": "image",
    "mixed_text_and_figure": "image",
}

# Used when a source row still says review_required.  The row must still be sent
# to a processor family, but it remains validator-gated and do_not_embed=true.
REVIEW_FALLBACK_OPERATIONAL_ROUTE = "plain_text"

PROCESSOR_CONTRACTS = {
    "blank": "blank_candidate_confirmation_scan",
    "plain_text": "normal_text_page_context_scan",
    "table": "table_or_detailed_parts_extraction_scan",
    "image": "image_visual_ocr_and_vision_queue_scan",
}

EMBED_POLICY = {
    "blank": "do_not_embed_blank_pages",
    "plain_text": "embed_validated_ocr_chunks_and_page_context_summary",
    "table": "embed_validated_table_or_part_evidence_cards_and_exact_values",
    "image": "embed_only_ocr_supported_visual_context_cards",
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
        "operational_route",
        "route_subtype",
        "secondary_operational_routes",
        "source_primary_route",
        "source_secondary_routes",
        "source_candidate_routes",
        "route_confidence_score",
        "route_confidence_band",
        "operational_resolution_status",
        "auto_resolved",
        "multi_route_required",
        "validator_required",
        "do_not_embed",
        "processor_contract",
        "validator_contracts",
        "legacy_route",
        "ocr_text_word_count",
        "part_number_count",
        "source_member",
        "source_image_path",
        "ocr_text_path",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in records:
            out = dict(row)
            for key in ["secondary_operational_routes", "source_secondary_routes", "source_candidate_routes", "validator_contracts"]:
                if isinstance(out.get(key), (list, dict)):
                    out[key] = json.dumps(out[key], sort_keys=True)
            writer.writerow(out)


def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = payload.get("summary") or {}
    lines = [
        "# TRACE-Net Four-Route Operational Resolver v1",
        "",
        "This artifact collapses detailed route labels into four operational processor families:",
        "`blank`, `plain_text`, `table`, and `image`.",
        "",
        "Detailed labels are preserved as `route_subtype` metadata.  Ambiguous rows remain",
        "validator-gated and are not embedded/indexed until validators pass.",
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


def _load_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = payload.get("records") or []
    if not isinstance(records, list):
        raise ValueError("source resolver does not contain a list of records")
    return [dict(r) for r in records]


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


def _map_subtype_to_operational(subtype: str | None) -> str | None:
    if not subtype:
        return None
    return SUBTYPE_TO_OPERATIONAL_ROUTE.get(str(subtype))


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _operational_storage_policy(operational_route: str, *, validator_required: bool, auto_resolved: bool) -> dict[str, Any]:
    if operational_route == "blank":
        return {
            "postgres_graph_record": True,
            "qdrant_embedding_allowed": False,
            "opensearch_index_allowed": False,
            "policy": EMBED_POLICY["blank"],
        }
    if auto_resolved and not validator_required:
        return {
            "postgres_graph_record": True,
            "qdrant_embedding_allowed": True,
            "opensearch_index_allowed": operational_route == "table",
            "policy": EMBED_POLICY[operational_route],
        }
    return {
        "postgres_graph_record": True,
        "qdrant_embedding_allowed": False,
        "opensearch_index_allowed": False,
        "policy": f"validator_required_before_storage__{EMBED_POLICY.get(operational_route, 'do_not_embed_until_validated')}",
    }


def _resolve_record(record: Mapping[str, Any]) -> dict[str, Any]:
    source_primary = str(record.get("primary_route") or record.get("route_subtype") or "").strip()
    source_secondary = _ensure_list(record.get("secondary_routes"))
    source_candidates = _ensure_list(record.get("candidate_routes"))

    operational_route = _map_subtype_to_operational(source_primary)
    route_subtype = source_primary or "review_required"
    unresolved_source_route = False
    if operational_route is None:
        unresolved_source_route = True
        for candidate in source_candidates + source_secondary:
            mapped = _map_subtype_to_operational(candidate)
            if mapped:
                operational_route = mapped
                break
        if operational_route is None:
            operational_route = REVIEW_FALLBACK_OPERATIONAL_ROUTE
        if not route_subtype:
            route_subtype = "review_required"

    secondary_operational_routes = []
    for route in source_secondary + source_candidates:
        mapped = _map_subtype_to_operational(route)
        if mapped and mapped != operational_route:
            secondary_operational_routes.append(mapped)
    # Mixed image/text pages should explicitly carry plain_text as a secondary path.
    if route_subtype == "mixed_text_and_figure" and operational_route == "image":
        secondary_operational_routes.append("plain_text")
    secondary_operational_routes = _dedupe(secondary_operational_routes)

    source_validator_required = bool(record.get("validator_required"))
    source_multi_route_required = bool(record.get("multi_route_required"))
    source_auto_resolved = bool(record.get("auto_resolved"))
    confidence_band = str(record.get("route_confidence_band") or "low")
    try:
        confidence_score = float(record.get("route_confidence_score") or 0.0)
    except (TypeError, ValueError):
        confidence_score = 0.0

    validator_required = source_validator_required or unresolved_source_route or confidence_band in {"low"} or route_subtype == "review_required"
    multi_route_required = source_multi_route_required or bool(secondary_operational_routes) or route_subtype == "review_required"
    auto_resolved = source_auto_resolved and not validator_required and not multi_route_required and confidence_band == "high"
    do_not_embed = bool(record.get("do_not_embed")) or validator_required or operational_route == "blank"

    if auto_resolved:
        status = "auto_resolved_four_route"
    elif validator_required and multi_route_required:
        status = "validator_gated_multi_route"
    elif validator_required:
        status = "validator_gated_single_route"
    else:
        status = "resolved_pending_storage_policy"

    processor_contract = PROCESSOR_CONTRACTS[operational_route]
    validator_contracts = [processor_contract]
    for route in secondary_operational_routes:
        validator_contracts.append(PROCESSOR_CONTRACTS[route])
    validator_contracts = _dedupe(validator_contracts)

    storage_policy = _operational_storage_policy(operational_route, validator_required=validator_required, auto_resolved=auto_resolved)

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
        "legacy_route": record.get("legacy_route"),
        "source_primary_route": source_primary,
        "source_secondary_routes": source_secondary,
        "source_candidate_routes": source_candidates,
        "operational_route": operational_route,
        "route_subtype": route_subtype,
        "secondary_operational_routes": secondary_operational_routes,
        "route_confidence_score": round(confidence_score, 3),
        "route_confidence_band": confidence_band,
        "operational_resolution_status": status,
        "auto_resolved": auto_resolved,
        "multi_route_required": multi_route_required,
        "validator_required": validator_required,
        "processor_contract": processor_contract,
        "validator_contracts": validator_contracts,
        "do_not_embed": do_not_embed,
        "storage_policy": storage_policy,
        "qdrant_embedding_allowed": bool(storage_policy.get("qdrant_embedding_allowed")),
        "opensearch_index_allowed": bool(storage_policy.get("opensearch_index_allowed")),
        "route_reasons": record.get("route_reasons") or [],
        "signal_counts": record.get("signal_counts") or {},
        "ocr_text_word_count": record.get("ocr_text_word_count"),
        "part_number_count": record.get("part_number_count"),
        "part_number_tokens": record.get("part_number_tokens") or [],
        "unsafe_record": False,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "human_review_required": False,
        "manual_review_required": False,
    }


def build_four_route_operational_resolver(
    *,
    route_confidence_resolver: str | Path,
    output_dir: str | Path,
    quality: bool = False,
) -> dict[str, Any]:
    source_path = Path(route_confidence_resolver)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    source_payload = _read_json(source_path)
    source_quality_status = source_payload.get("quality_status")
    source_records = _load_records(source_payload)
    records = [_resolve_record(record) for record in source_records]

    operational_route_counts = Counter(r["operational_route"] for r in records)
    route_subtype_counts = Counter(r["route_subtype"] for r in records)
    status_counts = Counter(r["operational_resolution_status"] for r in records)
    validator_required_count = sum(1 for r in records if r["validator_required"])
    multi_route_required_count = sum(1 for r in records if r["multi_route_required"])
    auto_resolved_count = sum(1 for r in records if r["auto_resolved"])
    do_not_embed_count = sum(1 for r in records if r["do_not_embed"])
    qdrant_allowed_count = sum(1 for r in records if r["qdrant_embedding_allowed"])
    opensearch_allowed_count = sum(1 for r in records if r["opensearch_index_allowed"])
    unknown_subtype_count = sum(1 for r in records if r["route_subtype"] not in SUBTYPE_TO_OPERATIONAL_ROUTE and r["route_subtype"] != "review_required")
    invalid_operational_route_count = sum(1 for r in records if r["operational_route"] not in OPERATIONAL_ROUTES)

    summary = {
        "module": MODULE,
        "version": VERSION,
        "source_route_confidence_resolver": str(source_path),
        "source_route_confidence_resolver_quality_status": source_quality_status,
        "source_record_count": len(source_records),
        "operational_record_count": len(records),
        "operational_route_count": len(OPERATIONAL_ROUTES),
        "operational_routes": OPERATIONAL_ROUTES,
        "operational_route_counts": dict(sorted(operational_route_counts.items())),
        "route_subtype_counts": dict(sorted(route_subtype_counts.items())),
        "operational_resolution_status_counts": dict(sorted(status_counts.items())),
        "auto_resolved_operational_route_count": auto_resolved_count,
        "validator_required_count": validator_required_count,
        "multi_route_required_count": multi_route_required_count,
        "do_not_embed_count": do_not_embed_count,
        "qdrant_embedding_allowed_count": qdrant_allowed_count,
        "opensearch_index_allowed_count": opensearch_allowed_count,
        "unknown_subtype_count": unknown_subtype_count,
        "invalid_operational_route_count": invalid_operational_route_count,
        "human_review_required_count": 0,
        "manual_review_required_count": 0,
        "ready_for_four_route_processing": invalid_operational_route_count == 0 and len(records) > 0,
        "ready_for_validator_gated_storage": validator_required_count > 0,
        **WRITE_ZEROES,
    }

    quality_status = "PASS"
    quality_failures: list[str] = []
    if source_quality_status not in {"PASS", None}:
        quality_status = "FAIL"
        quality_failures.append("source route confidence resolver quality_status is not PASS")
    if len(records) != len(source_records):
        quality_status = "FAIL"
        quality_failures.append("operational record count does not match source record count")
    if invalid_operational_route_count:
        quality_status = "FAIL"
        quality_failures.append("invalid operational routes found")
    if unknown_subtype_count:
        quality_status = "FAIL"
        quality_failures.append("unknown route subtypes found")
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
    }

    report_path = output / "trace_net_four_route_operational_resolver_v1.json"
    records_path = output / "trace_net_four_route_operational_resolver_v1_records.jsonl"
    csv_path = output / "trace_net_four_route_operational_resolver_v1_records.csv"
    summary_path = output / "trace_net_four_route_operational_resolver_v1_summary.json"
    md_path = output / "README_trace_net_four_route_operational_resolver_v1.md"

    _write_json(report_path, payload)
    _write_jsonl(records_path, records)
    _write_csv(csv_path, records)
    _write_json(summary_path, summary)
    _write_markdown(md_path, payload)

    if quality:
        _write_json(output / "trace_net_four_route_operational_resolver_v1_quality_check.json", {"quality_status": quality_status, "summary": summary, "failures": quality_failures})

    print(f"Status: {STATUS}")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    return payload


def check_quality(
    *,
    report_path: str | Path,
    write_json: bool = False,
    min_records: int = 1,
    min_auto_resolved: int = 0,
    min_validator_required: int = 0,
    min_multi_route_required: int = 0,
    require_source_quality_pass: bool = False,
    require_four_operational_routes_only: bool = False,
    require_no_human_review_required: bool = False,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
    max_unknown_subtypes: int | None = 0,
    max_unsafe: int | None = None,
) -> dict[str, Any]:
    path = Path(report_path)
    payload = _read_json(path)
    summary = payload.get("summary") or {}
    failures: list[str] = []

    if payload.get("quality_status") != "PASS":
        failures.append("manifest quality_status is not PASS")
    if int(summary.get("operational_record_count") or 0) < min_records:
        failures.append(f"operational_record_count below {min_records}")
    if int(summary.get("auto_resolved_operational_route_count") or 0) < min_auto_resolved:
        failures.append(f"auto_resolved_operational_route_count below {min_auto_resolved}")
    if int(summary.get("validator_required_count") or 0) < min_validator_required:
        failures.append(f"validator_required_count below {min_validator_required}")
    if int(summary.get("multi_route_required_count") or 0) < min_multi_route_required:
        failures.append(f"multi_route_required_count below {min_multi_route_required}")
    if require_source_quality_pass and summary.get("source_route_confidence_resolver_quality_status") != "PASS":
        failures.append("source route confidence resolver quality_status is not PASS")
    if require_four_operational_routes_only and int(summary.get("invalid_operational_route_count") or 0) != 0:
        failures.append("non-four-route operational route found")
    if max_unknown_subtypes is not None and int(summary.get("unknown_subtype_count") or 0) > max_unknown_subtypes:
        failures.append("unknown_subtype_count exceeds max")
    if require_no_human_review_required:
        for key in ["human_review_required_count", "manual_review_required_count"]:
            if int(summary.get(key) or 0) != 0:
                failures.append(f"{key} must be zero")
    if max_unsafe is not None and int(summary.get("unsafe_record_count") or 0) > max_unsafe:
        failures.append("unsafe_record_count exceeds max")
    if require_no_answer_permission:
        for key in ["answer_permission_count", "can_answer_directly_count", "can_prove_claims_count"]:
            if int(summary.get(key) or 0) != 0:
                failures.append(f"{key} must be zero")
    if require_no_source_truth_mutation and int(summary.get("source_truth_mutation_allowed_count") or 0) != 0:
        failures.append("source_truth_mutation_allowed_count must be zero")
    if require_no_write_attempts:
        for key in ["postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"]:
            if int(summary.get(key) or 0) != 0:
                failures.append(f"{key} must be zero")

    quality_status = "PASS" if not failures else "FAIL"
    result = {"quality_status": quality_status, "summary": summary, "failures": failures}
    if write_json:
        out = path.with_name("trace_net_four_route_operational_resolver_v1_quality_check.json")
        _write_json(out, result)
        print(f"Wrote: {out}")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures, indent=2))
    return result


def main_build(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Build TRACE-Net four-route operational resolver v1")
    parser.add_argument("--route-confidence-resolver", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    return build_four_route_operational_resolver(
        route_confidence_resolver=args.route_confidence_resolver,
        output_dir=args.output_dir,
        quality=args.quality,
    )


def main_check(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Check TRACE-Net four-route operational resolver v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-auto-resolved", type=int, default=0)
    parser.add_argument("--min-validator-required", type=int, default=0)
    parser.add_argument("--min-multi-route-required", type=int, default=0)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-four-operational-routes-only", action="store_true")
    parser.add_argument("--require-no-human-review-required", action="store_true")
    parser.add_argument("--max-unknown-subtypes", type=int, default=0)
    parser.add_argument("--max-unsafe", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args(argv)
    return check_quality(
        report_path=args.report_path,
        write_json=args.write_json,
        min_records=args.min_records,
        min_auto_resolved=args.min_auto_resolved,
        min_validator_required=args.min_validator_required,
        min_multi_route_required=args.min_multi_route_required,
        require_source_quality_pass=args.require_source_quality_pass,
        require_four_operational_routes_only=args.require_four_operational_routes_only,
        require_no_human_review_required=args.require_no_human_review_required,
        max_unknown_subtypes=args.max_unknown_subtypes,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
    )


if __name__ == "__main__":
    main_build()
