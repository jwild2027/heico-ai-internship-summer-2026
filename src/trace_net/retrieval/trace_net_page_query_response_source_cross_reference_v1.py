"""TRACE-Net Page Query Response Source Cross-Reference v1.

Cross-references page-level question/response records to the actual source files
inside a ResCarta/METS metadata ZIP. This is a read-only validation artifact: it
verifies that every response anchor points to a ZIP TIFF entry and METS checksum,
without granting answer permission or mutating source truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from xml.etree import ElementTree as ET

SCHEMA_VERSION = "trace_net_page_query_response_source_cross_reference_v1"
REPORT_NAME = "trace_net_page_query_response_source_cross_reference_v1.json"
QUALITY_NAME = "trace_net_page_query_response_source_cross_reference_v1_quality.json"
RECORDS_NAME = "trace_net_page_query_response_source_cross_reference_v1_records.jsonl"
RESPONSES_NAME = "trace_net_page_query_response_source_cross_reference_v1_responses.jsonl"
MARKDOWN_NAME = "trace_net_page_query_response_source_cross_reference_v1.md"

METS_NS = "{http://www.loc.gov/METS/}"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
DEFAULT_MANUAL_LABEL = "EMB CMM ATA 25-21-00 REV.4"


def load_json(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing JSON input: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: str | Path, records: Sequence[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


def compact_text(value: Any, max_chars: int = 1000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "..."
    return text


def page_number_from_id(page_id: str) -> Optional[int]:
    match = re.search(r"p(\d{6})$", page_id or "")
    if not match:
        return None
    return int(match.group(1))


def entry_name_from_page_number(page_number: Optional[int]) -> Optional[str]:
    if page_number is None:
        return None
    return f"{page_number:08d}.tif"


def normalize_entry_name(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip().replace("\\", "/")
    if not text:
        return None
    if text.lower().startswith("file://./"):
        text = text[9:]
    if text.lower().startswith("file://"):
        text = text[7:]
    text = text.split("?")[0].split("#")[0]
    return text.rsplit("/", 1)[-1] if text else None


def get_list(payload: Mapping[str, Any], keys: Sequence[str]) -> List[Dict[str, Any]]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [dict(v) for v in value if isinstance(v, dict)]
    return []


def get_nested(mapping: Mapping[str, Any], dotted: str) -> Any:
    cur: Any = mapping
    for part in dotted.split("."):
        if not isinstance(cur, Mapping):
            return None
        cur = cur.get(part)
    return cur


def extract_source_entry(record: Mapping[str, Any]) -> Optional[str]:
    candidates = [
        get_nested(record, "source_identity.source_package_entry_name"),
        get_nested(record, "graph_path.source_package_entry_name"),
        record.get("source_package_entry_name"),
        get_nested(record, "source_identity.source_package.trace_net:source_package_entry_name"),
    ]
    for candidate in candidates:
        entry = normalize_entry_name(candidate)
        if entry:
            return entry
    page_number = record.get("page_number")
    if isinstance(page_number, int):
        return entry_name_from_page_number(page_number)
    page_id = str(record.get("page_id") or "")
    return entry_name_from_page_number(page_number_from_id(page_id))


def extract_source_href(record: Mapping[str, Any], entry_name: Optional[str]) -> Optional[str]:
    candidates = [
        get_nested(record, "source_identity.source_package_entry_href"),
        get_nested(record, "graph_path.source_package_entry_href"),
        get_nested(record, "source_identity.source_package.trace_net:source_package_entry_href"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    if entry_name:
        return f"file://./{entry_name}"
    return None


def parse_metadata_zip(metadata_zip: str | Path, compute_checksums: bool = True) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
    path = Path(metadata_zip)
    if not path.exists():
        raise FileNotFoundError(f"Missing metadata zip: {path}")

    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        name_set = set(names)
        xml_name = next((n for n in names if n.lower().endswith("metadata.xml")), None)
        xml_text = zf.read(xml_name).decode("utf-8", errors="replace") if xml_name else ""
        mets_entries: Dict[str, Dict[str, Any]] = {}
        objid = None
        label = None
        package_type = None
        created_at = None
        record_status = None
        if xml_text:
            try:
                root = ET.fromstring(xml_text.encode("utf-8"))
                objid = root.attrib.get("OBJID")
                label = root.attrib.get("LABEL")
                package_type = root.attrib.get("TYPE")
                hdr = root.find(f"{METS_NS}metsHdr")
                if hdr is not None:
                    created_at = hdr.attrib.get("CREATEDATE")
                    record_status = hdr.attrib.get("RECORDSTATUS")
                for file_el in root.findall(f".//{METS_NS}file"):
                    flocat = file_el.find(f"{METS_NS}FLocat")
                    href = flocat.attrib.get(XLINK_HREF) if flocat is not None else None
                    entry_name = normalize_entry_name(href)
                    if not entry_name:
                        continue
                    mets_entries[entry_name] = {
                        "mets_file_id": file_el.attrib.get("ID"),
                        "mets_group_id": file_el.attrib.get("GROUPID"),
                        "mets_mimetype": file_el.attrib.get("MIMETYPE"),
                        "mets_checksum_type": file_el.attrib.get("CHECKSUMTYPE"),
                        "mets_checksum_sha1": file_el.attrib.get("CHECKSUM"),
                        "mets_size_bytes": int(file_el.attrib.get("SIZE")) if str(file_el.attrib.get("SIZE") or "").isdigit() else None,
                        "mets_href": href,
                        "source_package_entry_name": entry_name,
                    }
            except ET.ParseError as exc:
                raise ValueError(f"Could not parse metadata.xml in {path}: {exc}") from exc

        file_records: Dict[str, Dict[str, Any]] = {}
        for name in names:
            entry_name = normalize_entry_name(name)
            if not entry_name or entry_name.lower() == "metadata.xml":
                continue
            info = zf.getinfo(name)
            record = dict(mets_entries.get(entry_name) or {})
            record.update(
                {
                    "zip_entry_exists": True,
                    "zip_member_name": name,
                    "zip_entry_name": entry_name,
                    "zip_size_bytes": info.file_size,
                    "zip_compress_size_bytes": info.compress_size,
                }
            )
            if compute_checksums:
                sha1 = hashlib.sha1()
                with zf.open(name, "r") as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b""):
                        sha1.update(chunk)
                record["zip_entry_checksum_sha1_computed"] = sha1.hexdigest()
            expected_sha1 = record.get("mets_checksum_sha1")
            computed_sha1 = record.get("zip_entry_checksum_sha1_computed")
            record["checksum_match"] = bool(expected_sha1 and computed_sha1 and str(expected_sha1).lower() == str(computed_sha1).lower())
            mets_size = record.get("mets_size_bytes")
            record["size_match"] = bool(mets_size is not None and int(mets_size) == int(info.file_size))
            file_records[entry_name] = record

        # Include METS entries that were not found in the ZIP.
        for entry_name, record in mets_entries.items():
            if entry_name not in file_records:
                missing = dict(record)
                missing.update(
                    {
                        "zip_entry_exists": False,
                        "zip_entry_name": entry_name,
                        "zip_size_bytes": None,
                        "zip_compress_size_bytes": None,
                        "zip_entry_checksum_sha1_computed": None,
                        "checksum_match": False,
                        "size_match": False,
                    }
                )
                file_records[entry_name] = missing

    package_summary = {
        "metadata_zip_path": str(path),
        "metadata_xml_present": bool(xml_name),
        "metadata_xml_name": xml_name,
        "source_package_objid": objid,
        "source_package_label": label,
        "source_package_type": package_type,
        "source_package_created_at": created_at,
        "source_package_record_status": record_status,
        "source_package_file_count": len(names),
        "source_package_tiff_count": sum(1 for n in name_set if n.lower().endswith((".tif", ".tiff"))),
        "mets_file_entry_count": len(mets_entries),
        "zip_file_entry_count": len(file_records),
    }
    return package_summary, file_records


def response_mentions_page_and_entry(response: str, page_id: str, entry_name: Optional[str]) -> Tuple[bool, bool]:
    response_text = response or ""
    page_ok = bool(page_id and page_id in response_text)
    entry_ok = bool(entry_name and entry_name in response_text)
    return page_ok, entry_ok


def build_cross_reference_records(
    dataset_payload: Mapping[str, Any],
    package_summary: Mapping[str, Any],
    file_records: Mapping[str, Mapping[str, Any]],
    *,
    first_pages: int,
) -> List[Dict[str, Any]]:
    source_records = get_list(dataset_payload, ["query_response_records", "records"])
    out: List[Dict[str, Any]] = []
    for source in source_records:
        page_id = str(source.get("page_id") or "")
        page_number = source.get("page_number")
        if not isinstance(page_number, int):
            page_number = page_number_from_id(page_id)
        if page_number is None or page_number < 1 or page_number > first_pages:
            continue
        expected_entry = entry_name_from_page_number(page_number)
        response_entry = extract_source_entry(source)
        response_href = extract_source_href(source, response_entry)
        file_record = dict(file_records.get(response_entry or "") or {})
        zip_exists = bool(file_record.get("zip_entry_exists"))
        mets_resolved = bool(file_record.get("mets_file_id") or file_record.get("mets_href"))
        checksum_match = bool(file_record.get("checksum_match"))
        size_match = bool(file_record.get("size_match"))
        wrong_source_entry = bool(response_entry and expected_entry and response_entry != expected_entry)
        response = str(source.get("response") or "")
        page_anchor_ok, entry_anchor_ok = response_mentions_page_and_entry(response, page_id, response_entry)
        blank_expected = bool(source.get("blank_expected"))
        blank_ok = True
        if blank_expected:
            low = response.lower()
            blank_ok = "blank" in low or "empty" in low

        validation_flags: List[str] = []
        if wrong_source_entry:
            validation_flags.append("response_source_entry_not_expected_page_entry")
        if not zip_exists:
            validation_flags.append("zip_entry_missing")
        if not mets_resolved:
            validation_flags.append("mets_file_entry_missing")
        if zip_exists and mets_resolved and not checksum_match:
            validation_flags.append("checksum_mismatch")
        if zip_exists and mets_resolved and not size_match:
            validation_flags.append("size_mismatch")
        if not page_anchor_ok:
            validation_flags.append("response_missing_page_id_anchor")
        if not entry_anchor_ok:
            validation_flags.append("response_missing_source_entry_anchor")
        if blank_expected and not blank_ok:
            validation_flags.append("blank_response_missing_blank_or_empty")

        cross_reference_status = "PASS" if not validation_flags else "REVIEW"
        record = {
            "schema_version": SCHEMA_VERSION,
            "record_id": f"page_query_response_source_cross_reference::{page_id}",
            "page_id": page_id,
            "page_number": page_number,
            "question": source.get("question"),
            "response": response,
            "blank_expected": blank_expected,
            "expected_source_entry_name": expected_entry,
            "response_source_entry_name": response_entry,
            "response_source_entry_href": response_href,
            "source_package": {
                "metadata_xml_present": bool(package_summary.get("metadata_xml_present")),
                "source_package_objid": package_summary.get("source_package_objid"),
                "source_package_label": package_summary.get("source_package_label") or get_nested(source, "source_identity.source_package_label") or DEFAULT_MANUAL_LABEL,
                "source_package_type": package_summary.get("source_package_type"),
                "source_package_record_status": package_summary.get("source_package_record_status"),
            },
            "file_cross_reference": {
                "zip_entry_exists": zip_exists,
                "zip_member_name": file_record.get("zip_member_name"),
                "zip_entry_name": file_record.get("zip_entry_name") or response_entry,
                "zip_size_bytes": file_record.get("zip_size_bytes"),
                "zip_compress_size_bytes": file_record.get("zip_compress_size_bytes"),
                "mets_file_id": file_record.get("mets_file_id"),
                "mets_group_id": file_record.get("mets_group_id"),
                "mets_href": file_record.get("mets_href"),
                "mets_mimetype": file_record.get("mets_mimetype"),
                "mets_size_bytes": file_record.get("mets_size_bytes"),
                "mets_checksum_type": file_record.get("mets_checksum_type"),
                "mets_checksum_sha1": file_record.get("mets_checksum_sha1"),
                "zip_entry_checksum_sha1_computed": file_record.get("zip_entry_checksum_sha1_computed"),
                "checksum_match": checksum_match,
                "size_match": size_match,
            },
            "anchor_checks": {
                "response_mentions_page_id": page_anchor_ok,
                "response_mentions_source_entry": entry_anchor_ok,
                "blank_response_mentions_blank_or_empty": blank_ok if blank_expected else None,
                "response_source_entry_matches_expected_page": not wrong_source_entry,
            },
            "cross_reference_status": cross_reference_status,
            "validation_flags": validation_flags,
            "qdrant_eval": source.get("qdrant_eval") if isinstance(source.get("qdrant_eval"), dict) else {},
            "graph_path": source.get("graph_path") if isinstance(source.get("graph_path"), dict) else {},
            "safety_contract": {
                "retrieval_only": True,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
                "postgres_write_attempt": False,
                "qdrant_write_attempt": False,
                "opensearch_write_attempt": False,
            },
        }
        out.append(record)
    return out[:first_pages]


def summarize(records: Sequence[Mapping[str, Any]], dataset_payload: Mapping[str, Any], package_summary: Mapping[str, Any]) -> Dict[str, Any]:
    dataset_summary = dataset_payload.get("summary") if isinstance(dataset_payload.get("summary"), dict) else {}
    flag_counter = Counter()
    for record in records:
        flag_counter.update(record.get("validation_flags") or [])
    record_count = len(records)
    pass_count = sum(1 for r in records if r.get("cross_reference_status") == "PASS")
    return {
        "schema_version": SCHEMA_VERSION,
        "source_dataset_quality_status": dataset_payload.get("quality_status"),
        "source_dataset_status": dataset_payload.get("status"),
        "source_dataset_record_count": dataset_summary.get("record_count"),
        "source_dataset_response_count": dataset_summary.get("response_count"),
        "source_dataset_graph_path_resolved_count": dataset_summary.get("graph_path_resolved_count"),
        "source_dataset_source_identity_resolved_count": dataset_summary.get("source_identity_resolved_count"),
        "metadata_zip_path": package_summary.get("metadata_zip_path"),
        "metadata_xml_present": bool(package_summary.get("metadata_xml_present")),
        "metadata_xml_name": package_summary.get("metadata_xml_name"),
        "source_package_objid": package_summary.get("source_package_objid"),
        "source_package_label": package_summary.get("source_package_label"),
        "source_package_type": package_summary.get("source_package_type"),
        "source_package_file_count": package_summary.get("source_package_file_count"),
        "source_package_tiff_count": package_summary.get("source_package_tiff_count"),
        "mets_file_entry_count": package_summary.get("mets_file_entry_count"),
        "record_count": record_count,
        "response_count": sum(1 for r in records if r.get("response")),
        "question_count": sum(1 for r in records if r.get("question")),
        "cross_reference_pass_count": pass_count,
        "cross_reference_review_count": record_count - pass_count,
        "zip_entry_resolved_count": sum(1 for r in records if get_nested(r, "file_cross_reference.zip_entry_exists")),
        "mets_file_entry_resolved_count": sum(1 for r in records if get_nested(r, "file_cross_reference.mets_file_id") or get_nested(r, "file_cross_reference.mets_href")),
        "checksum_verified_count": sum(1 for r in records if get_nested(r, "file_cross_reference.checksum_match")),
        "size_match_count": sum(1 for r in records if get_nested(r, "file_cross_reference.size_match")),
        "response_page_anchor_count": sum(1 for r in records if get_nested(r, "anchor_checks.response_mentions_page_id")),
        "response_source_entry_anchor_count": sum(1 for r in records if get_nested(r, "anchor_checks.response_mentions_source_entry")),
        "expected_source_entry_match_count": sum(1 for r in records if get_nested(r, "anchor_checks.response_source_entry_matches_expected_page")),
        "blank_record_count": sum(1 for r in records if r.get("blank_expected")),
        "blank_answer_cross_reference_count": sum(1 for r in records if r.get("blank_expected") and get_nested(r, "anchor_checks.blank_response_mentions_blank_or_empty")),
        "missing_zip_entry_count": flag_counter.get("zip_entry_missing", 0),
        "missing_mets_entry_count": flag_counter.get("mets_file_entry_missing", 0),
        "checksum_mismatch_count": flag_counter.get("checksum_mismatch", 0),
        "size_mismatch_count": flag_counter.get("size_mismatch", 0),
        "wrong_source_entry_count": flag_counter.get("response_source_entry_not_expected_page_entry", 0),
        "response_missing_page_id_anchor_count": flag_counter.get("response_missing_page_id_anchor", 0),
        "response_missing_source_entry_anchor_count": flag_counter.get("response_missing_source_entry_anchor", 0),
        "blank_response_missing_blank_or_empty_count": flag_counter.get("blank_response_missing_blank_or_empty", 0),
        "validation_flag_counts": dict(sorted(flag_counter.items())),
        "unsafe_response_count": 0,
        "answer_capable_response_count": 0,
        "claim_proof_response_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }


def quality_checks(summary: Mapping[str, Any], thresholds: Mapping[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    checks: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    if thresholds.get("require_dataset_quality_pass"):
        add("source_dataset_quality_pass", summary.get("source_dataset_quality_status") == "PASS", f"source_dataset_quality_status={summary.get('source_dataset_quality_status')}")
    if thresholds.get("require_metadata_xml"):
        add("metadata_xml_present", bool(summary.get("metadata_xml_present")), f"metadata_xml_present={summary.get('metadata_xml_present')}")
    for summary_key, threshold_key, label in [
        ("record_count", "min_records", "records"),
        ("response_count", "min_responses", "responses"),
        ("zip_entry_resolved_count", "min_zip_entry_resolved", "zip entries"),
        ("mets_file_entry_resolved_count", "min_mets_file_entry_resolved", "METS entries"),
        ("checksum_verified_count", "min_checksum_verified", "checksum verified"),
        ("size_match_count", "min_size_matches", "size matches"),
        ("response_page_anchor_count", "min_response_page_anchors", "response page anchors"),
        ("response_source_entry_anchor_count", "min_response_source_entry_anchors", "response source entry anchors"),
        ("blank_answer_cross_reference_count", "min_blank_answer_cross_references", "blank answer cross refs"),
    ]:
        minimum = int(thresholds.get(threshold_key) or 0)
        add(summary_key, int(summary.get(summary_key) or 0) >= minimum, f"{label}={summary.get(summary_key)}; minimum={minimum}")

    for summary_key, threshold_key, label in [
        ("missing_zip_entry_count", "max_missing_zip_entries", "missing zip entries"),
        ("missing_mets_entry_count", "max_missing_mets_entries", "missing METS entries"),
        ("checksum_mismatch_count", "max_checksum_mismatches", "checksum mismatches"),
        ("size_mismatch_count", "max_size_mismatches", "size mismatches"),
        ("wrong_source_entry_count", "max_wrong_source_entries", "wrong source entries"),
        ("unsafe_response_count", "max_unsafe_responses", "unsafe responses"),
        ("answer_capable_response_count", "max_answer_capable_responses", "answer capable responses"),
        ("claim_proof_response_count", "max_claim_proof_responses", "claim proof responses"),
        ("source_truth_mutation_allowed_count", "max_source_truth_mutation_allowed", "source mutations"),
    ]:
        maximum = int(thresholds.get(threshold_key) or 0)
        add(summary_key, int(summary.get(summary_key) or 0) <= maximum, f"{label}={summary.get(summary_key)}; maximum={maximum}")

    add("no_write_attempts", not any(int(summary.get(k) or 0) for k in ["postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"]), "write attempts must be zero")
    if thresholds.get("require_no_answer_permission"):
        add("no_answer_permission", int(summary.get("can_answer_directly_count") or 0) == 0 and int(summary.get("can_prove_claims_count") or 0) == 0, "can_answer_directly/can_prove_claims must be zero")

    status = "PASS" if all(c["ok"] for c in checks) else "FAIL"
    return status, checks


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    lines = [
        "# TRACE-Net Page Query Response Source Cross-Reference v1",
        "",
        f"Status: `{payload.get('status')}`",
        f"Quality status: `{payload.get('quality_status')}`",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "record_count",
        "response_count",
        "zip_entry_resolved_count",
        "mets_file_entry_resolved_count",
        "checksum_verified_count",
        "size_match_count",
        "response_page_anchor_count",
        "response_source_entry_anchor_count",
        "blank_answer_cross_reference_count",
        "missing_zip_entry_count",
        "checksum_mismatch_count",
        "wrong_source_entry_count",
        "unsafe_response_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: `{summary.get(key)}`")
    lines.extend(
        [
            "",
            "## Safety contract",
            "",
            "This artifact is read-only. It cross-references response anchors to METS/ZIP source files; it does not grant answer permission or claim-proof authority.",
            "",
            "## Outputs",
            "",
            f"- Records JSONL: `{payload.get('records_path')}`",
            f"- Responses JSONL: `{payload.get('responses_path')}`",
        ]
    )
    return "\n".join(lines) + "\n"


def build_cross_reference(
    *,
    page_query_response_dataset: str | Path,
    metadata_zip: str | Path,
    output_dir: str | Path,
    first_pages: int,
    thresholds: Mapping[str, Any],
) -> Dict[str, Any]:
    dataset_payload = load_json(page_query_response_dataset)
    package_summary, file_records = parse_metadata_zip(metadata_zip, compute_checksums=True)
    records = build_cross_reference_records(dataset_payload, package_summary, file_records, first_pages=first_pages)
    summary = summarize(records, dataset_payload, package_summary)
    quality_status, checks = quality_checks(summary, thresholds)

    out_dir = Path(output_dir)
    report_path = out_dir / REPORT_NAME
    quality_path = out_dir / QUALITY_NAME
    records_path = out_dir / RECORDS_NAME
    responses_path = out_dir / RESPONSES_NAME
    markdown_path = out_dir / MARKDOWN_NAME

    response_records = [
        {
            "record_id": r.get("record_id"),
            "page_id": r.get("page_id"),
            "page_number": r.get("page_number"),
            "question": r.get("question"),
            "response": r.get("response"),
            "source_entry": r.get("response_source_entry_name"),
            "zip_entry_exists": get_nested(r, "file_cross_reference.zip_entry_exists"),
            "checksum_match": get_nested(r, "file_cross_reference.checksum_match"),
            "size_match": get_nested(r, "file_cross_reference.size_match"),
            "cross_reference_status": r.get("cross_reference_status"),
            "validation_flags": r.get("validation_flags"),
        }
        for r in records
    ]

    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "PAGE_QUERY_RESPONSE_SOURCE_CROSS_REFERENCE_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "quality_checks": checks,
        "source_package_summary": package_summary,
        "cross_reference_records": records,
        "records_path": str(records_path),
        "responses_path": str(responses_path),
        "quality_path": str(quality_path),
        "report_path": str(report_path),
        "markdown_path": str(markdown_path),
    }
    write_json(report_path, payload)
    write_json(quality_path, {k: payload[k] for k in ["schema_version", "status", "quality_status", "summary", "quality_checks"]})
    write_jsonl(records_path, records)
    write_jsonl(responses_path, response_records)
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload


def parse_thresholds(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "min_records": args.min_records,
        "min_responses": args.min_responses,
        "min_zip_entry_resolved": args.min_zip_entry_resolved,
        "min_mets_file_entry_resolved": args.min_mets_file_entry_resolved,
        "min_checksum_verified": args.min_checksum_verified,
        "min_size_matches": args.min_size_matches,
        "min_response_page_anchors": args.min_response_page_anchors,
        "min_response_source_entry_anchors": args.min_response_source_entry_anchors,
        "min_blank_answer_cross_references": args.min_blank_answer_cross_references,
        "max_missing_zip_entries": args.max_missing_zip_entries,
        "max_missing_mets_entries": args.max_missing_mets_entries,
        "max_checksum_mismatches": args.max_checksum_mismatches,
        "max_size_mismatches": args.max_size_mismatches,
        "max_wrong_source_entries": args.max_wrong_source_entries,
        "max_unsafe_responses": args.max_unsafe_responses,
        "max_answer_capable_responses": args.max_answer_capable_responses,
        "max_claim_proof_responses": args.max_claim_proof_responses,
        "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
        "require_dataset_quality_pass": args.require_dataset_quality_pass,
        "require_metadata_xml": args.require_metadata_xml,
        "require_no_answer_permission": args.require_no_answer_permission,
    }


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-records", type=int, default=0)
    parser.add_argument("--min-responses", type=int, default=0)
    parser.add_argument("--min-zip-entry-resolved", type=int, default=0)
    parser.add_argument("--min-mets-file-entry-resolved", type=int, default=0)
    parser.add_argument("--min-checksum-verified", type=int, default=0)
    parser.add_argument("--min-size-matches", type=int, default=0)
    parser.add_argument("--min-response-page-anchors", type=int, default=0)
    parser.add_argument("--min-response-source-entry-anchors", type=int, default=0)
    parser.add_argument("--min-blank-answer-cross-references", type=int, default=0)
    parser.add_argument("--max-missing-zip-entries", type=int, default=0)
    parser.add_argument("--max-missing-mets-entries", type=int, default=0)
    parser.add_argument("--max-checksum-mismatches", type=int, default=0)
    parser.add_argument("--max-size-mismatches", type=int, default=0)
    parser.add_argument("--max-wrong-source-entries", type=int, default=0)
    parser.add_argument("--max-unsafe-responses", type=int, default=0)
    parser.add_argument("--max-answer-capable-responses", type=int, default=0)
    parser.add_argument("--max-claim-proof-responses", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-dataset-quality-pass", action="store_true")
    parser.add_argument("--require-metadata-xml", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net page query response source cross-reference v1")
    parser.add_argument("--page-query-response-dataset", required=True)
    parser.add_argument("--metadata-zip", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--first-pages", type=int, default=200)
    parser.add_argument("--quality", action="store_true")
    add_common_args(parser)
    args = parser.parse_args(argv)

    payload = build_cross_reference(
        page_query_response_dataset=args.page_query_response_dataset,
        metadata_zip=args.metadata_zip,
        output_dir=args.output_dir,
        first_pages=args.first_pages,
        thresholds=parse_thresholds(args),
    )
    summary = payload.get("summary", {})
    print("TRACE-Net Page Query Response Source Cross-Reference v1")
    print(f" Status: {payload.get('status')}")
    print(f" Quality status: {payload.get('quality_status')}")
    for key in [
        "source_dataset_quality_status",
        "metadata_xml_present",
        "source_package_tiff_count",
        "record_count",
        "response_count",
        "zip_entry_resolved_count",
        "mets_file_entry_resolved_count",
        "checksum_verified_count",
        "size_match_count",
        "response_page_anchor_count",
        "response_source_entry_anchor_count",
        "blank_answer_cross_reference_count",
        "missing_zip_entry_count",
        "checksum_mismatch_count",
        "wrong_source_entry_count",
        "unsafe_response_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {payload.get('report_path')}")
    print(f" quality_path: {payload.get('quality_path')}")
    return 0 if not args.quality or payload.get("quality_status") == "PASS" else 1


def check_cross_reference_quality(report_path: str | Path, thresholds: Mapping[str, Any], write_json_report: bool = False) -> Dict[str, Any]:
    payload = load_json(report_path)
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    quality_status, checks = quality_checks(summary, thresholds)
    payload["quality_status"] = quality_status
    payload["quality_checks"] = checks
    if write_json_report:
        write_json(Path(report_path).with_name(QUALITY_NAME), {"schema_version": SCHEMA_VERSION, "status": payload.get("status"), "quality_status": quality_status, "summary": summary, "quality_checks": checks})
    return payload


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net page query response source cross-reference v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    add_common_args(parser)
    args = parser.parse_args(argv)
    payload = check_cross_reference_quality(args.report_path, parse_thresholds(args), write_json_report=args.write_json)
    summary = payload.get("summary", {})
    print("TRACE-Net Page Query Response Source Cross-Reference v1")
    print(f" Status: {payload.get('status')}")
    print(f" Quality status: {payload.get('quality_status')}")
    for key in [
        "record_count",
        "response_count",
        "zip_entry_resolved_count",
        "mets_file_entry_resolved_count",
        "checksum_verified_count",
        "size_match_count",
        "missing_zip_entry_count",
        "checksum_mismatch_count",
        "wrong_source_entry_count",
        "unsafe_response_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    return 0 if payload.get("quality_status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main_build())
