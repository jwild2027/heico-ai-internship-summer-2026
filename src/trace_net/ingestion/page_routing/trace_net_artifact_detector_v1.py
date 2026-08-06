from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, MutableMapping, Optional, Sequence, Tuple
import xml.etree.ElementTree as ET

from tiff.trace_net_artifact_detector_v1_quality import (
    PASS,
    FAIL,
    SCHEMA_VERSION,
    ArtifactDetectorQualityThresholds,
    evaluate_quality,
)

ARTIFACT_NAME = "TRACE-Net Artifact Detector v1"
REPORT_FILENAME = "trace_net_artifact_detector_v1.json"
QUALITY_FILENAME = "trace_net_artifact_detector_v1_quality.json"
ARTIFACT_CARDS_JSONL = "trace_net_artifact_detector_v1_artifact_cards.jsonl"
PAGE_CARDS_JSONL = "trace_net_artifact_detector_v1_page_artifact_cards.jsonl"
SOURCE_PAGE_CARDS_JSONL = "trace_net_artifact_detector_v1_source_page_cards.jsonl"
SUMMARY_FILENAME = "trace_net_artifact_detector_v1_summary.json"
MANIFEST_FILENAME = "trace_net_artifact_detector_v1_manifest.json"

KNOWN_CARD_ARRAYS = (
    "table_geometry_cards",
    "table_bbox_cards",
    "table_ocr_bbox_enrichment_cards",
    "table_image_cards",
    "table_image_resolver_cards",
    "table_crop_completeness_cards",
    "crop_completeness_cards",
    "recovery_cards",
    "review_cards",
    "review_tasks",
    "audit_cards",
    "parity_cards",
    "diagnostic_cards",
    "source_cards",
    "source_page_cards",
    "page_cards",
    "page_route_cards",
    "ocr_bbox_sidecar_cards",
    "ocr_source_cards",
    "document_cards",
    "community_cards",
    "retrieval_cards",
    "answer_cards",
)

PAGE_KEY_CANDIDATES = (
    "page_id",
    "source_page_id",
    "target_page_id",
    "resolved_page_id",
    "image_page_id",
    "ocr_page_id",
    "review_page_id",
)

TABLE_KEY_CANDIDATES = (
    "table_id",
    "source_table_id",
    "target_table_id",
)

SAFETY_COUNTER_KEYS = (
    "answer_permission_count",
    "can_answer_directly_count",
    "can_prove_claims_count",
    "source_truth_mutation_allowed_count",
    "source_truth_mutations_performed",
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
    "opensearch_write_attempt_count",
)

UNSAFE_COUNTER_KEYS = (
    "unsafe_artifact_card_count",
    "unsafe_source_card_count",
    "unsafe_review_task_count",
    "unsafe_review_card_count",
    "unsafe_geometry_card_count",
    "unsafe_recovery_card_count",
    "unsafe_crop_completeness_card_count",
    "unsafe_parity_card_count",
    "unsafe_diagnostic_card_count",
    "unsafe_route_card_count",
)


class ArtifactDetectorError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ArtifactDetectorError(f"JSON artifact is not an object: {path}")
    return payload


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True))
            f.write("\n")


def _first_mapping(*values: Any) -> Mapping[str, Any]:
    for value in values:
        if isinstance(value, Mapping):
            return value
    return {}


def _schema_version(payload: Mapping[str, Any]) -> Optional[str]:
    summary = _first_mapping(payload.get("summary"))
    return payload.get("schema_version") or summary.get("schema_version")


def _quality_status(payload: Mapping[str, Any]) -> Optional[str]:
    summary = _first_mapping(payload.get("summary"))
    return payload.get("quality_status") or summary.get("quality_status")


def _status(payload: Mapping[str, Any]) -> Optional[str]:
    summary = _first_mapping(payload.get("summary"))
    return payload.get("status") or summary.get("status")


def _artifact_key(path: Path, payload: Mapping[str, Any]) -> str:
    schema = _schema_version(payload)
    if schema:
        key = str(schema)
        key = re.sub(r"^trace_net_", "", key)
        key = re.sub(r"_v\d+$", "", key)
        return key
    parent = path.parent.name
    if parent and parent != ".":
        return parent
    return path.stem


def _category_for_artifact(artifact_key: str, schema_version: Optional[str], path: Path) -> str:
    haystack = " ".join([artifact_key or "", schema_version or "", str(path).lower()])
    if "table" in haystack:
        return "table"
    if any(token in haystack for token in ("visual", "figure", "diagram", "callout", "image", "ink")):
        return "image_visual"
    if any(token in haystack for token in ("ocr", "source", "ingest", "text", "document")):
        return "ocr_text"
    if "review" in haystack:
        return "human_review"
    if any(token in haystack for token in ("retrieval", "answer", "runtime")):
        return "retrieval_answer"
    return "general"


def _find_card_arrays(payload: Mapping[str, Any]) -> Dict[str, List[Mapping[str, Any]]]:
    arrays: Dict[str, List[Mapping[str, Any]]] = {}
    for key in KNOWN_CARD_ARRAYS:
        value = payload.get(key)
        if isinstance(value, list):
            cards = [item for item in value if isinstance(item, Mapping)]
            if cards:
                arrays[key] = cards
    # Also detect unknown top-level lists of cards if they carry page/table ids.
    for key, value in payload.items():
        if key in arrays or not isinstance(value, list):
            continue
        cards = [item for item in value if isinstance(item, Mapping)]
        if not cards:
            continue
        if any(_extract_page_ids_from_card(card) for card in cards):
            arrays[key] = cards
    return arrays


def _extract_page_ids_from_card(card: Mapping[str, Any]) -> List[str]:
    page_ids: List[str] = []
    for key in PAGE_KEY_CANDIDATES:
        value = card.get(key)
        if isinstance(value, str) and value.strip():
            page_ids.append(value.strip())
    # Common nested locations.
    for nested_key in ("page", "source_page", "target_page", "image", "resolved_image", "metadata"):
        nested = card.get(nested_key)
        if isinstance(nested, Mapping):
            for key in PAGE_KEY_CANDIDATES:
                value = nested.get(key)
                if isinstance(value, str) and value.strip():
                    page_ids.append(value.strip())
    return sorted(set(page_ids))


def _extract_table_ids_from_card(card: Mapping[str, Any]) -> List[str]:
    table_ids: List[str] = []
    for key in TABLE_KEY_CANDIDATES:
        value = card.get(key)
        if isinstance(value, str) and value.strip():
            table_ids.append(value.strip())
    return sorted(set(table_ids))


def _collect_safety_counters(payload: Mapping[str, Any]) -> Dict[str, int]:
    summary = _first_mapping(payload.get("summary"))
    counters: Dict[str, int] = {}
    for key in SAFETY_COUNTER_KEYS + UNSAFE_COUNTER_KEYS:
        counters[key] = _safe_int(payload.get(key, summary.get(key)))
    return counters


def _unsafe_from_counters(counters: Mapping[str, int]) -> bool:
    # Routing artifacts are allowed to report read-only OpenSearch writes from older loaders,
    # but this detector itself must not grant answer/source-truth authority.
    authority_keys = (
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "source_truth_mutations_performed",
    )
    unsafe_keys = UNSAFE_COUNTER_KEYS
    return any(_safe_int(counters.get(key)) > 0 for key in authority_keys + unsafe_keys)


def iter_json_files(roots: Sequence[Path], max_files: int) -> List[Path]:
    files: List[Path] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        if root.is_file() and root.suffix.lower() == ".json":
            candidates = [root]
        else:
            candidates = sorted(p for p in root.rglob("*.json") if p.is_file())
        for path in candidates:
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            files.append(path)
            if len(files) >= max_files:
                return files
    return files


def detect_artifact_card(path: Path, root_hint: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    try:
        payload = read_json(path)
    except Exception as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_key": path.stem,
            "artifact_path": str(path),
            "artifact_path_relative": str(path),
            "artifact_detection_status": "ARTIFACT_JSON_READ_FAILED",
            "artifact_detection_error": str(exc),
            "is_trace_net_artifact": False,
            "safe_for_routing": False,
            "quality_status": None,
            "status": None,
            "card_count": 0,
            "page_id_count": 0,
            "table_id_count": 0,
            "page_ids_sample": [],
            "table_ids_sample": [],
            "card_array_counts": {},
            "evidence_category": "unreadable",
            "unsafe_artifact_card": True,
        }

    schema = _schema_version(payload)
    quality = _quality_status(payload)
    status = _status(payload)
    key = _artifact_key(path, payload)
    card_arrays = _find_card_arrays(payload)
    card_array_counts = {array_key: len(cards) for array_key, cards in sorted(card_arrays.items())}
    card_count = sum(card_array_counts.values())

    page_ids: set[str] = set()
    table_ids: set[str] = set()
    for cards in card_arrays.values():
        for card in cards:
            page_ids.update(_extract_page_ids_from_card(card))
            table_ids.update(_extract_table_ids_from_card(card))

    counters = _collect_safety_counters(payload)
    unsafe = _unsafe_from_counters(counters)
    is_trace_net_artifact = bool(schema and str(schema).startswith("trace_net_")) or bool(card_arrays)
    safe_for_routing = is_trace_net_artifact and not unsafe and (quality in (PASS, None, ""))

    try:
        relative = str(path.relative_to(root_hint)) if root_hint and path.is_relative_to(root_hint) else str(path)
    except AttributeError:
        try:
            relative = str(path.relative_to(root_hint)) if root_hint else str(path)
        except Exception:
            relative = str(path)

    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_key": key,
        "artifact_path": str(path),
        "artifact_path_relative": relative,
        "artifact_detection_status": "TRACE_NET_ARTIFACT_DETECTED" if is_trace_net_artifact else "JSON_NOT_RECOGNIZED_AS_TRACE_NET_ARTIFACT",
        "is_trace_net_artifact": is_trace_net_artifact,
        "safe_for_routing": safe_for_routing,
        "artifact_schema_version": schema,
        "quality_status": quality,
        "status": status,
        "card_count": card_count,
        "page_id_count": len(page_ids),
        "table_id_count": len(table_ids),
        "page_ids_sample": sorted(page_ids)[:25],
        "table_ids_sample": sorted(table_ids)[:25],
        "card_array_counts": card_array_counts,
        "evidence_category": _category_for_artifact(key, schema, path),
        "safety_counters": counters,
        "unsafe_artifact_card": unsafe,
        "answer_permission_count": counters.get("answer_permission_count", 0),
        "can_answer_directly_count": counters.get("can_answer_directly_count", 0),
        "can_prove_claims_count": counters.get("can_prove_claims_count", 0),
        "source_truth_mutation_allowed_count": counters.get("source_truth_mutation_allowed_count", 0),
    }


def _xml_attr(element: ET.Element, local_name: str) -> Optional[str]:
    for key, value in element.attrib.items():
        if key == local_name or key.endswith("}" + local_name):
            return value
    return None


def _clean_file_href(href: Optional[str]) -> Optional[str]:
    if not href:
        return None
    value = href
    if value.startswith("file://./"):
        value = value[len("file://./") :]
    elif value.startswith("file://"):
        value = value[len("file://") :]
    return value.lstrip("./")


def parse_metadata_zip(metadata_zip: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if not metadata_zip.exists():
        raise ArtifactDetectorError(f"Metadata zip does not exist: {metadata_zip}")
    with zipfile.ZipFile(metadata_zip) as z:
        if "metadata.xml" not in z.namelist():
            raise ArtifactDetectorError(f"metadata.xml not found in {metadata_zip}")
        xml_bytes = z.read("metadata.xml")
        namelist = z.namelist()
    root = ET.fromstring(xml_bytes)
    ns = {
        "mets": "http://www.loc.gov/METS/",
        "mods": "http://www.loc.gov/mods/v3",
        "xlink": "http://www.w3.org/1999/xlink",
    }
    title_el = root.find(".//mods:title", ns)
    local_id_el = root.find(".//mods:identifier", ns)
    doc_meta = {
        "document_label": root.attrib.get("LABEL"),
        "document_objid": root.attrib.get("OBJID"),
        "document_type": root.attrib.get("TYPE"),
        "title": title_el.text.strip() if title_el is not None and title_el.text else None,
        "local_identifier": local_id_el.text.strip() if local_id_el is not None and local_id_el.text else None,
        "metadata_zip_path": str(metadata_zip),
        "zip_entry_count": len(namelist),
        "metadata_xml_sha256": hashlib.sha256(xml_bytes).hexdigest(),
    }

    files_by_id: Dict[str, Dict[str, Any]] = {}
    for file_el in root.findall(".//mets:file", ns):
        file_id = file_el.attrib.get("ID")
        flocat = file_el.find("mets:FLocat", ns)
        href = _clean_file_href(_xml_attr(flocat, "href") if flocat is not None else None)
        if not file_id:
            continue
        files_by_id[file_id] = {
            "file_id": file_id,
            "group_id": file_el.attrib.get("GROUPID"),
            "mimetype": file_el.attrib.get("MIMETYPE"),
            "size_bytes": _safe_int(file_el.attrib.get("SIZE")),
            "checksum": file_el.attrib.get("CHECKSUM"),
            "checksum_type": file_el.attrib.get("CHECKSUMTYPE"),
            "image_filename": href,
        }

    page_cards: List[Dict[str, Any]] = []
    for div in root.findall(".//mets:structMap//mets:div", ns):
        if div.attrib.get("TYPE") != "page":
            continue
        fptr = div.find("mets:fptr", ns)
        file_id = fptr.attrib.get("FILEID") if fptr is not None else None
        file_meta = files_by_id.get(file_id or "", {})
        order = _safe_int(div.attrib.get("ORDER"))
        page_label = div.attrib.get("LABEL") or (str(order) if order else None)
        image_filename = file_meta.get("image_filename")
        filename_stem = Path(str(image_filename)).stem if image_filename else None
        page_aliases = [alias for alias in [
            f"metadata_page_{order:06d}" if order else None,
            f"p{order:06d}" if order else None,
            filename_stem,
            image_filename,
            _xml_attr(div, "label"),
            page_label,
        ] if alias]
        page_cards.append({
            "schema_version": SCHEMA_VERSION,
            "source_page_id": f"metadata_page_{order:06d}" if order else f"metadata_page_unknown_{len(page_cards)+1}",
            "page_number": order,
            "page_label": page_label,
            "physical_page_label": _xml_attr(div, "label"),
            "file_id": file_id,
            "image_filename": image_filename,
            "mimetype": file_meta.get("mimetype"),
            "size_bytes": file_meta.get("size_bytes"),
            "checksum": file_meta.get("checksum"),
            "checksum_type": file_meta.get("checksum_type"),
            "page_aliases": sorted(set(str(a) for a in page_aliases if str(a).strip())),
            "metadata_zip_path": str(metadata_zip),
            "document_label": doc_meta.get("document_label"),
            "document_objid": doc_meta.get("document_objid"),
            "evidence_category": "source_metadata",
            "safe_for_routing": True,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
        })
    doc_meta["source_page_count"] = len(page_cards)
    return doc_meta, page_cards


def build_page_artifact_cards(
    artifact_cards: Sequence[Mapping[str, Any]],
    source_page_cards: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    page_to_artifacts: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for artifact in artifact_cards:
        for page_id in artifact.get("page_ids_sample") or []:
            if isinstance(page_id, str) and page_id:
                page_to_artifacts[page_id].append(artifact)

    cards: List[Dict[str, Any]] = []
    for page_id in sorted(page_to_artifacts):
        artifacts = page_to_artifacts[page_id]
        categories = Counter(str(a.get("evidence_category") or "general") for a in artifacts)
        safe_count = sum(1 for a in artifacts if a.get("safe_for_routing"))
        artifact_keys = sorted(str(a.get("artifact_key")) for a in artifacts if a.get("artifact_key"))
        cards.append({
            "schema_version": SCHEMA_VERSION,
            "page_id": page_id,
            "page_artifact_detection_status": "PAGE_ARTIFACT_EVIDENCE_FOUND",
            "artifact_count": len(artifacts),
            "safe_artifact_count": safe_count,
            "unsafe_artifact_count": len(artifacts) - safe_count,
            "artifact_keys": artifact_keys,
            "evidence_categories": sorted(categories),
            "evidence_category_counts": dict(sorted(categories.items())),
            "table_evidence_artifact_count": categories.get("table", 0),
            "image_visual_evidence_artifact_count": categories.get("image_visual", 0),
            "ocr_text_evidence_artifact_count": categories.get("ocr_text", 0),
            "human_review_evidence_artifact_count": categories.get("human_review", 0),
            "safe_for_routing": safe_count > 0,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
        })

    # Include metadata pages as source examples even when no TRACE-Net page_id has been joined yet.
    existing_ids = {card["page_id"] for card in cards}
    for source in source_page_cards:
        source_page_id = str(source.get("source_page_id") or "")
        if not source_page_id or source_page_id in existing_ids:
            continue
        cards.append({
            "schema_version": SCHEMA_VERSION,
            "page_id": source_page_id,
            "source_page_id": source_page_id,
            "page_number": source.get("page_number"),
            "image_filename": source.get("image_filename"),
            "page_aliases": source.get("page_aliases") or [],
            "page_artifact_detection_status": "SOURCE_METADATA_PAGE_ONLY",
            "artifact_count": 1,
            "safe_artifact_count": 1,
            "unsafe_artifact_count": 0,
            "artifact_keys": ["metadata_zip"],
            "evidence_categories": ["source_metadata"],
            "evidence_category_counts": {"source_metadata": 1},
            "table_evidence_artifact_count": 0,
            "image_visual_evidence_artifact_count": 0,
            "ocr_text_evidence_artifact_count": 0,
            "human_review_evidence_artifact_count": 0,
            "safe_for_routing": True,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
        })
    return sorted(cards, key=lambda c: (str(c.get("page_id") or "")))


def build_artifact_detector_report(
    artifact_roots: Sequence[Path],
    output_dir: Path,
    metadata_zip: Optional[Path] = None,
    max_json_files_scanned: int = 25000,
    thresholds: Optional[ArtifactDetectorQualityThresholds] = None,
    write_outputs: bool = True,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    roots = [Path(root) for root in artifact_roots]
    json_files = iter_json_files(roots, max_json_files_scanned)
    root_hint = roots[0] if roots else None

    artifact_cards: List[Dict[str, Any]] = []
    for path in json_files:
        card = detect_artifact_card(path, root_hint=root_hint)
        if card and card.get("is_trace_net_artifact"):
            artifact_cards.append(card)

    source_document_metadata: Dict[str, Any] = {}
    source_page_cards: List[Dict[str, Any]] = []
    if metadata_zip:
        source_document_metadata, source_page_cards = parse_metadata_zip(Path(metadata_zip))

    page_artifact_cards = build_page_artifact_cards(artifact_cards, source_page_cards)
    category_counts = Counter(str(card.get("evidence_category") or "general") for card in artifact_cards)
    quality_counts = Counter(str(card.get("quality_status") or "UNKNOWN") for card in artifact_cards)
    unsafe_artifact_card_count = sum(1 for card in artifact_cards if card.get("unsafe_artifact_card"))
    unsafe_safe_for_routing_artifact_card_count = sum(
        1 for card in artifact_cards
        if card.get("unsafe_artifact_card") and card.get("safe_for_routing")
    )
    safe_for_routing_answer_permission_count = sum(
        _safe_int(card.get("answer_permission_count"))
        for card in artifact_cards
        if card.get("safe_for_routing")
    )
    safe_for_routing_source_truth_mutation_allowed_count = sum(
        _safe_int(card.get("source_truth_mutation_allowed_count"))
        for card in artifact_cards
        if card.get("safe_for_routing")
    )

    answer_permission_count = sum(_safe_int(card.get("answer_permission_count")) for card in artifact_cards)
    can_answer_directly_count = sum(_safe_int(card.get("can_answer_directly_count")) for card in artifact_cards)
    can_prove_claims_count = sum(_safe_int(card.get("can_prove_claims_count")) for card in artifact_cards)
    source_truth_mutation_allowed_count = sum(_safe_int(card.get("source_truth_mutation_allowed_count")) for card in artifact_cards)

    summary: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "TRACE_NET_ARTIFACT_DETECTOR_BUILT",
        "artifact_root_paths": [str(root) for root in roots],
        "metadata_zip_path": str(metadata_zip) if metadata_zip else None,
        "json_file_scanned_count": len(json_files),
        "artifact_card_count": len(artifact_cards),
        "safe_for_routing_artifact_card_count": sum(1 for card in artifact_cards if card.get("safe_for_routing")),
        "unsafe_artifact_card_count": unsafe_artifact_card_count,
        "unsafe_safe_for_routing_artifact_card_count": unsafe_safe_for_routing_artifact_card_count,
        "safe_for_routing_answer_permission_count": safe_for_routing_answer_permission_count,
        "safe_for_routing_source_truth_mutation_allowed_count": safe_for_routing_source_truth_mutation_allowed_count,
        "page_artifact_card_count": len(page_artifact_cards),
        "source_page_card_count": len(source_page_cards),
        "metadata_document_label": source_document_metadata.get("document_label"),
        "metadata_document_objid": source_document_metadata.get("document_objid"),
        "evidence_category_counts": dict(sorted(category_counts.items())),
        "artifact_quality_status_counts": dict(sorted(quality_counts.items())),
        "table_evidence_page_count": sum(1 for card in page_artifact_cards if _safe_int(card.get("table_evidence_artifact_count")) > 0),
        "image_visual_evidence_page_count": sum(1 for card in page_artifact_cards if _safe_int(card.get("image_visual_evidence_artifact_count")) > 0),
        "ocr_text_evidence_page_count": sum(1 for card in page_artifact_cards if _safe_int(card.get("ocr_text_evidence_artifact_count")) > 0),
        "metadata_source_only_page_count": sum(1 for card in page_artifact_cards if card.get("page_artifact_detection_status") == "SOURCE_METADATA_PAGE_ONLY"),
        "answer_permission_count": answer_permission_count,
        "can_answer_directly_count": can_answer_directly_count,
        "can_prove_claims_count": can_prove_claims_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "source_truth_mutations_performed": 0,
    }

    report: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_name": ARTIFACT_NAME,
        "status": "TRACE_NET_ARTIFACT_DETECTOR_BUILT",
        "created_at_utc": _utc_now(),
        "quality_status": "UNKNOWN",
        "summary": summary,
        "source_document_metadata": source_document_metadata,
        "artifact_cards": artifact_cards,
        "page_artifact_cards": page_artifact_cards,
        "source_page_cards": source_page_cards,
    }
    quality = evaluate_quality(report, thresholds)
    report["quality_status"] = quality["quality_status"]
    report["summary"]["quality_status"] = quality["quality_status"]
    report["summary"]["quality_fail_reasons"] = quality.get("quality_fail_reasons", [])
    report["summary"]["checks"] = quality.get("checks", {})

    if write_outputs:
        report_path = output_dir / REPORT_FILENAME
        quality_path = output_dir / QUALITY_FILENAME
        summary_path = output_dir / SUMMARY_FILENAME
        manifest_path = output_dir / MANIFEST_FILENAME
        artifact_cards_path = output_dir / ARTIFACT_CARDS_JSONL
        page_cards_path = output_dir / PAGE_CARDS_JSONL
        source_page_cards_path = output_dir / SOURCE_PAGE_CARDS_JSONL

        write_json(report_path, report)
        write_json(quality_path, quality)
        write_json(summary_path, report["summary"])
        write_jsonl(artifact_cards_path, artifact_cards)
        write_jsonl(page_cards_path, page_artifact_cards)
        write_jsonl(source_page_cards_path, source_page_cards)
        write_json(manifest_path, {
            "schema_version": SCHEMA_VERSION,
            "report_path": str(report_path),
            "quality_path": str(quality_path),
            "summary_path": str(summary_path),
            "artifact_cards_jsonl_path": str(artifact_cards_path),
            "page_artifact_cards_jsonl_path": str(page_cards_path),
            "source_page_cards_jsonl_path": str(source_page_cards_path),
            "quality_status": quality["quality_status"],
        })
        report["report_path"] = str(report_path)
        report["quality_path"] = str(quality_path)
    return report


def thresholds_from_args(args: argparse.Namespace) -> ArtifactDetectorQualityThresholds:
    return ArtifactDetectorQualityThresholds(
        min_artifact_cards=args.min_artifact_cards,
        min_page_artifact_cards=args.min_page_artifact_cards,
        min_source_page_cards=args.min_source_page_cards,
        max_unsafe_artifact_cards=args.max_unsafe_artifact_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_metadata_pages=args.require_metadata_pages,
        require_no_answer_permission=args.require_no_answer_permission,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=ARTIFACT_NAME)
    parser.add_argument("--artifact-root", action="append", default=[], help="TRACE-Net artifact root or JSON file to scan. May be repeated.")
    parser.add_argument("--metadata-zip", type=Path, default=None, help="Optional ResCarta/METS metadata zip for source-page examples.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-json-files-scanned", type=int, default=25000)
    parser.add_argument("--min-artifact-cards", type=int, default=1)
    parser.add_argument("--min-page-artifact-cards", type=int, default=1)
    parser.add_argument("--min-source-page-cards", type=int, default=0)
    parser.add_argument("--max-unsafe-artifact-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-metadata-pages", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def print_report(report: Mapping[str, Any]) -> None:
    summary = report.get("summary", {})
    print(ARTIFACT_NAME)
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in (
        "json_file_scanned_count",
        "artifact_card_count",
        "safe_for_routing_artifact_card_count",
        "page_artifact_card_count",
        "source_page_card_count",
        "metadata_source_only_page_count",
        "table_evidence_page_count",
        "image_visual_evidence_page_count",
        "ocr_text_evidence_page_count",
        "unsafe_artifact_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    if report.get("report_path"):
        print(f" report_path: {report.get('report_path')}")
    if report.get("quality_path"):
        print(f" quality_path: {report.get('quality_path')}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    roots = [Path(root) for root in args.artifact_root] if args.artifact_root else [Path("local_data/organization/trace_net")]
    report = build_artifact_detector_report(
        artifact_roots=roots,
        metadata_zip=args.metadata_zip,
        output_dir=args.output_dir,
        max_json_files_scanned=args.max_json_files_scanned,
        thresholds=thresholds_from_args(args),
    )
    print_report(report)
    return 0 if report.get("quality_status") == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
