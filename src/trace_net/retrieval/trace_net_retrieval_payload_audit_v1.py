"""TRACE-Net Retrieval Payload Audit v1.

Audits steps 1-3 after OCR/classification:

1. Route separation correctness against OCR/layout evidence.
2. Chunk/source-trace correctness for semantic retrieval payloads.
3. Qdrant/OpenSearch dry-run payload correctness before any live embedding/index write.

The module is intentionally dry-run only. It never writes to Postgres, Qdrant, or
OpenSearch and never grants answer permission.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

MODULE = "trace_net_retrieval_payload_audit_v1"
VERSION = "v1"

REPORT_NAME = "trace_net_retrieval_payload_audit_v1.json"
RECORDS_JSONL = "trace_net_retrieval_payload_audit_v1_records.jsonl"
RECORDS_CSV = "trace_net_retrieval_payload_audit_v1_records.csv"
QDRANT_PAYLOAD_JSONL = "trace_net_retrieval_payload_audit_v1_qdrant_payload_audit.jsonl"
OPENSEARCH_PAYLOAD_JSONL = "trace_net_retrieval_payload_audit_v1_opensearch_payload_audit.jsonl"
VIOLATIONS_CSV = "trace_net_retrieval_payload_audit_v1_violations.csv"
SUMMARY_JSON = "trace_net_retrieval_payload_audit_v1_summary.json"
QUALITY_JSON = "trace_net_retrieval_payload_audit_v1_quality_check.json"

VALID_ROUTES = {"blank", "plain_text", "table", "image"}
PART_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
TABLE_TERMS = ("part number", "item", "fig", "figure", "assy", "assembly", "qty", "nomenclature", "effectivity")
PLAIN_TERMS = ("description", "operation", "procedure", "install", "remove", "maintenance", "inspection", "warning", "caution")
IMAGE_TERMS = ("callout", "leader", "view", "diagram", "illustration", "figure")


@dataclass(frozen=True)
class AuditPaths:
    output_dir: Path
    report: Path
    records_jsonl: Path
    records_csv: Path
    qdrant_payload_jsonl: Path
    opensearch_payload_jsonl: Path
    violations_csv: Path
    summary_json: Path
    quality_json: Path


def _paths(output_dir: Path) -> AuditPaths:
    return AuditPaths(
        output_dir=output_dir,
        report=output_dir / REPORT_NAME,
        records_jsonl=output_dir / RECORDS_JSONL,
        records_csv=output_dir / RECORDS_CSV,
        qdrant_payload_jsonl=output_dir / QDRANT_PAYLOAD_JSONL,
        opensearch_payload_jsonl=output_dir / OPENSEARCH_PAYLOAD_JSONL,
        violations_csv=output_dir / VIOLATIONS_CSV,
        summary_json=output_dir / SUMMARY_JSON,
        quality_json=output_dir / QUALITY_JSON,
    )


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _flatten(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return value


def _write_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys: List[str] = []
    for record in records:
        for key in record.keys():
            if key not in keys:
                keys.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        for record in records:
            writer.writerow({key: _flatten(record.get(key)) for key in keys})


def _records(payload: Mapping[str, Any], key: str = "records") -> List[Dict[str, Any]]:
    value = payload.get(key) or []
    if not isinstance(value, list):
        return []
    return [dict(r) for r in value if isinstance(r, Mapping)]


def _nonempty(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _page_id(record: Mapping[str, Any]) -> Optional[str]:
    for key in ("page_id", "canonical_page_id", "source_page_id"):
        value = record.get(key)
        if _nonempty(value):
            return str(value)
    return None


def _page_number(record: Mapping[str, Any]) -> Optional[int]:
    for key in ("page_number", "canonical_page_number", "source_page_number"):
        value = record.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
    return None


def _route(record: Mapping[str, Any]) -> Optional[str]:
    for key in ("route", "final_validated_operational_route", "operational_route", "source_operational_route"):
        value = record.get(key)
        if _nonempty(value):
            return str(value)
    return None


def _candidate_text(record: Mapping[str, Any]) -> str:
    chunks: List[str] = []
    for key in (
        "ocr_text",
        "best_ocr_text",
        "tesseract_text",
        "text",
        "page_text",
        "ocr_sample_text",
        "sample_text",
        "text_sample",
        "visual_summary_text",
        "summary_text",
    ):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            chunks.append(value.strip())
    if chunks:
        return "\n".join(chunks)
    # Some scan-pack records store PSM outputs as dictionaries/lists.
    for key in ("tesseract_results", "ocr_results", "psm_results"):
        value = record.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, Mapping):
                    text = item.get("text") or item.get("ocr_text")
                    if isinstance(text, str) and text.strip():
                        chunks.append(text.strip())
        elif isinstance(value, Mapping):
            for item in value.values():
                if isinstance(item, Mapping):
                    text = item.get("text") or item.get("ocr_text")
                    if isinstance(text, str) and text.strip():
                        chunks.append(text.strip())
                elif isinstance(item, str) and item.strip():
                    chunks.append(item.strip())
    return "\n".join(chunks)


def _part_number_count(record: Mapping[str, Any], text: str) -> int:
    for key in ("part_number_count", "detected_part_number_count", "part_numbers_count"):
        value = record.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
    for key in ("part_numbers", "detected_part_numbers"):
        value = record.get(key)
        if isinstance(value, list):
            return len(value)
    return len(PART_RE.findall(text or ""))


def _term_count(text: str, terms: Sequence[str]) -> int:
    lower = (text or "").lower()
    return sum(lower.count(term) for term in terms)


def _build_ocr_index(ocr_payload: Mapping[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Dict[int, Dict[str, Any]]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    by_num: Dict[int, Dict[str, Any]] = {}
    for rec in _records(ocr_payload):
        pid = _page_id(rec)
        pnum = _page_number(rec)
        text = _candidate_text(rec)
        enriched = dict(rec)
        enriched["_audit_ocr_text"] = text
        enriched["_audit_ocr_char_count"] = len(text)
        enriched["_audit_part_number_count"] = _part_number_count(enriched, text)
        enriched["_audit_table_term_count"] = _term_count(text, TABLE_TERMS)
        enriched["_audit_plain_term_count"] = _term_count(text, PLAIN_TERMS)
        enriched["_audit_image_term_count"] = _term_count(text, IMAGE_TERMS)
        if pid:
            by_id[pid] = enriched
        if pnum is not None:
            by_num[pnum] = enriched
    return by_id, by_num


def _lookup_ocr(record: Mapping[str, Any], by_id: Mapping[str, Mapping[str, Any]], by_num: Mapping[int, Mapping[str, Any]]) -> Dict[str, Any]:
    pid = _page_id(record)
    if pid and pid in by_id:
        return dict(by_id[pid])
    pnum = _page_number(record)
    if pnum is not None and pnum in by_num:
        return dict(by_num[pnum])
    return {}


def _has_lineage(record: Mapping[str, Any]) -> bool:
    required = ("page_id", "page_number", "source_member", "raw_tiff_reference", "source_image_sha256")
    return all(_nonempty(record.get(k)) for k in required)


def _targets(record: Mapping[str, Any]) -> List[str]:
    value = record.get("contract_ready_targets") or record.get("loader_targets") or []
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def _route_separation(record: Mapping[str, Any], ocr: Mapping[str, Any]) -> Tuple[str, List[str]]:
    route = _route(record)
    text_chars = int(ocr.get("_audit_ocr_char_count") or 0)
    part_count = int(ocr.get("_audit_part_number_count") or 0)
    table_terms = int(ocr.get("_audit_table_term_count") or 0)
    image_terms = int(ocr.get("_audit_image_term_count") or 0)
    targets = set(_targets(record))
    reasons: List[str] = []

    if route not in VALID_ROUTES:
        return "FAIL", ["invalid_or_missing_operational_route"]

    if route == "blank":
        if "qdrant" in targets or "opensearch" in targets:
            return "FAIL", ["blank_page_has_retrieval_target"]
        if text_chars > 80 or part_count > 0:
            return "WARNING", ["blank_route_has_nontrivial_ocr_or_part_numbers"]
        return "PASS", ["blank_not_loaded_to_retrieval"]

    if route == "table":
        if "opensearch" not in targets:
            return "WARNING", ["table_route_not_exact_index_ready"]
        if part_count == 0 and table_terms == 0:
            return "WARNING", ["table_route_has_weak_table_ocr_signals"]
        return "PASS", ["table_route_has_exact_index_contract"]

    if route == "plain_text":
        if "qdrant" not in targets:
            return "WARNING", ["plain_text_not_semantic_index_ready"]
        if "opensearch" in targets:
            return "WARNING", ["plain_text_has_exact_index_target"]
        if part_count > 25 and table_terms > 10:
            return "WARNING", ["plain_text_has_high_table_density"]
        return "PASS", ["plain_text_semantic_only_contract"]

    if route == "image":
        if "qdrant" not in targets:
            return "WARNING", ["image_not_semantic_index_ready"]
        if "opensearch" in targets:
            return "WARNING", ["image_has_exact_index_target"]
        if part_count > 25 and table_terms > image_terms:
            return "WARNING", ["image_has_table_like_ocr_density"]
        return "PASS", ["image_semantic_observation_contract"]

    return "FAIL", ["unreachable_route_separation_state"]


def _chunk_audit(record: Mapping[str, Any], ocr: Mapping[str, Any]) -> Tuple[str, List[str]]:
    route = _route(record)
    targets = set(_targets(record))
    final_do_not_embed = bool(record.get("final_do_not_embed"))
    validator_gated = bool(record.get("validator_gated"))
    reasons: List[str] = []

    if not _has_lineage(record):
        return "FAIL", ["missing_required_source_trace_fields"]
    if bool(record.get("answer_permission")):
        return "FAIL", ["answer_permission_true_on_payload_candidate"]
    if bool(record.get("source_truth_mutation_allowed")):
        return "FAIL", ["source_truth_mutation_allowed_true_on_payload_candidate"]

    if route == "blank" and "qdrant" in targets:
        return "FAIL", ["blank_page_has_semantic_chunk_target"]
    if validator_gated and "qdrant" in targets:
        return "FAIL", ["validator_gated_page_has_semantic_chunk_target"]
    if final_do_not_embed and "qdrant" in targets:
        return "FAIL", ["do_not_embed_page_has_semantic_chunk_target"]

    if "qdrant" not in targets:
        return "NOT_APPLICABLE", ["no_semantic_chunk_expected_for_record"]

    text_chars = int(ocr.get("_audit_ocr_char_count") or 0)
    # Image pages may use a visual observation/summary payload instead of OCR text;
    # table pages may use validated evidence summaries. We still warn on totally empty
    # OCR/supporting text so the operator can inspect payload generation later.
    if text_chars == 0 and route in {"plain_text", "table"}:
        return "WARNING", ["semantic_payload_has_no_ocr_text_in_scan_pack"]

    reasons.append("semantic_payload_lineage_and_route_gate_pass")
    return "PASS", reasons


def _qdrant_payload_audit(record: Mapping[str, Any], ocr: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    targets = set(_targets(record))
    if "qdrant" not in targets:
        return None
    route = _route(record)
    pid = _page_id(record)
    payload = {
        "payload_id": f"{pid or 'unknown'}::qdrant::0001",
        "page_id": pid,
        "page_number": _page_number(record),
        "route": route,
        "source_member": record.get("source_member"),
        "raw_tiff_reference": record.get("raw_tiff_reference"),
        "source_image_sha256": record.get("source_image_sha256"),
        "storage_decision": record.get("storage_decision"),
        "embedding_scope": record.get("embedding_scope"),
        "candidate_reason": record.get("candidate_reason"),
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "write_attempted": False,
        "dry_run_only": True,
        "ocr_char_count": int(ocr.get("_audit_ocr_char_count") or 0),
        "part_number_count": int(ocr.get("_audit_part_number_count") or 0),
    }
    violations: List[str] = []
    if route == "blank":
        violations.append("blank_payload_violation")
    if bool(record.get("validator_gated")):
        violations.append("blocked_payload_violation")
    if bool(record.get("final_do_not_embed")):
        violations.append("do_not_embed_payload_violation")
    if not _has_lineage(record):
        violations.append("missing_lineage_payload_violation")
    if route not in {"plain_text", "table", "image"}:
        violations.append("route_payload_mismatch")
    if not _nonempty(record.get("embedding_scope")):
        violations.append("missing_embedding_scope")
    payload["payload_audit_status"] = "FAIL" if violations else "PASS"
    payload["payload_violations"] = violations
    return payload


def _opensearch_payload_audit(record: Mapping[str, Any], ocr: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    targets = set(_targets(record))
    if "opensearch" not in targets:
        return None
    route = _route(record)
    pid = _page_id(record)
    payload = {
        "payload_id": f"{pid or 'unknown'}::opensearch::0001",
        "page_id": pid,
        "page_number": _page_number(record),
        "route": route,
        "source_member": record.get("source_member"),
        "raw_tiff_reference": record.get("raw_tiff_reference"),
        "source_image_sha256": record.get("source_image_sha256"),
        "storage_decision": record.get("storage_decision"),
        "exact_index_scope": record.get("exact_index_scope"),
        "candidate_reason": record.get("candidate_reason"),
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "write_attempted": False,
        "dry_run_only": True,
        "ocr_char_count": int(ocr.get("_audit_ocr_char_count") or 0),
        "part_number_count": int(ocr.get("_audit_part_number_count") or 0),
    }
    violations: List[str] = []
    if route != "table":
        violations.append("exact_payload_not_table_route")
    if bool(record.get("validator_gated")) or bool(record.get("final_do_not_embed")):
        violations.append("blocked_exact_payload_violation")
    if not _has_lineage(record):
        violations.append("missing_lineage_exact_payload_violation")
    if not _nonempty(record.get("exact_index_scope")):
        violations.append("missing_exact_index_scope")
    payload["payload_audit_status"] = "FAIL" if violations else "PASS"
    payload["payload_violations"] = violations
    return payload


def _count(records: Sequence[Mapping[str, Any]], key: str, value: Any) -> int:
    return sum(1 for record in records if record.get(key) == value)


def _contains_violation(records: Sequence[Mapping[str, Any]], token: str) -> int:
    total = 0
    for record in records:
        values = record.get("payload_violations") or record.get("audit_violations") or []
        if isinstance(values, list) and token in values:
            total += 1
    return total


def build_retrieval_payload_audit(
    *,
    loader_contract_audit_path: Path,
    ocr_route_scan_pack_path: Path,
    output_dir: Path,
    quality: bool = False,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = _paths(output_dir)

    contract_payload = _read_json(loader_contract_audit_path)
    ocr_payload = _read_json(ocr_route_scan_pack_path)
    source_quality = contract_payload.get("quality_status")
    ocr_quality = ocr_payload.get("quality_status")

    by_id, by_num = _build_ocr_index(ocr_payload)
    records: List[Dict[str, Any]] = []
    qdrant_payloads: List[Dict[str, Any]] = []
    opensearch_payloads: List[Dict[str, Any]] = []
    violation_records: List[Dict[str, Any]] = []

    for source in _records(contract_payload):
        record = dict(source)
        ocr = _lookup_ocr(record, by_id, by_num)
        route = _route(record)
        separation_status, separation_reasons = _route_separation(record, ocr)
        chunk_status, chunk_reasons = _chunk_audit(record, ocr)
        qpayload = _qdrant_payload_audit(record, ocr)
        opayload = _opensearch_payload_audit(record, ocr)

        audit_violations: List[str] = []
        if separation_status == "FAIL":
            audit_violations.append("route_separation_violation")
        if chunk_status == "FAIL":
            audit_violations.append("chunk_source_trace_violation")
        if qpayload and qpayload.get("payload_audit_status") == "FAIL":
            audit_violations.extend(qpayload.get("payload_violations") or [])
        if opayload and opayload.get("payload_audit_status") == "FAIL":
            audit_violations.extend(opayload.get("payload_violations") or [])

        out = {
            "module": MODULE,
            "version": VERSION,
            "page_id": _page_id(record),
            "page_number": _page_number(record),
            "route": route,
            "source_member": record.get("source_member"),
            "raw_tiff_reference": record.get("raw_tiff_reference"),
            "source_image_sha256": record.get("source_image_sha256"),
            "lineage_ready": bool(record.get("lineage_ready")) or _has_lineage(record),
            "contract_ready_targets": _targets(record),
            "route_separation_status": separation_status,
            "route_separation_reasons": separation_reasons,
            "semantic_chunk_audit_status": chunk_status,
            "semantic_chunk_audit_reasons": chunk_reasons,
            "qdrant_payload_ready": qpayload is not None and qpayload.get("payload_audit_status") == "PASS",
            "opensearch_payload_ready": opayload is not None and opayload.get("payload_audit_status") == "PASS",
            "ocr_char_count": int(ocr.get("_audit_ocr_char_count") or 0),
            "part_number_count": int(ocr.get("_audit_part_number_count") or 0),
            "table_term_count": int(ocr.get("_audit_table_term_count") or 0),
            "plain_term_count": int(ocr.get("_audit_plain_term_count") or 0),
            "image_term_count": int(ocr.get("_audit_image_term_count") or 0),
            "blank_payload_violation": "blank_payload_violation" in audit_violations,
            "blocked_payload_violation": "blocked_payload_violation" in audit_violations or "blocked_exact_payload_violation" in audit_violations,
            "missing_lineage_payload_violation": "missing_lineage_payload_violation" in audit_violations or "missing_lineage_exact_payload_violation" in audit_violations,
            "route_payload_mismatch": "route_payload_mismatch" in audit_violations or "exact_payload_not_table_route" in audit_violations,
            "audit_violations": sorted(set(audit_violations)),
            "retrieval_payload_audit_status": "FAIL" if audit_violations else "PASS",
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "write_attempted": False,
            "dry_run_only": True,
        }
        records.append(out)
        if qpayload:
            qdrant_payloads.append(qpayload)
        if opayload:
            opensearch_payloads.append(opayload)
        if audit_violations:
            violation_records.append(out)

    route_counts: Dict[str, int] = {}
    for record in records:
        route = str(record.get("route"))
        route_counts[route] = route_counts.get(route, 0) + 1

    summary = {
        "module": MODULE,
        "version": VERSION,
        "source_loader_contract_audit": str(loader_contract_audit_path),
        "source_loader_contract_audit_quality_status": source_quality,
        "source_ocr_route_scan_pack": str(ocr_route_scan_pack_path),
        "source_ocr_route_scan_pack_quality_status": ocr_quality,
        "retrieval_payload_audit_record_count": len(records),
        "route_counts": route_counts,
        "route_separation_pass_count": _count(records, "route_separation_status", "PASS"),
        "route_separation_warning_count": _count(records, "route_separation_status", "WARNING"),
        "route_separation_fail_count": _count(records, "route_separation_status", "FAIL"),
        "semantic_chunk_pass_count": _count(records, "semantic_chunk_audit_status", "PASS"),
        "semantic_chunk_warning_count": _count(records, "semantic_chunk_audit_status", "WARNING"),
        "semantic_chunk_not_applicable_count": _count(records, "semantic_chunk_audit_status", "NOT_APPLICABLE"),
        "semantic_chunk_fail_count": _count(records, "semantic_chunk_audit_status", "FAIL"),
        "qdrant_payload_count": len(qdrant_payloads),
        "qdrant_payload_pass_count": _count(qdrant_payloads, "payload_audit_status", "PASS"),
        "opensearch_payload_count": len(opensearch_payloads),
        "opensearch_payload_pass_count": _count(opensearch_payloads, "payload_audit_status", "PASS"),
        "blank_payload_violation_count": _contains_violation(qdrant_payloads, "blank_payload_violation"),
        "blocked_payload_violation_count": _contains_violation(qdrant_payloads, "blocked_payload_violation") + _contains_violation(opensearch_payloads, "blocked_exact_payload_violation"),
        "missing_lineage_payload_count": _contains_violation(qdrant_payloads, "missing_lineage_payload_violation") + _contains_violation(opensearch_payloads, "missing_lineage_exact_payload_violation"),
        "route_payload_mismatch_count": _contains_violation(qdrant_payloads, "route_payload_mismatch") + _contains_violation(opensearch_payloads, "exact_payload_not_table_route"),
        "empty_chunk_warning_count": _count(records, "semantic_chunk_audit_status", "WARNING"),
        "violation_record_count": len(violation_records),
        "lineage_ready_count": sum(1 for r in records if r.get("lineage_ready")),
        "human_review_required_count": 0,
        "manual_review_required_count": 0,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "write_attempt_count": 0,
        "dry_run_only": True,
        "ready_for_qdrant_payload_review": True,
        "ready_for_opensearch_payload_review": True,
        "ready_for_route_separation_review": True,
    }
    quality_status = "PASS" if (source_quality == "PASS" and ocr_quality == "PASS" and summary["violation_record_count"] == 0) else "FAIL"

    payload = {
        "module": MODULE,
        "version": VERSION,
        "status": "TRACE_NET_RETRIEVAL_PAYLOAD_AUDIT_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "records": records,
        "qdrant_payload_audit_records": qdrant_payloads,
        "opensearch_payload_audit_records": opensearch_payloads,
        "violation_records": violation_records,
    }

    _write_json(paths.report, payload)
    _write_json(paths.summary_json, summary)
    _write_jsonl(paths.records_jsonl, records)
    _write_csv(paths.records_csv, records)
    _write_jsonl(paths.qdrant_payload_jsonl, qdrant_payloads)
    _write_jsonl(paths.opensearch_payload_jsonl, opensearch_payloads)
    _write_csv(paths.violations_csv, violation_records)

    if quality:
        check_payload = check_quality(
            report_path=paths.report,
            write_json=True,
            min_records=1,
            min_route_separation_pass=1,
            min_qdrant_payloads=1,
            min_opensearch_payloads=0,
            max_violation_records=0,
            require_source_quality_pass=True,
            require_no_human_review_required=True,
            max_unsafe=0,
            require_no_answer_permission=True,
            require_no_source_truth_mutation=True,
            require_no_write_attempts=True,
        )
        payload["quality_check"] = check_payload
        _write_json(paths.report, payload)

    print("Status: TRACE_NET_RETRIEVAL_PAYLOAD_AUDIT_BUILT")
    print(f"Quality status: {payload['quality_status']}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    return payload


def check_quality(
    *,
    report_path: Path,
    write_json: bool = False,
    min_records: int = 1,
    min_route_separation_pass: int = 1,
    min_qdrant_payloads: int = 1,
    min_opensearch_payloads: int = 0,
    max_violation_records: int = 0,
    require_source_quality_pass: bool = False,
    require_no_human_review_required: bool = False,
    max_unsafe: int = 0,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
) -> Dict[str, Any]:
    payload = _read_json(report_path)
    summary = dict(payload.get("summary") or {})
    failures: List[str] = []

    if payload.get("quality_status") != "PASS":
        failures.append("manifest quality_status is not PASS")
    if int(summary.get("retrieval_payload_audit_record_count") or 0) < min_records:
        failures.append(f"record count below minimum {min_records}")
    if int(summary.get("route_separation_pass_count") or 0) < min_route_separation_pass:
        failures.append(f"route separation pass count below minimum {min_route_separation_pass}")
    if int(summary.get("qdrant_payload_count") or 0) < min_qdrant_payloads:
        failures.append(f"qdrant payload count below minimum {min_qdrant_payloads}")
    if int(summary.get("opensearch_payload_count") or 0) < min_opensearch_payloads:
        failures.append(f"opensearch payload count below minimum {min_opensearch_payloads}")
    if int(summary.get("violation_record_count") or 0) > max_violation_records:
        failures.append(f"violation record count above maximum {max_violation_records}")
    if require_source_quality_pass:
        if summary.get("source_loader_contract_audit_quality_status") != "PASS":
            failures.append("source loader contract audit quality_status is not PASS")
        if summary.get("source_ocr_route_scan_pack_quality_status") != "PASS":
            failures.append("source OCR route scan pack quality_status is not PASS")
    if require_no_human_review_required and int(summary.get("human_review_required_count") or 0) != 0:
        failures.append("human review required count is not zero")
    if int(summary.get("unsafe_record_count") or 0) > max_unsafe:
        failures.append(f"unsafe record count above maximum {max_unsafe}")
    if require_no_answer_permission and int(summary.get("answer_permission_count") or 0) != 0:
        failures.append("answer permission count is not zero")
    if require_no_source_truth_mutation and int(summary.get("source_truth_mutation_allowed_count") or 0) != 0:
        failures.append("source truth mutation allowed count is not zero")
    if require_no_write_attempts and int(summary.get("write_attempt_count") or 0) != 0:
        failures.append("write attempt count is not zero")
    for key in (
        "blank_payload_violation_count",
        "blocked_payload_violation_count",
        "missing_lineage_payload_count",
        "route_payload_mismatch_count",
    ):
        if int(summary.get(key) or 0) != 0:
            failures.append(f"{key} is not zero")

    result = {
        "quality_status": "FAIL" if failures else "PASS",
        "summary": summary,
        "failures": failures,
    }
    if write_json:
        _write_json(report_path.parent / QUALITY_JSON, result)
        print(f"Wrote: {report_path.parent / QUALITY_JSON}")
    print(f"Quality status: {result['quality_status']}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures, indent=2))
    return result


def main_build() -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Build TRACE-Net retrieval payload audit v1")
    parser.add_argument("--loader-contract-audit", required=True, type=Path)
    parser.add_argument("--ocr-route-scan-pack", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args()
    return build_retrieval_payload_audit(
        loader_contract_audit_path=args.loader_contract_audit,
        ocr_route_scan_pack_path=args.ocr_route_scan_pack,
        output_dir=args.output_dir,
        quality=args.quality,
    )


def main_check() -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Check TRACE-Net retrieval payload audit v1 quality")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-route-separation-pass", type=int, default=1)
    parser.add_argument("--min-qdrant-payloads", type=int, default=1)
    parser.add_argument("--min-opensearch-payloads", type=int, default=0)
    parser.add_argument("--max-violation-records", type=int, default=0)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-no-human-review-required", action="store_true")
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args()
    return check_quality(
        report_path=args.report_path,
        write_json=args.write_json,
        min_records=args.min_records,
        min_route_separation_pass=args.min_route_separation_pass,
        min_qdrant_payloads=args.min_qdrant_payloads,
        min_opensearch_payloads=args.min_opensearch_payloads,
        max_violation_records=args.max_violation_records,
        require_source_quality_pass=args.require_source_quality_pass,
        require_no_human_review_required=args.require_no_human_review_required,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
    )


if __name__ == "__main__":
    main_build()
