"""TRACE-Net Image Visual Summary v1.

Builds structured visual-observation cards for pages routed to image_visual.

This module is intentionally artifact-only unless ``--vision-mode ollama`` is
selected. Even then, the vision model is used only as a visual observer. Output
cards remain retrieval/review guidance and never grant answer permission.

Safety contract:
- no Postgres, Qdrant, or OpenSearch writes
- no source-truth mutation
- no answer permission
- no direct engineering approval/proof claims
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import urllib.error
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

MODULE_VERSION = "trace_net_image_visual_summary_v1"
REPORT_NAME = "trace_net_image_visual_summary_v1.json"
SUPPORTED_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp")
SUPPORTED_RENDERED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")

VISION_PROMPT = """You are a visual-observation extractor. Analyze only the attached scanned technical manual page image.
Return JSON only. Do not repeat these instructions. Do not mention the prompt, the user, or TRACE-Net.
Do not infer engineering approval, interchangeability, safe installation, airworthiness, or source-truth proof.
Use this exact JSON shape: {"visual_page_type": string, "observed_visual_features": [string],
"visible_callouts": [string], "visible_text_or_labels": [string], "summary": string,
"uncertainty_flags": [string]}. If text is not legible, use empty lists and say uncertain.
"""

FORBIDDEN_ASSERTION_PHRASES = (
    "approved replacement",
    "guaranteed fit",
    "safe to install",
    "interchangeable",
    "engineering-approved",
    "airworthy",
)

PROMPT_LEAK_PHRASES = (
    "trace-net's visual observer",
    "trace net's visual observer",
    "the prompt",
    "provided in the prompt",
    "ones provided in the prompt",
    "you are",
    "return concise json",
    "return json only",
    "do not claim",
    "describe only what is visible",
    "attached scanned technical manual page image",
)

LOW_VALUE_LABEL_PHRASES = (
    "a scanned technical manual page",
    "scanned technical manual page",
)

GENERIC_VISUAL_LABELS = (
    "none",
    "n/a",
    "unknown",
    "text",
    "lines of text",
    "bullet points",
    "numbered list",
    "instructions",
    "instructional text",
    "questions",
    "answers",
    "list of items",
    "items",
    "specifications",
    "dimensions",
    "material specifications",
    "component identification",
    "seat specifications",
    "seat type",
)

SEMANTIC_VALIDATION_VERSION = "semantic_validator_v1"


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing JSON file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    summary = payload.get("summary") or {}
    lines = [
        "# TRACE-Net Image Visual Summary v1",
        "",
        f"Quality status: **{payload.get('quality_status')}**",
        "",
        "## Summary",
        "",
        f"- Image visual handoffs: {summary.get('image_visual_handoff_count')}",
        f"- Visual summary cards: {summary.get('visual_summary_card_count')}",
        f"- Image source found: {summary.get('image_source_found_count')}",
        f"- Vision model called: {summary.get('vision_model_called_count')}",
        f"- Vision observation ready: {summary.get('vision_observation_ready_count')}",
        f"- Clean vision observations: {summary.get('clean_vision_observation_ready_count')}",
        f"- Prompt leak suspected: {summary.get('prompt_leak_suspected_count')}",
        f"- Review-required visual observations: {summary.get('review_required_visual_observation_count')}",
        f"- WebUI visual context allowed: {summary.get('webui_visual_context_allowed_count')}",
        f"- Review-only visual context: {summary.get('review_only_visual_context_count')}",
        f"- High hallucination-risk cards: {(summary.get('hallucination_risk_status_counts') or {}).get('HIGH_REVIEW_REQUIRED')}",
        f"- Missing image source: {summary.get('missing_image_source_count')}",
        f"- Unsafe records: {summary.get('unsafe_record_count')}",
        f"- Answer permission: {summary.get('answer_permission_count')}",
        "",
        "## Safety",
        "",
        "These cards are visual-observer guidance only. They do not prove engineering approval, fit, interchangeability, or airworthiness.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _flatten_records(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    for key in (
        "records",
        "route_dispatch_records",
        "dispatch_records",
        "page_records",
        "pages",
        "items",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            return [r for r in value if isinstance(r, dict)]
    # Route dispatch handoff also stores per-route lists under route_handoffs.
    route_handoffs = payload.get("route_handoffs")
    if isinstance(route_handoffs, dict):
        records: List[Dict[str, Any]] = []
        for value in route_handoffs.values():
            if isinstance(value, list):
                records.extend(r for r in value if isinstance(r, dict))
        return records
    return []


def _route_of(record: Mapping[str, Any]) -> str:
    for key in ("accepted_route", "selected_route", "route", "route_handoff", "target_route", "primary_route"):
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return "unknown"


def _page_id(record: Mapping[str, Any], index: int) -> str:
    for key in (
        "source_page_id",
        "page_id",
        "canonical_page_id",
        "metadata_page_id",
        "trace_page_id",
        "current_route_manifest_page_id",
        "change_record_page_id",
    ):
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return f"unknown_image_page_{index+1:06d}"


def _page_number_candidates(value: Any) -> List[int]:
    text = str(value or "")
    candidates: List[int] = []

    # Route/page artifacts commonly use tagged identifiers such as
    # t_p_120_1176_p000001, source_p000001, metadata_page_000001, or
    # local OCR filenames such as zip_page_000001_00000001.tif.
    for pattern in (
        r"source_p(\d{3,8})",
        r"metadata_page_(\d{3,8})",
        r"page[_ -]?(\d{3,8})",
        r"p(\d{3,8})",
    ):
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            try:
                candidates.append(int(match.group(1)))
            except ValueError:
                pass

    # ResCarta metadata.zip stores page rasters as bare eight-digit TIFF names,
    # e.g. 00000001.tif. Treat a bare numeric image stem as a page number.
    name = Path(text).name
    stem = Path(name).stem
    if stem.isdigit() and 1 <= len(stem) <= 8:
        try:
            candidates.append(int(stem))
        except ValueError:
            pass

    # Fallback for other compact filenames/tokens. Keep this after tagged/bare
    # detection so technical identifiers in longer strings do not dominate.
    if not candidates:
        for match in re.finditer(r"(?<!\d)(\d{1,8})(?!\d)", text):
            try:
                candidates.append(int(match.group(1)))
            except ValueError:
                pass

    # preserve order while deduping
    seen = set()
    ordered = []
    for num in candidates:
        if num not in seen:
            seen.add(num)
            ordered.append(num)
    return ordered


def _page_number_for_record(record: Mapping[str, Any], index: int) -> Optional[int]:
    fields = [
        record.get("source_page_id"),
        record.get("page_id"),
        record.get("canonical_page_id"),
        record.get("metadata_page_id"),
        record.get("trace_page_id"),
        record.get("source_image_path"),
        record.get("image_path"),
        record.get("page_image_path"),
        record.get("source_file"),
        record.get("file_path"),
    ]
    for field in fields:
        candidates = _page_number_candidates(field)
        if candidates:
            return candidates[-1]
    if isinstance(record.get("page_number"), int):
        return int(record["page_number"])
    return None


def _direct_image_path(record: Mapping[str, Any]) -> Optional[Path]:
    for key in (
        "source_image_path",
        "image_path",
        "page_image_path",
        "rendered_image_path",
        "source_tiff_path",
        "tiff_path",
        "file_path",
        "source_file",
    ):
        value = record.get(key)
        if value not in (None, ""):
            path = Path(str(value))
            if path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS and path.exists():
                return path
    return None


def _fishnet_image_lookup(fishnet_grid_path: Optional[Path]) -> Dict[int, Path]:
    lookup: Dict[int, Path] = {}
    if not fishnet_grid_path or not fishnet_grid_path.exists():
        return lookup
    payload = _read_json(fishnet_grid_path)
    for index, record in enumerate(_flatten_records(payload)):
        page_num = _page_number_for_record(record, index)
        direct = _direct_image_path(record)
        if page_num is not None and direct is not None:
            lookup.setdefault(page_num, direct)
    return lookup


def _zip_image_lookup(source_package_path: Optional[Path]) -> Dict[int, str]:
    lookup: Dict[int, str] = {}
    if not source_package_path or not source_package_path.exists() or not zipfile.is_zipfile(source_package_path):
        return lookup
    with zipfile.ZipFile(source_package_path) as zf:
        for name in zf.namelist():
            suffix = Path(name).suffix.lower()
            if suffix not in SUPPORTED_IMAGE_EXTENSIONS:
                continue
            candidates = _page_number_candidates(name)
            if not candidates:
                continue
            page_num = candidates[-1]
            lookup.setdefault(page_num, name)
    return lookup


def _copy_or_extract_image(
    *,
    page_id: str,
    page_number: Optional[int],
    record: Mapping[str, Any],
    output_dir: Path,
    fishnet_lookup: Mapping[int, Path],
    ocr_text_lookup: Mapping[int, str],
    zip_lookup: Mapping[int, str],
    source_package_path: Optional[Path],
    write_image_copies: bool,
) -> Tuple[Optional[Path], str]:
    direct = _direct_image_path(record)
    source_kind = "missing"
    source_path: Optional[Path] = None
    zip_member: Optional[str] = None

    if direct is not None:
        source_kind = "record_path"
        source_path = direct
    elif page_number is not None and page_number in fishnet_lookup:
        source_kind = "fishnet_path"
        source_path = fishnet_lookup[page_number]
    elif page_number is not None and page_number in zip_lookup:
        source_kind = "source_package_member"
        zip_member = zip_lookup[page_number]

    if source_path is None and zip_member is None:
        return None, source_kind

    if not write_image_copies:
        return source_path, source_kind

    image_dir = output_dir / "page_images"
    image_dir.mkdir(parents=True, exist_ok=True)
    safe_page_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", page_id)

    if source_path is not None:
        out_path = image_dir / f"{safe_page_id}{source_path.suffix.lower()}"
        shutil.copyfile(source_path, out_path)
        return out_path, source_kind

    if zip_member and source_package_path is not None:
        suffix = Path(zip_member).suffix.lower()
        out_path = image_dir / f"{safe_page_id}{suffix}"
        with zipfile.ZipFile(source_package_path) as zf:
            with zf.open(zip_member) as src, out_path.open("wb") as dst:
                shutil.copyfileobj(src, dst)
        return out_path, source_kind

    return None, source_kind


def _maybe_convert_for_vision(image_path: Path, output_dir: Path) -> Path:
    """Return PNG/JPEG path when possible; otherwise return original path.

    Ollama vision models are most reliable with PNG/JPEG. If Pillow is installed,
    convert TIFF/WEBP to PNG. If not installed, leave the source path untouched and
    let the caller report any model error.
    """
    if image_path.suffix.lower() in SUPPORTED_RENDERED_EXTENSIONS:
        return image_path
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return image_path
    rendered_dir = output_dir / "rendered_for_vision"
    rendered_dir.mkdir(parents=True, exist_ok=True)
    out_path = rendered_dir / f"{image_path.stem}.png"
    with Image.open(image_path) as img:
        # Some TIFFs are mode 1/P; RGB keeps model input simple.
        img.convert("RGB").save(out_path)
    return out_path


def _call_ollama_vision(
    *,
    image_path: Path,
    model: str,
    base_url: str,
    timeout_seconds: int,
    prompt: str = VISION_PROMPT,
) -> Tuple[Optional[str], Optional[str]]:
    api_url = base_url.rstrip("/") + "/api/generate"
    image_bytes = image_path.read_bytes()
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [base64.b64encode(image_bytes).decode("ascii")],
        "stream": False,
        "options": {"temperature": 0},
    }
    req = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        text = data.get("response")
        return str(text or "").strip(), None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _parse_vision_json(text: Optional[str]) -> Dict[str, Any]:
    if not text:
        return {}
    stripped = text.strip()
    # Ollama may wrap JSON with prose. Pull the widest JSON object if present.
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        candidate = stripped[start : end + 1]
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            pass
    return {"raw_visual_observer_text": stripped}


def _stringify_observation_item(item: Any) -> str:
    """Normalize LLaVA field values to readable strings.

    LLaVA sometimes returns lists of objects such as {"label": "..."} or
    {"feature": "text", "location": "center"}. Downstream TRACE-Net artifacts
    should be stable JSON with string arrays, so flatten those objects while
    preserving useful content.
    """
    if item is None:
        return ""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, (int, float)):
        return str(item)
    if isinstance(item, Mapping):
        preferred = []
        for key in ("label", "callout", "text", "feature", "description", "name", "value"):
            value = item.get(key)
            if value not in (None, ""):
                preferred.append(str(value).strip())
        location = item.get("location")
        if location not in (None, "") and preferred:
            preferred[-1] = f"{preferred[-1]} at {location}"
        if preferred:
            return "; ".join(v for v in preferred if v)
        return "; ".join(str(v).strip() for v in item.values() if v not in (None, ""))
    if isinstance(item, (list, tuple)):
        return "; ".join(_stringify_observation_item(v) for v in item if _stringify_observation_item(v))
    return str(item).strip()


def _contains_prompt_leak(text: str) -> bool:
    low = str(text or "").lower()
    return any(phrase in low for phrase in PROMPT_LEAK_PHRASES)


def _is_low_value_label(text: str) -> bool:
    low = str(text or "").lower().strip()
    return low in LOW_VALUE_LABEL_PHRASES


def _normalize_string_list(value: Any) -> List[str]:
    if value in (None, ""):
        return []
    raw_items = value if isinstance(value, list) else [value]
    normalized: List[str] = []
    seen = set()
    for item in raw_items:
        text = _stringify_observation_item(item)
        text = re.sub(r"\s+", " ", text).strip(" \t\r\n,;:")
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
    return normalized


def _normalize_visual_observation(observation: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return a cleaned visual observation plus a cleanup report.

    The goal is not to hide model quality problems; it is to keep prompt leakage
    out of retrieval evidence while recording when cleanup was required.
    """
    raw = dict(observation or {})
    prompt_leak_removed_items: List[str] = []
    low_value_removed_items: List[str] = []
    moved_non_numeric_callouts: List[str] = []

    summary = _stringify_observation_item(raw.get("summary") or raw.get("raw_visual_observer_text") or "").strip()
    summary_prompt_leak = _contains_prompt_leak(summary)
    if summary_prompt_leak:
        prompt_leak_removed_items.append(summary)
        summary = "Vision model returned a page-level observation, but prompt-leak text was removed from the summary. Treat as review-required visual guidance."

    visual_page_type = _stringify_observation_item(raw.get("visual_page_type") or "unknown_visual_page_type")
    if _contains_prompt_leak(visual_page_type):
        prompt_leak_removed_items.append(visual_page_type)
        visual_page_type = "unknown_visual_page_type"

    observed_features = []
    for item in _normalize_string_list(raw.get("observed_visual_features")):
        if _contains_prompt_leak(item):
            prompt_leak_removed_items.append(item)
            continue
        if _is_low_value_label(item):
            low_value_removed_items.append(item)
            continue
        observed_features.append(item)

    visible_labels = []
    for item in _normalize_string_list(raw.get("visible_text_or_labels")):
        if _contains_prompt_leak(item):
            prompt_leak_removed_items.append(item)
            continue
        if _is_low_value_label(item):
            low_value_removed_items.append(item)
            continue
        visible_labels.append(item)

    visible_callouts = []
    for item in _normalize_string_list(raw.get("visible_callouts")):
        if _contains_prompt_leak(item):
            prompt_leak_removed_items.append(item)
            continue
        if _is_low_value_label(item):
            low_value_removed_items.append(item)
            continue
        # A callout should normally contain a number/letter designator. Long
        # prose/text labels from a cover page belong in visible_text_or_labels.
        if not re.search(r"\d", item) and len(item.split()) > 2:
            moved_non_numeric_callouts.append(item)
            visible_labels.append(item)
            continue
        visible_callouts.append(item)

    visible_labels = _normalize_string_list(visible_labels)
    visible_callouts = _normalize_string_list(visible_callouts)
    observed_features = _normalize_string_list(observed_features)

    uncertainty_flags = _normalize_string_list(raw.get("uncertainty_flags"))
    prompt_leak_suspected = bool(prompt_leak_removed_items or summary_prompt_leak)
    if prompt_leak_suspected:
        uncertainty_flags.append("prompt_leak_removed_from_visual_model_output")
        uncertainty_flags.append("review_required_before_using_visual_labels")
    if moved_non_numeric_callouts:
        uncertainty_flags.append("non_numeric_callouts_reclassified_as_visible_labels")
    if not visible_callouts:
        uncertainty_flags.append("no_clear_callout_numbers_detected")
    if not observed_features and not visible_labels:
        uncertainty_flags.append("low_visual_content_or_uncertain_observation")
    uncertainty_flags.append("vision_derived_guidance_not_source_truth")
    uncertainty_flags = _normalize_string_list(uncertainty_flags)

    cleaned = {
        "visual_page_type": visual_page_type or "unknown_visual_page_type",
        "observed_visual_features": observed_features,
        "visible_callouts": visible_callouts,
        "visible_text_or_labels": visible_labels,
        "summary": summary,
        "uncertainty_flags": uncertainty_flags,
    }
    if "raw_visual_observer_text" in raw:
        cleaned["raw_visual_observer_text"] = _stringify_observation_item(raw.get("raw_visual_observer_text"))

    report = {
        "prompt_leak_suspected": prompt_leak_suspected,
        "prompt_leak_removed_item_count": len(prompt_leak_removed_items),
        "prompt_leak_removed_items": prompt_leak_removed_items[:20],
        "low_value_removed_item_count": len(low_value_removed_items),
        "moved_non_numeric_callout_count": len(moved_non_numeric_callouts),
        "moved_non_numeric_callouts": moved_non_numeric_callouts[:20],
    }
    return cleaned, report



def _compact_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _ocr_text_from_record(record: Mapping[str, Any]) -> str:
    """Extract OCR-ish text from a fishnet/page record without knowing schema.

    Fishnet v1.5 stores most useful text as page_ocr_features.sample_text
    and cell_records[*].sample_text rather than a top-level ocr_text field.
    Keep this permissive and read-only so semantic validation can join OCR
    support across artifact revisions without changing source truth.
    """
    text_keys = (
        "ocr_text",
        "text",
        "page_text",
        "raw_text",
        "clean_text",
        "ocr_full_text",
        "full_text",
        "extracted_text",
        "sample_text",
        "line_text",
        "label",
        "value",
    )
    word_keys = ("text", "word", "token", "value", "label", "sample_text")
    list_keys = (
        "ocr_words",
        "words",
        "word_boxes",
        "ocr_word_boxes",
        "tokens",
        "cells",
        "grid_cells",
        "cell_records",
        "lines",
        "ocr_lines",
        "text_lines",
    )
    mapping_keys = (
        "page_ocr_features",
        "ocr_features",
        "ocr_summary",
        "page_text_features",
    )

    parts: List[str] = []

    def add_text(value: Any) -> None:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                parts.append(stripped)

    def collect_from_mapping(mapping: Mapping[str, Any], *, depth: int = 0) -> None:
        if depth > 3:
            return
        for key in text_keys:
            add_text(mapping.get(key))
        for key in word_keys:
            add_text(mapping.get(key))
        for key in mapping_keys:
            nested = mapping.get(key)
            if isinstance(nested, Mapping):
                collect_from_mapping(nested, depth=depth + 1)
        for key in list_keys:
            value = mapping.get(key)
            if isinstance(value, list):
                for item in value[:2000]:
                    if isinstance(item, str):
                        add_text(item)
                    elif isinstance(item, Mapping):
                        collect_from_mapping(item, depth=depth + 1)

    collect_from_mapping(record)

    # Preserve order while dropping duplicates/empty snippets.
    seen = set()
    unique_parts: List[str] = []
    for part in parts:
        compact = re.sub(r"\s+", " ", part).strip()
        key = compact.lower()
        if compact and key not in seen:
            seen.add(key)
            unique_parts.append(compact)
    return " ".join(unique_parts)


def _ocr_text_lookup(fishnet_grid_path: Optional[Path]) -> Dict[int, str]:
    lookup: Dict[int, str] = {}
    if not fishnet_grid_path or not fishnet_grid_path.exists():
        return lookup
    payload = _read_json(fishnet_grid_path)
    for index, record in enumerate(_flatten_records(payload)):
        page_num = _page_number_for_record(record, index)
        if page_num is None:
            continue
        text = _ocr_text_from_record(record)
        if text.strip():
            if page_num in lookup:
                lookup[page_num] = f"{lookup[page_num]} {text}"
            else:
                lookup[page_num] = text
    return lookup


def _is_generic_visual_label(text: str) -> bool:
    compact = _compact_text(text)
    if not compact:
        return True
    return compact in {_compact_text(label) for label in GENERIC_VISUAL_LABELS}


def _label_supported_by_ocr(label: str, ocr_text: str) -> bool:
    compact_label = _compact_text(label)
    compact_ocr = _compact_text(ocr_text)
    if not compact_label or not compact_ocr:
        return False
    if compact_label in compact_ocr:
        return True
    label_terms = [term for term in compact_label.split() if len(term) >= 4]
    if not label_terms:
        return False
    supported_terms = sum(1 for term in label_terms if term in compact_ocr)
    return supported_terms >= max(1, min(2, len(label_terms)))


def _looks_like_invented_item_sequence(labels: Sequence[str]) -> bool:
    numbers = []
    for label in labels:
        match = re.fullmatch(r"item\s+(\d{1,4})", str(label or "").strip(), flags=re.IGNORECASE)
        if match:
            numbers.append(int(match.group(1)))
    if len(numbers) < 10:
        return False
    numbers = sorted(set(numbers))
    longest_run = 1
    current = 1
    for prev, cur in zip(numbers, numbers[1:]):
        if cur == prev + 1:
            current += 1
            longest_run = max(longest_run, current)
        else:
            current = 1
    return longest_run >= 10


def _validate_visual_observation_semantics(
    *,
    visual_observation: Mapping[str, Any],
    ocr_text: str,
    execution_status: str,
    prompt_leak_suspected: bool,
    vision_error: Optional[str],
) -> Dict[str, Any]:
    """Conservative semantic gate for LLaVA observations.

    Vision-model text is useful retrieval guidance, but not source truth. This
    validator decides whether the observation can be surfaced to WebUI/Self-RAG
    as low-risk visual context or must remain review-only.
    """
    labels = _normalize_string_list(visual_observation.get("visible_text_or_labels"))
    callouts = _normalize_string_list(visual_observation.get("visible_callouts"))
    features = _normalize_string_list(visual_observation.get("observed_visual_features"))
    summary = str(visual_observation.get("summary") or "")
    all_visual_terms = labels + callouts

    ocr_text = ocr_text or ""
    ocr_available = bool(ocr_text.strip())
    supported = [term for term in all_visual_terms if _label_supported_by_ocr(term, ocr_text)]
    unsupported = [term for term in all_visual_terms if term and not _label_supported_by_ocr(term, ocr_text)]
    generic = [term for term in all_visual_terms if _is_generic_visual_label(term)]
    invented_sequence = _looks_like_invented_item_sequence(labels)
    excessive_label_count = len(labels) > 25 or len(all_visual_terms) > 35
    generic_feature_count = sum(1 for term in features if _is_generic_visual_label(term))

    review_reasons: List[str] = []
    if execution_status != "vision_model_observation_ready":
        review_reasons.append("vision_model_not_ready")
    if vision_error:
        review_reasons.append("vision_model_error")
    if prompt_leak_suspected:
        review_reasons.append("prompt_leak_removed")
    if not ocr_available:
        review_reasons.append("ocr_text_missing_for_semantic_support_check")
    if excessive_label_count:
        review_reasons.append("excessive_visual_label_count")
    if invented_sequence:
        review_reasons.append("invented_item_sequence_suspected")
    if generic:
        review_reasons.append("generic_visual_labels_present")
    if unsupported and ocr_available:
        review_reasons.append("unsupported_visual_labels_present")
    if not labels and not callouts and not features:
        review_reasons.append("empty_visual_observation")
    if not supported and ocr_available and (labels or callouts):
        review_reasons.append("no_visual_labels_supported_by_ocr")

    high_risk = bool(vision_error or prompt_leak_suspected or excessive_label_count or invented_sequence)
    medium_risk = bool(generic or (unsupported and ocr_available) or not supported)
    if high_risk:
        hallucination_risk_status = "HIGH_REVIEW_REQUIRED"
    elif medium_risk:
        hallucination_risk_status = "MEDIUM_REVIEW_REQUIRED"
    else:
        hallucination_risk_status = "LOW_SUPPORTED_BY_OCR"

    # Be intentionally conservative. Visual context can be used automatically
    # only when the model executed, there is OCR support, no high-risk pattern,
    # and at least one label/callout survived support checks.
    webui_visual_context_allowed = (
        execution_status == "vision_model_observation_ready"
        and not high_risk
        and ocr_available
        and bool(supported)
    )
    semantic_validation_status = (
        "WEBUI_VISUAL_CONTEXT_ALLOWED"
        if webui_visual_context_allowed
        else "REVIEW_ONLY_VISUAL_CONTEXT"
        if execution_status == "vision_model_observation_ready"
        else "VISION_OBSERVATION_ERROR_REVIEW_ONLY"
    )

    return {
        "semantic_validation_version": SEMANTIC_VALIDATION_VERSION,
        "semantic_validation_status": semantic_validation_status,
        "hallucination_risk_status": hallucination_risk_status,
        "webui_visual_context_allowed": webui_visual_context_allowed,
        "ocr_text_available": ocr_available,
        "ocr_text_char_count": len(ocr_text),
        "ocr_label_support_count": len(supported),
        "ocr_supported_visual_terms": supported[:50],
        "unsupported_visual_label_count": len(unsupported),
        "unsupported_visual_labels": unsupported[:50],
        "generic_visual_label_count": len(generic),
        "generic_visual_labels": generic[:50],
        "generic_visual_feature_count": generic_feature_count,
        "excessive_visual_label_count": excessive_label_count,
        "invented_item_sequence_suspected": invented_sequence,
        "semantic_review_required": not webui_visual_context_allowed,
        "semantic_review_reasons": _normalize_string_list(review_reasons),
        "visual_label_count": len(labels),
        "visual_callout_count": len(callouts),
        "visual_feature_count": len(features),
        "summary_char_count": len(summary),
    }


def _has_forbidden_assertion(text: str) -> bool:
    low = text.lower()
    return any(phrase in low for phrase in FORBIDDEN_ASSERTION_PHRASES)


def _dry_run_visual_observation(page_id: str, image_source_status: str, image_path: Optional[Path]) -> Dict[str, Any]:
    return {
        "visual_page_type": "image_visual_route_page",
        "observed_visual_features": [],
        "visible_callouts": [],
        "visible_text_or_labels": [],
        "summary": (
            "Image/visual routed page prepared for vision-model observation; "
            "no pixel-level visual model was executed in dry_run mode."
        ),
        "uncertainty_flags": [
            "dry_run_no_vision_model_called",
            "not_source_truth",
            "requires OCR/citation confirmation",
            f"image_source_status={image_source_status}",
            "image_path_available" if image_path is not None else "image_path_missing",
        ],
    }


def _visual_summary_card(
    *,
    record: Mapping[str, Any],
    index: int,
    output_dir: Path,
    fishnet_lookup: Mapping[int, Path],
    ocr_text_lookup: Mapping[int, str],
    zip_lookup: Mapping[int, str],
    source_package_path: Optional[Path],
    write_image_copies: bool,
    vision_mode: str,
    vision_model: str,
    ollama_base_url: str,
    request_timeout: int,
) -> Dict[str, Any]:
    page_id = _page_id(record, index)
    page_number = _page_number_for_record(record, index)
    accepted_route = _route_of(record)
    image_path, image_source_status = _copy_or_extract_image(
        page_id=page_id,
        page_number=page_number,
        record=record,
        output_dir=output_dir,
        fishnet_lookup=fishnet_lookup,
        ocr_text_lookup=ocr_text_lookup,
        zip_lookup=zip_lookup,
        source_package_path=source_package_path,
        write_image_copies=write_image_copies,
    )

    visual_observation: Dict[str, Any]
    vision_error: Optional[str] = None
    vision_model_called = False
    rendered_image_path: Optional[Path] = None

    if vision_mode == "ollama" and image_path is not None:
        vision_model_called = True
        rendered_image_path = _maybe_convert_for_vision(image_path, output_dir)
        text, vision_error = _call_ollama_vision(
            image_path=rendered_image_path,
            model=vision_model,
            base_url=ollama_base_url,
            timeout_seconds=request_timeout,
        )
        visual_observation = _parse_vision_json(text)
        if not visual_observation:
            visual_observation = {
                "summary": "Vision model returned no structured observation.",
                "uncertainty_flags": ["vision_model_empty_or_unparseable"],
            }
    elif vision_mode == "ollama" and image_path is None:
        visual_observation = {
            "summary": "Vision model not called because no image source was resolved for this image_visual page.",
            "uncertainty_flags": ["image_source_missing", "vision_model_not_called"],
        }
    else:
        visual_observation = _dry_run_visual_observation(page_id, image_source_status, image_path)

    visual_observation, cleanup_report = _normalize_visual_observation(visual_observation)
    observation_text = json.dumps(visual_observation, sort_keys=True)
    unsafe = accepted_route != "image_visual" or _has_forbidden_assertion(observation_text)
    execution_status = (
        "vision_model_observation_ready"
        if vision_model_called and not vision_error
        else "vision_model_error"
        if vision_model_called and vision_error
        else "vision_not_called_dry_run"
        if vision_mode == "dry_run"
        else "vision_not_called_missing_image"
    )
    visual_observation_quality_status = (
        "CLEAN_VISION_OBSERVATION_READY"
        if execution_status == "vision_model_observation_ready" and not cleanup_report.get("prompt_leak_suspected")
        else "VISION_OBSERVATION_REVIEW_REQUIRED_PROMPT_LEAK_REMOVED"
        if execution_status == "vision_model_observation_ready" and cleanup_report.get("prompt_leak_suspected")
        else "VISION_OBSERVATION_NOT_EXECUTED"
        if not vision_model_called
        else "VISION_OBSERVATION_ERROR"
    )
    visual_review_reasons = []
    if cleanup_report.get("prompt_leak_suspected"):
        visual_review_reasons.append("prompt_leak_removed")
    if unsafe:
        visual_review_reasons.append("unsafe_or_forbidden_assertion_detected")
    if not vision_model_called:
        visual_review_reasons.append("vision_model_not_called")
    if vision_error:
        visual_review_reasons.append("vision_model_error")

    ocr_text_for_page = ocr_text_lookup.get(page_number, "") if page_number is not None else ""
    semantic_validation = _validate_visual_observation_semantics(
        visual_observation=visual_observation,
        ocr_text=ocr_text_for_page,
        execution_status=execution_status,
        prompt_leak_suspected=bool(cleanup_report.get("prompt_leak_suspected")),
        vision_error=vision_error,
    )
    if semantic_validation.get("semantic_review_required"):
        visual_review_reasons.extend(semantic_validation.get("semantic_review_reasons") or [])
        visual_review_reasons = _normalize_string_list(visual_review_reasons)

    return {
        "image_visual_summary_version": MODULE_VERSION,
        "card_id": f"image_visual_summary_{index+1:06d}",
        "page_id": page_id,
        "source_page_id": record.get("source_page_id"),
        "canonical_page_number": page_number,
        "accepted_route": accepted_route,
        "source_route_dispatch_handoff_page_id": record.get("page_id"),
        "image_source_status": image_source_status,
        "image_source_candidates": {
            "canonical_page_number": page_number,
            "source_package_member": zip_lookup.get(page_number) if page_number is not None else None,
            "fishnet_path": str(fishnet_lookup.get(page_number)) if page_number is not None and page_number in fishnet_lookup else None,
        },
        "image_path": str(image_path) if image_path is not None else None,
        "rendered_image_path": str(rendered_image_path) if rendered_image_path is not None else None,
        "vision_mode": vision_mode,
        "vision_model": vision_model if vision_mode == "ollama" else None,
        "vision_model_called": vision_model_called,
        "vision_model_error": vision_error,
        "visual_model_execution_status": execution_status,
        "visual_observation": visual_observation,
        "visual_summary_text": str(visual_observation.get("summary") or visual_observation.get("raw_visual_observer_text") or ""),
        "visual_observation_cleanup": cleanup_report,
        "prompt_leak_suspected": cleanup_report.get("prompt_leak_suspected", False),
        "prompt_leak_removed_item_count": cleanup_report.get("prompt_leak_removed_item_count", 0),
        "visual_observation_quality_status": visual_observation_quality_status,
        "visual_review_reasons": visual_review_reasons,
        "semantic_validation": semantic_validation,
        "semantic_validation_status": semantic_validation.get("semantic_validation_status"),
        "hallucination_risk_status": semantic_validation.get("hallucination_risk_status"),
        "webui_visual_context_allowed": semantic_validation.get("webui_visual_context_allowed", False),
        "ocr_text_available_for_visual_validation": semantic_validation.get("ocr_text_available", False),
        "ocr_text_char_count_for_visual_validation": semantic_validation.get("ocr_text_char_count", 0),
        "ocr_label_support_count": semantic_validation.get("ocr_label_support_count", 0),
        "unsupported_visual_label_count": semantic_validation.get("unsupported_visual_label_count", 0),
        "generic_visual_label_count": semantic_validation.get("generic_visual_label_count", 0),
        "invented_item_sequence_suspected": semantic_validation.get("invented_item_sequence_suspected", False),
        "excessive_visual_label_count": semantic_validation.get("excessive_visual_label_count", False),
        "visual_observation_authority": "vision_derived_retrieval_guidance_not_source_truth",
        "requires_ocr_or_source_citation_confirmation": True,
        "human_review_recommended": True,
        "processor_execution_allowed": False,
        "source_truth_mutation_allowed": False,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "unsafe": unsafe,
        "safety_contract": {
            "artifact_authority": "visual_observer_guidance_only",
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "postgres_write_allowed": False,
            "qdrant_write_allowed": False,
            "opensearch_write_allowed": False,
            "forbidden_claims": list(FORBIDDEN_ASSERTION_PHRASES),
        },
    }


def build_image_visual_summary(
    *,
    route_dispatch_handoff_path: Path,
    output_dir: Path,
    fishnet_ocr_grid_path: Optional[Path] = None,
    source_package_path: Optional[Path] = None,
    vision_mode: str = "dry_run",
    vision_model: str = "llava",
    ollama_base_url: str = "http://127.0.0.1:11434",
    request_timeout: int = 180,
    max_image_pages: Optional[int] = None,
    write_image_copies: bool = False,
) -> Dict[str, Any]:
    if vision_mode not in {"dry_run", "ollama"}:
        raise ValueError("vision_mode must be dry_run or ollama")

    route_payload = _read_json(route_dispatch_handoff_path)
    source_quality = route_payload.get("quality_status")
    all_records = _flatten_records(route_payload)
    image_records = [record for record in all_records if _route_of(record) == "image_visual"]
    if max_image_pages is not None:
        image_records = image_records[: max(0, max_image_pages)]

    fishnet_lookup = _fishnet_image_lookup(fishnet_ocr_grid_path)
    ocr_text_lookup = _ocr_text_lookup(fishnet_ocr_grid_path)
    zip_lookup = _zip_image_lookup(source_package_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    cards = [
        _visual_summary_card(
            record=record,
            index=index,
            output_dir=output_dir,
            fishnet_lookup=fishnet_lookup,
            ocr_text_lookup=ocr_text_lookup,
            zip_lookup=zip_lookup,
            source_package_path=source_package_path,
            write_image_copies=write_image_copies,
            vision_mode=vision_mode,
            vision_model=vision_model,
            ollama_base_url=ollama_base_url,
            request_timeout=request_timeout,
        )
        for index, record in enumerate(image_records)
    ]

    status_counts = Counter(card.get("visual_model_execution_status") for card in cards)
    summary = {
        "source_route_dispatch_handoff_quality_status": source_quality,
        "source_route_dispatch_handoff_record_count": len(all_records),
        "image_visual_handoff_count": len([r for r in all_records if _route_of(r) == "image_visual"]),
        "visual_summary_card_count": len(cards),
        "vision_mode": vision_mode,
        "vision_model": vision_model if vision_mode == "ollama" else None,
        "max_image_pages": max_image_pages,
        "image_source_found_count": sum(1 for card in cards if card.get("image_path")),
        "missing_image_source_count": sum(1 for card in cards if not card.get("image_path")),
        "vision_model_called_count": sum(1 for card in cards if card.get("vision_model_called")),
        "vision_model_error_count": sum(1 for card in cards if card.get("vision_model_error")),
        "vision_observation_ready_count": status_counts.get("vision_model_observation_ready", 0),
        "dry_run_card_count": status_counts.get("vision_not_called_dry_run", 0),
        "execution_status_counts": dict(sorted(status_counts.items())),
        "prompt_leak_suspected_count": sum(1 for card in cards if card.get("prompt_leak_suspected")),
        "prompt_leak_removed_item_count": sum(int(card.get("prompt_leak_removed_item_count") or 0) for card in cards),
        "clean_vision_observation_ready_count": sum(1 for card in cards if card.get("visual_observation_quality_status") == "CLEAN_VISION_OBSERVATION_READY"),
        "review_required_visual_observation_count": sum(1 for card in cards if card.get("visual_review_reasons")),
        "visual_observation_quality_status_counts": dict(sorted(Counter(card.get("visual_observation_quality_status") for card in cards).items())),
        "semantic_validation_status_counts": dict(sorted(Counter(card.get("semantic_validation_status") for card in cards).items())),
        "hallucination_risk_status_counts": dict(sorted(Counter(card.get("hallucination_risk_status") for card in cards).items())),
        "webui_visual_context_allowed_count": sum(1 for card in cards if card.get("webui_visual_context_allowed")),
        "review_only_visual_context_count": sum(1 for card in cards if not card.get("webui_visual_context_allowed")),
        "ocr_text_available_for_visual_validation_count": sum(1 for card in cards if card.get("ocr_text_available_for_visual_validation")),
        "ocr_label_support_count": sum(int(card.get("ocr_label_support_count") or 0) for card in cards),
        "unsupported_visual_label_count": sum(int(card.get("unsupported_visual_label_count") or 0) for card in cards),
        "generic_visual_label_count": sum(int(card.get("generic_visual_label_count") or 0) for card in cards),
        "invented_item_sequence_suspected_count": sum(1 for card in cards if card.get("invented_item_sequence_suspected")),
        "excessive_visual_label_count": sum(1 for card in cards if card.get("excessive_visual_label_count")),
        "unsafe_record_count": sum(1 for card in cards if card.get("unsafe")),
        "answer_permission_count": sum(1 for card in cards if card.get("answer_permission")),
        "can_answer_directly_count": sum(1 for card in cards if card.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for card in cards if card.get("can_prove_claims")),
        "source_truth_mutation_allowed_count": sum(1 for card in cards if card.get("source_truth_mutation_allowed")),
        "postgres_write_attempt_count": sum(1 for card in cards if card.get("postgres_write_attempt")),
        "qdrant_write_attempt_count": sum(1 for card in cards if card.get("qdrant_write_attempt")),
        "opensearch_write_attempt_count": sum(1 for card in cards if card.get("opensearch_write_attempt")),
    }

    quality_status = "PASS"
    if source_quality != "PASS":
        quality_status = "FAIL"
    if summary["unsafe_record_count"] != 0:
        quality_status = "FAIL"
    if summary["answer_permission_count"] != 0 or summary["source_truth_mutation_allowed_count"] != 0:
        quality_status = "FAIL"
    if vision_mode == "ollama" and summary["vision_model_called_count"] > 0 and summary["vision_model_error_count"] == summary["vision_model_called_count"]:
        # Do not fail when no images are found. Do fail when every attempted model call errored.
        quality_status = "FAIL"

    payload: Dict[str, Any] = {
        "module": MODULE_VERSION,
        "status": "TRACE_NET_IMAGE_VISUAL_SUMMARY_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "source_route_dispatch_handoff_path": str(route_dispatch_handoff_path),
        "source_fishnet_ocr_grid_path": str(fishnet_ocr_grid_path) if fishnet_ocr_grid_path else None,
        "source_package_path": str(source_package_path) if source_package_path else None,
        "records": cards,
        "visual_summary_cards": cards,
        "safety_contract": {
            "artifact_authority": "visual_observer_guidance_only",
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "postgres_write_allowed": False,
            "qdrant_write_allowed": False,
            "opensearch_write_allowed": False,
        },
    }

    _write_json(output_dir / REPORT_NAME, payload)
    _write_jsonl(output_dir / "trace_net_image_visual_summary_v1_records.jsonl", cards)
    _write_json(output_dir / "trace_net_image_visual_summary_v1_summary.json", summary)
    _write_json(output_dir / "trace_net_image_visual_summary_v1_quality.json", {"quality_status": quality_status, "summary": summary})
    _write_markdown(output_dir / "trace_net_image_visual_summary_v1.md", payload)
    return payload


def check_image_visual_summary_quality(
    *,
    report_path: Path,
    require_source_route_dispatch_quality_pass: bool = False,
    min_image_visual_handoffs: int = 0,
    min_summary_cards: int = 0,
    min_image_source_found: int = 0,
    min_vision_model_called: int = 0,
    require_vision_mode: Optional[str] = None,
    require_vision_execution: bool = False,
    min_clean_vision_observation_ready: int = 0,
    max_prompt_leak_suspected: Optional[int] = None,
    max_review_required: Optional[int] = None,
    min_webui_visual_context_allowed: int = 0,
    max_hallucination_high: Optional[int] = None,
    max_invented_item_sequence_suspected: Optional[int] = None,
    max_excessive_visual_label_count: Optional[int] = None,
    require_semantic_validation: bool = False,
    max_unsafe: int = 0,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
) -> Dict[str, Any]:
    payload = _read_json(report_path)
    summary = payload.get("summary") or {}
    failures: List[str] = []

    def fail_if(condition: bool, msg: str) -> None:
        if condition:
            failures.append(msg)

    fail_if(payload.get("quality_status") != "PASS", "report quality_status is not PASS")
    if require_source_route_dispatch_quality_pass:
        fail_if(summary.get("source_route_dispatch_handoff_quality_status") != "PASS", "source route dispatch quality is not PASS")
    fail_if(summary.get("image_visual_handoff_count", 0) < min_image_visual_handoffs, "not enough image_visual handoffs")
    fail_if(summary.get("visual_summary_card_count", 0) < min_summary_cards, "not enough visual summary cards")
    fail_if(summary.get("image_source_found_count", 0) < min_image_source_found, "not enough image sources found")
    fail_if(summary.get("vision_model_called_count", 0) < min_vision_model_called, "not enough vision model calls")
    if require_vision_mode is not None:
        fail_if(summary.get("vision_mode") != require_vision_mode, "vision mode mismatch")
    if require_vision_execution:
        fail_if(summary.get("vision_observation_ready_count", 0) <= 0, "no ready vision-model observations")
    fail_if(summary.get("clean_vision_observation_ready_count", 0) < min_clean_vision_observation_ready, "not enough clean vision observations")
    if max_prompt_leak_suspected is not None:
        fail_if(summary.get("prompt_leak_suspected_count", 0) > max_prompt_leak_suspected, "prompt leak suspected count exceeded")
    if max_review_required is not None:
        fail_if(summary.get("review_required_visual_observation_count", 0) > max_review_required, "review-required visual observation count exceeded")
    fail_if(summary.get("webui_visual_context_allowed_count", 0) < min_webui_visual_context_allowed, "not enough WebUI-allowed visual context cards")
    if max_hallucination_high is not None:
        high_count = (summary.get("hallucination_risk_status_counts") or {}).get("HIGH_REVIEW_REQUIRED", 0)
        fail_if(high_count > max_hallucination_high, "high hallucination-risk visual card count exceeded")
    if max_invented_item_sequence_suspected is not None:
        fail_if(summary.get("invented_item_sequence_suspected_count", 0) > max_invented_item_sequence_suspected, "invented item sequence suspected count exceeded")
    if max_excessive_visual_label_count is not None:
        fail_if(summary.get("excessive_visual_label_count", 0) > max_excessive_visual_label_count, "excessive visual label count exceeded")
    if require_semantic_validation:
        fail_if(not summary.get("semantic_validation_status_counts"), "semantic validation status counts missing")
    fail_if(summary.get("unsafe_record_count", 0) > max_unsafe, "unsafe record count exceeded")
    if require_no_answer_permission:
        fail_if(summary.get("answer_permission_count", 0) != 0, "answer permission count not zero")
        fail_if(summary.get("can_answer_directly_count", 0) != 0, "can_answer_directly count not zero")
        fail_if(summary.get("can_prove_claims_count", 0) != 0, "can_prove_claims count not zero")
    if require_no_source_truth_mutation:
        fail_if(summary.get("source_truth_mutation_allowed_count", 0) != 0, "source truth mutation allowed count not zero")
    if require_no_write_attempts:
        fail_if(summary.get("postgres_write_attempt_count", 0) != 0, "postgres write attempt count not zero")
        fail_if(summary.get("qdrant_write_attempt_count", 0) != 0, "qdrant write attempt count not zero")
        fail_if(summary.get("opensearch_write_attempt_count", 0) != 0, "opensearch write attempt count not zero")

    return {
        "quality_status": "FAIL" if failures else "PASS",
        "summary": summary,
        "failures": failures,
        "checked_report_path": str(report_path),
    }


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net image visual summary v1.")
    parser.add_argument("--route-dispatch-handoff", required=True)
    parser.add_argument("--fishnet-ocr-grid")
    parser.add_argument("--source-package")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--vision-mode", choices=("dry_run", "ollama"), default="dry_run")
    parser.add_argument("--vision-model", default="llava")
    parser.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--request-timeout", type=int, default=180)
    parser.add_argument("--max-image-pages", type=int)
    parser.add_argument("--write-image-copies", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    payload = build_image_visual_summary(
        route_dispatch_handoff_path=Path(args.route_dispatch_handoff),
        fishnet_ocr_grid_path=Path(args.fishnet_ocr_grid) if args.fishnet_ocr_grid else None,
        source_package_path=Path(args.source_package) if args.source_package else None,
        output_dir=Path(args.output_dir),
        vision_mode=args.vision_mode,
        vision_model=args.vision_model,
        ollama_base_url=args.ollama_base_url,
        request_timeout=args.request_timeout,
        max_image_pages=args.max_image_pages,
        write_image_copies=args.write_image_copies,
    )
    print("Status:", payload["status"])
    print("Quality status:", payload["quality_status"])
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["quality_status"] == "PASS" else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net image visual summary v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--require-source-route-dispatch-quality-pass", action="store_true")
    parser.add_argument("--min-image-visual-handoffs", type=int, default=0)
    parser.add_argument("--min-summary-cards", type=int, default=0)
    parser.add_argument("--min-image-source-found", type=int, default=0)
    parser.add_argument("--min-vision-model-called", type=int, default=0)
    parser.add_argument("--require-vision-mode")
    parser.add_argument("--require-vision-execution", action="store_true")
    parser.add_argument("--min-clean-vision-observation-ready", type=int, default=0)
    parser.add_argument("--max-prompt-leak-suspected", type=int)
    parser.add_argument("--max-review-required", type=int)
    parser.add_argument("--min-webui-visual-context-allowed", type=int, default=0)
    parser.add_argument("--max-hallucination-high", type=int)
    parser.add_argument("--max-invented-item-sequence-suspected", type=int)
    parser.add_argument("--max-excessive-visual-label-count", type=int)
    parser.add_argument("--require-semantic-validation", action="store_true")
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args(argv)

    result = check_image_visual_summary_quality(
        report_path=Path(args.report_path),
        require_source_route_dispatch_quality_pass=args.require_source_route_dispatch_quality_pass,
        min_image_visual_handoffs=args.min_image_visual_handoffs,
        min_summary_cards=args.min_summary_cards,
        min_image_source_found=args.min_image_source_found,
        min_vision_model_called=args.min_vision_model_called,
        require_vision_mode=args.require_vision_mode,
        require_vision_execution=args.require_vision_execution,
        min_clean_vision_observation_ready=args.min_clean_vision_observation_ready,
        max_prompt_leak_suspected=args.max_prompt_leak_suspected,
        max_review_required=args.max_review_required,
        min_webui_visual_context_allowed=args.min_webui_visual_context_allowed,
        max_hallucination_high=args.max_hallucination_high,
        max_invented_item_sequence_suspected=args.max_invented_item_sequence_suspected,
        max_excessive_visual_label_count=args.max_excessive_visual_label_count,
        require_semantic_validation=args.require_semantic_validation,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
    )
    print("Quality status:", result["quality_status"])
    print("Summary:", json.dumps(result["summary"], sort_keys=True))
    if result["failures"]:
        print("Failures:", json.dumps(result["failures"], indent=2))
    if args.write_json:
        out = Path(args.report_path).with_name("trace_net_image_visual_summary_v1_quality_check.json")
        _write_json(out, result)
        print("Wrote:", out)
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main_build())
