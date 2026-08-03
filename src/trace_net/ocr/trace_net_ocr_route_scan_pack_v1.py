"""TRACE-Net OCR Route Scan Pack v1.

Builds a per-page scan/router metadata pack from raw TIFF pages.  This module is
intentionally file/artifact based: it does not write Postgres, Qdrant, or
OpenSearch.  It prepares a 1-to-1 comparison manifest so a later audit can check
raw TIFF page images against extracted OCR/route metadata.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from collections import Counter
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

VERSION = "v1"
MODULE = "trace_net_ocr_route_scan_pack_v1"
REPORT_NAME = "trace_net_ocr_route_scan_pack_v1.json"
RECORDS_NAME = "trace_net_ocr_route_scan_pack_v1_records.jsonl"
COMPARISON_NAME = "trace_net_ocr_route_scan_pack_v1_page_comparison_manifest.jsonl"
SUMMARY_NAME = "trace_net_ocr_route_scan_pack_v1_summary.json"
QUALITY_NAME = "trace_net_ocr_route_scan_pack_v1_quality_check.json"
MARKDOWN_NAME = "README_trace_net_ocr_route_scan_pack_v1_report.md"

IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".webp"}
PART_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:-]*")

TABLE_KEYWORDS = {
    "item", "part", "partno", "part_no", "partnumber", "nomenclature", "qty",
    "effect", "effectivity", "figure", "fig", "ipl", "assy", "assembly", "units",
    "chapter", "section", "page", "code", "description", "vendor", "serial",
}
VISUAL_KEYWORDS = {
    "figure", "fig", "diagram", "drawing", "illustration", "callout", "view",
    "exploded", "seat", "assembly", "detail", "dimension", "dimensions", "shown",
}
GENERIC_STOP = {"the", "and", "for", "with", "from", "page", "manual", "technical"}

SAFETY_CONTRACT = {
    "artifact_authority": "ocr_route_scan_metadata_not_source_truth",
    "can_answer_directly": False,
    "can_prove_claims": False,
    "answer_permission": False,
    "source_truth_mutation_allowed": False,
    "postgres_write_allowed": False,
    "qdrant_write_allowed": False,
    "opensearch_write_allowed": False,
    "requires_downstream_source_truth_confirmation": True,
    "guidance_only": True,
}


def _normalize_git_bash_path(value: str | Path | None) -> Path | None:
    if value is None:
        return None
    text = str(value)
    if re.match(r"^/[A-Za-z]/", text):
        text = f"{text[1].upper()}:{text[2:]}"
    return Path(text)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _write_markdown(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_page_number(name: str, fallback_index: int) -> int:
    base = Path(name).stem
    numbers = re.findall(r"\d+", base)
    if not numbers:
        return fallback_index
    return int(numbers[-1])


@dataclass(frozen=True)
class SourcePage:
    source_member: str
    page_number: int
    page_id: str
    canonical_page_id: str
    file_name: str
    image_bytes: bytes
    byte_count: int
    sha256: str


def _iter_source_pages(source_package: Path, *, max_pages: int | None = None, page_numbers: set[int] | None = None) -> list[SourcePage]:
    pages: list[SourcePage] = []
    if source_package.is_dir():
        files = [p for p in source_package.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]
        files.sort(key=lambda p: str(p).lower())
        for idx, path in enumerate(files, 1):
            page_number = _parse_page_number(path.name, idx)
            if page_numbers and page_number not in page_numbers:
                continue
            data = path.read_bytes()
            pages.append(_source_page_from_bytes(str(path.relative_to(source_package)), path.name, page_number, data))
            if max_pages and len(pages) >= max_pages:
                break
        return pages

    with zipfile.ZipFile(source_package) as archive:
        names = [n for n in archive.namelist() if Path(n).suffix.lower() in IMAGE_EXTENSIONS and not n.endswith("/")]
        names.sort(key=lambda n: (_parse_page_number(n, 10**9), n.lower()))
        for idx, name in enumerate(names, 1):
            page_number = _parse_page_number(name, idx)
            if page_numbers and page_number not in page_numbers:
                continue
            data = archive.read(name)
            pages.append(_source_page_from_bytes(name, Path(name).name, page_number, data))
            if max_pages and len(pages) >= max_pages:
                break
    return pages


def _source_page_from_bytes(member: str, file_name: str, page_number: int, data: bytes) -> SourcePage:
    page_id = f"source_p{page_number:06d}"
    canonical_page_id = f"t_p_120_1176_p{page_number:06d}"
    return SourcePage(
        source_member=member,
        page_number=page_number,
        page_id=page_id,
        canonical_page_id=canonical_page_id,
        file_name=file_name,
        image_bytes=data,
        byte_count=len(data),
        sha256=_sha256_bytes(data),
    )


def _image_features(image_bytes: bytes) -> dict[str, Any]:
    features: dict[str, Any] = {
        "image_feature_status": "not_available",
        "image_width_px": None,
        "image_height_px": None,
        "ink_ratio_estimate": None,
        "mean_darkness_estimate": None,
    }
    try:
        from PIL import Image  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency branch
        features["image_feature_status"] = "pil_not_available"
        features["image_feature_error"] = str(exc)
        return features
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            width, height = img.size
            gray = img.convert("L")
            gray.thumbnail((300, 300))
            pixels = list(gray.getdata())
            if pixels:
                dark = [255 - int(v) for v in pixels]
                ink = sum(1 for v in pixels if int(v) < 235)
                features.update(
                    {
                        "image_feature_status": "ok",
                        "image_width_px": width,
                        "image_height_px": height,
                        "ink_ratio_estimate": round(ink / len(pixels), 6),
                        "mean_darkness_estimate": round(sum(dark) / (255 * len(dark)), 6),
                    }
                )
    except Exception as exc:
        features["image_feature_status"] = "error"
        features["image_feature_error"] = str(exc)
    return features


def _parse_page_numbers(text: str | None) -> set[int] | None:
    if not text:
        return None
    values: set[int] = set()
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            a, b = chunk.split("-", 1)
            values.update(range(int(a), int(b) + 1))
        else:
            values.add(int(chunk))
    return values


def _decode_process_bytes(value: bytes | str | None) -> str:
    """Decode OCR subprocess output without using the Windows locale codec.

    Tesseract can emit non-UTF/control bytes on Windows.  Using
    subprocess.run(..., text=True) lets Python decode with cp1252 on Git Bash
    and can crash inside the reader thread.  Capturing bytes and decoding with
    replacement keeps the scan pack moving while preserving a readable sample.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    for encoding in ("utf-8", "latin-1"):
        try:
            return value.decode(encoding)
        except UnicodeDecodeError:
            continue
    return value.decode("utf-8", errors="replace")


def _run_tesseract_on_bytes(
    image_bytes: bytes,
    *,
    suffix: str,
    tesseract_cmd: str,
    psm_modes: Sequence[int],
    request_timeout: int,
) -> dict[str, Any]:
    normalized_cmd = str(_normalize_git_bash_path(tesseract_cmd) or tesseract_cmd)
    attempts: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    with tempfile.TemporaryDirectory(prefix="trace_net_ocr_route_scan_") as tmp:
        input_path = Path(tmp) / f"page{suffix}"
        input_path.write_bytes(image_bytes)
        for psm in psm_modes:
            cmd = [normalized_cmd, str(input_path), "stdout", "--oem", "3", "--psm", str(psm)]
            started = time.time()
            try:
                proc = subprocess.run(cmd, capture_output=True, text=False, timeout=request_timeout)
                elapsed = round(time.time() - started, 3)
                text = _decode_process_bytes(proc.stdout)
                stderr_text = _decode_process_bytes(proc.stderr)
                tokens = _tokens(text)
                part_numbers = sorted(set(PART_RE.findall(text)))
                attempt = {
                    "psm": psm,
                    "returncode": proc.returncode,
                    "elapsed_seconds": elapsed,
                    "stderr_sample": stderr_text[:500],
                    "ocr_text_char_count": len(text),
                    "ocr_text_word_count": len(tokens),
                    "part_number_token_count": len(part_numbers),
                    "part_number_tokens": part_numbers[:50],
                    "score": len(tokens) + 15 * len(part_numbers),
                    "text": text,
                }
            except Exception as exc:
                attempt = {
                    "psm": psm,
                    "returncode": None,
                    "elapsed_seconds": round(time.time() - started, 3),
                    "error": str(exc),
                    "ocr_text_char_count": 0,
                    "ocr_text_word_count": 0,
                    "part_number_token_count": 0,
                    "part_number_tokens": [],
                    "score": -1,
                    "text": "",
                }
            attempts.append({k: v for k, v in attempt.items() if k != "text"})
            if best is None or int(attempt.get("score", -1)) > int(best.get("score", -1)):
                best = attempt
    best = best or {"text": "", "score": -1}
    return {
        "tesseract_execution_status": "ok" if best.get("score", -1) >= 0 else "error",
        "tesseract_cmd": normalized_cmd,
        "tesseract_attempt_count": len(attempts),
        "tesseract_attempts": attempts,
        "best_psm": best.get("psm"),
        "best_ocr_text": best.get("text") or "",
        "best_ocr_text_char_count": len(best.get("text") or ""),
        "best_ocr_text_word_count": len(_tokens(best.get("text") or "")),
        "best_part_number_tokens": sorted(set(PART_RE.findall(best.get("text") or "")))[:50],
    }


def _tokens(text: str) -> list[str]:
    return WORD_RE.findall(text or "")


def _keyword_count(tokens: Iterable[str], keywords: set[str]) -> int:
    normalized = [re.sub(r"[^a-z0-9]", "", t.lower()) for t in tokens]
    return sum(1 for t in normalized if t in keywords)


def _classify_route(*, text: str, image_features: Mapping[str, Any], tesseract_status: str | None) -> tuple[str, float, list[str]]:
    tokens = _tokens(text)
    token_count = len(tokens)
    char_count = len(text or "")
    part_numbers = PART_RE.findall(text or "")
    numeric_count = len(NUMBER_RE.findall(text or ""))
    table_count = _keyword_count(tokens, TABLE_KEYWORDS)
    visual_count = _keyword_count(tokens, VISUAL_KEYWORDS)
    ink_ratio = image_features.get("ink_ratio_estimate")
    reasons: list[str] = []

    if tesseract_status and tesseract_status.startswith("error"):
        reasons.append("tesseract_error")
        return "review_required", 0.0, reasons

    if char_count == 0 and isinstance(ink_ratio, (int, float)) and ink_ratio < 0.006:
        reasons.append("empty_ocr_low_ink")
        return "blank_candidate", 0.85, reasons

    if char_count == 0:
        reasons.append("empty_ocr_nonblank_or_unknown_ink")
        return "image_visual", 0.55, reasons

    if len(part_numbers) >= 2 or table_count >= 4 or (numeric_count >= 25 and token_count >= 40):
        reasons.append("table_or_parts_list_text_cues")
        return "table", min(0.95, 0.45 + 0.05 * table_count + 0.04 * len(part_numbers)), reasons

    if visual_count >= 2 and token_count < 180:
        reasons.append("visual_keywords_with_limited_text")
        return "image_visual", min(0.9, 0.5 + 0.07 * visual_count), reasons

    if token_count < 8 and isinstance(ink_ratio, (int, float)) and ink_ratio > 0.02:
        reasons.append("low_ocr_text_nonblank_image")
        return "image_visual", 0.6, reasons

    reasons.append("normal_text_ocr_density")
    return "normal_text", min(0.95, 0.5 + min(token_count, 200) / 500), reasons


def _route_processor_contract(route: str) -> dict[str, Any]:
    contracts = {
        "normal_text": {
            "processor": "normal_text_ocr_summary_scan",
            "scanned_data_kinds": ["ocr_text", "part_number_tokens", "semantic_text_candidates"],
        },
        "table": {
            "processor": "table_ocr_table_candidate_scan",
            "scanned_data_kinds": ["ocr_text", "table_keyword_cues", "numeric_tokens", "part_number_tokens"],
        },
        "image_visual": {
            "processor": "image_visual_ocr_and_vision_queue_scan",
            "scanned_data_kinds": ["image_features", "ocr_text_if_any", "visual_keywords", "vision_model_pending"],
        },
        "blank_candidate": {
            "processor": "blank_candidate_confirmation_scan",
            "scanned_data_kinds": ["image_ink_features", "empty_ocr_confirmation"],
        },
        "review_required": {
            "processor": "human_review_or_retry_scan",
            "scanned_data_kinds": ["error_metadata", "retry_candidate_metadata"],
        },
    }
    return contracts.get(route, contracts["review_required"])


def _build_record(
    page: SourcePage,
    *,
    output_dir: Path,
    run_tesseract: bool,
    tesseract_cmd: str | None,
    psm_modes: Sequence[int],
    request_timeout: int,
    write_page_images: bool,
    write_text_sidecars: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    features = _image_features(page.image_bytes)
    tesseract_payload: dict[str, Any] = {"tesseract_execution_status": "not_requested"}
    text = ""
    if run_tesseract:
        if not tesseract_cmd:
            tesseract_payload = {"tesseract_execution_status": "missing_tesseract_cmd"}
        else:
            tesseract_payload = _run_tesseract_on_bytes(
                page.image_bytes,
                suffix=Path(page.file_name).suffix or ".tif",
                tesseract_cmd=tesseract_cmd,
                psm_modes=psm_modes,
                request_timeout=request_timeout,
            )
            text = tesseract_payload.get("best_ocr_text") or ""
    tokens = _tokens(text)
    part_numbers = sorted(set(PART_RE.findall(text)))
    numeric_tokens = NUMBER_RE.findall(text)
    table_keyword_count = _keyword_count(tokens, TABLE_KEYWORDS)
    visual_keyword_count = _keyword_count(tokens, VISUAL_KEYWORDS)
    route, confidence, route_reasons = _classify_route(
        text=text,
        image_features=features,
        tesseract_status=tesseract_payload.get("tesseract_execution_status"),
    )
    contract = _route_processor_contract(route)

    page_image_path = None
    if write_page_images:
        page_image_path = output_dir / "page_images" / f"{page.canonical_page_id}{Path(page.file_name).suffix.lower() or '.tif'}"
        page_image_path.parent.mkdir(parents=True, exist_ok=True)
        page_image_path.write_bytes(page.image_bytes)

    ocr_text_path = None
    if write_text_sidecars and text:
        ocr_text_path = output_dir / "ocr_text" / f"{page.canonical_page_id}.txt"
        ocr_text_path.parent.mkdir(parents=True, exist_ok=True)
        ocr_text_path.write_text(text, encoding="utf-8")

    record = {
        "module": MODULE,
        "version": VERSION,
        "record_type": "ocr_route_scan_page_record",
        "page_id": page.canonical_page_id,
        "source_page_id": page.page_id,
        "canonical_page_number": page.page_number,
        "source_member": page.source_member,
        "file_name": page.file_name,
        "source_image_sha256": page.sha256,
        "source_image_byte_count": page.byte_count,
        "source_image_path": str(page_image_path) if page_image_path else None,
        "ocr_text_path": str(ocr_text_path) if ocr_text_path else None,
        "ocr_text_sha256": _sha256_bytes(text.encode("utf-8")) if text else None,
        "ocr_text_char_count": len(text),
        "ocr_text_word_count": len(tokens),
        "ocr_sample_text": text[:1000],
        "part_number_tokens": part_numbers[:100],
        "part_number_token_count": len(part_numbers),
        "numeric_token_count": len(numeric_tokens),
        "table_keyword_count": table_keyword_count,
        "visual_keyword_count": visual_keyword_count,
        "accepted_route": route,
        "route_confidence": round(confidence, 4),
        "route_reasons": route_reasons,
        "route_processor": contract["processor"],
        "scanned_data_kinds": contract["scanned_data_kinds"],
        "tesseract_execution_status": tesseract_payload.get("tesseract_execution_status"),
        "tesseract_best_psm": tesseract_payload.get("best_psm"),
        "tesseract_attempt_count": tesseract_payload.get("tesseract_attempt_count", 0),
        "tesseract_attempts": tesseract_payload.get("tesseract_attempts", []),
        **features,
        "comparison_ready": True,
        "comparison_contract": {
            "raw_tiff_sha256": page.sha256,
            "compare_raw_tiff_to": ["source_image_sha256", "source_member", "canonical_page_number", "accepted_route", "ocr_text_sha256"],
            "one_to_one_page_mapping_required": True,
        },
        "safety_contract": SAFETY_CONTRACT,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }
    comparison = {
        "record_type": "raw_tiff_to_scan_metadata_comparison_pointer",
        "page_id": page.canonical_page_id,
        "source_page_id": page.page_id,
        "canonical_page_number": page.page_number,
        "source_member": page.source_member,
        "source_image_sha256": page.sha256,
        "source_image_byte_count": page.byte_count,
        "source_image_path": record["source_image_path"],
        "accepted_route": route,
        "route_processor": contract["processor"],
        "ocr_text_path": record["ocr_text_path"],
        "ocr_text_sha256": record["ocr_text_sha256"],
        "comparison_ready": True,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }
    return record, comparison


def _summary(records: list[dict[str, Any]], source_count: int, source_package: Path, *, run_tesseract: bool) -> dict[str, Any]:
    route_counts = Counter(r.get("accepted_route") for r in records)
    tesseract_counts = Counter(r.get("tesseract_execution_status") for r in records)
    image_feature_counts = Counter(r.get("image_feature_status") for r in records)
    return {
        "source_package": str(source_package),
        "source_page_count": source_count,
        "scan_record_count": len(records),
        "comparison_manifest_record_count": len(records),
        "run_tesseract": run_tesseract,
        "tesseract_execution_status_counts": dict(tesseract_counts),
        "image_feature_status_counts": dict(image_feature_counts),
        "route_counts": dict(route_counts),
        "page_with_ocr_text_count": sum(1 for r in records if int(r.get("ocr_text_char_count") or 0) > 0),
        "page_with_part_number_count": sum(1 for r in records if int(r.get("part_number_token_count") or 0) > 0),
        "raw_image_hash_count": sum(1 for r in records if r.get("source_image_sha256")),
        "one_to_one_comparison_ready_count": sum(1 for r in records if r.get("comparison_ready")),
        "table_route_count": route_counts.get("table", 0),
        "image_visual_route_count": route_counts.get("image_visual", 0),
        "normal_text_route_count": route_counts.get("normal_text", 0),
        "blank_candidate_route_count": route_counts.get("blank_candidate", 0),
        "review_required_route_count": route_counts.get("review_required", 0),
        "unsafe_record_count": 0,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }


def _quality_status(summary: Mapping[str, Any], *, require_source_count: int | None = None) -> str:
    if summary.get("unsafe_record_count"):
        return "FAIL"
    if summary.get("answer_permission_count"):
        return "FAIL"
    if summary.get("source_truth_mutation_allowed_count"):
        return "FAIL"
    if require_source_count is not None and int(summary.get("scan_record_count") or 0) < require_source_count:
        return "FAIL"
    return "PASS"


def build_ocr_route_scan_pack(
    *,
    source_package: str | Path,
    output_dir: str | Path,
    run_tesseract: bool = False,
    tesseract_cmd: str | None = None,
    psm_modes: Sequence[int] = (3, 6, 11),
    request_timeout: int = 180,
    max_pages: int | None = None,
    page_numbers: str | None = None,
    write_page_images: bool = False,
    write_text_sidecars: bool = True,
    quality: bool = False,
) -> dict[str, Any]:
    source_path = _normalize_git_bash_path(source_package)
    if source_path is None or not source_path.exists():
        raise FileNotFoundError(f"source package not found: {source_package}")
    out = _normalize_git_bash_path(output_dir) or Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    page_set = _parse_page_numbers(page_numbers)
    pages = _iter_source_pages(source_path, max_pages=max_pages, page_numbers=page_set)
    records: list[dict[str, Any]] = []
    comparison_records: list[dict[str, Any]] = []
    for page in pages:
        record, comparison = _build_record(
            page,
            output_dir=out,
            run_tesseract=run_tesseract,
            tesseract_cmd=tesseract_cmd,
            psm_modes=psm_modes,
            request_timeout=request_timeout,
            write_page_images=write_page_images,
            write_text_sidecars=write_text_sidecars,
        )
        records.append(record)
        comparison_records.append(comparison)

    summary = _summary(records, len(pages), source_path, run_tesseract=run_tesseract)
    status = "TRACE_NET_OCR_ROUTE_SCAN_PACK_BUILT"
    quality_status = _quality_status(summary, require_source_count=None if max_pages or page_set else 1)
    payload = {
        "module": MODULE,
        "version": VERSION,
        "status": status,
        "quality_status": quality_status,
        "summary": summary,
        "records": records,
        "comparison_manifest": comparison_records,
        "safety_contract": SAFETY_CONTRACT,
    }
    _write_json(out / REPORT_NAME, payload)
    _write_jsonl(out / RECORDS_NAME, records)
    _write_jsonl(out / COMPARISON_NAME, comparison_records)
    _write_json(out / SUMMARY_NAME, summary)
    _write_markdown(out / MARKDOWN_NAME, _markdown_report(payload))
    if quality:
        _write_json(out / QUALITY_NAME, {"quality_status": quality_status, "summary": summary})
    print(f"Status: {status}")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    return payload


def _markdown_report(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "# TRACE-Net OCR Route Scan Pack v1",
        "",
        f"Quality status: `{payload.get('quality_status')}`",
        "",
        "## Summary",
        "",
        "```json",
        json.dumps(summary, indent=2, sort_keys=True),
        "```",
        "",
        "## Authority",
        "",
        "This artifact is scan/router metadata and comparison guidance only. It is not source truth and grants no answer permission.",
    ]
    return "\n".join(lines) + "\n"


def check_quality(
    *,
    report_path: str | Path,
    write_json: bool = False,
    require_source_page_count: int | None = None,
    min_route_records: int = 1,
    min_raw_image_hash_count: int = 1,
    min_ocr_text_pages: int = 0,
    min_tesseract_attempted: int = 0,
    require_comparison_manifest: bool = False,
    max_unsafe: int | None = None,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
) -> dict[str, Any]:
    path = _normalize_git_bash_path(report_path) or Path(report_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    summary = payload.get("summary") or {}
    failures: list[str] = []
    if payload.get("quality_status") != "PASS":
        failures.append("manifest quality_status is not PASS")
    if require_source_page_count is not None and int(summary.get("source_page_count") or 0) < require_source_page_count:
        failures.append(f"not enough source pages: expected {require_source_page_count}")
    if int(summary.get("scan_record_count") or 0) < min_route_records:
        failures.append("not enough scan records")
    if int(summary.get("raw_image_hash_count") or 0) < min_raw_image_hash_count:
        failures.append("not enough raw image hashes")
    if int(summary.get("page_with_ocr_text_count") or 0) < min_ocr_text_pages:
        failures.append("not enough pages with OCR text")
    attempted = sum(v for k, v in (summary.get("tesseract_execution_status_counts") or {}).items() if k != "not_requested")
    if attempted < min_tesseract_attempted:
        failures.append("not enough tesseract attempted pages")
    if require_comparison_manifest and int(summary.get("comparison_manifest_record_count") or 0) < int(summary.get("scan_record_count") or 0):
        failures.append("comparison manifest is incomplete")
    if max_unsafe is not None and int(summary.get("unsafe_record_count") or 0) > max_unsafe:
        failures.append("too many unsafe records")
    if require_no_answer_permission and int(summary.get("answer_permission_count") or 0) != 0:
        failures.append("answer permission was granted")
    if require_no_source_truth_mutation and int(summary.get("source_truth_mutation_allowed_count") or 0) != 0:
        failures.append("source truth mutation was allowed")
    if require_no_write_attempts:
        for key in ["postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"]:
            if int(summary.get(key) or 0) != 0:
                failures.append(f"{key} was nonzero")
    quality_status = "FAIL" if failures else "PASS"
    result = {"quality_status": quality_status, "summary": summary, "failures": failures}
    if write_json:
        _write_json(path.with_name("trace_net_ocr_route_scan_pack_v1_quality_check.json"), result)
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures, indent=2))
    return result


def _parse_psm_modes(text: str) -> tuple[int, ...]:
    return tuple(int(x.strip()) for x in text.split(",") if x.strip())


def main_build(argv: Sequence[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Build TRACE-Net OCR route scan pack v1")
    parser.add_argument("--source-package", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-tesseract", action="store_true")
    parser.add_argument("--tesseract-cmd")
    parser.add_argument("--psm-modes", default="3,6,11")
    parser.add_argument("--request-timeout", type=int, default=180)
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--page-numbers")
    parser.add_argument("--write-page-images", action="store_true")
    parser.add_argument("--no-text-sidecars", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    return build_ocr_route_scan_pack(
        source_package=args.source_package,
        output_dir=args.output_dir,
        run_tesseract=args.run_tesseract,
        tesseract_cmd=args.tesseract_cmd,
        psm_modes=_parse_psm_modes(args.psm_modes),
        request_timeout=args.request_timeout,
        max_pages=args.max_pages,
        page_numbers=args.page_numbers,
        write_page_images=args.write_page_images,
        write_text_sidecars=not args.no_text_sidecars,
        quality=args.quality,
    )


def main_check(argv: Sequence[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Check TRACE-Net OCR route scan pack v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--require-source-page-count", type=int)
    parser.add_argument("--min-route-records", type=int, default=1)
    parser.add_argument("--min-raw-image-hash-count", type=int, default=1)
    parser.add_argument("--min-ocr-text-pages", type=int, default=0)
    parser.add_argument("--min-tesseract-attempted", type=int, default=0)
    parser.add_argument("--require-comparison-manifest", action="store_true")
    parser.add_argument("--max-unsafe", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args(argv)
    return check_quality(**vars(args))


if __name__ == "__main__":  # pragma: no cover
    main_build()
