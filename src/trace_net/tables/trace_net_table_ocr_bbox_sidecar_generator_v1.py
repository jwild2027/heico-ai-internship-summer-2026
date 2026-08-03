"""TRACE-Net Table OCR BBox Sidecar Generator v1.

This module generates local OCR bbox sidecars for resolved table page images. It is
read-only with respect to source truth and external stores: it only writes new
sidecar artifacts under the requested output directory.
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Mapping, MutableMapping, Sequence

try:  # support direct execution from scripts wrappers
    from tiff.trace_net_table_ocr_bbox_sidecar_generator_v1_quality import (
        SidecarQualityThresholds,
        evaluate_sidecar_generator_quality,
    )
except ModuleNotFoundError:  # pragma: no cover
    from trace_net_table_ocr_bbox_sidecar_generator_v1_quality import (  # type: ignore
        SidecarQualityThresholds,
        evaluate_sidecar_generator_quality,
    )

SCHEMA_VERSION = "trace_net_table_ocr_bbox_sidecar_generator_v1"
REPORT_NAME = "trace_net_table_ocr_bbox_sidecar_generator_v1.json"
QUALITY_NAME = "trace_net_table_ocr_bbox_sidecar_generator_v1_quality.json"
SUMMARY_NAME = "trace_net_table_ocr_bbox_sidecar_generator_v1_summary.json"
MANIFEST_NAME = "trace_net_table_ocr_bbox_sidecar_generator_v1_manifest.json"
CARDS_JSONL_NAME = "trace_net_table_ocr_bbox_sidecar_generator_v1_cards.jsonl"
PART_NUMBER_RE = re.compile(r"(?<!\d)(?:\d{2,3})-\d{4,6}-\d{3}(?!\d)")


@dataclass(frozen=True)
class GeneratorConfig:
    table_image_resolver_path: Path
    output_dir: Path
    table_line_geometry_path: Path | None = None
    table_cell_normalizer_path: Path | None = None
    image_root: Path = Path(".")
    tesseract_cmd: str = "tesseract"
    lang: str = "eng"
    psm: str = "6"
    oem: str | None = None
    max_pages: int = 20
    timeout_seconds: int = 120
    require_table_image_resolver_quality_pass: bool = False
    require_no_answer_permission: bool = False


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def stable_id(prefix: str, *parts: Any, length: int = 14) -> str:
    text = "||".join(str(p) for p in parts if p is not None)
    digest = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def read_json(path: Path | None) -> Mapping[str, Any]:
    if not path:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
            count += 1
    return count


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _norm_path(path: str | Path, root: Path | None = None) -> Path:
    p = Path(str(path).replace("\\", "/"))
    if p.is_absolute():
        return p
    return (root or Path(".")).joinpath(p).resolve()


def _read_image_size(path: Path) -> tuple[int | None, int | None]:
    try:
        from PIL import Image  # type: ignore
        with Image.open(path) as img:
            return int(img.width), int(img.height)
    except Exception:
        return None, None


def _quality_status(payload: Mapping[str, Any]) -> str | None:
    value = payload.get("quality_status") or (payload.get("summary") or {}).get("quality_status")
    return str(value) if value is not None else None


def load_source_cards(
    table_image_resolver: Mapping[str, Any],
    table_line_geometry: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return one source card per table image that has a resolved image path."""
    cards: list[dict[str, Any]] = []

    resolver_cards = table_image_resolver.get("table_image_resolution_cards") or []
    if isinstance(resolver_cards, list):
        for card in resolver_cards:
            if not isinstance(card, Mapping):
                continue
            image_path = card.get("resolved_image_path")
            if not image_path:
                continue
            cards.append({
                "page_id": card.get("page_id"),
                "table_id": card.get("table_id"),
                "table_type": card.get("table_type"),
                "resolved_image_path": image_path,
                "image_resolution_confidence": card.get("image_resolution_confidence"),
                "source": "table_image_resolver",
            })

    # Fallback to geometry if resolver has no cards.
    if not cards and table_line_geometry:
        for card in table_line_geometry.get("table_geometry_cards") or []:
            if not isinstance(card, Mapping):
                continue
            image_path = card.get("resolved_image_path")
            if not image_path:
                continue
            cards.append({
                "page_id": card.get("page_id"),
                "table_id": card.get("table_id"),
                "table_type": card.get("table_type"),
                "resolved_image_path": image_path,
                "image_resolution_confidence": None,
                "source": "table_line_geometry",
            })

    # Deduplicate by page_id + table_id + path while preserving order.
    seen: set[tuple[Any, Any, Any]] = set()
    unique: list[dict[str, Any]] = []
    for card in cards:
        key = (card.get("page_id"), card.get("table_id"), str(card.get("resolved_image_path")))
        if key in seen:
            continue
        seen.add(key)
        unique.append(card)
    return unique


def _walk_records(obj: Any) -> Iterator[Mapping[str, Any]]:
    if isinstance(obj, Mapping):
        yield obj
        for value in obj.values():
            yield from _walk_records(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_records(item)


def collect_table_tokens(table_cell_normalizer: Mapping[str, Any]) -> dict[tuple[str | None, str | None], dict[str, Any]]:
    """Collect text and part-number tokens by (page_id, table_id)."""
    out: dict[tuple[str | None, str | None], dict[str, Any]] = {}
    for record in _walk_records(table_cell_normalizer):
        page_id = record.get("page_id") or record.get("source_page_id")
        table_id = record.get("table_id") or record.get("normalized_table_id")
        text = record.get("text") or record.get("normalized_text") or record.get("value") or record.get("normalized_value")
        if not text:
            continue
        key = (str(page_id) if page_id is not None else None, str(table_id) if table_id is not None else None)
        bucket = out.setdefault(key, {"texts": [], "part_numbers": set()})
        text_s = str(text)
        if len(bucket["texts"]) < 500:
            bucket["texts"].append(text_s)
        for match in PART_NUMBER_RE.findall(text_s):
            bucket["part_numbers"].add(match)
    # convert sets for JSON friendliness in callers if used directly
    return out


def tesseract_available(tesseract_cmd: str) -> bool:
    if shutil.which(tesseract_cmd):
        return True
    # Windows users may pass an absolute path, and shutil.which can fail for quoted paths.
    return Path(str(tesseract_cmd).strip('"')).exists()


def run_tesseract_tsv(
    image_path: Path,
    *,
    tesseract_cmd: str,
    lang: str,
    psm: str,
    oem: str | None,
    timeout_seconds: int,
) -> tuple[str | None, str | None]:
    cmd = [tesseract_cmd, str(image_path), "stdout", "-l", lang, "--psm", str(psm), "tsv"]
    if oem:
        cmd[5:5] = ["--oem", str(oem)]
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        return None, f"tesseract_not_found: {exc}"
    except subprocess.TimeoutExpired as exc:
        return None, f"tesseract_timeout_after_{timeout_seconds}s"
    except Exception as exc:  # pragma: no cover - defensive
        return None, f"tesseract_exception: {exc}"

    if proc.returncode != 0:
        return None, f"tesseract_returncode_{proc.returncode}: {proc.stderr.strip()[:500]}"
    if not proc.stdout.strip():
        return None, "tesseract_empty_stdout"
    return proc.stdout, None


def parse_tesseract_tsv(tsv_text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(tsv_text.splitlines(), delimiter="\t")
    records: list[dict[str, Any]] = []
    for row in reader:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        try:
            conf = float(row.get("conf") or -1)
        except Exception:
            conf = -1.0
        try:
            left = int(float(row.get("left") or 0))
            top = int(float(row.get("top") or 0))
            width = int(float(row.get("width") or 0))
            height = int(float(row.get("height") or 0))
        except Exception:
            continue
        if width <= 0 or height <= 0:
            continue
        records.append({
            "level": int(float(row.get("level") or 0)),
            "page_num": int(float(row.get("page_num") or 0)),
            "block_num": int(float(row.get("block_num") or 0)),
            "par_num": int(float(row.get("par_num") or 0)),
            "line_num": int(float(row.get("line_num") or 0)),
            "word_num": int(float(row.get("word_num") or 0)),
            "text": text,
            "conf": conf,
            "bbox": {"x0": left, "y0": top, "x1": left + width, "y1": top + height, "width": width, "height": height},
        })
    return records


def group_word_records_into_lines(words: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[int, int, int, int], list[Mapping[str, Any]]] = {}
    for word in words:
        key = (
            int(word.get("page_num") or 0),
            int(word.get("block_num") or 0),
            int(word.get("par_num") or 0),
            int(word.get("line_num") or 0),
        )
        buckets.setdefault(key, []).append(word)

    lines: list[dict[str, Any]] = []
    for key, items in sorted(buckets.items(), key=lambda kv: (min((w.get("bbox") or {}).get("y0", 0) for w in kv[1]), min((w.get("bbox") or {}).get("x0", 0) for w in kv[1]))):
        sorted_items = sorted(items, key=lambda w: ((w.get("bbox") or {}).get("x0", 0), int(w.get("word_num") or 0)))
        xs0 = [(w.get("bbox") or {}).get("x0", 0) for w in sorted_items]
        ys0 = [(w.get("bbox") or {}).get("y0", 0) for w in sorted_items]
        xs1 = [(w.get("bbox") or {}).get("x1", 0) for w in sorted_items]
        ys1 = [(w.get("bbox") or {}).get("y1", 0) for w in sorted_items]
        text = " ".join(str(w.get("text") or "") for w in sorted_items).strip()
        confs = [float(w.get("conf") or 0) for w in sorted_items if float(w.get("conf") or -1) >= 0]
        lines.append({
            "line_key": {"page_num": key[0], "block_num": key[1], "par_num": key[2], "line_num": key[3]},
            "text": text,
            "word_count": len(sorted_items),
            "mean_conf": round(sum(confs) / len(confs), 3) if confs else None,
            "bbox": {"x0": min(xs0), "y0": min(ys0), "x1": max(xs1), "y1": max(ys1), "width": max(xs1) - min(xs0), "height": max(ys1) - min(ys0)},
            "words": [dict(w) for w in sorted_items],
        })
    return lines


def _combine_bbox(boxes: Sequence[Mapping[str, Any]]) -> dict[str, int] | None:
    boxes = [b for b in boxes if isinstance(b, Mapping)]
    if not boxes:
        return None
    x0 = min(int(float(b.get("x0", 0))) for b in boxes)
    y0 = min(int(float(b.get("y0", 0))) for b in boxes)
    x1 = max(int(float(b.get("x1", 0))) for b in boxes)
    y1 = max(int(float(b.get("y1", 0))) for b in boxes)
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "width": x1 - x0, "height": y1 - y0}


def find_part_number_matches(lines: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Find exact and split-token part numbers in OCR lines with bboxes."""
    matches: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int, int, int]] = set()
    for line_idx, line in enumerate(lines):
        words = line.get("words") or []
        if not isinstance(words, list):
            continue
        line_text = str(line.get("text") or "")

        # Normal exact matches in the rendered line text.
        for match in PART_NUMBER_RE.finditer(line_text):
            token = match.group(0)
            # include words whose text overlaps token loosely.
            token_words = [w for w in words if token in str(w.get("text") or "") or str(w.get("text") or "") in token]
            if not token_words:
                token_words = words
            bbox = _combine_bbox([(w.get("bbox") or {}) for w in token_words])
            if not bbox:
                continue
            key = (token, bbox["x0"], bbox["y0"], bbox["x1"], bbox["y1"])
            if key in seen:
                continue
            seen.add(key)
            matches.append({"part_number": token, "match_type": "exact_line_text", "line_index": line_idx, "line_text": line_text, "bbox": bbox})

        # Split-token repair: join adjacent word text without spaces and map chars to words.
        compact = ""
        char_to_word: list[int] = []
        for idx, word in enumerate(words):
            cleaned = re.sub(r"[^A-Za-z0-9-]", "", str(word.get("text") or ""))
            if not cleaned:
                continue
            for ch in cleaned:
                compact += ch
                char_to_word.append(idx)
        for match in PART_NUMBER_RE.finditer(compact):
            token = match.group(0)
            word_indices = sorted(set(char_to_word[match.start():match.end()]))
            token_words = [words[i] for i in word_indices if 0 <= i < len(words)]
            bbox = _combine_bbox([(w.get("bbox") or {}) for w in token_words])
            if not bbox:
                continue
            key = (token, bbox["x0"], bbox["y0"], bbox["x1"], bbox["y1"])
            if key in seen:
                continue
            seen.add(key)
            matches.append({"part_number": token, "match_type": "split_token_repair", "line_index": line_idx, "line_text": line_text, "bbox": bbox})
    return matches


def infer_table_candidate_bbox(
    words: Sequence[Mapping[str, Any]],
    lines: Sequence[Mapping[str, Any]],
    part_matches: Sequence[Mapping[str, Any]],
    *,
    image_width: int | None,
    image_height: int | None,
) -> dict[str, Any] | None:
    """Infer a broad table region from part-number rows or dense OCR lines."""
    boxes: list[Mapping[str, Any]] = []
    source = "ocr_dense_line_bbox"
    if part_matches:
        y_min = min((m.get("bbox") or {}).get("y0", 0) for m in part_matches)
        y_max = max((m.get("bbox") or {}).get("y1", 0) for m in part_matches)
        band_margin = max(120, int((y_max - y_min + 1) * 0.75))
        lo, hi = max(0, int(y_min) - band_margin), int(y_max) + band_margin
        for line in lines:
            bbox = line.get("bbox") or {}
            if int(bbox.get("y1", 0)) >= lo and int(bbox.get("y0", 0)) <= hi:
                boxes.append(bbox)
        source = "part_number_ocr_line_band_bbox"
    else:
        # Dense lines with three or more words are often table/text lines. Keep broad fallback.
        for line in lines:
            if int(line.get("word_count") or 0) >= 3:
                boxes.append(line.get("bbox") or {})

    bbox = _combine_bbox(boxes)
    if not bbox:
        return None

    # Expand but clamp to image when dimensions are known.
    margin_x = max(20, int(bbox["width"] * 0.08))
    margin_y = max(20, int(bbox["height"] * 0.08))
    x0 = bbox["x0"] - margin_x
    y0 = bbox["y0"] - margin_y
    x1 = bbox["x1"] + margin_x
    y1 = bbox["y1"] + margin_y
    if image_width:
        x0, x1 = max(0, x0), min(int(image_width), x1)
    if image_height:
        y0, y1 = max(0, y0), min(int(image_height), y1)
    region = {"x0": int(x0), "y0": int(y0), "x1": int(x1), "y1": int(y1), "width": int(x1 - x0), "height": int(y1 - y0)}
    area = max(1, region["width"] * region["height"])
    page_area = max(1, (image_width or region["x1"] or 1) * (image_height or region["y1"] or 1))
    region["coverage_ratio"] = round(area / page_area, 6)
    return {"bbox": region, "bbox_source": source}


def _sidecar_base_name(page_id: Any, image_path: Path) -> str:
    safe_page = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(page_id or "page"))
    return f"{safe_page}__{image_path.stem}"


def generate_sidecars_for_card(
    card: Mapping[str, Any],
    *,
    config: GeneratorConfig,
    sidecar_dir: Path,
    token_bucket: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    page_id = card.get("page_id")
    table_id = card.get("table_id")
    image_path_raw = card.get("resolved_image_path")
    image_path = _norm_path(str(image_path_raw), config.image_root)
    base_name = _sidecar_base_name(page_id, image_path)
    tsv_path = sidecar_dir / f"{base_name}.tsv"
    word_jsonl_path = sidecar_dir / f"{base_name}_ocr_bboxes.jsonl"
    line_jsonl_path = sidecar_dir / f"{base_name}_ocr_lines.jsonl"
    part_jsonl_path = sidecar_dir / f"{base_name}_part_number_matches.jsonl"
    summary_json_path = sidecar_dir / f"{base_name}_summary.json"

    width, height = _read_image_size(image_path)
    result: dict[str, Any] = {
        "sidecar_card_id": stable_id("table_ocr_sidecar", page_id, table_id, image_path_raw),
        "page_id": page_id,
        "table_id": table_id,
        "table_type": card.get("table_type"),
        "resolved_image_path": str(image_path_raw),
        "resolved_image_exists": image_path.exists(),
        "image_width": width,
        "image_height": height,
        "tesseract_cmd": config.tesseract_cmd,
        "tesseract_lang": config.lang,
        "tesseract_psm": str(config.psm),
        "sidecar_status": "NOT_RUN",
        "tsv_sidecar_path": str(tsv_path.as_posix()),
        "ocr_bbox_jsonl_path": str(word_jsonl_path.as_posix()),
        "ocr_line_jsonl_path": str(line_jsonl_path.as_posix()),
        "part_number_match_jsonl_path": str(part_jsonl_path.as_posix()),
        "summary_json_path": str(summary_json_path.as_posix()),
        "ocr_word_record_count": 0,
        "ocr_line_record_count": 0,
        "part_number_match_count": 0,
        "table_candidate_bbox": None,
        "table_candidate_bbox_source": None,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "retrieval_only_answer_allowed": False,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "unsafe_sidecar_card": False,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "review_required": False,
        "review_flags": [],
        "recommended_actions": [],
    }

    if not image_path.exists():
        result.update({"sidecar_status": "IMAGE_NOT_FOUND", "tesseract_error": f"image_not_found: {image_path}"})
        result["review_required"] = True
        result["review_flags"].append("resolved_image_not_found")
        result["recommended_actions"].append("check_table_image_resolver_paths")
        return result

    tsv_text, error = run_tesseract_tsv(
        image_path,
        tesseract_cmd=config.tesseract_cmd,
        lang=config.lang,
        psm=config.psm,
        oem=config.oem,
        timeout_seconds=config.timeout_seconds,
    )
    if error or not tsv_text:
        result.update({"sidecar_status": "TESSERACT_FAILED", "tesseract_error": error or "tesseract_no_output"})
        result["review_required"] = True
        result["review_flags"].append("tesseract_ocr_failed")
        result["recommended_actions"].append("install_or_configure_tesseract_for_ocr_bbox_sidecars")
        return result

    tsv_path.parent.mkdir(parents=True, exist_ok=True)
    tsv_path.write_text(tsv_text, encoding="utf-8", newline="\n")
    words = parse_tesseract_tsv(tsv_text)
    # annotate with page/table context for downstream enrichment.
    word_rows: list[dict[str, Any]] = []
    for i, word in enumerate(words):
        row = dict(word)
        row.update({
            "ocr_bbox_record_id": stable_id("ocrbbox", page_id, table_id, i, row.get("text")),
            "page_id": page_id,
            "table_id": table_id,
            "table_type": card.get("table_type"),
            "resolved_image_path": str(image_path_raw),
            "source_sidecar": str(tsv_path.as_posix()),
            "bbox_source": "tesseract_tsv",
        })
        word_rows.append(row)
    lines = group_word_records_into_lines(word_rows)
    part_matches = find_part_number_matches(lines)
    table_bbox = infer_table_candidate_bbox(word_rows, lines, part_matches, image_width=width, image_height=height)

    # Add page/table context to match and line records.
    line_rows: list[dict[str, Any]] = []
    for i, line in enumerate(lines):
        row = dict(line)
        row.update({
            "ocr_line_record_id": stable_id("ocrline", page_id, table_id, i, row.get("text")),
            "page_id": page_id,
            "table_id": table_id,
            "table_type": card.get("table_type"),
            "resolved_image_path": str(image_path_raw),
            "source_sidecar": str(tsv_path.as_posix()),
            "bbox_source": "tesseract_tsv",
        })
        # Avoid duplicating all nested word details in line sidecars; the word JSONL is authoritative.
        row.pop("words", None)
        line_rows.append(row)

    part_rows: list[dict[str, Any]] = []
    for i, match in enumerate(part_matches):
        row = dict(match)
        row.update({
            "part_number_match_id": stable_id("partocr", page_id, table_id, i, row.get("part_number")),
            "page_id": page_id,
            "table_id": table_id,
            "table_type": card.get("table_type"),
            "resolved_image_path": str(image_path_raw),
            "source_sidecar": str(tsv_path.as_posix()),
            "bbox_source": "tesseract_tsv",
        })
        part_rows.append(row)

    write_jsonl(word_jsonl_path, word_rows)
    write_jsonl(line_jsonl_path, line_rows)
    write_jsonl(part_jsonl_path, part_rows)

    sidecar_summary = {
        "schema_version": "trace_net_table_ocr_bbox_sidecar_page_summary_v1",
        "page_id": page_id,
        "table_id": table_id,
        "table_type": card.get("table_type"),
        "resolved_image_path": str(image_path_raw),
        "image_width": width,
        "image_height": height,
        "ocr_word_record_count": len(word_rows),
        "ocr_line_record_count": len(line_rows),
        "part_number_match_count": len(part_rows),
        "part_numbers_sample": sorted({r.get("part_number") for r in part_rows if r.get("part_number")})[:25],
        "table_candidate_bbox": table_bbox.get("bbox") if table_bbox else None,
        "table_candidate_bbox_source": table_bbox.get("bbox_source") if table_bbox else None,
        "tsv_sidecar_path": str(tsv_path.as_posix()),
        "ocr_bbox_jsonl_path": str(word_jsonl_path.as_posix()),
        "ocr_line_jsonl_path": str(line_jsonl_path.as_posix()),
        "part_number_match_jsonl_path": str(part_jsonl_path.as_posix()),
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }
    write_json(summary_json_path, sidecar_summary)

    result.update({
        "sidecar_status": "GENERATED",
        "tsv_sidecar_exists": tsv_path.exists(),
        "ocr_bbox_jsonl_exists": word_jsonl_path.exists(),
        "ocr_line_jsonl_exists": line_jsonl_path.exists(),
        "part_number_match_jsonl_exists": part_jsonl_path.exists(),
        "ocr_word_record_count": len(word_rows),
        "ocr_line_record_count": len(line_rows),
        "part_number_match_count": len(part_rows),
        "part_numbers_sample": sidecar_summary["part_numbers_sample"],
        "table_candidate_bbox": sidecar_summary["table_candidate_bbox"],
        "table_candidate_bbox_source": sidecar_summary["table_candidate_bbox_source"],
    })
    if not word_rows:
        result["review_required"] = True
        result["review_flags"].append("ocr_tsv_generated_no_words")
        result["recommended_actions"].append("review_tesseract_page_segmentation_mode")
    if not part_rows and card.get("table_type") == "parts_list_table":
        result["review_required"] = True
        result["review_flags"].append("parts_list_table_without_part_number_ocr_matches")
        result["recommended_actions"].append("review_ocr_part_number_split_token_repair")
    return result


def build_sidecar_generator_report(
    config: GeneratorConfig,
    thresholds: SidecarQualityThresholds,
    *,
    quality: bool = True,
) -> dict[str, Any]:
    output_dir = config.output_dir
    sidecar_dir = output_dir / "sidecars"
    output_dir.mkdir(parents=True, exist_ok=True)
    sidecar_dir.mkdir(parents=True, exist_ok=True)

    table_image_resolver = read_json(config.table_image_resolver_path)
    table_line_geometry = read_json(config.table_line_geometry_path) if config.table_line_geometry_path else {}
    table_cell_normalizer = read_json(config.table_cell_normalizer_path) if config.table_cell_normalizer_path else {}

    source_cards = load_source_cards(table_image_resolver, table_line_geometry)
    source_cards = source_cards[: max(0, config.max_pages)]
    token_buckets = collect_table_tokens(table_cell_normalizer) if table_cell_normalizer else {}

    cards: list[dict[str, Any]] = []
    for card in source_cards:
        key = (str(card.get("page_id")) if card.get("page_id") is not None else None, str(card.get("table_id")) if card.get("table_id") is not None else None)
        cards.append(generate_sidecars_for_card(card, config=config, sidecar_dir=sidecar_dir, token_bucket=token_buckets.get(key)))

    generated = [c for c in cards if c.get("sidecar_status") == "GENERATED"]
    tesseract_errors = [c for c in cards if c.get("sidecar_status") == "TESSERACT_FAILED"]
    image_errors = [c for c in cards if c.get("sidecar_status") == "IMAGE_NOT_FOUND"]

    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": "TABLE_OCR_BBOX_SIDECARS_BUILT",
        "quality_status": "PENDING",
        "source_table_image_card_count": len(source_cards),
        "attempted_page_count": len(cards),
        "generated_sidecar_page_count": len(generated),
        "failed_sidecar_page_count": len(cards) - len(generated),
        "image_not_found_count": len(image_errors),
        "tesseract_available": tesseract_available(config.tesseract_cmd),
        "tesseract_error_count": len(tesseract_errors),
        "tsv_sidecar_count": sum(1 for c in generated if c.get("tsv_sidecar_exists")),
        "jsonl_sidecar_count": sum(1 for c in generated if c.get("ocr_bbox_jsonl_exists")),
        "ocr_word_record_count": sum(int(c.get("ocr_word_record_count") or 0) for c in cards),
        "ocr_line_record_count": sum(int(c.get("ocr_line_record_count") or 0) for c in cards),
        "part_number_match_count": sum(int(c.get("part_number_match_count") or 0) for c in cards),
        "table_candidate_bbox_count": sum(1 for c in cards if c.get("table_candidate_bbox")),
        "review_required_card_count": sum(1 for c in cards if c.get("review_required")),
        "unsafe_sidecar_card_count": sum(1 for c in cards if c.get("unsafe_sidecar_card")),
        "answer_permission_count": sum(1 for c in cards if c.get("answer_permission")),
        "can_answer_directly_count": sum(1 for c in cards if c.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for c in cards if c.get("can_prove_claims")),
        "retrieval_only_answer_allowed_count": sum(1 for c in cards if c.get("retrieval_only_answer_allowed")),
        "source_truth_mutation_allowed_count": sum(1 for c in cards if c.get("source_truth_mutation_allowed")),
        "source_truth_mutations_performed": sum(int(c.get("source_truth_mutations_performed") or 0) for c in cards),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "table_image_resolver_quality_status": _quality_status(table_image_resolver),
        "table_line_geometry_quality_status": _quality_status(table_line_geometry) if table_line_geometry else None,
        "table_cell_normalizer_quality_status": _quality_status(table_cell_normalizer) if table_cell_normalizer else None,
        "sidecar_output_dir": str(sidecar_dir.as_posix()),
        "tesseract_cmd": config.tesseract_cmd,
        "tesseract_lang": config.lang,
        "tesseract_psm": str(config.psm),
    }

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "status": "TABLE_OCR_BBOX_SIDECARS_BUILT",
        "quality_status": "PENDING",
        "summary": summary,
        "source_paths": {
            "table_image_resolver": str(config.table_image_resolver_path.as_posix()),
            "table_line_geometry": str(config.table_line_geometry_path.as_posix()) if config.table_line_geometry_path else None,
            "table_cell_normalizer": str(config.table_cell_normalizer_path.as_posix()) if config.table_cell_normalizer_path else None,
            "image_root": str(config.image_root.as_posix()),
        },
        "sidecar_cards": cards,
        "safety_contract": {
            "read_only_source_truth": True,
            "no_postgres_writes": True,
            "no_qdrant_writes": True,
            "no_opensearch_writes": True,
            "no_source_truth_mutation": True,
            "no_answer_permission": True,
            "no_claim_proof_authority": True,
            "sidecars_are_advisory_ocr_bbox_artifacts": True,
        },
    }

    quality_payload = evaluate_sidecar_generator_quality(report, thresholds) if quality else {"quality_status": "NOT_RUN", "checks": {}}
    report["quality_status"] = quality_payload.get("quality_status")
    report["status"] = "TABLE_OCR_BBOX_SIDECARS_BUILT" if report["quality_status"] == "PASS" else "TABLE_OCR_BBOX_SIDECARS_NOT_READY"
    report["summary"]["quality_status"] = report["quality_status"]
    report["summary"]["status"] = report["status"]
    report["quality_fail_reasons"] = quality_payload.get("quality_fail_reasons", [])
    report["checks"] = quality_payload.get("checks", {})
    return report


def write_report_artifacts(report: Mapping[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / REPORT_NAME
    quality_path = output_dir / QUALITY_NAME
    summary_path = output_dir / SUMMARY_NAME
    manifest_path = output_dir / MANIFEST_NAME
    cards_path = output_dir / CARDS_JSONL_NAME

    write_json(report_path, report)
    quality_payload = {
        "schema_version": "trace_net_table_ocr_bbox_sidecar_generator_v1_quality",
        "status": report.get("quality_status"),
        "quality_status": report.get("quality_status"),
        "checks": report.get("checks", {}),
        "summary": report.get("summary", {}),
        "quality_fail_reasons": report.get("quality_fail_reasons", []),
    }
    write_json(quality_path, quality_payload)
    write_json(summary_path, report.get("summary", {}))
    write_json(manifest_path, {
        "schema_version": "trace_net_table_ocr_bbox_sidecar_generator_v1_manifest",
        "generated_at": report.get("generated_at"),
        "report_path": str(report_path.as_posix()),
        "quality_path": str(quality_path.as_posix()),
        "summary_path": str(summary_path.as_posix()),
        "cards_path": str(cards_path.as_posix()),
        "sidecar_output_dir": (report.get("summary") or {}).get("sidecar_output_dir"),
    })
    write_jsonl(cards_path, report.get("sidecar_cards") or [])
    return {"report_path": str(report_path), "quality_path": str(quality_path), "summary_path": str(summary_path), "manifest_path": str(manifest_path), "cards_path": str(cards_path)}


def _add_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--table-image-resolver", required=True)
    parser.add_argument("--table-line-geometry")
    parser.add_argument("--table-cell-normalizer")
    parser.add_argument("--image-root", default=".")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--tesseract-cmd", default="tesseract")
    parser.add_argument("--lang", default="eng")
    parser.add_argument("--psm", default="6")
    parser.add_argument("--oem")
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--min-source-cards", type=int, default=1)
    parser.add_argument("--min-attempted-pages", type=int, default=1)
    parser.add_argument("--min-generated-sidecar-pages", type=int, default=1)
    parser.add_argument("--min-ocr-word-records", type=int, default=1)
    parser.add_argument("--min-part-number-matches", type=int, default=0)
    parser.add_argument("--max-tesseract-error-count", type=int, default=None)
    parser.add_argument("--max-unsafe-sidecar-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-image-resolver-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-tesseract-available", action="store_true")
    parser.add_argument("--quality", action="store_true")


def config_from_args(args: argparse.Namespace) -> GeneratorConfig:
    return GeneratorConfig(
        table_image_resolver_path=Path(args.table_image_resolver),
        table_line_geometry_path=Path(args.table_line_geometry) if args.table_line_geometry else None,
        table_cell_normalizer_path=Path(args.table_cell_normalizer) if args.table_cell_normalizer else None,
        image_root=Path(args.image_root),
        output_dir=Path(args.output_dir),
        tesseract_cmd=args.tesseract_cmd,
        lang=args.lang,
        psm=str(args.psm),
        oem=args.oem,
        max_pages=args.max_pages,
        timeout_seconds=args.timeout_seconds,
        require_table_image_resolver_quality_pass=args.require_table_image_resolver_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )


def thresholds_from_args(args: argparse.Namespace) -> SidecarQualityThresholds:
    return SidecarQualityThresholds(
        min_source_cards=args.min_source_cards,
        min_attempted_pages=args.min_attempted_pages,
        min_generated_sidecar_pages=args.min_generated_sidecar_pages,
        min_ocr_word_records=args.min_ocr_word_records,
        min_part_number_matches=args.min_part_number_matches,
        max_tesseract_error_count=args.max_tesseract_error_count,
        max_unsafe_sidecar_cards=args.max_unsafe_sidecar_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_table_image_resolver_quality_pass=args.require_table_image_resolver_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
        require_tesseract_available=args.require_tesseract_available,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate TRACE-Net OCR bbox sidecars for resolved table pages.")
    _add_args(parser)
    args = parser.parse_args(argv)
    config = config_from_args(args)
    thresholds = thresholds_from_args(args)
    report = build_sidecar_generator_report(config, thresholds, quality=args.quality)
    paths = write_report_artifacts(report, config.output_dir)
    summary = report.get("summary", {})

    print("TRACE-Net Table OCR BBox Sidecar Generator v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "source_table_image_card_count",
        "attempted_page_count",
        "generated_sidecar_page_count",
        "failed_sidecar_page_count",
        "tsv_sidecar_count",
        "jsonl_sidecar_count",
        "ocr_word_record_count",
        "ocr_line_record_count",
        "part_number_match_count",
        "table_candidate_bbox_count",
        "tesseract_available",
        "tesseract_error_count",
        "unsafe_sidecar_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key, 0)}")
    print(f" report_path: {paths['report_path']}")
    print(f" quality_path: {paths['quality_path']}")
    return 0 if report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
