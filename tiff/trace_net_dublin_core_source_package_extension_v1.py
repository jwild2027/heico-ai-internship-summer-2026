"""TRACE-Net Dublin Core Source Package Extension v1.

Read-only enrichment layer that joins a source package ZIP/METS metadata.xml to
refined Dublin Core page metadata. It adds source-package provenance such as TIFF
entry name, file size, checksum, page number, package label, METS OBJID, and
traceability status. This module never mutates source truth or writes to search,
vector, graph, or database services.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET

SCHEMA_VERSION = "trace_net_dublin_core_source_package_extension_v1"
STATUS_BUILT = "DUBLIN_CORE_SOURCE_PACKAGE_EXTENSION_BUILT"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

PAGE_ID_RE = re.compile(r"p(\d{6})$")
TIFF_RE = re.compile(r"(\d{1,8})\.tiff?$", re.IGNORECASE)

NS = {
    "mets": "http://www.loc.gov/METS/",
    "mods": "http://www.loc.gov/mods/v3",
    "xlink": "http://www.w3.org/1999/xlink",
}

# These fields are intentionally not answer/proof authority. This extension is
# catalog/provenance metadata only.
SAFETY_FLAGS = {
    "can_answer_directly": False,
    "can_prove_claims": False,
    "can_mutate_source_truth": False,
    "source_truth_mutation_allowed": False,
    "direct_answer_allowed": False,
    "claim_proof_allowed": False,
}


@dataclass(frozen=True)
class SourcePackageEntry:
    entry_name: str
    entry_suffix: str
    page_number: int | None
    href: str
    mets_file_id: str
    mets_group_id: str
    mimetype: str
    size_bytes_mets: int | None
    size_bytes_zip: int | None
    checksum_sha1_mets: str
    checksum_sha1_computed: str
    checksum_match: bool | None
    zip_crc: int | None
    zip_compress_size: int | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_name": self.entry_name,
            "entry_suffix": self.entry_suffix,
            "page_number": self.page_number,
            "href": self.href,
            "mets_file_id": self.mets_file_id,
            "mets_group_id": self.mets_group_id,
            "mimetype": self.mimetype,
            "size_bytes_mets": self.size_bytes_mets,
            "size_bytes_zip": self.size_bytes_zip,
            "checksum_sha1_mets": self.checksum_sha1_mets,
            "checksum_sha1_computed": self.checksum_sha1_computed,
            "checksum_match": self.checksum_match,
            "zip_crc": self.zip_crc,
            "zip_compress_size": self.zip_compress_size,
        }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


def safe_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_zip_entry_name(value: str) -> str:
    value = value.replace("\\", "/")
    value = value.replace("file://./", "")
    value = value.replace("file://", "")
    value = value.lstrip("./")
    return value


def suffix_for(name: str) -> str:
    suffix = Path(name).suffix.lower()
    return suffix or ""


def page_number_from_entry_name(name: str) -> int | None:
    match = TIFF_RE.search(Path(name).name)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def page_number_from_page_id(page_id: str) -> int | None:
    match = PAGE_ID_RE.search(page_id or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def text_at(root: ET.Element, xpath: str) -> str:
    node = root.find(xpath, NS)
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def all_text_at(root: ET.Element, xpath: str) -> list[str]:
    values: list[str] = []
    for node in root.findall(xpath, NS):
        if node.text and node.text.strip():
            values.append(node.text.strip())
    return values


def sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_source_package(metadata_zip_path: Path, verify_checksums: bool = True) -> dict[str, Any]:
    """Parse metadata.zip and embedded METS metadata.xml."""
    if not metadata_zip_path.exists():
        raise FileNotFoundError(f"metadata zip not found: {metadata_zip_path}")

    with zipfile.ZipFile(metadata_zip_path) as zf:
        infos = {info.filename: info for info in zf.infolist() if not info.is_dir()}
        metadata_names = [name for name in infos if Path(name).name.lower() == "metadata.xml"]
        if not metadata_names:
            raise ValueError("metadata.xml not found in source package")
        metadata_name = metadata_names[0]
        metadata_xml = zf.read(metadata_name)
        root = ET.fromstring(metadata_xml)

        mets_label = root.attrib.get("LABEL", "")
        mets_objid = root.attrib.get("OBJID", "")
        mets_type = root.attrib.get("TYPE", "")
        hdr = root.find("mets:metsHdr", NS)
        created_at = hdr.attrib.get("CREATEDATE", "") if hdr is not None else ""
        record_status = hdr.attrib.get("RECORDSTATUS", "") if hdr is not None else ""

        agent_names = all_text_at(root, ".//mets:metsHdr/mets:agent/mets:name")
        agent_notes = all_text_at(root, ".//mets:metsHdr/mets:agent/mets:note")

        title = text_at(root, ".//mods:titleInfo/mods:title")
        owner = text_at(root, ".//mods:name/mods:namePart")
        type_of_resource = text_at(root, ".//mods:typeOfResource")
        genre = text_at(root, ".//mods:genre")
        date_captured = text_at(root, ".//mods:originInfo/mods:dateCaptured")
        issuance = text_at(root, ".//mods:originInfo/mods:issuance")
        language_code = text_at(root, ".//mods:languageTerm")
        abstract = text_at(root, ".//mods:abstract")
        local_identifier = text_at(root, ".//mods:identifier[@type='local']")
        location_url = text_at(root, ".//mods:location/mods:url")
        extent_start = safe_int(text_at(root, ".//mods:part/mods:extent/mods:start"))
        extent_end = safe_int(text_at(root, ".//mods:part/mods:extent/mods:end"))

        zip_entry_sizes = {normalize_zip_entry_name(name): info.file_size for name, info in infos.items()}
        zip_entry_info = {normalize_zip_entry_name(name): info for name, info in infos.items()}

        entries: list[SourcePackageEntry] = []
        for file_node in root.findall(".//mets:file", NS):
            mimetype = file_node.attrib.get("MIMETYPE", "")
            if mimetype and mimetype.lower() != "image/tiff":
                continue
            href = ""
            flocat = file_node.find("mets:FLocat", NS)
            if flocat is not None:
                href = flocat.attrib.get(f"{{{NS['xlink']}}}href", "")
            entry_name = normalize_zip_entry_name(href)
            info = zip_entry_info.get(entry_name)
            computed = ""
            checksum_match: bool | None = None
            mets_checksum = file_node.attrib.get("CHECKSUM", "").lower()
            if verify_checksums and info is not None:
                data = zf.read(info.filename)
                computed = sha1_bytes(data)
                checksum_match = computed.lower() == mets_checksum.lower() if mets_checksum else None
            entries.append(
                SourcePackageEntry(
                    entry_name=entry_name,
                    entry_suffix=suffix_for(entry_name),
                    page_number=page_number_from_entry_name(entry_name),
                    href=href,
                    mets_file_id=file_node.attrib.get("ID", ""),
                    mets_group_id=file_node.attrib.get("GROUPID", ""),
                    mimetype=mimetype,
                    size_bytes_mets=safe_int(file_node.attrib.get("SIZE")),
                    size_bytes_zip=zip_entry_sizes.get(entry_name),
                    checksum_sha1_mets=mets_checksum,
                    checksum_sha1_computed=computed,
                    checksum_match=checksum_match,
                    zip_crc=info.CRC if info is not None else None,
                    zip_compress_size=info.compress_size if info is not None else None,
                )
            )

        tiff_names = [normalize_zip_entry_name(n) for n in infos if suffix_for(n) in {".tif", ".tiff"}]
        suffix_counts = Counter(suffix_for(n) or "<none>" for n in infos)
        checksum_mismatch_count = sum(1 for e in entries if e.checksum_match is False)
        missing_zip_entry_count = sum(1 for e in entries if e.size_bytes_zip is None)
        duplicate_page_numbers = [
            page for page, count in Counter(e.page_number for e in entries if e.page_number is not None).items() if count > 1
        ]

        package_summary = {
            "source_package_path": str(metadata_zip_path),
            "source_package_file_name": metadata_zip_path.name,
            "metadata_xml_entry_name": metadata_name,
            "metadata_xml_present": True,
            "mets_label": mets_label,
            "mets_objid": mets_objid,
            "mets_type": mets_type,
            "record_status": record_status,
            "created_at": created_at,
            "title": title,
            "owner": owner,
            "type_of_resource": type_of_resource,
            "genre": genre,
            "date_captured": date_captured,
            "issuance": issuance,
            "language_code": language_code,
            "abstract": abstract,
            "local_identifier": local_identifier,
            "location_url": location_url,
            "extent_start": extent_start,
            "extent_end": extent_end,
            "agent_names": agent_names,
            "agent_notes": agent_notes,
            "zip_entry_count": len(infos),
            "zip_tiff_count": len(tiff_names),
            "mets_tiff_file_count": len(entries),
            "zip_total_uncompressed_bytes": sum(info.file_size for info in infos.values()),
            "zip_total_compressed_bytes": sum(info.compress_size for info in infos.values()),
            "suffix_counts": dict(sorted(suffix_counts.items())),
            "checksum_verification_enabled": verify_checksums,
            "checksum_mismatch_count": checksum_mismatch_count,
            "missing_zip_entry_count": missing_zip_entry_count,
            "duplicate_page_numbers": sorted(duplicate_page_numbers),
        }

        return {
            "package_summary": package_summary,
            "entries": [e.as_dict() for e in entries],
            "entries_by_page_number": {str(e.page_number): e.as_dict() for e in entries if e.page_number is not None},
        }


def load_page_records(crosswalk_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    payload = read_json(crosswalk_path)
    page_records = payload.get("page_records") or payload.get("pages") or []
    document_records = payload.get("document_records") or payload.get("documents") or []
    if not isinstance(page_records, list):
        raise ValueError("crosswalk page_records must be a list")
    if not isinstance(document_records, list):
        document_records = []
    return page_records, document_records, payload


def ensure_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    return [value]


def append_unique(value: Any, item: Any) -> list[Any]:
    values = ensure_list(value)
    if item not in values:
        values.append(item)
    return values


def infer_document_id_from_page_id(page_id: str) -> str:
    if "_p" in page_id:
        return page_id.rsplit("_p", 1)[0]
    return page_id


def build_page_source_package_block(
    page_record: dict[str, Any],
    entry: dict[str, Any] | None,
    package_summary: dict[str, Any],
) -> dict[str, Any]:
    page_id = page_record.get("page_id") or page_record.get("dc", {}).get("dc:identifier", "")
    page_number = page_number_from_page_id(page_id)
    matched = entry is not None
    return {
        "trace_net:source_package_id": package_summary.get("mets_objid") or package_summary.get("local_identifier") or "metadata.zip",
        "trace_net:source_package_label": package_summary.get("mets_label") or package_summary.get("title"),
        "trace_net:source_package_objid": package_summary.get("mets_objid"),
        "trace_net:source_package_type": package_summary.get("mets_type"),
        "trace_net:source_package_record_status": package_summary.get("record_status"),
        "trace_net:source_package_created_at": package_summary.get("created_at"),
        "trace_net:source_package_date_captured": package_summary.get("date_captured"),
        "trace_net:source_package_language_code": package_summary.get("language_code"),
        "trace_net:source_package_entry_name": entry.get("entry_name") if entry else "",
        "trace_net:source_package_entry_suffix": entry.get("entry_suffix") if entry else "",
        "trace_net:source_package_entry_href": entry.get("href") if entry else "",
        "trace_net:source_package_entry_size_bytes": entry.get("size_bytes_zip") if entry else None,
        "trace_net:source_package_entry_size_bytes_mets": entry.get("size_bytes_mets") if entry else None,
        "trace_net:source_package_entry_checksum_sha1": entry.get("checksum_sha1_mets") if entry else "",
        "trace_net:source_package_entry_checksum_sha1_computed": entry.get("checksum_sha1_computed") if entry else "",
        "trace_net:source_package_entry_checksum_match": entry.get("checksum_match") if entry else None,
        "trace_net:source_package_page_number": entry.get("page_number") if entry else page_number,
        "trace_net:source_package_match_method": "page_id_to_zero_padded_tiff" if matched else "not_matched",
        "trace_net:source_traceability_status": "matched_to_mets_file_entry" if matched else "missing_source_package_entry",
        "trace_net:metadata_xml_present": bool(package_summary.get("metadata_xml_present")),
        "trace_net:source_package_tiff_count": package_summary.get("zip_tiff_count"),
        "trace_net:source_package_file_count": package_summary.get("zip_entry_count"),
    }


def enrich_page_record(
    page_record: dict[str, Any],
    entry_by_page: dict[str, dict[str, Any]],
    package_summary: dict[str, Any],
) -> dict[str, Any]:
    record = copy.deepcopy(page_record)
    page_id = record.get("page_id") or record.get("dc", {}).get("dc:identifier", "")
    page_number = page_number_from_page_id(page_id)
    entry = entry_by_page.get(str(page_number)) if page_number is not None else None
    source_package = build_page_source_package_block(record, entry, package_summary)

    dc = record.setdefault("dc", {})
    trace_net = record.setdefault("trace_net", {})

    dc["dcterms:source"] = package_summary.get("mets_objid") or package_summary.get("local_identifier") or "metadata.zip"
    dc["dcterms:provenance"] = append_unique(
        dc.get("dcterms:provenance"),
        f"ResCarta METS source package {package_summary.get('mets_objid') or package_summary.get('source_package_file_name')}",
    )
    dc["dcterms:hasFormat"] = append_unique(dc.get("dcterms:hasFormat"), "image/tiff")
    if entry:
        dc["dcterms:identifier"] = append_unique(dc.get("dcterms:identifier"), entry.get("mets_file_id"))
        dc["dcterms:extent"] = (
            f"source TIFF size: {entry.get('size_bytes_zip')} bytes; " + str(dc.get("dcterms:extent", "")).strip()
        ).rstrip("; ")
    dc["dc:language"] = package_summary.get("language_code") or dc.get("dc:language", "")

    trace_net["trace_net:source_package"] = source_package
    trace_net["trace_net:source_package_traceability_status"] = source_package["trace_net:source_traceability_status"]
    trace_net["trace_net:source_package_entry_checksum_sha1"] = source_package[
        "trace_net:source_package_entry_checksum_sha1"
    ]
    trace_net["trace_net:source_package_entry_size_bytes"] = source_package[
        "trace_net:source_package_entry_size_bytes"
    ]
    trace_net["trace_net:source_package_page_number"] = source_package["trace_net:source_package_page_number"]
    trace_net.update(SAFETY_FLAGS)

    record["source_package"] = source_package
    return record


def enrich_document_record(document_record: dict[str, Any], package_summary: dict[str, Any]) -> dict[str, Any]:
    record = copy.deepcopy(document_record)
    dc = record.setdefault("dc", {})
    trace_net = record.setdefault("trace_net", {})

    dc.setdefault("dc:title", package_summary.get("title") or package_summary.get("mets_label"))
    dc["dc:identifier"] = package_summary.get("mets_objid") or package_summary.get("local_identifier") or dc.get("dc:identifier")
    dc["dc:type"] = append_unique(dc.get("dc:type"), package_summary.get("type_of_resource") or "text")
    dc["dc:format"] = append_unique(dc.get("dc:format"), "source_package/metadata_zip")
    dc["dc:source"] = package_summary.get("source_package_file_name")
    dc["dc:description"] = package_summary.get("abstract") or dc.get("dc:description", "")
    dc["dc:language"] = package_summary.get("language_code") or dc.get("dc:language", "")
    dc["dcterms:provenance"] = append_unique(
        dc.get("dcterms:provenance"),
        f"METS/MODS source package generated by {', '.join(package_summary.get('agent_names') or [])}".strip(),
    )
    dc["dcterms:extent"] = f"pages {package_summary.get('extent_start')}-{package_summary.get('extent_end')}; TIFF files: {package_summary.get('zip_tiff_count')}"

    trace_net["trace_net:source_package_summary"] = package_summary
    trace_net.update(SAFETY_FLAGS)
    record["source_package_summary"] = package_summary
    return record


def build_dublin_core_source_package_extension(
    *,
    dublin_core_refined_path: Path,
    metadata_zip_path: Path,
    output_dir: Path,
    verify_checksums: bool = True,
    require_page_count: int | None = None,
    min_page_records: int = 1,
    min_pages_with_source_package_entry: int = 1,
    require_metadata_xml: bool = True,
    write_quality: bool = False,
) -> dict[str, Any]:
    source_package = parse_source_package(metadata_zip_path, verify_checksums=verify_checksums)
    package_summary = source_package["package_summary"]
    entries_by_page = source_package["entries_by_page_number"]
    page_records, document_records, source_crosswalk = load_page_records(dublin_core_refined_path)

    enriched_pages = [enrich_page_record(r, entries_by_page, package_summary) for r in page_records]
    if document_records:
        enriched_docs = [enrich_document_record(r, package_summary) for r in document_records]
    else:
        enriched_docs = [
            enrich_document_record(
                {
                    "document_id": package_summary.get("mets_objid") or "source_package_document",
                    "dc": {},
                    "trace_net": {},
                },
                package_summary,
            )
        ]

    summary = summarize_extension(
        enriched_pages,
        enriched_docs,
        package_summary,
        source_crosswalk,
        require_page_count=require_page_count,
        min_page_records=min_page_records,
        min_pages_with_source_package_entry=min_pages_with_source_package_entry,
        require_metadata_xml=require_metadata_xml,
    )
    quality_status = QUALITY_PASS if summary["status"] == QUALITY_PASS else QUALITY_FAIL

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_dublin_core_source_package_extension_v1.json"
    pages_path = output_dir / "trace_net_dublin_core_source_package_pages_v1.jsonl"
    docs_path = output_dir / "trace_net_dublin_core_source_package_documents_v1.jsonl"
    entries_path = output_dir / "trace_net_dublin_core_source_package_entries_v1.jsonl"
    summary_path = output_dir / "trace_net_dublin_core_source_package_extension_v1_summary.json"
    quality_path = output_dir / "trace_net_dublin_core_source_package_extension_v1_quality.json"
    manifest_path = output_dir / "trace_net_dublin_core_source_package_extension_v1_manifest.json"
    md_path = output_dir / "trace_net_dublin_core_source_package_extension_v1.md"
    html_path = output_dir / "trace_net_dublin_core_source_package_extension_v1.html"

    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "generated_at": utc_now_iso(),
        "source_artifacts": {
            "dublin_core_refined": str(dublin_core_refined_path),
            "metadata_zip": str(metadata_zip_path),
        },
        "package_summary": package_summary,
        "page_records": enriched_pages,
        "document_records": enriched_docs,
        "source_package_entries": source_package["entries"],
        "summary": summary,
        "report_path": str(report_path),
        "pages_path": str(pages_path),
        "documents_path": str(docs_path),
        "entries_path": str(entries_path),
        "quality_path": str(quality_path),
    }

    write_json(report_path, payload)
    write_jsonl(pages_path, enriched_pages)
    write_jsonl(docs_path, enriched_docs)
    write_jsonl(entries_path, source_package["entries"])
    write_json(summary_path, summary)
    write_json(manifest_path, {
        "schema_version": SCHEMA_VERSION,
        "generated_at": payload["generated_at"],
        "report_path": str(report_path),
        "pages_path": str(pages_path),
        "documents_path": str(docs_path),
        "entries_path": str(entries_path),
        "quality_path": str(quality_path),
    })
    write_markdown(md_path, payload)
    write_html(html_path, payload)
    if write_quality:
        write_json(quality_path, quality_report(payload))
    else:
        write_json(quality_path, quality_report(payload))

    return payload


def summarize_extension(
    page_records: list[dict[str, Any]],
    document_records: list[dict[str, Any]],
    package_summary: dict[str, Any],
    source_crosswalk: dict[str, Any],
    *,
    require_page_count: int | None,
    min_page_records: int,
    min_pages_with_source_package_entry: int,
    require_metadata_xml: bool,
) -> dict[str, Any]:
    page_count = len(page_records)
    pages_with_entry = 0
    missing_entry = 0
    missing_entry_name = 0
    missing_checksum = 0
    checksum_mismatch = 0
    missing_size = 0
    source_truth_mutation_allowed = 0
    direct_answer_allowed = 0
    claim_proof_allowed = 0

    for record in page_records:
        source_pkg = record.get("source_package", {})
        if source_pkg.get("trace_net:source_traceability_status") == "matched_to_mets_file_entry":
            pages_with_entry += 1
        else:
            missing_entry += 1
        if not source_pkg.get("trace_net:source_package_entry_name"):
            missing_entry_name += 1
        if not source_pkg.get("trace_net:source_package_entry_checksum_sha1"):
            missing_checksum += 1
        if source_pkg.get("trace_net:source_package_entry_checksum_match") is False:
            checksum_mismatch += 1
        if source_pkg.get("trace_net:source_package_entry_size_bytes") in (None, ""):
            missing_size += 1
        trace_net = record.get("trace_net", {})
        if trace_net.get("source_truth_mutation_allowed") or trace_net.get("trace_net:source_truth_mutation_allowed"):
            source_truth_mutation_allowed += 1
        if trace_net.get("can_answer_directly") or trace_net.get("trace_net:can_answer_directly"):
            direct_answer_allowed += 1
        if trace_net.get("can_prove_claims") or trace_net.get("trace_net:can_prove_claims"):
            claim_proof_allowed += 1

    quality_checks = {
        "page_count_matches_required": True if require_page_count is None else page_count == require_page_count,
        "min_page_records_met": page_count >= min_page_records,
        "min_pages_with_source_package_entry_met": pages_with_entry >= min_pages_with_source_package_entry,
        "metadata_xml_present": bool(package_summary.get("metadata_xml_present")) if require_metadata_xml else True,
        "checksum_mismatch_count_zero": checksum_mismatch == 0,
        "source_truth_mutation_allowed_count_zero": source_truth_mutation_allowed == 0,
        "direct_answer_allowed_count_zero": direct_answer_allowed == 0,
        "claim_proof_allowed_count_zero": claim_proof_allowed == 0,
    }
    status = QUALITY_PASS if all(quality_checks.values()) else QUALITY_FAIL

    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "source_crosswalk_quality_status": source_crosswalk.get("quality_status", ""),
        "page_record_count": page_count,
        "document_record_count": len(document_records),
        "metadata_xml_present": bool(package_summary.get("metadata_xml_present")),
        "source_package_label": package_summary.get("mets_label"),
        "source_package_objid": package_summary.get("mets_objid"),
        "source_package_type": package_summary.get("mets_type"),
        "source_package_record_status": package_summary.get("record_status"),
        "source_package_created_at": package_summary.get("created_at"),
        "source_package_date_captured": package_summary.get("date_captured"),
        "source_package_language_code": package_summary.get("language_code"),
        "source_package_tiff_count": package_summary.get("zip_tiff_count", 0),
        "source_package_entry_count": package_summary.get("zip_entry_count", 0),
        "source_package_total_uncompressed_bytes": package_summary.get("zip_total_uncompressed_bytes", 0),
        "source_package_total_compressed_bytes": package_summary.get("zip_total_compressed_bytes", 0),
        "pages_with_source_package_entry_count": pages_with_entry,
        "missing_source_package_entry_count": missing_entry,
        "missing_source_package_entry_name_count": missing_entry_name,
        "missing_source_package_checksum_count": missing_checksum,
        "checksum_mismatch_count": checksum_mismatch,
        "missing_source_package_size_count": missing_size,
        "duplicate_source_package_page_number_count": len(package_summary.get("duplicate_page_numbers", [])),
        "direct_answer_allowed_count": direct_answer_allowed,
        "claim_proof_allowed_count": claim_proof_allowed,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed,
        "source_truth_mutations_performed": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "quality_checks": quality_checks,
    }


def quality_report(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary", {})
    checks = {
        "report_quality_status_pass": report.get("quality_status") == QUALITY_PASS,
        "summary_status_pass": summary.get("status") == QUALITY_PASS,
        "metadata_xml_present": bool(summary.get("metadata_xml_present")),
        "checksum_mismatch_count_zero": summary.get("checksum_mismatch_count", 0) == 0,
        "source_truth_mutation_allowed_count_zero": summary.get("source_truth_mutation_allowed_count", 0) == 0,
        "direct_answer_allowed_count_zero": summary.get("direct_answer_allowed_count", 0) == 0,
        "claim_proof_allowed_count_zero": summary.get("claim_proof_allowed_count", 0) == 0,
    }
    status = QUALITY_PASS if all(checks.values()) else QUALITY_FAIL
    return {
        "schema_version": SCHEMA_VERSION + "_quality",
        "status": status,
        "quality_status": status,
        "page_record_count": summary.get("page_record_count", 0),
        "document_record_count": summary.get("document_record_count", 0),
        "pages_with_source_package_entry_count": summary.get("pages_with_source_package_entry_count", 0),
        "missing_source_package_entry_count": summary.get("missing_source_package_entry_count", 0),
        "checksum_mismatch_count": summary.get("checksum_mismatch_count", 0),
        "source_truth_mutation_allowed_count": summary.get("source_truth_mutation_allowed_count", 0),
        "direct_answer_allowed_count": summary.get("direct_answer_allowed_count", 0),
        "claim_proof_allowed_count": summary.get("claim_proof_allowed_count", 0),
        "checks": checks,
    }


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    s = payload.get("summary", {})
    lines = [
        "# TRACE-Net Dublin Core Source Package Extension v1",
        "",
        f"**Status:** {payload.get('status')}",
        f"**Quality:** {payload.get('quality_status')}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "page_record_count",
        "document_record_count",
        "metadata_xml_present",
        "source_package_label",
        "source_package_objid",
        "source_package_tiff_count",
        "pages_with_source_package_entry_count",
        "missing_source_package_entry_count",
        "checksum_mismatch_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {s.get(key)}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_html(path: Path, payload: dict[str, Any]) -> None:
    s = payload.get("summary", {})
    items = "\n".join(f"<li><b>{html.escape(str(k))}</b>: {html.escape(str(v))}</li>" for k, v in s.items())
    body = f"""<!doctype html>
<html><head><meta charset='utf-8'><title>TRACE-Net Dublin Core Source Package Extension v1</title></head>
<body><h1>TRACE-Net Dublin Core Source Package Extension v1</h1>
<p><b>Status:</b> {html.escape(str(payload.get('status')))}<br>
<b>Quality:</b> {html.escape(str(payload.get('quality_status')))}</p>
<ul>{items}</ul></body></html>
"""
    path.write_text(body, encoding="utf-8")


def check_quality(
    *,
    report_path: Path,
    require_page_count: int | None = None,
    min_page_records: int = 1,
    min_pages_with_source_package_entry: int = 1,
    require_metadata_xml: bool = False,
    write_json_report: bool = False,
) -> dict[str, Any]:
    report = read_json(report_path)
    summary = report.get("summary", {})
    checks = dict(summary.get("quality_checks", {}))
    if require_page_count is not None:
        checks["page_count_matches_required_at_check"] = summary.get("page_record_count") == require_page_count
    checks["min_page_records_met_at_check"] = summary.get("page_record_count", 0) >= min_page_records
    checks["min_pages_with_source_package_entry_met_at_check"] = (
        summary.get("pages_with_source_package_entry_count", 0) >= min_pages_with_source_package_entry
    )
    if require_metadata_xml:
        checks["metadata_xml_present_at_check"] = bool(summary.get("metadata_xml_present"))
    checks["checksum_mismatch_count_zero_at_check"] = summary.get("checksum_mismatch_count", 0) == 0
    checks["source_truth_mutation_allowed_count_zero_at_check"] = summary.get("source_truth_mutation_allowed_count", 0) == 0
    checks["direct_answer_allowed_count_zero_at_check"] = summary.get("direct_answer_allowed_count", 0) == 0
    checks["claim_proof_allowed_count_zero_at_check"] = summary.get("claim_proof_allowed_count", 0) == 0
    status = QUALITY_PASS if all(checks.values()) else QUALITY_FAIL
    quality = {
        "schema_version": SCHEMA_VERSION + "_quality",
        "status": status,
        "quality_status": status,
        "page_record_count": summary.get("page_record_count", 0),
        "document_record_count": summary.get("document_record_count", 0),
        "pages_with_source_package_entry_count": summary.get("pages_with_source_package_entry_count", 0),
        "missing_source_package_entry_count": summary.get("missing_source_package_entry_count", 0),
        "checksum_mismatch_count": summary.get("checksum_mismatch_count", 0),
        "source_truth_mutation_allowed_count": summary.get("source_truth_mutation_allowed_count", 0),
        "direct_answer_allowed_count": summary.get("direct_answer_allowed_count", 0),
        "claim_proof_allowed_count": summary.get("claim_proof_allowed_count", 0),
        "checks": checks,
    }
    if write_json_report:
        quality_path = Path(report.get("quality_path") or report_path.with_name(report_path.stem + "_quality.json"))
        write_json(quality_path, quality)
    return quality


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Dublin Core Source Package Extension v1")
    parser.add_argument("--dublin-core-refined", required=True, type=Path)
    parser.add_argument("--metadata-zip", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--require-page-count", type=int, default=None)
    parser.add_argument("--min-page-records", type=int, default=1)
    parser.add_argument("--min-pages-with-source-package-entry", type=int, default=1)
    parser.add_argument("--no-verify-checksums", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    payload = build_dublin_core_source_package_extension(
        dublin_core_refined_path=args.dublin_core_refined,
        metadata_zip_path=args.metadata_zip,
        output_dir=args.output_dir,
        verify_checksums=not args.no_verify_checksums,
        require_page_count=args.require_page_count,
        min_page_records=args.min_page_records,
        min_pages_with_source_package_entry=args.min_pages_with_source_package_entry,
        write_quality=args.quality,
    )
    s = payload["summary"]
    print("TRACE-Net Dublin Core Source Package Extension v1")
    print(f" Status: {payload['status']}")
    print(f" Quality status: {payload['quality_status']}")
    for key in [
        "page_record_count",
        "document_record_count",
        "source_package_tiff_count",
        "pages_with_source_package_entry_count",
        "missing_source_package_entry_count",
        "checksum_mismatch_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {s.get(key)}")
    print(f" report_path: {payload['report_path']}")
    print(f" quality_path: {payload['quality_path']}")
    return 0 if payload["quality_status"] == QUALITY_PASS else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
