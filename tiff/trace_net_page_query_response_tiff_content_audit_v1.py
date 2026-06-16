"""TRACE-Net Page Query Response TIFF Content Audit v1.

Read-only verifier that opens source TIFFs from metadata.zip and checks whether
page query/response records are at least visually consistent with the page image.
Optionally calls a local Ollama vision model for sampled or full content review.

This module is deliberately not an answer gate. It never grants answer authority
or proof authority; it only produces review/evaluation records.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:  # Pillow is expected in the TRACE-Net image pipeline, but keep errors clear.
    from PIL import Image, ImageOps
except Exception:  # pragma: no cover - exercised only if Pillow is absent
    Image = None  # type: ignore[assignment]
    ImageOps = None  # type: ignore[assignment]

SCHEMA_VERSION = "trace_net_page_query_response_tiff_content_audit_v1"
REPORT_NAME = f"{SCHEMA_VERSION}.json"
QUALITY_NAME = f"{SCHEMA_VERSION}_quality.json"
RECORDS_JSONL = f"{SCHEMA_VERSION}_records.jsonl"
RESPONSES_JSONL = f"{SCHEMA_VERSION}_responses.jsonl"
SUMMARY_MD = f"{SCHEMA_VERSION}.md"

DEFAULT_BLANK_INK_RATIO_MAX = 0.0015
DEFAULT_LOW_INK_RATIO_MAX = 0.01
DEFAULT_DENSE_INK_RATIO_MIN = 0.035


@dataclass
class Thresholds:
    min_records: int = 1
    min_image_opened: int = 1
    min_blank_image_matches: int = 0
    min_response_page_anchors: int = 0
    min_response_source_entry_anchors: int = 0
    min_vision_evaluated: int = 0
    max_missing_zip_entries: int = 0
    max_image_open_failures: int = 0
    max_blank_mismatches: int = 0
    max_vision_failures: int = 0
    max_vision_call_failures: int = 0
    max_unsafe_responses: int = 0
    max_answer_capable_responses: int = 0
    max_claim_proof_responses: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_dataset_quality_pass: bool = False
    require_no_answer_permission: bool = False


@dataclass
class AuditOptions:
    page_query_response_dataset: Path
    metadata_zip: Path
    output_dir: Path
    first_pages: int = 200
    blank_ink_ratio_max: float = DEFAULT_BLANK_INK_RATIO_MAX
    low_ink_ratio_max: float = DEFAULT_LOW_INK_RATIO_MAX
    dense_ink_ratio_min: float = DEFAULT_DENSE_INK_RATIO_MIN
    run_ollama_vision: bool = False
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3-vl:latest"
    ollama_timeout: int = 300
    ollama_retries: int = 1
    ollama_num_predict: int = 220
    ollama_num_ctx: int = 4096
    max_vision_pages: int = 0
    vision_include_blank_pages: bool = True
    vision_image_max_side: int = 1400
    progress: bool = False
    quality: bool = False
    thresholds: Thresholds = field(default_factory=Thresholds)


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing JSON input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


def compact_text(value: Any, limit: int = 1200) -> str:
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def page_number_from_page_id(page_id: str) -> Optional[int]:
    m = re.search(r"p(\d{6})$", page_id or "")
    if not m:
        return None
    return int(m.group(1))


def expected_source_entry_for_page(page_number: int) -> str:
    return f"{page_number:08d}.tif"


def load_dataset_records(payload: Mapping[str, Any], first_pages: int) -> List[Dict[str, Any]]:
    records = list(payload.get("query_response_records") or payload.get("records") or [])
    selected: List[Dict[str, Any]] = []
    for record in records:
        page_number = record.get("page_number")
        if page_number is None:
            page_number = page_number_from_page_id(str(record.get("page_id") or ""))
        if page_number is None:
            continue
        if 1 <= int(page_number) <= int(first_pages):
            r = dict(record)
            r["page_number"] = int(page_number)
            selected.append(r)
    selected.sort(key=lambda r: (int(r.get("page_number") or 0), str(r.get("page_id") or "")))
    return selected


def extract_source_entry(record: Mapping[str, Any]) -> Optional[str]:
    source_identity = record.get("source_identity") or {}
    if isinstance(source_identity, Mapping):
        value = source_identity.get("source_package_entry_name")
        if value:
            return str(value)
    value = record.get("source_entry") or record.get("response_source_entry_name")
    if value:
        return str(value)
    response = str(record.get("response") or "")
    m = re.search(r"\b(\d{8}\.tif)\b", response, flags=re.IGNORECASE)
    if m:
        return m.group(1)
    page_number = record.get("page_number")
    return expected_source_entry_for_page(int(page_number)) if page_number else None


def response_mentions_page_id(record: Mapping[str, Any]) -> bool:
    page_id = str(record.get("page_id") or "")
    response = str(record.get("response") or "")
    return bool(page_id and page_id in response)


def response_mentions_source_entry(record: Mapping[str, Any], source_entry: Optional[str]) -> bool:
    response = str(record.get("response") or "")
    return bool(source_entry and source_entry in response)


def response_says_blank(response: str) -> bool:
    t = response.lower()
    return any(phrase in t for phrase in ["blank", "empty", "no page content", "no content to summarize"])


def response_claims_permission(response: str) -> Tuple[bool, bool, bool]:
    t = response.lower()
    answer_capable = any(
        phrase in t
        for phrase in [
            "can answer directly",
            "final answer authority",
            "answer authority granted",
            "allowed to answer directly",
        ]
    )
    claim_proof = any(
        phrase in t
        for phrase in [
            "can prove claims",
            "proves the claim",
            "claim-proof authority",
            "proof authority granted",
        ]
    )
    source_mutation = "source truth mutation" in t and not any(
        safe in t for safe in ["no source truth mutation", "source_truth_mutation_allowed: false", "source truth mutation allowed: false"]
    )
    return answer_capable, claim_proof, source_mutation


def normalize_ollama_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/api/generate"):
        return base
    return base + "/api/generate"


def open_tiff_from_zip(zip_obj: zipfile.ZipFile, entry_name: str) -> Tuple[bytes, Any]:
    if entry_name not in zip_obj.namelist():
        raise FileNotFoundError(entry_name)
    data = zip_obj.read(entry_name)
    if Image is None or ImageOps is None:
        raise RuntimeError("Pillow is required to inspect TIFF image content")
    img = Image.open(io.BytesIO(data))
    img.load()
    return data, img


def compute_image_metrics(image: Any, entry_bytes: bytes, blank_ink_ratio_max: float, low_ink_ratio_max: float, dense_ink_ratio_min: float) -> Dict[str, Any]:
    if ImageOps is None:
        raise RuntimeError("Pillow is required to inspect TIFF image content")
    width, height = image.size
    gray = ImageOps.grayscale(image)
    thumb = gray.copy()
    thumb.thumbnail((1200, 1200))
    hist = thumb.histogram()
    total = sum(hist) or 1
    dark_245 = sum(hist[:245])
    dark_230 = sum(hist[:230])
    dark_200 = sum(hist[:200])
    dark_128 = sum(hist[:128])
    ink_ratio_245 = dark_245 / total
    ink_ratio_230 = dark_230 / total
    ink_ratio_200 = dark_200 / total
    black_ratio_128 = dark_128 / total
    mean = sum(i * c for i, c in enumerate(hist)) / total
    # Simple row/column ink-line features for table-ish pages.
    bw = thumb.point(lambda p: 1 if p < 230 else 0)
    tw, th = bw.size
    px = list(bw.getdata())
    row_dense = 0
    col_dense = 0
    if tw and th:
        for y in range(th):
            row_sum = sum(px[y * tw : (y + 1) * tw])
            if row_sum / tw > 0.35:
                row_dense += 1
        for x in range(tw):
            col_sum = 0
            for y in range(th):
                col_sum += px[y * tw + x]
            if col_sum / th > 0.35:
                col_dense += 1
    blank_by_image = ink_ratio_230 <= blank_ink_ratio_max
    low_ink = ink_ratio_230 <= low_ink_ratio_max
    dense_text_or_table = ink_ratio_230 >= dense_ink_ratio_min
    likely_table_or_grid = row_dense >= 4 or col_dense >= 4
    return {
        "width": width,
        "height": height,
        "mode": str(image.mode),
        "zip_size_bytes": len(entry_bytes),
        "image_mean_brightness": round(mean, 6),
        "ink_ratio_245": round(ink_ratio_245, 8),
        "ink_ratio_230": round(ink_ratio_230, 8),
        "ink_ratio_200": round(ink_ratio_200, 8),
        "black_ratio_128": round(black_ratio_128, 8),
        "blank_by_image_heuristic": blank_by_image,
        "low_ink_page": low_ink,
        "dense_text_or_table_signal": dense_text_or_table,
        "likely_table_or_grid_signal": likely_table_or_grid,
        "dense_row_count": row_dense,
        "dense_column_count": col_dense,
        "sha1": hashlib.sha1(entry_bytes).hexdigest(),
    }


def infer_expected_content_tags(record: Mapping[str, Any]) -> List[str]:
    text = " ".join(
        compact_text(record.get(k), 2000).lower()
        for k in ["question", "response", "expected_answer_behavior"]
    )
    tags: List[str] = []
    if "blank" in text or "empty" in text:
        tags.append("blank_or_empty")
    if any(x in text for x in ["parts list", "part-number", "part number", "part numbers", "applicability"]):
        tags.append("parts_or_table")
    if any(x in text for x in ["list of effective pages", "lep", "revision", "front-matter", "front matter", "title block"]):
        tags.append("front_matter_or_revision")
    if any(x in text for x in ["diagram", "visual", "figure", "drawing", "callout"]):
        tags.append("visual_or_diagram")
    return sorted(set(tags))


def heuristic_support_check(record: Mapping[str, Any], metrics: Optional[Mapping[str, Any]], source_entry: Optional[str]) -> Tuple[str, List[str]]:
    flags: List[str] = []
    response = str(record.get("response") or "")
    blank_expected = bool(record.get("blank_expected")) or response_says_blank(response)
    image_blank = bool(metrics and metrics.get("blank_by_image_heuristic"))
    image_opened = bool(metrics)
    if not image_opened:
        flags.append("image_not_opened")
        return "REVIEW", flags
    if not response_mentions_page_id(record):
        flags.append("response_missing_page_id_anchor")
    if not response_mentions_source_entry(record, source_entry):
        flags.append("response_missing_source_entry_anchor")
    if blank_expected and not image_blank:
        flags.append("blank_response_but_image_has_ink")
    if image_blank and not response_says_blank(response):
        flags.append("image_blank_but_response_not_blank")
    if not blank_expected and image_blank:
        flags.append("nonblank_response_but_image_blank")
    tags = infer_expected_content_tags(record)
    if "parts_or_table" in tags and not metrics.get("dense_text_or_table_signal"):
        flags.append("parts_table_answer_low_ink_review")
    if "front_matter_or_revision" in tags and metrics.get("blank_by_image_heuristic"):
        flags.append("front_matter_answer_blank_image_review")
    answer_capable, claim_proof, source_mutation = response_claims_permission(response)
    if answer_capable:
        flags.append("answer_capable_phrase_in_response")
    if claim_proof:
        flags.append("claim_proof_phrase_in_response")
    if source_mutation:
        flags.append("source_truth_mutation_phrase_in_response")
    hard_fail_flags = {
        "blank_response_but_image_has_ink",
        "image_blank_but_response_not_blank",
        "nonblank_response_but_image_blank",
        "answer_capable_phrase_in_response",
        "claim_proof_phrase_in_response",
        "source_truth_mutation_phrase_in_response",
    }
    if hard_fail_flags.intersection(flags):
        return "FAIL", flags
    if flags:
        return "REVIEW", flags
    return "PASS", flags


def image_to_base64_png(image: Any, max_side: int) -> str:
    rgb = ImageOps.exif_transpose(image).convert("RGB") if ImageOps is not None else image.convert("RGB")
    rgb.thumbnail((max_side, max_side))
    out = io.BytesIO()
    rgb.save(out, format="PNG", optimize=True)
    return base64.b64encode(out.getvalue()).decode("ascii")


def build_vision_prompt(record: Mapping[str, Any], metrics: Mapping[str, Any], source_entry: str) -> str:
    page_id = record.get("page_id")
    page_number = record.get("page_number")
    question = compact_text(record.get("question"), 800)
    response = compact_text(record.get("response"), 1400)
    tags = ", ".join(infer_expected_content_tags(record)) or "none"
    return (
        "You are auditing whether a TRACE-Net page response is visually consistent with the attached TIFF page image.\n"
        "Look at the image itself. Do not use external knowledge. Do not grant answer authority.\n"
        "Return short line-based output only, with these exact fields:\n"
        "VERDICT: PASS or REVIEW or FAIL\n"
        "BLANK_PAGE: true or false\n"
        "IMAGE_SUMMARY: one short sentence about what is visible\n"
        "RESPONSE_CHECK: one short sentence saying whether the response matches the visible page\n"
        "REASONS: comma-separated reasons\n\n"
        f"PAGE_ID: {page_id}\n"
        f"PAGE_NUMBER: {page_number}\n"
        f"SOURCE_ENTRY: {source_entry}\n"
        f"EXPECTED_TAGS: {tags}\n"
        f"IMAGE_METRICS: ink_ratio_230={metrics.get('ink_ratio_230')}, blank_by_image={metrics.get('blank_by_image_heuristic')}, likely_table_or_grid={metrics.get('likely_table_or_grid_signal')}\n"
        f"USER_QUESTION: {question}\n"
        f"TRACE_NET_RESPONSE_TO_CHECK: {response}\n"
    )


def call_ollama_vision(
    *,
    ollama_url: str,
    model: str,
    prompt: str,
    image_b64: str,
    timeout: int,
    retries: int,
    num_predict: int,
    num_ctx: int,
) -> Tuple[bool, str, Optional[str]]:
    endpoint = normalize_ollama_url(ollama_url)
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": int(num_predict),
            "num_ctx": int(num_ctx),
        },
    }
    body = json.dumps(payload).encode("utf-8")
    last_error: Optional[str] = None
    for attempt in range(max(1, int(retries) + 1)):
        try:
            req = urllib.request.Request(
                endpoint,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return True, str(data.get("response") or ""), None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < max(1, int(retries)):
                time.sleep(min(2.0, 0.5 + attempt))
    return False, "", last_error or "unknown_error"


def parse_vision_response(text: str) -> Dict[str, Any]:
    raw = text or ""
    data: Dict[str, Any] = {}
    # JSON fallback if the model returns JSON despite the line prompt.
    try:
        m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if m:
            obj = json.loads(m.group(0))
            verdict = str(obj.get("verdict") or obj.get("VERDICT") or "").upper()
            if verdict:
                data["verdict"] = verdict
            if "blank_page" in obj or "BLANK_PAGE" in obj:
                data["blank_page"] = bool(obj.get("blank_page", obj.get("BLANK_PAGE")))
            data["image_summary"] = compact_text(obj.get("image_summary") or obj.get("IMAGE_SUMMARY"), 500)
            data["response_check"] = compact_text(obj.get("response_check") or obj.get("RESPONSE_CHECK"), 500)
            data["reasons"] = obj.get("reasons") or obj.get("REASONS") or []
            return data
    except Exception:
        pass
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    for line in lines:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key_u = key.strip().upper().replace(" ", "_")
        value = value.strip()
        if key_u == "VERDICT":
            val = value.upper()
            if "PASS" in val:
                data["verdict"] = "PASS"
            elif "FAIL" in val:
                data["verdict"] = "FAIL"
            elif "REVIEW" in val:
                data["verdict"] = "REVIEW"
        elif key_u == "BLANK_PAGE":
            data["blank_page"] = value.lower().startswith("true") or value.lower().startswith("yes")
        elif key_u == "IMAGE_SUMMARY":
            data["image_summary"] = compact_text(value, 500)
        elif key_u == "RESPONSE_CHECK":
            data["response_check"] = compact_text(value, 500)
        elif key_u == "REASONS":
            data["reasons"] = [v.strip() for v in value.split(",") if v.strip()]
    if "verdict" not in data:
        lower = raw.lower()
        if "verdict" in lower and "pass" in lower:
            data["verdict"] = "PASS"
        elif "fail" in lower:
            data["verdict"] = "FAIL"
        elif raw.strip():
            data["verdict"] = "REVIEW"
    return data


def should_run_vision_for_record(record: Mapping[str, Any], max_vision_pages: int, include_blank: bool, selected_so_far: int) -> bool:
    if max_vision_pages <= 0:
        return False
    if selected_so_far >= max_vision_pages:
        return False
    if bool(record.get("blank_expected")) and not include_blank:
        return False
    return True


def build_tiff_content_audit(options: AuditOptions) -> Dict[str, Any]:
    dataset_payload = read_json(options.page_query_response_dataset)
    dataset_quality_status = str(dataset_payload.get("quality_status") or dataset_payload.get("summary", {}).get("quality_status") or "")
    records = load_dataset_records(dataset_payload, options.first_pages)
    if not options.metadata_zip.exists():
        raise FileNotFoundError(f"Missing metadata zip: {options.metadata_zip}")

    output_records: List[Dict[str, Any]] = []
    response_records: List[Dict[str, Any]] = []
    vision_selected = 0
    zip_names: set[str]
    with zipfile.ZipFile(options.metadata_zip) as z:
        zip_names = set(z.namelist())
        for idx, record in enumerate(records, 1):
            page_id = str(record.get("page_id") or "")
            page_number = int(record.get("page_number") or page_number_from_page_id(page_id) or 0)
            expected_entry = expected_source_entry_for_page(page_number)
            response_entry = extract_source_entry(record)
            source_entry = response_entry or expected_entry
            item: Dict[str, Any] = {
                "record_id": f"page_query_response_tiff_content_audit::{page_id}",
                "page_id": page_id,
                "page_number": page_number,
                "question": record.get("question"),
                "response": record.get("response"),
                "blank_expected": bool(record.get("blank_expected")),
                "expected_source_entry_name": expected_entry,
                "response_source_entry_name": response_entry,
                "source_entry_name_used": source_entry,
                "response_mentions_page_id": response_mentions_page_id(record),
                "response_mentions_source_entry": response_mentions_source_entry(record, response_entry),
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
                "retrieval_only": True,
                "content_tags": infer_expected_content_tags(record),
                "tiff_image_metrics": None,
                "heuristic_content_status": "REVIEW",
                "heuristic_flags": [],
                "vision_evaluated": False,
                "vision_model": None,
                "vision_status": "NOT_RUN",
                "vision_verdict": None,
                "vision_blank_page": None,
                "vision_image_summary": None,
                "vision_response_check": None,
                "vision_reasons": [],
                "vision_call_failed": False,
                "vision_error": None,
                "content_audit_status": "REVIEW",
                "review_recommended": True,
            }
            image = None
            entry_exists = source_entry in zip_names if source_entry else False
            item["zip_entry_exists"] = entry_exists
            if not entry_exists:
                item["heuristic_flags"] = ["missing_zip_entry"]
                item["content_audit_status"] = "FAIL"
            else:
                try:
                    entry_bytes, image = open_tiff_from_zip(z, str(source_entry))
                    metrics = compute_image_metrics(
                        image,
                        entry_bytes,
                        options.blank_ink_ratio_max,
                        options.low_ink_ratio_max,
                        options.dense_ink_ratio_min,
                    )
                    item["tiff_image_metrics"] = metrics
                    status, flags = heuristic_support_check(record, metrics, source_entry)
                    item["heuristic_content_status"] = status
                    item["heuristic_flags"] = flags
                    item["content_audit_status"] = "PASS" if status == "PASS" else status
                    item["review_recommended"] = status != "PASS"
                except Exception as exc:
                    item["image_open_failed"] = True
                    item["image_open_error"] = f"{type(exc).__name__}: {exc}"
                    item["heuristic_flags"] = ["image_open_failed"]
                    item["content_audit_status"] = "FAIL"
                    item["review_recommended"] = True
            if options.run_ollama_vision and image is not None and should_run_vision_for_record(
                record, options.max_vision_pages, options.vision_include_blank_pages, vision_selected
            ):
                vision_selected += 1
                if options.progress:
                    print(
                        f"TRACE-Net TIFF content audit: running vision {vision_selected}/{options.max_vision_pages} page={page_id}",
                        file=sys.stderr,
                    )
                try:
                    metrics = item.get("tiff_image_metrics") or {}
                    prompt = build_vision_prompt(record, metrics, str(source_entry))
                    image_b64 = image_to_base64_png(image, options.vision_image_max_side)
                    ok, response_text, error = call_ollama_vision(
                        ollama_url=options.ollama_url,
                        model=options.ollama_model,
                        prompt=prompt,
                        image_b64=image_b64,
                        timeout=options.ollama_timeout,
                        retries=options.ollama_retries,
                        num_predict=options.ollama_num_predict,
                        num_ctx=options.ollama_num_ctx,
                    )
                    item["vision_evaluated"] = True
                    item["vision_model"] = options.ollama_model
                    item["vision_raw_response_preview"] = compact_text(response_text, 1500)
                    if not ok:
                        item["vision_call_failed"] = True
                        item["vision_error"] = error
                        item["vision_status"] = "CALL_FAILED"
                        item["content_audit_status"] = "REVIEW" if item["content_audit_status"] == "PASS" else item["content_audit_status"]
                    else:
                        parsed = parse_vision_response(response_text)
                        verdict = str(parsed.get("verdict") or "REVIEW").upper()
                        if verdict not in {"PASS", "REVIEW", "FAIL"}:
                            verdict = "REVIEW"
                        item["vision_status"] = "PARSED" if parsed else "UNPARSED_REVIEW"
                        item["vision_verdict"] = verdict
                        item["vision_blank_page"] = parsed.get("blank_page")
                        item["vision_image_summary"] = parsed.get("image_summary")
                        item["vision_response_check"] = parsed.get("response_check")
                        reasons = parsed.get("reasons") or []
                        if isinstance(reasons, str):
                            reasons = [reasons]
                        item["vision_reasons"] = reasons
                        # Vision FAIL is hard review/fail. Vision REVIEW keeps review.
                        if verdict == "FAIL":
                            item["content_audit_status"] = "FAIL"
                            item["review_recommended"] = True
                        elif verdict == "REVIEW" and item["content_audit_status"] == "PASS":
                            item["content_audit_status"] = "REVIEW"
                            item["review_recommended"] = True
                        elif verdict == "PASS" and item["content_audit_status"] == "PASS":
                            item["review_recommended"] = False
                except Exception as exc:
                    item["vision_evaluated"] = True
                    item["vision_model"] = options.ollama_model
                    item["vision_call_failed"] = True
                    item["vision_error"] = f"{type(exc).__name__}: {exc}"
                    item["vision_status"] = "CALL_FAILED"
            # Safety response scans.
            answer_capable, claim_proof, source_mutation = response_claims_permission(str(record.get("response") or ""))
            item["answer_capable_response"] = answer_capable
            item["claim_proof_response"] = claim_proof
            item["source_truth_mutation_response"] = source_mutation
            if answer_capable or claim_proof or source_mutation:
                item["content_audit_status"] = "FAIL"
                item["review_recommended"] = True
            output_records.append(item)
            response_records.append(
                {
                    "record_id": item["record_id"],
                    "page_id": page_id,
                    "page_number": page_number,
                    "source_entry": source_entry,
                    "question": item.get("question"),
                    "response": item.get("response"),
                    "blank_expected": item.get("blank_expected"),
                    "image_blank": (item.get("tiff_image_metrics") or {}).get("blank_by_image_heuristic"),
                    "ink_ratio_230": (item.get("tiff_image_metrics") or {}).get("ink_ratio_230"),
                    "heuristic_content_status": item.get("heuristic_content_status"),
                    "vision_evaluated": item.get("vision_evaluated"),
                    "vision_verdict": item.get("vision_verdict"),
                    "vision_image_summary": item.get("vision_image_summary"),
                    "content_audit_status": item.get("content_audit_status"),
                    "review_recommended": item.get("review_recommended"),
                    "flags": item.get("heuristic_flags"),
                }
            )
            if options.progress and not item.get("vision_evaluated") and idx % 25 == 0:
                print(f"TRACE-Net TIFF content audit: inspected {idx}/{len(records)} images", file=sys.stderr)

    summary = summarize_records(output_records, dataset_quality_status, options, zip_names)
    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "PAGE_QUERY_RESPONSE_TIFF_CONTENT_AUDIT_BUILT",
        "quality_status": "UNKNOWN",
        "source_dataset_path": str(options.page_query_response_dataset),
        "metadata_zip_path": str(options.metadata_zip),
        "summary": summary,
        "content_audit_records": output_records,
    }
    quality = check_quality(payload, options.thresholds)
    payload["quality_status"] = quality["quality_status"]
    payload["summary"]["status"] = quality["quality_status"]
    payload["quality_report"] = quality
    return payload


def summarize_records(records: Sequence[Mapping[str, Any]], dataset_quality_status: str, options: AuditOptions, zip_names: set[str]) -> Dict[str, Any]:
    def count(pred) -> int:
        return sum(1 for r in records if pred(r))

    blank_expected = count(lambda r: bool(r.get("blank_expected")))
    image_opened = count(lambda r: bool(r.get("tiff_image_metrics")))
    blank_image = count(lambda r: bool((r.get("tiff_image_metrics") or {}).get("blank_by_image_heuristic")))
    blank_response = count(lambda r: response_says_blank(str(r.get("response") or "")))
    blank_matches = count(
        lambda r: bool(r.get("blank_expected"))
        and bool((r.get("tiff_image_metrics") or {}).get("blank_by_image_heuristic"))
        and response_says_blank(str(r.get("response") or ""))
    )
    blank_mismatches = count(
        lambda r: (
            bool(r.get("blank_expected")) != bool((r.get("tiff_image_metrics") or {}).get("blank_by_image_heuristic"))
        )
        or (
            bool((r.get("tiff_image_metrics") or {}).get("blank_by_image_heuristic"))
            and not response_says_blank(str(r.get("response") or ""))
        )
        or (
            response_says_blank(str(r.get("response") or ""))
            and not bool((r.get("tiff_image_metrics") or {}).get("blank_by_image_heuristic"))
        )
    )
    status_counts: Dict[str, int] = {}
    vision_counts: Dict[str, int] = {}
    flag_counts: Dict[str, int] = {}
    for r in records:
        status_counts[str(r.get("content_audit_status") or "UNKNOWN")] = status_counts.get(str(r.get("content_audit_status") or "UNKNOWN"), 0) + 1
        vision_counts[str(r.get("vision_verdict") or r.get("vision_status") or "NOT_RUN")] = vision_counts.get(str(r.get("vision_verdict") or r.get("vision_status") or "NOT_RUN"), 0) + 1
        for flag in r.get("heuristic_flags") or []:
            flag_counts[str(flag)] = flag_counts.get(str(flag), 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "source_dataset_quality_status": dataset_quality_status,
        "metadata_zip_entry_count": len(zip_names),
        "record_count": len(records),
        "image_opened_count": image_opened,
        "missing_zip_entry_count": count(lambda r: not r.get("zip_entry_exists")),
        "image_open_failure_count": count(lambda r: bool(r.get("image_open_failed"))),
        "blank_expected_count": blank_expected,
        "blank_image_count": blank_image,
        "blank_response_count": blank_response,
        "blank_image_response_match_count": blank_matches,
        "blank_mismatch_count": blank_mismatches,
        "response_page_anchor_count": count(lambda r: bool(r.get("response_mentions_page_id"))),
        "response_source_entry_anchor_count": count(lambda r: bool(r.get("response_mentions_source_entry"))),
        "heuristic_pass_count": count(lambda r: r.get("heuristic_content_status") == "PASS"),
        "heuristic_review_count": count(lambda r: r.get("heuristic_content_status") == "REVIEW"),
        "heuristic_fail_count": count(lambda r: r.get("heuristic_content_status") == "FAIL"),
        "vision_enabled": bool(options.run_ollama_vision),
        "vision_model": options.ollama_model if options.run_ollama_vision else None,
        "vision_evaluated_count": count(lambda r: bool(r.get("vision_evaluated"))),
        "vision_support_pass_count": count(lambda r: r.get("vision_verdict") == "PASS"),
        "vision_support_review_count": count(lambda r: r.get("vision_verdict") == "REVIEW"),
        "vision_support_fail_count": count(lambda r: r.get("vision_verdict") == "FAIL"),
        "vision_call_failed_count": count(lambda r: bool(r.get("vision_call_failed"))),
        "content_audit_pass_count": count(lambda r: r.get("content_audit_status") == "PASS"),
        "content_audit_review_count": count(lambda r: r.get("content_audit_status") == "REVIEW"),
        "content_audit_fail_count": count(lambda r: r.get("content_audit_status") == "FAIL"),
        "review_recommended_count": count(lambda r: bool(r.get("review_recommended"))),
        "unsafe_response_count": 0,
        "answer_capable_response_count": count(lambda r: bool(r.get("answer_capable_response"))),
        "claim_proof_response_count": count(lambda r: bool(r.get("claim_proof_response"))),
        "source_truth_mutation_allowed_count": count(lambda r: bool(r.get("source_truth_mutation_response"))),
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "content_audit_status_counts": status_counts,
        "vision_status_counts": vision_counts,
        "heuristic_flag_counts": flag_counts,
    }


def check_quality(payload: Mapping[str, Any], thresholds: Thresholds) -> Dict[str, Any]:
    summary = payload.get("summary") or {}
    checks: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, observed: Any, expected: Any) -> None:
        checks.append({"name": name, "ok": bool(ok), "observed": observed, "expected": expected})

    add("record_count", int(summary.get("record_count") or 0) >= thresholds.min_records, summary.get("record_count"), f">= {thresholds.min_records}")
    add("image_opened_count", int(summary.get("image_opened_count") or 0) >= thresholds.min_image_opened, summary.get("image_opened_count"), f">= {thresholds.min_image_opened}")
    add("blank_image_response_match_count", int(summary.get("blank_image_response_match_count") or 0) >= thresholds.min_blank_image_matches, summary.get("blank_image_response_match_count"), f">= {thresholds.min_blank_image_matches}")
    add("response_page_anchor_count", int(summary.get("response_page_anchor_count") or 0) >= thresholds.min_response_page_anchors, summary.get("response_page_anchor_count"), f">= {thresholds.min_response_page_anchors}")
    add("response_source_entry_anchor_count", int(summary.get("response_source_entry_anchor_count") or 0) >= thresholds.min_response_source_entry_anchors, summary.get("response_source_entry_anchor_count"), f">= {thresholds.min_response_source_entry_anchors}")
    add("vision_evaluated_count", int(summary.get("vision_evaluated_count") or 0) >= thresholds.min_vision_evaluated, summary.get("vision_evaluated_count"), f">= {thresholds.min_vision_evaluated}")
    add("missing_zip_entry_count", int(summary.get("missing_zip_entry_count") or 0) <= thresholds.max_missing_zip_entries, summary.get("missing_zip_entry_count"), f"<= {thresholds.max_missing_zip_entries}")
    add("image_open_failure_count", int(summary.get("image_open_failure_count") or 0) <= thresholds.max_image_open_failures, summary.get("image_open_failure_count"), f"<= {thresholds.max_image_open_failures}")
    add("blank_mismatch_count", int(summary.get("blank_mismatch_count") or 0) <= thresholds.max_blank_mismatches, summary.get("blank_mismatch_count"), f"<= {thresholds.max_blank_mismatches}")
    add("vision_support_fail_count", int(summary.get("vision_support_fail_count") or 0) <= thresholds.max_vision_failures, summary.get("vision_support_fail_count"), f"<= {thresholds.max_vision_failures}")
    add("vision_call_failed_count", int(summary.get("vision_call_failed_count") or 0) <= thresholds.max_vision_call_failures, summary.get("vision_call_failed_count"), f"<= {thresholds.max_vision_call_failures}")
    add("unsafe_response_count", int(summary.get("unsafe_response_count") or 0) <= thresholds.max_unsafe_responses, summary.get("unsafe_response_count"), f"<= {thresholds.max_unsafe_responses}")
    add("answer_capable_response_count", int(summary.get("answer_capable_response_count") or 0) <= thresholds.max_answer_capable_responses, summary.get("answer_capable_response_count"), f"<= {thresholds.max_answer_capable_responses}")
    add("claim_proof_response_count", int(summary.get("claim_proof_response_count") or 0) <= thresholds.max_claim_proof_responses, summary.get("claim_proof_response_count"), f"<= {thresholds.max_claim_proof_responses}")
    add("source_truth_mutation_allowed_count", int(summary.get("source_truth_mutation_allowed_count") or 0) <= thresholds.max_source_truth_mutation_allowed, summary.get("source_truth_mutation_allowed_count"), f"<= {thresholds.max_source_truth_mutation_allowed}")
    if thresholds.require_dataset_quality_pass:
        add("source_dataset_quality_status", summary.get("source_dataset_quality_status") == "PASS", summary.get("source_dataset_quality_status"), "PASS")
    if thresholds.require_no_answer_permission:
        add("can_answer_directly_count", int(summary.get("can_answer_directly_count") or 0) == 0, summary.get("can_answer_directly_count"), "0")
        add("can_prove_claims_count", int(summary.get("can_prove_claims_count") or 0) == 0, summary.get("can_prove_claims_count"), "0")
    quality_status = "PASS" if all(c["ok"] for c in checks) else "FAIL"
    return {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": payload.get("status"),
        "quality_status": quality_status,
        "summary": summary,
        "checks": checks,
    }


def write_outputs(payload: Dict[str, Any], output_dir: Path, thresholds: Thresholds, write_quality_json: bool = True) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / REPORT_NAME
    quality_path = output_dir / QUALITY_NAME
    records_path = output_dir / RECORDS_JSONL
    responses_path = output_dir / RESPONSES_JSONL
    md_path = output_dir / SUMMARY_MD
    write_json(report_path, payload)
    quality = check_quality(payload, thresholds)
    if write_quality_json:
        write_json(quality_path, quality)
    write_jsonl(records_path, payload.get("content_audit_records") or [])
    lightweight: List[Mapping[str, Any]] = []
    for r in payload.get("content_audit_records") or []:
        lightweight.append(
            {
                "page_id": r.get("page_id"),
                "page_number": r.get("page_number"),
                "source_entry": r.get("source_entry_name_used"),
                "question": r.get("question"),
                "response": r.get("response"),
                "blank_expected": r.get("blank_expected"),
                "image_blank": (r.get("tiff_image_metrics") or {}).get("blank_by_image_heuristic"),
                "ink_ratio_230": (r.get("tiff_image_metrics") or {}).get("ink_ratio_230"),
                "heuristic_content_status": r.get("heuristic_content_status"),
                "vision_evaluated": r.get("vision_evaluated"),
                "vision_verdict": r.get("vision_verdict"),
                "vision_image_summary": r.get("vision_image_summary"),
                "content_audit_status": r.get("content_audit_status"),
                "review_recommended": r.get("review_recommended"),
                "flags": r.get("heuristic_flags"),
            }
        )
    write_jsonl(responses_path, lightweight)
    summary = payload.get("summary") or {}
    md = [
        "# TRACE-Net Page Query Response TIFF Content Audit v1",
        "",
        f"Quality status: **{payload.get('quality_status')}**",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "record_count",
        "image_opened_count",
        "blank_expected_count",
        "blank_image_response_match_count",
        "blank_mismatch_count",
        "vision_evaluated_count",
        "vision_support_pass_count",
        "vision_support_review_count",
        "vision_support_fail_count",
        "content_audit_pass_count",
        "content_audit_review_count",
        "content_audit_fail_count",
        "unsafe_response_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        md.append(f"- {key}: {summary.get(key)}")
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return {
        "report_path": report_path,
        "quality_path": quality_path,
        "records_path": records_path,
        "responses_path": responses_path,
        "markdown_path": md_path,
    }


def parse_thresholds(args: argparse.Namespace) -> Thresholds:
    return Thresholds(
        min_records=args.min_records,
        min_image_opened=args.min_image_opened,
        min_blank_image_matches=args.min_blank_image_matches,
        min_response_page_anchors=args.min_response_page_anchors,
        min_response_source_entry_anchors=args.min_response_source_entry_anchors,
        min_vision_evaluated=args.min_vision_evaluated,
        max_missing_zip_entries=args.max_missing_zip_entries,
        max_image_open_failures=args.max_image_open_failures,
        max_blank_mismatches=args.max_blank_mismatches,
        max_vision_failures=args.max_vision_failures,
        max_vision_call_failures=args.max_vision_call_failures,
        max_unsafe_responses=args.max_unsafe_responses,
        max_answer_capable_responses=args.max_answer_capable_responses,
        max_claim_proof_responses=args.max_claim_proof_responses,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_dataset_quality_pass=args.require_dataset_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Page Query Response TIFF Content Audit v1")
    parser.add_argument("--page-query-response-dataset", required=True, type=Path)
    parser.add_argument("--metadata-zip", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--first-pages", type=int, default=200)
    parser.add_argument("--blank-ink-ratio-max", type=float, default=DEFAULT_BLANK_INK_RATIO_MAX)
    parser.add_argument("--low-ink-ratio-max", type=float, default=DEFAULT_LOW_INK_RATIO_MAX)
    parser.add_argument("--dense-ink-ratio-min", type=float, default=DEFAULT_DENSE_INK_RATIO_MIN)
    parser.add_argument("--run-ollama-vision", action="store_true")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--ollama-model", default="qwen3-vl:latest")
    parser.add_argument("--ollama-timeout", type=int, default=300)
    parser.add_argument("--ollama-retries", type=int, default=1)
    parser.add_argument("--ollama-num-predict", type=int, default=220)
    parser.add_argument("--ollama-num-ctx", type=int, default=4096)
    parser.add_argument("--max-vision-pages", type=int, default=0)
    parser.add_argument("--skip-blank-vision-pages", action="store_true")
    parser.add_argument("--vision-image-max-side", type=int, default=1400)
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--quality", action="store_true")
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-image-opened", type=int, default=1)
    parser.add_argument("--min-blank-image-matches", type=int, default=0)
    parser.add_argument("--min-response-page-anchors", type=int, default=0)
    parser.add_argument("--min-response-source-entry-anchors", type=int, default=0)
    parser.add_argument("--min-vision-evaluated", type=int, default=0)
    parser.add_argument("--max-missing-zip-entries", type=int, default=0)
    parser.add_argument("--max-image-open-failures", type=int, default=0)
    parser.add_argument("--max-blank-mismatches", type=int, default=0)
    parser.add_argument("--max-vision-failures", type=int, default=0)
    parser.add_argument("--max-vision-call-failures", type=int, default=0)
    parser.add_argument("--max-unsafe-responses", type=int, default=0)
    parser.add_argument("--max-answer-capable-responses", type=int, default=0)
    parser.add_argument("--max-claim-proof-responses", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-dataset-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    return parser


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    thresholds = parse_thresholds(args)
    options = AuditOptions(
        page_query_response_dataset=args.page_query_response_dataset,
        metadata_zip=args.metadata_zip,
        output_dir=args.output_dir,
        first_pages=args.first_pages,
        blank_ink_ratio_max=args.blank_ink_ratio_max,
        low_ink_ratio_max=args.low_ink_ratio_max,
        dense_ink_ratio_min=args.dense_ink_ratio_min,
        run_ollama_vision=args.run_ollama_vision,
        ollama_url=args.ollama_url,
        ollama_model=args.ollama_model,
        ollama_timeout=args.ollama_timeout,
        ollama_retries=args.ollama_retries,
        ollama_num_predict=args.ollama_num_predict,
        ollama_num_ctx=args.ollama_num_ctx,
        max_vision_pages=args.max_vision_pages,
        vision_include_blank_pages=not args.skip_blank_vision_pages,
        vision_image_max_side=args.vision_image_max_side,
        progress=args.progress,
        quality=args.quality,
        thresholds=thresholds,
    )
    payload = build_tiff_content_audit(options)
    paths = write_outputs(payload, args.output_dir, thresholds)
    summary = payload.get("summary", {})
    print("TRACE-Net Page Query Response TIFF Content Audit v1")
    print(f" Status: {payload.get('status')}")
    print(f" Quality status: {payload.get('quality_status')}")
    for key in [
        "source_dataset_quality_status",
        "record_count",
        "image_opened_count",
        "blank_expected_count",
        "blank_image_count",
        "blank_image_response_match_count",
        "blank_mismatch_count",
        "vision_evaluated_count",
        "vision_support_pass_count",
        "vision_support_review_count",
        "vision_support_fail_count",
        "vision_call_failed_count",
        "content_audit_pass_count",
        "content_audit_review_count",
        "content_audit_fail_count",
        "unsafe_response_count",
        "answer_capable_response_count",
        "claim_proof_response_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {paths['report_path']}")
    print(f" quality_path: {paths['quality_path']}")
    return 0 if payload.get("quality_status") == "PASS" or not args.quality else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Page Query Response TIFF Content Audit v1 quality")
    parser.add_argument("--report-path", required=True, type=Path)
    # Same thresholds, no build inputs.
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-image-opened", type=int, default=1)
    parser.add_argument("--min-blank-image-matches", type=int, default=0)
    parser.add_argument("--min-response-page-anchors", type=int, default=0)
    parser.add_argument("--min-response-source-entry-anchors", type=int, default=0)
    parser.add_argument("--min-vision-evaluated", type=int, default=0)
    parser.add_argument("--max-missing-zip-entries", type=int, default=0)
    parser.add_argument("--max-image-open-failures", type=int, default=0)
    parser.add_argument("--max-blank-mismatches", type=int, default=0)
    parser.add_argument("--max-vision-failures", type=int, default=0)
    parser.add_argument("--max-vision-call-failures", type=int, default=0)
    parser.add_argument("--max-unsafe-responses", type=int, default=0)
    parser.add_argument("--max-answer-capable-responses", type=int, default=0)
    parser.add_argument("--max-claim-proof-responses", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-dataset-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    args = parser.parse_args(argv)
    payload = read_json(args.report_path)
    thresholds = parse_thresholds(args)
    quality = check_quality(payload, thresholds)
    if args.write_json:
        write_json(args.report_path.with_name(QUALITY_NAME), quality)
    summary = quality.get("summary", {})
    print("TRACE-Net Page Query Response TIFF Content Audit v1 quality")
    print(f" Status: {payload.get('status')}")
    print(f" Quality status: {quality.get('quality_status')}")
    for key in [
        "record_count",
        "image_opened_count",
        "blank_image_response_match_count",
        "blank_mismatch_count",
        "vision_evaluated_count",
        "vision_support_fail_count",
        "vision_call_failed_count",
        "unsafe_response_count",
        "answer_capable_response_count",
        "claim_proof_response_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    return 0 if quality.get("quality_status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main_build())
