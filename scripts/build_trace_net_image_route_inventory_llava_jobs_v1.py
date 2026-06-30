#!/usr/bin/env python3
"""Build TRACE-Net image-route inventory records and LLaVA job manifests.

Patch A for the image/visual route. This module is artifact-only and dry-run safe:
it reads route/OCR/source metadata artifacts, inventories image/diagram pages, checks
whether LLaVA visual summaries already exist, and writes job records for missing
summaries. It does not call LLaVA and does not write to Postgres, Qdrant, or
OpenSearch.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, MutableMapping, Optional, Sequence, Tuple

MODULE_NAME = "trace_net_image_route_inventory_llava_jobs_v1"
STATUS_BUILT = "TRACE_NET_IMAGE_ROUTE_INVENTORY_LLAVA_JOBS_BUILT"
DEFAULT_OUTPUT_DIR = "local_data/organization/trace_net/image_route_inventory_llava_jobs_v1"
DEFAULT_LLAVA_OUTPUT_ROOT = "local_data/organization/trace_net/llava_visual_summaries_v1"

IMAGE_ROUTE_EXACT_LABELS = {
    "image_visual",
    "image_or_diagram",
    "image",
    "visual",
    "diagram",
    "figure",
    "visual_diagram",
    "image-route",
    "image_route",
}

IMAGE_ROUTE_HINTS = ("image", "visual", "diagram", "figure", "callout")
NON_IMAGE_ROUTE_HINTS = ("table", "normal_text", "blank", "text_only")

PAGE_ID_KEYS = (
    "page_id",
    "trace_page_id",
    "source_page_id",
    "page_key",
    "id",
)
PAGE_NUMBER_KEYS = (
    "page_number",
    "page_num",
    "page_index",
    "page",
    "source_page_number",
    "physical_page_number",
)
ROUTE_KEYS = (
    "route_label",
    "primary_route",
    "route",
    "route_type",
    "assigned_route",
    "page_route",
    "processor_route",
    "selected_route",
    "classification_route",
)
SOURCE_MEMBER_KEYS = (
    "source_member",
    "tiff_member",
    "tif_member",
    "archive_member",
    "member_name",
    "image_member",
    "page_member",
    "source_file",
    "source_path",
    "tiff_path",
    "document_member",
    "source_package_member",
)
TEXT_KEYS = (
    "ocr_text",
    "text",
    "page_text",
    "ocr_excerpt",
    "ocr_preview",
    "raw_text",
    "content",
    "recognized_text",
    "plain_text",
)
SUMMARY_KEYS = (
    "visual_summary",
    "llava_summary",
    "image_visual_summary",
    "diagram_summary",
    "summary",
    "caption",
)
QUALITY_KEYS = (
    "quality_status",
    "source_quality_status",
    "route_quality_status",
    "status_quality",
)

FIGURE_PATTERN = re.compile(r"\b(?:FIG(?:URE)?\.?|ILLUS(?:TRATION)?\.?)\s*[-:#]?\s*([A-Z0-9]+(?:[-–][A-Z0-9]+)?)\b", re.IGNORECASE)
ITEM_PATTERN = re.compile(r"\b(?:ITEM|CALLOUT|INDEX\s+NO\.?|FIG(?:URE)?\.?\s+ITEM)\s*[-:#]?\s*([0-9A-Z]+)\b", re.IGNORECASE)
PART_PATTERN = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")


@dataclass(frozen=True)
class InputArtifact:
    path: Optional[Path]
    exists: bool
    quality_status: str
    status: str


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def normalize_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def first_present(record: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return None


def coerce_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    match = re.search(r"\d+", text)
    if match:
        try:
            return int(match.group(0))
        except ValueError:
            return None
    return None


def iter_dicts(value: Any) -> Iterator[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from iter_dicts(child)
    elif isinstance(value, list):
        for item in value:
            yield from iter_dicts(item)


def lower_key_map(record: Mapping[str, Any]) -> Dict[str, Any]:
    return {str(k).lower(): v for k, v in record.items()}


def find_first_quality_status(payload: Any) -> str:
    if isinstance(payload, Mapping):
        for key in QUALITY_KEYS:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().upper()
        summary = payload.get("summary")
        if isinstance(summary, Mapping):
            for key in QUALITY_KEYS:
                value = summary.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip().upper()
    for record in iter_dicts(payload):
        for key in QUALITY_KEYS:
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().upper()
    return "UNKNOWN"


def find_first_status(payload: Any) -> str:
    if isinstance(payload, Mapping):
        value = payload.get("status")
        if isinstance(value, str) and value.strip():
            return value.strip()
    for record in iter_dicts(payload):
        value = record.get("status")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "UNKNOWN"


def load_optional_json(path_text: Optional[str]) -> Tuple[Optional[Any], InputArtifact]:
    if not path_text:
        return None, InputArtifact(path=None, exists=False, quality_status="MISSING_OPTIONAL", status="MISSING_OPTIONAL")
    path = Path(path_text)
    if not path.exists():
        return None, InputArtifact(path=path, exists=False, quality_status="MISSING_OPTIONAL", status="MISSING_OPTIONAL")
    payload = read_json(path)
    return payload, InputArtifact(path=path, exists=True, quality_status=find_first_quality_status(payload), status=find_first_status(payload))


def load_required_json(path_text: str) -> Tuple[Any, InputArtifact]:
    path = Path(path_text)
    if not path.exists():
        raise FileNotFoundError(f"Required input artifact not found: {path}")
    payload = read_json(path)
    return payload, InputArtifact(path=path, exists=True, quality_status=find_first_quality_status(payload), status=find_first_status(payload))


def discover_source_package_members(path_text: Optional[str]) -> Tuple[set[str], Dict[str, Any]]:
    if not path_text:
        return set(), {"exists": False, "member_count": 0, "tiff_member_count": 0}
    path = Path(path_text)
    if not path.exists():
        return set(), {"path": str(path), "exists": False, "member_count": 0, "tiff_member_count": 0}
    members: set[str] = set()
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
        tiff_names = [name for name in names if name.lower().endswith((".tif", ".tiff"))]
        members.update(names)
        members.update(Path(name).name for name in names)
        return members, {
            "path": str(path),
            "exists": True,
            "type": "zip",
            "member_count": len(names),
            "tiff_member_count": len(tiff_names),
        }
    if path.is_dir():
        files = [p for p in path.rglob("*") if p.is_file()]
        members.update(str(p.relative_to(path)).replace("\\", "/") for p in files)
        members.update(p.name for p in files)
        tiff_files = [p for p in files if p.suffix.lower() in {".tif", ".tiff"}]
        return members, {
            "path": str(path),
            "exists": True,
            "type": "directory",
            "member_count": len(files),
            "tiff_member_count": len(tiff_files),
        }
    return set(), {"path": str(path), "exists": True, "type": "unsupported", "member_count": 0, "tiff_member_count": 0}


def normalize_route_label(raw: Any) -> str:
    text = normalize_string(raw).lower().replace(" ", "_").replace("-", "_")
    text = text.strip("._/")
    return text


def infer_route_label(record: Mapping[str, Any]) -> str:
    lower = lower_key_map(record)
    for key in ROUTE_KEYS:
        if key in lower:
            label = normalize_route_label(lower[key])
            if label:
                return label
    for key, value in lower.items():
        if key.endswith("route") or "route" in key or key in {"label", "class", "classification"}:
            label = normalize_route_label(value)
            if label:
                return label
    return ""


def is_image_route_label(route_label: str) -> bool:
    label = normalize_route_label(route_label)
    if not label:
        return False
    if label in IMAGE_ROUTE_EXACT_LABELS:
        return True
    if any(non_image in label for non_image in NON_IMAGE_ROUTE_HINTS):
        return False
    return any(hint in label for hint in IMAGE_ROUTE_HINTS)


def likely_page_record(record: Mapping[str, Any]) -> bool:
    lower = lower_key_map(record)
    has_page = any(key in lower for key in PAGE_ID_KEYS) or any(key in lower for key in PAGE_NUMBER_KEYS)
    return has_page


def extract_page_id(record: Mapping[str, Any]) -> str:
    lower = lower_key_map(record)
    value = first_present(lower, PAGE_ID_KEYS)
    if value is None:
        return ""
    return normalize_string(value)


def extract_page_number(record: Mapping[str, Any]) -> Optional[int]:
    lower = lower_key_map(record)
    value = first_present(lower, PAGE_NUMBER_KEYS)
    page_number = coerce_int(value)
    if page_number is not None:
        return page_number
    page_id = extract_page_id(record)
    match = re.search(r"p0*([0-9]{1,6})\b", page_id)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def extract_source_member(record: Mapping[str, Any]) -> str:
    lower = lower_key_map(record)
    value = first_present(lower, SOURCE_MEMBER_KEYS)
    return normalize_string(value)


def extract_text(record: Mapping[str, Any]) -> str:
    lower = lower_key_map(record)
    for key in TEXT_KEYS:
        value = lower.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key, value in lower.items():
        if ("ocr" in key or "text" in key or "content" in key) and isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def compact_preview(text: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def extract_route_records(payload: Any) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    seen: set[Tuple[str, Optional[int], str]] = set()
    for raw in iter_dicts(payload):
        if not likely_page_record(raw):
            continue
        route_label = infer_route_label(raw)
        if not is_image_route_label(route_label):
            continue
        page_id = extract_page_id(raw)
        page_number = extract_page_number(raw)
        source_member = extract_source_member(raw)
        key = (page_id, page_number, route_label)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "page_id": page_id,
                "page_number": page_number,
                "route_label": route_label,
                "source_member": source_member,
                "raw_keys": sorted(str(k) for k in raw.keys()),
                "route_record": dict(raw),
            }
        )
    records.sort(key=lambda item: ((item.get("page_number") is None), item.get("page_number") or 10**9, item.get("page_id") or ""))
    return records


def extract_ocr_records(payload: Optional[Any], max_chars: int) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    if payload is None:
        return index
    for raw in iter_dicts(payload):
        if not likely_page_record(raw):
            continue
        text = extract_text(raw)
        source_member = extract_source_member(raw)
        page_id = extract_page_id(raw)
        page_number = extract_page_number(raw)
        if not (text or source_member or page_id or page_number is not None):
            continue
        record = {
            "page_id": page_id,
            "page_number": page_number,
            "source_member": source_member,
            "ocr_preview": compact_preview(text, max_chars),
            "ocr_text_available": bool(text),
        }
        for key in page_lookup_keys(page_id, page_number):
            index.setdefault(key, record)
    return index


def extract_existing_summary_index(payload: Optional[Any]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    if payload is None:
        return index
    for raw in iter_dicts(payload):
        if not likely_page_record(raw):
            continue
        lower = lower_key_map(raw)
        has_summary_key = any(key in lower for key in SUMMARY_KEYS) or any("llava" in key for key in lower)
        summary_text = ""
        for key in SUMMARY_KEYS:
            value = lower.get(key)
            if isinstance(value, str) and value.strip():
                summary_text = value.strip()
                break
        if not (has_summary_key or summary_text):
            continue
        page_id = extract_page_id(raw)
        page_number = extract_page_number(raw)
        if not (page_id or page_number is not None):
            continue
        summary = {
            "page_id": page_id,
            "page_number": page_number,
            "summary_present": bool(summary_text or has_summary_key),
            "summary_preview": compact_preview(summary_text, 240),
        }
        for key in page_lookup_keys(page_id, page_number):
            index.setdefault(key, summary)
    return index


def page_lookup_keys(page_id: str, page_number: Optional[int]) -> List[str]:
    keys: List[str] = []
    if page_id:
        keys.append(f"id:{page_id}")
    if page_number is not None:
        keys.append(f"num:{page_number}")
    return keys


def lookup_page(index: Mapping[str, Dict[str, Any]], page_id: str, page_number: Optional[int]) -> Optional[Dict[str, Any]]:
    for key in page_lookup_keys(page_id, page_number):
        if key in index:
            return index[key]
    return None


def derive_source_member(page_number: Optional[int], source_members: set[str]) -> str:
    if page_number is None:
        return ""
    candidates = [
        f"{page_number:08d}.tif",
        f"{page_number:08d}.tiff",
        f"{page_number}.tif",
        f"{page_number}.tiff",
    ]
    for candidate in candidates:
        if candidate in source_members:
            return candidate
    return candidates[0] if source_members else ""


def source_member_present(member: str, source_members: set[str]) -> bool:
    if not member or not source_members:
        return False
    normalized = member.replace("\\", "/")
    basename = Path(normalized).name
    return normalized in source_members or basename in source_members


def infer_figure_candidates(text: str, route_record: Mapping[str, Any]) -> List[Dict[str, str]]:
    values: List[Dict[str, str]] = []
    seen: set[Tuple[str, str]] = set()

    combined = text or ""
    for key, value in route_record.items():
        key_text = str(key).lower()
        if "figure" in key_text or "fig" == key_text or "item" in key_text or "callout" in key_text:
            combined += f" {value}"

    for match in FIGURE_PATTERN.finditer(combined):
        key = ("figure", match.group(1).upper())
        if key not in seen:
            seen.add(key)
            values.append({"candidate_type": "figure", "value": match.group(1).upper(), "source": "ocr_or_route_regex"})
    for match in ITEM_PATTERN.finditer(combined):
        key = ("item", match.group(1).upper())
        if key not in seen:
            seen.add(key)
            values.append({"candidate_type": "item", "value": match.group(1).upper(), "source": "ocr_or_route_regex"})
    for match in PART_PATTERN.finditer(combined):
        key = ("part_number", match.group(0))
        if key not in seen:
            seen.add(key)
            values.append({"candidate_type": "visible_part_number", "value": match.group(0), "source": "ocr_regex"})
    return values[:20]


def build_llava_prompt(page_id: str, page_number: Optional[int], ocr_preview: str, figure_candidates: List[Dict[str, str]]) -> str:
    seed = {
        "page_id": page_id,
        "page_number": page_number,
        "figure_candidates_from_ocr": figure_candidates,
        "ocr_preview_for_alignment_only": ocr_preview,
        "required_output_schema": {
            "page_id": page_id,
            "figure_candidates": [],
            "callout_candidates": [],
            "visible_text_candidates": [],
            "diagram_type": "",
            "visual_summary": "",
            "uncertainties": [],
        },
    }
    return (
        "You are TRACE-Net's local visual/page understanding helper. "
        "Inspect only the supplied page image. Return structured JSON only. "
        "Do not identify parts, applicability, effectivity, substitutions, or interchangeability as proven. "
        "List visual observations, callouts, visible text candidates, diagram type, and uncertainties. "
        "OCR/table/figure-item evidence will be used separately as source truth. "
        f"Seed context: {json.dumps(seed, sort_keys=True)}"
    )


def bool_count(records: Iterable[Mapping[str, Any]], key: str) -> int:
    return sum(1 for record in records if bool(record.get(key)))


def unsafe_count(records: Iterable[Mapping[str, Any]]) -> int:
    unsafe_keys = ("unsafe", "unsafe_record", "route_contract_violation", "blocked_dispatch_leak")
    total = 0
    for record in records:
        if any(bool(record.get(key)) for key in unsafe_keys):
            total += 1
    return total


def evaluate_quality(
    records: List[Dict[str, Any]],
    jobs: List[Dict[str, Any]],
    route_artifact: InputArtifact,
    ocr_artifact: InputArtifact,
) -> Tuple[str, List[Dict[str, Any]]]:
    checks: List[Dict[str, Any]] = []

    def add(name: str, passed: bool, observed: Any, expected: str, severity: str = "error") -> None:
        checks.append({"name": name, "passed": bool(passed), "observed": observed, "expected": expected, "severity": severity})

    route_quality_ok = route_artifact.quality_status in {"PASS", "UNKNOWN"}
    ocr_quality_ok = ocr_artifact.quality_status in {"PASS", "UNKNOWN", "MISSING_OPTIONAL"}
    add("source_route_artifact_quality_pass_if_available", route_quality_ok, route_artifact.quality_status, "PASS or UNKNOWN")
    add("ocr_scan_pack_quality_pass_if_available", ocr_quality_ok, ocr_artifact.quality_status, "PASS/UNKNOWN/MISSING_OPTIONAL")
    add("image_route_record_count_min_1", len(records) >= 1, len(records), ">= 1")
    add("llava_job_count_min_1", len(jobs) >= 1, len(jobs), ">= 1")
    add("source_trace_ready_count_min_1", bool_count(records, "source_trace_ready") >= 1, bool_count(records, "source_trace_ready"), ">= 1")
    add("no_human_review_required", bool_count(records, "human_review_required") == 0, bool_count(records, "human_review_required"), "0")
    add("unsafe_record_count_zero", unsafe_count(records) == 0, unsafe_count(records), "0")
    add("answer_permission_count_zero", bool_count(records, "answer_permission") == 0, bool_count(records, "answer_permission"), "0")
    add("source_truth_mutation_allowed_count_zero", bool_count(records, "source_truth_mutation_allowed") == 0, bool_count(records, "source_truth_mutation_allowed"), "0")
    add("write_attempt_count_zero", sum(int(record.get("write_attempt_count") or 0) for record in records) == 0, sum(int(record.get("write_attempt_count") or 0) for record in records), "0")
    quality_status = "PASS" if all(check["passed"] or check.get("severity") == "warning" for check in checks) else "FAIL"
    return quality_status, checks


def build_inventory(args: argparse.Namespace) -> Dict[str, Any]:
    route_payload, route_artifact = load_required_json(args.route_validator_runner)
    ocr_payload, ocr_artifact = load_optional_json(args.ocr_route_scan_pack)
    summary_payload, summary_artifact = load_optional_json(args.image_visual_summary)
    source_members, source_package_info = discover_source_package_members(args.source_package_metadata_zip)

    route_records = extract_route_records(route_payload)
    ocr_index = extract_ocr_records(ocr_payload, args.max_ocr_preview_chars)
    summary_index = extract_existing_summary_index(summary_payload)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    llava_output_root = Path(args.llava_output_root)

    records: List[Dict[str, Any]] = []
    jobs: List[Dict[str, Any]] = []

    for idx, route in enumerate(route_records, start=1):
        page_id = route.get("page_id") or f"image_route_page_{idx:04d}"
        page_number = route.get("page_number")
        ocr = lookup_page(ocr_index, page_id, page_number) or {}
        existing_summary = lookup_page(summary_index, page_id, page_number)

        source_member = normalize_string(route.get("source_member") or ocr.get("source_member"))
        if not source_member:
            source_member = derive_source_member(page_number, source_members)
        member_confirmed = source_member_present(source_member, source_members)
        ocr_preview = normalize_string(ocr.get("ocr_preview"))
        figure_candidates = infer_figure_candidates(ocr_preview, route.get("route_record") or {})
        llava_status = "existing" if existing_summary and existing_summary.get("summary_present") else "missing"
        output_target = str((llava_output_root / f"{page_id}_llava_visual_summary_v1.json").as_posix())
        recommended_prompt = build_llava_prompt(page_id, page_number, ocr_preview, figure_candidates)
        source_trace_fields = {
            "page_id": page_id,
            "page_number": page_number,
            "source_member": source_member,
            "source_package_member_confirmed": member_confirmed,
            "route_artifact_path": str(Path(args.route_validator_runner)),
            "ocr_scan_pack_path": str(Path(args.ocr_route_scan_pack)) if args.ocr_route_scan_pack else "",
            "source_package_metadata_zip": str(Path(args.source_package_metadata_zip)) if args.source_package_metadata_zip else "",
        }
        source_trace_ready = bool(page_id and (source_member or page_number is not None))

        record = {
            "record_id": f"image_route_inventory_{idx:04d}",
            "page_id": page_id,
            "page_number": page_number,
            "source_member": source_member,
            "tiff_member": source_member if source_member.lower().endswith((".tif", ".tiff")) else "",
            "route_label": route.get("route_label") or "image_visual",
            "ocr_excerpt_preview": ocr_preview,
            "ocr_text_available": bool(ocr.get("ocr_text_available")),
            "figure_candidates": figure_candidates,
            "source_trace_ready": source_trace_ready,
            "source_trace_fields": source_trace_fields,
            "llava_status": llava_status,
            "existing_llava_summary_preview": (existing_summary or {}).get("summary_preview", "") if existing_summary else "",
            "recommended_llava_prompt": recommended_prompt,
            "llava_output_target_path": output_target,
            "human_review_required": False,
            "unsafe": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "opensearch_upload_attempt": False,
            "write_attempt_count": 0,
            "authority_note": "LLaVA observations are visual guidance only; OCR/table/figure-item evidence must prove final facts.",
        }
        records.append(record)
        if llava_status == "missing":
            jobs.append(
                {
                    "job_id": f"llava_visual_summary_job_{idx:04d}",
                    "page_id": page_id,
                    "page_number": page_number,
                    "source_member": source_member,
                    "tiff_member": record["tiff_member"],
                    "route_label": record["route_label"],
                    "ocr_excerpt_preview": ocr_preview,
                    "figure_candidates": figure_candidates,
                    "source_trace_fields": source_trace_fields,
                    "source_trace_ready": source_trace_ready,
                    "llava_status": llava_status,
                    "recommended_llava_prompt": recommended_prompt,
                    "llava_output_target_path": output_target,
                    "answer_permission": False,
                    "source_truth_mutation_allowed": False,
                    "write_attempt_count": 0,
                }
            )

    quality_status, checks = evaluate_quality(records, jobs, route_artifact, ocr_artifact)

    summary = {
        "image_route_record_count": len(records),
        "llava_job_count": len(jobs),
        "existing_llava_summary_count": sum(1 for record in records if record.get("llava_status") == "existing"),
        "missing_llava_summary_count": sum(1 for record in records if record.get("llava_status") == "missing"),
        "source_trace_ready_count": bool_count(records, "source_trace_ready"),
        "ocr_preview_available_count": bool_count(records, "ocr_text_available"),
        "figure_candidate_record_count": sum(1 for record in records if record.get("figure_candidates")),
        "human_review_required_count": bool_count(records, "human_review_required"),
        "unsafe_record_count": unsafe_count(records),
        "answer_permission_count": bool_count(records, "answer_permission"),
        "source_truth_mutation_allowed_count": bool_count(records, "source_truth_mutation_allowed"),
        "postgres_write_attempt_count": bool_count(records, "postgres_write_attempt"),
        "qdrant_write_attempt_count": bool_count(records, "qdrant_write_attempt"),
        "opensearch_write_attempt_count": bool_count(records, "opensearch_write_attempt"),
        "opensearch_upload_attempt_count": bool_count(records, "opensearch_upload_attempt"),
        "write_attempt_count": sum(int(record.get("write_attempt_count") or 0) for record in records),
    }

    inventory_path = output_dir / f"{MODULE_NAME}.json"
    quality_path = output_dir / f"{MODULE_NAME}_quality_check.json"
    jobs_path = output_dir / f"{MODULE_NAME}_jobs.jsonl"
    csv_path = output_dir / f"{MODULE_NAME}_records.csv"
    readme_path = output_dir / "README_trace_net_image_route_inventory_llava_jobs_v1.md"

    artifact_paths = {
        "inventory": str(inventory_path.as_posix()),
        "quality_check": str(quality_path.as_posix()),
        "jobs_jsonl": str(jobs_path.as_posix()),
        "records_csv": str(csv_path.as_posix()),
        "readme": str(readme_path.as_posix()),
    }

    inventory = {
        "module_name": MODULE_NAME,
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "created_at_utc": utc_now(),
        "inputs": {
            "route_validator_runner": {
                "path": str(route_artifact.path) if route_artifact.path else "",
                "exists": route_artifact.exists,
                "status": route_artifact.status,
                "quality_status": route_artifact.quality_status,
            },
            "ocr_route_scan_pack": {
                "path": str(ocr_artifact.path) if ocr_artifact.path else "",
                "exists": ocr_artifact.exists,
                "status": ocr_artifact.status,
                "quality_status": ocr_artifact.quality_status,
            },
            "image_visual_summary": {
                "path": str(summary_artifact.path) if summary_artifact.path else "",
                "exists": summary_artifact.exists,
                "status": summary_artifact.status,
                "quality_status": summary_artifact.quality_status,
            },
            "source_package_metadata": source_package_info,
        },
        "safety_contract": {
            "postgres_writes": False,
            "qdrant_writes": False,
            "opensearch_writes": False,
            "source_truth_mutation": False,
            "answer_permission": False,
            "llava_called_by_this_module": False,
        },
        "authority_model": {
            "llava_role": "visual observation and page understanding guidance only",
            "proof_role": "OCR/table/figure-item/source-truth evidence must prove part identity and final factual claims",
            "graph_leiden_role": "related-context navigation/ranking only",
        },
        "summary": summary,
        "quality_checks": checks,
        "artifact_paths": artifact_paths,
        "records": records,
    }

    quality_payload = {
        "module_name": MODULE_NAME,
        "status": f"{STATUS_BUILT}_QUALITY_CHECKED",
        "quality_status": quality_status,
        "created_at_utc": inventory["created_at_utc"],
        "summary": summary,
        "checks": checks,
        "artifact_paths": artifact_paths,
    }

    write_json(inventory_path, inventory)
    write_json(quality_path, quality_payload)
    with jobs_path.open("w", encoding="utf-8") as f:
        for job in jobs:
            f.write(json.dumps(job, sort_keys=True) + "\n")
    write_records_csv(csv_path, records)
    write_readme(readme_path, inventory)

    return inventory


def write_records_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    fieldnames = [
        "record_id",
        "page_id",
        "page_number",
        "source_member",
        "tiff_member",
        "route_label",
        "llava_status",
        "source_trace_ready",
        "ocr_text_available",
        "figure_candidate_count",
        "llava_output_target_path",
        "answer_permission",
        "source_truth_mutation_allowed",
        "write_attempt_count",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            row = {key: record.get(key, "") for key in fieldnames}
            row["figure_candidate_count"] = len(record.get("figure_candidates") or [])
            writer.writerow(row)


def write_readme(path: Path, inventory: Mapping[str, Any]) -> None:
    summary = inventory.get("summary", {})
    text = f"""# TRACE-Net Image Route Inventory + LLaVA Jobs v1

Status: `{inventory.get('status')}`  
Quality: `{inventory.get('quality_status')}`

This artifact inventories TRACE-Net image/diagram route pages and creates JSONL jobs for missing LLaVA visual summaries. It is Patch A for the image route. It does not call LLaVA; it only prepares source-traced job records.

## Authority model

LLaVA sees/describes visual content. OCR/table/figure-item evidence proves text and part identity. Graph/Leiden connects related evidence. TRACE-Net gates. Fast composers answer only after evidence is packaged.

## Counts

- image_route_record_count: {summary.get('image_route_record_count')}
- llava_job_count: {summary.get('llava_job_count')}
- existing_llava_summary_count: {summary.get('existing_llava_summary_count')}
- missing_llava_summary_count: {summary.get('missing_llava_summary_count')}
- source_trace_ready_count: {summary.get('source_trace_ready_count')}
- answer_permission_count: {summary.get('answer_permission_count')}
- source_truth_mutation_allowed_count: {summary.get('source_truth_mutation_allowed_count')}
- write_attempt_count: {summary.get('write_attempt_count')}

## Outputs

- `{inventory.get('artifact_paths', {}).get('inventory')}`
- `{inventory.get('artifact_paths', {}).get('quality_check')}`
- `{inventory.get('artifact_paths', {}).get('jobs_jsonl')}`
- `{inventory.get('artifact_paths', {}).get('records_csv')}`

"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net image-route inventory and LLaVA job manifest.")
    parser.add_argument("--route-validator-runner", required=True, help="Validated route runner / route manifest JSON artifact.")
    parser.add_argument("--ocr-route-scan-pack", default="", help="OCR route scan pack JSON artifact, optional but recommended.")
    parser.add_argument("--source-package-metadata-zip", default="", help="metadata.zip or source package directory with TIFF members, optional.")
    parser.add_argument("--image-visual-summary", default="", help="Existing LLaVA/image visual summary JSON artifact, optional.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory for inventory artifacts.")
    parser.add_argument("--llava-output-root", default=DEFAULT_LLAVA_OUTPUT_ROOT, help="Future output root for per-page LLaVA summaries.")
    parser.add_argument("--max-ocr-preview-chars", type=int, default=360, help="Maximum OCR preview characters to include in each job.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        inventory = build_inventory(args)
    except Exception as exc:  # pragma: no cover - exercised through CLI behavior
        print(f"{MODULE_NAME}: ERROR: {exc}", file=sys.stderr)
        return 2
    summary = inventory.get("summary", {})
    print(f"status={inventory.get('status')}")
    print(f"quality_status={inventory.get('quality_status')}")
    print(f"image_route_record_count={summary.get('image_route_record_count')}")
    print(f"llava_job_count={summary.get('llava_job_count')}")
    print(f"source_trace_ready_count={summary.get('source_trace_ready_count')}")
    print(f"missing_llava_summary_count={summary.get('missing_llava_summary_count')}")
    print(f"inventory={inventory.get('artifact_paths', {}).get('inventory')}")
    return 0 if inventory.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
