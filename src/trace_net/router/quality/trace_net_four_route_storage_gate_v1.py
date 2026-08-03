"""TRACE-Net Four Route Storage Gate v1.

Converts four-route validated routing decisions into a conservative ingestion/storage
policy. This module is deliberately non-mutating: it writes only local manifest files
and never writes to Postgres, Qdrant, or OpenSearch.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

VALID_OPERATIONAL_ROUTES = {"blank", "plain_text", "table", "image"}
MODULE = "trace_net_four_route_storage_gate_v1"
VERSION = "v1"


def _read_json(path: Path) -> dict[str, Any]:
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


def _write_csv(path: Path, records: list[Mapping[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        field_set: list[str] = []
        seen: set[str] = set()
        for record in records:
            for key in record:
                if key not in seen:
                    seen.add(key)
                    field_set.append(key)
        fieldnames = field_set
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(record)


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "pass", "allowed"}
    return default


def _records_from_payload(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = payload.get("records") or []
    if not isinstance(records, list):
        raise ValueError("source payload records must be a list")
    return [r for r in records if isinstance(r, dict)]


def _infer_page_number(record: Mapping[str, Any]) -> Any:
    for key in ("page_number", "canonical_page_number", "source_page_number"):
        value = record.get(key)
        if value is not None:
            return value
    return None


def _infer_final_route(record: Mapping[str, Any]) -> str | None:
    for key in (
        "final_validated_operational_route",
        "validated_operational_route",
        "source_operational_route",
        "operational_route",
    ):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _is_unresolved(record: Mapping[str, Any]) -> bool:
    decision_text = " ".join(
        str(record.get(key) or "")
        for key in (
            "retry_validation_decision",
            "validation_decision",
            "validation_status",
            "retry_status",
            "operational_resolution_status",
        )
    ).lower()
    return "unresolved" in decision_text or "review_required" in decision_text


def _policy_for_record(record: Mapping[str, Any]) -> dict[str, Any]:
    final_route = _infer_final_route(record)
    invalid_route = final_route not in VALID_OPERATIONAL_ROUTES
    final_do_not_embed = _as_bool(record.get("final_do_not_embed"), default=False)
    unsafe = _as_bool(record.get("unsafe"), default=False) or _as_bool(record.get("unsafe_record"), default=False)
    source_mutation = _as_bool(record.get("source_truth_mutation_allowed"), default=False)
    answer_permission = _as_bool(record.get("answer_permission"), default=False) or _as_bool(
        record.get("can_answer_directly"), default=False
    )
    unresolved = _is_unresolved(record)

    if invalid_route:
        final_route = "unresolved"
        final_do_not_embed = True
        unresolved = True

    # Source tool outputs are advisory, but the storage gate enforces a final block
    # whenever the route is invalid, unresolved, unsafe, or explicitly do-not-embed.
    blocked = final_do_not_embed or unresolved or unsafe or source_mutation or answer_permission

    postgres_graph_record = True
    raw_tiff_reference_preserved = True

    if final_route == "blank":
        qdrant_allowed = False
        opensearch_allowed = False
        final_do_not_embed = True
        storage_decision = "graph_only_blank"
        reasons = ["blank_pages_are_recorded_in_graph_but_not_embedded"]
    elif blocked:
        qdrant_allowed = False
        opensearch_allowed = False
        final_do_not_embed = True
        storage_decision = "graph_only_validator_gated"
        reasons = ["blocked_until_validator_or_retry_passes"]
    else:
        source_qdrant = _as_bool(record.get("qdrant_embedding_allowed"), default=True)
        source_opensearch = _as_bool(record.get("opensearch_index_allowed"), default=False)
        qdrant_allowed = source_qdrant and final_route in {"plain_text", "table", "image"}
        opensearch_allowed = source_opensearch and final_route == "table"
        if opensearch_allowed:
            storage_decision = "validated_graph_semantic_and_exact_index"
            reasons = ["validated_table_or_exact_evidence_can_enter_semantic_and_exact_indexes"]
        elif qdrant_allowed:
            storage_decision = "validated_graph_and_semantic_index"
            reasons = ["validated_nonblank_evidence_can_enter_semantic_index"]
        else:
            storage_decision = "validated_graph_only"
            reasons = ["validated_route_kept_out_of_retrieval_by_source_policy"]

    return {
        "page_id": record.get("page_id"),
        "page_number": _infer_page_number(record),
        "source_member": record.get("source_member"),
        "source_image_sha256": record.get("source_image_sha256"),
        "source_operational_route": record.get("source_operational_route") or record.get("operational_route"),
        "route_subtype": record.get("route_subtype"),
        "final_validated_operational_route": final_route,
        "storage_decision": storage_decision,
        "storage_reasons": reasons,
        "postgres_graph_record": postgres_graph_record,
        "raw_tiff_reference_preserved": raw_tiff_reference_preserved,
        "qdrant_embedding_allowed": qdrant_allowed,
        "opensearch_index_allowed": opensearch_allowed,
        "final_do_not_embed": final_do_not_embed,
        "validator_gated": blocked and final_route != "blank",
        "invalid_operational_route": invalid_route,
        "human_review_required": False,
        "manual_review_required": False,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "unsafe_record": unsafe,
        "source_retry_status": record.get("retry_status"),
        "source_validation_decision": record.get("retry_validation_decision") or record.get("validation_decision"),
        "source_validation_score": record.get("final_validation_score") or record.get("validation_score"),
        "source_validation_reasons": record.get("final_validation_reasons") or record.get("validation_reasons"),
        "ocr_text_word_count": record.get("ocr_text_word_count"),
        "part_number_count": record.get("part_number_count"),
    }


def _summarize(records: list[Mapping[str, Any]], source_payload: Mapping[str, Any], source_path: Path) -> dict[str, Any]:
    final_routes = Counter(r.get("final_validated_operational_route") for r in records)
    decisions = Counter(r.get("storage_decision") for r in records)
    summary: dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "source_route_unresolved_retry_probe": str(source_path),
        "source_route_unresolved_retry_probe_quality_status": source_payload.get("quality_status"),
        "source_record_count": len(_records_from_payload(source_payload)),
        "storage_gate_record_count": len(records),
        "postgres_graph_record_count": sum(1 for r in records if r.get("postgres_graph_record")),
        "raw_tiff_reference_preserved_count": sum(1 for r in records if r.get("raw_tiff_reference_preserved")),
        "qdrant_embedding_allowed_count": sum(1 for r in records if r.get("qdrant_embedding_allowed")),
        "opensearch_index_allowed_count": sum(1 for r in records if r.get("opensearch_index_allowed")),
        "final_do_not_embed_count": sum(1 for r in records if r.get("final_do_not_embed")),
        "validator_gated_count": sum(1 for r in records if r.get("validator_gated")),
        "invalid_operational_route_count": sum(1 for r in records if r.get("invalid_operational_route")),
        "final_validated_route_counts": dict(sorted(final_routes.items(), key=lambda item: str(item[0]))),
        "storage_decision_counts": dict(sorted(decisions.items(), key=lambda item: str(item[0]))),
        "human_review_required_count": sum(1 for r in records if r.get("human_review_required")),
        "manual_review_required_count": sum(1 for r in records if r.get("manual_review_required")),
        "answer_permission_count": sum(1 for r in records if r.get("answer_permission")),
        "can_answer_directly_count": sum(1 for r in records if r.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for r in records if r.get("can_prove_claims")),
        "source_truth_mutation_allowed_count": sum(1 for r in records if r.get("source_truth_mutation_allowed")),
        "unsafe_record_count": sum(1 for r in records if r.get("unsafe_record")),
        "postgres_write_attempt_count": sum(1 for r in records if r.get("postgres_write_attempt")),
        "qdrant_write_attempt_count": sum(1 for r in records if r.get("qdrant_write_attempt")),
        "opensearch_write_attempt_count": sum(1 for r in records if r.get("opensearch_write_attempt")),
        "ready_for_graph_ingestion_manifest": True,
        "ready_for_qdrant_candidate_export": True,
        "ready_for_opensearch_candidate_export": True,
        "ready_for_unresolved_escalation": any(r.get("validator_gated") for r in records),
    }
    return summary


def _quality_status(summary: Mapping[str, Any], *, require_source_quality_pass: bool = True) -> tuple[str, list[str]]:
    failures: list[str] = []
    if require_source_quality_pass and summary.get("source_route_unresolved_retry_probe_quality_status") != "PASS":
        failures.append("source route unresolved retry/probe quality_status is not PASS")
    if summary.get("storage_gate_record_count", 0) <= 0:
        failures.append("no storage gate records were produced")
    if summary.get("postgres_graph_record_count") != summary.get("storage_gate_record_count"):
        failures.append("not every page has a Postgres graph record policy")
    for key in (
        "human_review_required_count",
        "manual_review_required_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "invalid_operational_route_count",
    ):
        if summary.get(key, 0) != 0:
            failures.append(f"{key} must be zero")
    return ("PASS" if not failures else "FAIL", failures)


def build_four_route_storage_gate(
    *,
    route_unresolved_retry_probe_path: Path,
    output_dir: Path,
    quality: bool = False,
) -> dict[str, Any]:
    source_payload = _read_json(route_unresolved_retry_probe_path)
    source_records = _records_from_payload(source_payload)
    output_dir.mkdir(parents=True, exist_ok=True)

    records = [_policy_for_record(record) for record in source_records]
    summary = _summarize(records, source_payload, route_unresolved_retry_probe_path)
    status, failures = _quality_status(summary)

    graph_records = [r for r in records if r.get("postgres_graph_record")]
    qdrant_records = [r for r in records if r.get("qdrant_embedding_allowed")]
    opensearch_records = [r for r in records if r.get("opensearch_index_allowed")]
    blocked_records = [r for r in records if r.get("final_do_not_embed") or r.get("validator_gated")]

    paths = {
        "records_jsonl_path": str(output_dir / "trace_net_four_route_storage_gate_v1_records.jsonl"),
        "records_csv_path": str(output_dir / "trace_net_four_route_storage_gate_v1_records.csv"),
        "postgres_graph_manifest_jsonl_path": str(output_dir / "trace_net_four_route_storage_gate_v1_postgres_graph_manifest.jsonl"),
        "qdrant_candidates_jsonl_path": str(output_dir / "trace_net_four_route_storage_gate_v1_qdrant_candidates.jsonl"),
        "opensearch_candidates_jsonl_path": str(output_dir / "trace_net_four_route_storage_gate_v1_opensearch_candidates.jsonl"),
        "blocked_records_csv_path": str(output_dir / "trace_net_four_route_storage_gate_v1_blocked_records.csv"),
    }
    summary.update(paths)

    payload: dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "status": "TRACE_NET_FOUR_ROUTE_STORAGE_GATE_BUILT",
        "quality_status": status,
        "quality_failures": failures,
        "summary": summary,
        "records": records,
        "postgres_graph_records": graph_records,
        "qdrant_candidate_records": qdrant_records,
        "opensearch_candidate_records": opensearch_records,
        "blocked_records": blocked_records,
    }

    report_path = output_dir / "trace_net_four_route_storage_gate_v1.json"
    _write_json(report_path, payload)
    _write_jsonl(Path(paths["records_jsonl_path"]), records)
    _write_csv(Path(paths["records_csv_path"]), records)
    _write_jsonl(Path(paths["postgres_graph_manifest_jsonl_path"]), graph_records)
    _write_jsonl(Path(paths["qdrant_candidates_jsonl_path"]), qdrant_records)
    _write_jsonl(Path(paths["opensearch_candidates_jsonl_path"]), opensearch_records)
    _write_csv(Path(paths["blocked_records_csv_path"]), blocked_records)
    _write_json(output_dir / "trace_net_four_route_storage_gate_v1_summary.json", summary)

    markdown = _markdown_report(payload)
    (output_dir / "trace_net_four_route_storage_gate_v1.md").write_text(markdown, encoding="utf-8")

    if quality:
        _write_json(output_dir / "trace_net_four_route_storage_gate_v1_quality_check.json", payload)

    print("Status:", payload["status"])
    print("Quality status:", payload["quality_status"])
    print("Summary:", json.dumps(summary, sort_keys=True))
    return payload


def _markdown_report(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary", {})
    lines = [
        "# TRACE-Net Four Route Storage Gate v1",
        "",
        f"Quality status: **{payload.get('quality_status')}**",
        "",
        "## Summary",
        "",
        "```json",
        json.dumps(summary, indent=2, sort_keys=True),
        "```",
        "",
        "## Storage contract",
        "",
        "- Every page receives a Postgres graph/source-map record policy.",
        "- Qdrant candidates are limited to validated, non-blank, non-blocked evidence.",
        "- OpenSearch candidates are limited to validated table/exact-evidence records.",
        "- Unresolved or blocked records remain source-traceable but are not embedded/indexed.",
        "- This builder performs no writes to Postgres, Qdrant, or OpenSearch.",
    ]
    return "\n".join(lines) + "\n"


def main_build(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Build TRACE-Net four-route storage gate manifest v1")
    parser.add_argument("--route-unresolved-retry-probe", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    return build_four_route_storage_gate(
        route_unresolved_retry_probe_path=args.route_unresolved_retry_probe,
        output_dir=args.output_dir,
        quality=args.quality,
    )


if __name__ == "__main__":  # pragma: no cover
    main_build()
