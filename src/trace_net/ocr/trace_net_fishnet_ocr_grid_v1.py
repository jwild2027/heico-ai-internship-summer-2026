"""TRACE-Net Fishnet OCR Grid v1.

Read-only fishnet/grid analysis for scanned TIFF pages.

This module creates page-scoped grid cards that combine spatial ink features
with optional OCR text features. The output is intentionally a router/classifier
input artifact, not an answer artifact. It never writes to Postgres, Qdrant, or
OpenSearch, never mutates source truth, and never grants answer permission.

Typical use:
    python scripts/build/ocr/build_trace_net_fishnet_ocr_grid_v1.py \
      --source-package local_data/source_packages/metadata.zip \
      --output-dir local_data/organization/trace_net/fishnet_ocr_grid \
      --rows 8 \
      --cols 6 \
      --ocr-mode available \
      --ocr-scope cell \
      --quality
"""

from __future__ import annotations

import argparse
import io
import json
import math
import re
import statistics
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

try:  # Pillow is expected in the project stack but kept optional for import tests.
    from PIL import Image, ImageDraw, ImageOps
except Exception:  # pragma: no cover - exercised only when Pillow is absent.
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]
    ImageOps = None  # type: ignore[assignment]

MODULE_NAME = "trace_net_fishnet_ocr_grid_v1"
VERSION = "v1.5"
DEFAULT_REPORT_NAME = "trace_net_fishnet_ocr_grid_v1.json"
DEFAULT_CARDS_NAME = "trace_net_fishnet_ocr_grid_v1_cards.jsonl"
DEFAULT_SUMMARY_NAME = "trace_net_fishnet_ocr_grid_v1_summary.json"
DEFAULT_QUALITY_NAME = "trace_net_fishnet_ocr_grid_v1_quality.json"
DEFAULT_CONTACT_SHEET_NAME = "trace_net_fishnet_ocr_grid_contact_sheet_v1.png"

IMAGE_SUFFIXES = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".webp", ".bmp"}
XML_SUFFIXES = {".xml"}
PAGE_ID_RE = re.compile(r"(?:^|[_-])(p\d{3,6})(?:\D|$)", re.IGNORECASE)
PART_NUMBER_RE = re.compile(r"\b\d{2,4}-\d{3,6}(?:-\d{2,4})?\b")
NUMBER_RE = re.compile(r"\b\d+(?:[.-]\d+)*\b")
CALLOUT_RE = re.compile(r"\b(?:FIG\.?|ITEM|DETAIL|SEE|REF\.?|IPL|ATA)\b", re.IGNORECASE)
TABLE_KEYWORD_RE = re.compile(r"\b(?:CHAPTER|SECTION|SUBJECT|PAGE|DATE|ITEM|PART|PARTS|NUMBER|NOMENCLATURE|QTY|QUANTITY|EFFECTIVITY|APPLICABILITY|INDEX|LIST)\b", re.IGNORECASE)
VISUAL_KEYWORD_RE = re.compile(r"\b(?:FIG\.?|FIGURE|DETAIL|VIEW|CALLOUT|ILLUSTRATION|ASSEMBLY|EXPLODED)\b", re.IGNORECASE)

SAFETY_CONTRACT: dict[str, Any] = {
    "artifact_authority": "router_classifier_input_only",
    "can_answer_directly": False,
    "can_prove_claims": False,
    "answer_permission": False,
    "source_truth_mutation_allowed": False,
    "postgres_write_allowed": False,
    "qdrant_write_allowed": False,
    "opensearch_write_allowed": False,
    "raw_scan_query_time_allowed": False,
    "requires_downstream_source_truth_confirmation": True,
    "guidance_only": True,
}


@dataclass(frozen=True)
class SourcePage:
    """A source page image discovered in a zip package or directory."""

    page_id: str
    source_path: str
    file_name: str
    page_number: int | None
    package_kind: str
    zip_path: str | None = None


def _safe_json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")


def _jsonl_dump(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=False) + "\n")


def _derive_page_id(path_text: str, ordinal: int) -> str:
    stem = Path(path_text).stem
    cleaned_stem = re.sub(r"[^A-Za-z0-9_\-]+", "_", stem).strip("_")
    match = PAGE_ID_RE.search(cleaned_stem)
    if match and cleaned_stem.startswith("t_p_"):
        return cleaned_stem
    if cleaned_stem.startswith("t_p_"):
        return cleaned_stem
    if match:
        page_token = match.group(1).lower()
        return f"source_{page_token}"
    return f"source_p{ordinal:06d}"


def _derive_page_number(path_text: str, ordinal: int) -> int | None:
    match = PAGE_ID_RE.search(Path(path_text).stem)
    if not match:
        return ordinal
    digits = re.sub(r"\D", "", match.group(1))
    try:
        return int(digits)
    except ValueError:
        return ordinal


def discover_source_pages(source_package: Path) -> list[SourcePage]:
    """Discover page images from a metadata zip or directory.

    The uploaded sample package uses a zip containing metadata.xml plus TIFF
    pages. This function also supports an unpacked directory so the same module
    works after the corpus is staged on a server.
    """

    source_package = Path(source_package)
    if not source_package.exists():
        raise FileNotFoundError(f"source package not found: {source_package}")

    pages: list[SourcePage] = []
    if source_package.is_file() and zipfile.is_zipfile(source_package):
        with zipfile.ZipFile(source_package) as zf:
            image_names = sorted(
                name
                for name in zf.namelist()
                if not name.endswith("/") and Path(name).suffix.lower() in IMAGE_SUFFIXES
            )
        for ordinal, name in enumerate(image_names, start=1):
            pages.append(
                SourcePage(
                    page_id=_derive_page_id(name, ordinal),
                    source_path=name,
                    file_name=Path(name).name,
                    page_number=_derive_page_number(name, ordinal),
                    package_kind="zip",
                    zip_path=str(source_package),
                )
            )
        return pages

    if source_package.is_dir():
        image_paths = sorted(
            path
            for path in source_package.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
        for ordinal, path in enumerate(image_paths, start=1):
            rel = str(path.relative_to(source_package))
            pages.append(
                SourcePage(
                    page_id=_derive_page_id(rel, ordinal),
                    source_path=rel,
                    file_name=path.name,
                    page_number=_derive_page_number(rel, ordinal),
                    package_kind="directory",
                    zip_path=None,
                )
            )
        return pages

    raise ValueError(f"unsupported source package: {source_package}")


def _open_page_image(source_package: Path, page: SourcePage):
    if Image is None:
        raise RuntimeError("Pillow is required to analyze page images")
    if page.package_kind == "zip":
        with zipfile.ZipFile(source_package) as zf:
            raw = zf.read(page.source_path)
        image = Image.open(io.BytesIO(raw))
    else:
        image = Image.open(source_package / page.source_path)
    image.load()
    return image.convert("RGB")


def _cell_bbox(width: int, height: int, row: int, col: int, rows: int, cols: int) -> tuple[int, int, int, int]:
    left = int(round(col * width / cols))
    top = int(round(row * height / rows))
    right = int(round((col + 1) * width / cols))
    bottom = int(round((row + 1) * height / rows))
    return left, top, max(left + 1, right), max(top + 1, bottom)


def _ink_features(image) -> dict[str, Any]:
    if ImageOps is None:
        return {"ink_pixel_count": 0, "total_pixel_count": 0, "ink_ratio": 0.0, "mean_darkness": 0.0}
    gray = ImageOps.grayscale(image)
    # Downsample large cells/pages for deterministic low-cost analysis.
    max_side = 384
    if max(gray.size) > max_side:
        gray.thumbnail((max_side, max_side))
    pixels = list(gray.getdata())
    total = len(pixels) or 1
    ink_pixels = sum(1 for px in pixels if px < 245)
    darkness_values = [(255 - px) / 255.0 for px in pixels]
    return {
        "ink_pixel_count": ink_pixels,
        "total_pixel_count": total,
        "ink_ratio": round(ink_pixels / total, 6),
        "mean_darkness": round(sum(darkness_values) / total, 6),
    }


def _unique_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            unique.append(cleaned)
    return unique


def _ocr_configs(primary_config: str) -> list[str]:
    """Return conservative OCR configs for scanned manual pages.

    A single Tesseract page-segmentation mode can silently return empty text on
    noisy scans. v1.2 treats empty OCR as a diagnosable status and tries a small
    deterministic config ladder before giving up.
    """

    return _unique_strings([
        primary_config,
        "--oem 3 --psm 6",
        "--oem 3 --psm 11",
        "--oem 3 --psm 3",
    ])


def _ocr_image_variants(image) -> list[tuple[str, Any]]:
    """Build a small set of deterministic image variants for OCR fallback."""

    if ImageOps is None:
        return [("original", image)]

    variants: list[tuple[str, Any]] = [("original", image)]
    gray = ImageOps.grayscale(image)
    variants.append(("grayscale", gray))
    try:
        autocontrast = ImageOps.autocontrast(gray)
    except Exception:
        autocontrast = gray
    variants.append(("autocontrast", autocontrast))

    # Tesseract often does better on scanned TIFF pages after a light upscale.
    try:
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        w, h = autocontrast.size
        if max(w, h) < 4200:
            upscaled = autocontrast.resize((max(1, w * 2), max(1, h * 2)), resampling)
            variants.append(("autocontrast_x2", upscaled))
    except Exception:
        pass

    try:
        thresholded = autocontrast.point(lambda px: 0 if px < 200 else 255, mode="1")
        variants.append(("threshold_200", thresholded))
    except Exception:
        pass

    return variants


def _ocr_text(
    image,
    *,
    ocr_mode: str,
    tesseract_cmd: str | None = None,
    tesseract_config: str = "--psm 6",
    request_timeout_note: str = "",
) -> tuple[str, str, str | None]:
    """Return OCR text, status, and optional error string.

    Status values:
      disabled    -> OCR intentionally skipped
      unavailable -> pytesseract/Tesseract not available
      failed      -> Tesseract raised an exception
      empty       -> Tesseract ran but produced no text after fallbacks
      ok          -> non-empty OCR text was produced
    """

    if ocr_mode == "disabled":
        return "", "disabled", None
    try:
        import pytesseract  # type: ignore
    except Exception as exc:
        if ocr_mode == "required":
            raise RuntimeError(f"pytesseract import failed: {exc}") from exc
        return "", "unavailable", f"pytesseract import failed: {exc}"

    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = str(tesseract_cmd)

    errors: list[str] = []
    empty_attempts: list[str] = []
    for variant_name, ocr_image in _ocr_image_variants(image):
        for config in _ocr_configs(tesseract_config):
            try:
                text = pytesseract.image_to_string(ocr_image, config=config) or ""
            except Exception as exc:
                errors.append(f"{variant_name}|{config}: {exc}")
                continue
            text = text.strip()
            if text:
                return text, "ok", None
            empty_attempts.append(f"{variant_name}|{config}")

    hint = (
        "Tesseract ran but produced empty text. This usually means the page needs OCR preprocessing, "
        "a different psm, or the source image is mostly visual/blank. v1.2 records this as empty, not ok."
    )
    if errors and not empty_attempts:
        error_text = f"tesseract OCR failed after fallbacks: {'; '.join(errors[:3])}. {request_timeout_note}".strip()
        if ocr_mode == "required":
            raise RuntimeError(error_text)
        return "", "failed", error_text
    return "", "empty", f"{hint} attempted={empty_attempts[:6]} errors={errors[:2]}"



def _parse_confidence(value: Any) -> float | None:
    try:
        score = float(value)
    except Exception:
        return None
    if score < 0:
        return None
    return score


def _ocr_word_boxes(
    image,
    *,
    ocr_mode: str,
    tesseract_cmd: str | None = None,
    tesseract_config: str = "--psm 6",
) -> tuple[list[dict[str, Any]], str, str | None]:
    """Return page OCR word boxes from Tesseract TSV output.

    Fishnet routing needs spatial text, but running Tesseract once per cell is
    expensive. This helper runs Tesseract's page-level TSV pass and assigns the
    resulting word boxes to fishnet cells. It is still derived router guidance,
    not source-truth evidence.
    """

    if ocr_mode == "disabled":
        return [], "disabled", None
    try:
        import pytesseract  # type: ignore
    except Exception as exc:
        if ocr_mode == "required":
            raise RuntimeError(f"pytesseract import failed for word boxes: {exc}") from exc
        return [], "unavailable", f"pytesseract import failed for word boxes: {exc}"

    if not hasattr(pytesseract, "image_to_data"):
        return [], "unavailable", "pytesseract.image_to_data unavailable; cannot build word boxes"

    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = str(tesseract_cmd)

    output_dict = getattr(getattr(pytesseract, "Output", object()), "DICT", "dict")
    errors: list[str] = []
    empty_attempts: list[str] = []
    # Keep only same-size OCR variants so coordinates map directly onto the
    # original page image. Upscaled variants are useful for text fallback, but
    # would require coordinate rescaling and are intentionally skipped here.
    variants = [(name, variant) for name, variant in _ocr_image_variants(image) if getattr(variant, "size", None) == getattr(image, "size", None)]
    for variant_name, ocr_image in variants:
        for config in _ocr_configs(tesseract_config):
            try:
                data = pytesseract.image_to_data(ocr_image, output_type=output_dict, config=config)
            except Exception as exc:
                errors.append(f"{variant_name}|{config}: {exc}")
                continue
            words: list[dict[str, Any]] = []
            texts = data.get("text", []) if isinstance(data, Mapping) else []
            lefts = data.get("left", []) if isinstance(data, Mapping) else []
            tops = data.get("top", []) if isinstance(data, Mapping) else []
            widths = data.get("width", []) if isinstance(data, Mapping) else []
            heights = data.get("height", []) if isinstance(data, Mapping) else []
            confs = data.get("conf", []) if isinstance(data, Mapping) else []
            for idx, raw_text in enumerate(texts):
                text = str(raw_text or "").strip()
                if not text:
                    continue
                try:
                    left = int(float(lefts[idx]))
                    top = int(float(tops[idx]))
                    width = int(float(widths[idx]))
                    height = int(float(heights[idx]))
                except Exception:
                    continue
                if width <= 0 or height <= 0:
                    continue
                conf = _parse_confidence(confs[idx] if idx < len(confs) else None)
                words.append(
                    {
                        "text": text,
                        "left": left,
                        "top": top,
                        "right": left + width,
                        "bottom": top + height,
                        "center_x": left + width / 2.0,
                        "center_y": top + height / 2.0,
                        "confidence": conf,
                    }
                )
            if words:
                return words, "ok", None
            empty_attempts.append(f"{variant_name}|{config}")
    if errors and not empty_attempts:
        error_text = f"tesseract word-box OCR failed after fallbacks: {'; '.join(errors[:3])}"
        if ocr_mode == "required":
            raise RuntimeError(error_text)
        return [], "failed", error_text
    return [], "empty", f"Tesseract TSV produced no word boxes. attempted={empty_attempts[:6]} errors={errors[:2]}"


def _words_in_bbox(word_boxes: Sequence[Mapping[str, Any]], bbox: tuple[int, int, int, int]) -> list[Mapping[str, Any]]:
    left, top, right, bottom = bbox
    selected: list[Mapping[str, Any]] = []
    for word in word_boxes:
        try:
            x = float(word.get("center_x"))
            y = float(word.get("center_y"))
        except Exception:
            continue
        if left <= x < right and top <= y < bottom:
            selected.append(word)
    return selected


def _word_box_features(words: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    confs = [float(w["confidence"]) for w in words if w.get("confidence") is not None]
    return {
        "ocr_word_box_count": len(words),
        "ocr_mean_confidence": round(sum(confs) / len(confs), 4) if confs else None,
    }

def _token_features(text: str) -> dict[str, Any]:
    words = re.findall(r"\b[A-Za-z0-9][A-Za-z0-9\-/\.]*\b", text or "")
    part_numbers = PART_NUMBER_RE.findall(text or "")
    numeric_tokens = NUMBER_RE.findall(text or "")
    callout_tokens = CALLOUT_RE.findall(text or "")
    line_count = len([line for line in (text or "").splitlines() if line.strip()])
    return {
        "ocr_char_count": len(text or ""),
        "ocr_word_count": len(words),
        "ocr_line_count": line_count,
        "part_number_token_count": len(part_numbers),
        "numeric_token_count": len(numeric_tokens),
        "callout_hint_count": len(callout_tokens),
        "table_keyword_count": len(TABLE_KEYWORD_RE.findall(text or "")),
        "visual_keyword_count": len(VISUAL_KEYWORD_RE.findall(text or "")),
        "sample_text": " ".join((text or "").split())[:240],
    }


def _score_route(page_features: Mapping[str, Any], cell_records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    cell_count = max(1, len(cell_records))
    grid_rows = max(1, int(page_features.get("grid_rows") or 1))
    grid_cols = max(1, int(page_features.get("grid_cols") or 1))
    ink_ratio = float(page_features.get("ink_ratio") or 0.0)
    ocr_char_count = int(page_features.get("ocr_char_count") or 0)
    ocr_cell_count = sum(1 for c in cell_records if int(c.get("ocr_char_count") or 0) > 0)
    dense_text_cell_count = sum(1 for c in cell_records if int(c.get("ocr_word_count") or 0) >= 6)
    very_dense_text_cell_count = sum(1 for c in cell_records if int(c.get("ocr_word_count") or 0) >= 12)
    table_like_cell_count = sum(
        1
        for c in cell_records
        if (int(c.get("numeric_token_count") or 0) >= 2 or int(c.get("part_number_token_count") or 0) >= 1)
        and float(c.get("ink_ratio") or 0.0) >= 0.01
    )
    numeric_heavy_cell_count = sum(1 for c in cell_records if int(c.get("numeric_token_count") or 0) >= 5)
    part_heavy_cell_count = sum(1 for c in cell_records if int(c.get("part_number_token_count") or 0) >= 2)
    table_keyword_cell_count = sum(1 for c in cell_records if int(c.get("table_keyword_count") or 0) >= 2)
    visual_like_cell_count = sum(
        1
        for c in cell_records
        if float(c.get("ink_ratio") or 0.0) >= 0.04 and int(c.get("ocr_word_count") or 0) <= 3
    )
    rows_with_ocr = {c.get("row_index") for c in cell_records if int(c.get("ocr_char_count") or 0) > 0}
    cols_with_ocr = {c.get("col_index") for c in cell_records if int(c.get("ocr_char_count") or 0) > 0}
    rows_with_ink = {c.get("row_index") for c in cell_records if float(c.get("ink_ratio") or 0.0) >= 0.01}
    cols_with_ink = {c.get("col_index") for c in cell_records if float(c.get("ink_ratio") or 0.0) >= 0.01}
    rows_with_table_like = {c.get("row_index") for c in cell_records if int(c.get("numeric_token_count") or 0) >= 2 or int(c.get("part_number_token_count") or 0) >= 1}
    cols_with_table_like = {c.get("col_index") for c in cell_records if int(c.get("numeric_token_count") or 0) >= 2 or int(c.get("part_number_token_count") or 0) >= 1}

    text_distribution = min(1.0, len(rows_with_ocr) / grid_rows)
    column_distribution = min(1.0, len(cols_with_ocr) / grid_cols)
    table_row_distribution = min(1.0, len(rows_with_table_like) / grid_rows)
    table_col_distribution = min(1.0, len(cols_with_table_like) / grid_cols)
    ink_distribution = min(1.0, (len(rows_with_ink) + len(cols_with_ink)) / max(1, grid_rows + grid_cols))

    page_word_count = int(page_features.get("ocr_word_count") or 0)
    page_line_count = int(page_features.get("ocr_line_count") or 0)
    page_numeric_count = int(page_features.get("numeric_token_count") or 0)
    page_part_count = int(page_features.get("part_number_token_count") or 0)
    page_callout_count = int(page_features.get("callout_hint_count") or 0)

    page_table_keyword_count = int(page_features.get("table_keyword_count") or 0)
    page_visual_keyword_count = int(page_features.get("visual_keyword_count") or 0)
    page_level_ocr_only = bool(ocr_char_count > 0 and ocr_cell_count == 0)
    word_box_count = int(page_features.get("ocr_word_box_count") or 0)

    page_text_strength = min(1.0, (ocr_char_count / 900.0) * 0.70 + (page_word_count / 140.0) * 0.30)
    numeric_density = min(1.0, page_numeric_count / max(1, page_word_count) * 1.25)
    part_density = min(1.0, page_part_count / max(1, page_word_count) * 2.0)
    keyword_density = min(1.0, page_table_keyword_count / max(1, page_word_count) * 7.5)
    cell_table_density = table_like_cell_count / cell_count
    numeric_cell_density = numeric_heavy_cell_count / cell_count
    part_cell_density = part_heavy_cell_count / cell_count

    # Table/list strength must come from repeated structured cues, not merely
    # from a few manual-header words such as "PARTS LIST". This prevents cover
    # pages and ordinary prose pages from becoming table candidates just because
    # the manual title contains table-ish words.
    structured_table_evidence = min(
        1.0,
        cell_table_density * 0.34
        + numeric_cell_density * 0.18
        + part_cell_density * 0.22
        + table_row_distribution * table_col_distribution * 0.16
        + numeric_density * 0.18
        + part_density * 0.20
        + keyword_density * 0.10,
    )
    strong_part_list = bool(page_part_count >= 8 and table_like_cell_count >= 4)
    strong_numeric_list = bool(page_numeric_count >= 60 and table_like_cell_count >= 10 and len(rows_with_table_like) >= 3)
    strong_keyword_grid = bool(page_table_keyword_count >= 12 and table_keyword_cell_count >= 4 and numeric_cell_density >= 0.08)
    structural_table_cues = bool(strong_part_list or strong_numeric_list or strong_keyword_grid)

    page_visual_word_penalty = 0.24 if ocr_char_count >= 500 else (0.46 if ocr_char_count >= 150 else 1.0)
    page_callout_visual_boost = min(0.20, (page_callout_count + page_visual_keyword_count) / 24.0)

    visual_cell_weight = 0.28 if page_level_ocr_only else 1.45
    text_distribution_signal = max(text_distribution, 0.75 if page_word_count >= 80 else (0.45 if page_word_count >= 25 else 0.0))

    blank_score = 1.0 - min(1.0, (ink_ratio / 0.012) + (ocr_char_count / 120.0))
    plain_text_score = min(
        1.0,
        page_text_strength * 0.76
        + text_distribution_signal * 0.14
        + (dense_text_cell_count / cell_count) * 0.18
        + (0.12 if page_word_count >= 60 else 0.0)
        - (0.30 if structural_table_cues and page_word_count >= 80 else 0.0),
    )
    table_score = min(
        1.0,
        structured_table_evidence * 0.92
        + (0.18 if strong_part_list else 0.0)
        + (0.14 if strong_numeric_list else 0.0)
        + (0.10 if strong_keyword_grid else 0.0),
    )
    if not structural_table_cues:
        table_score *= 0.42
    if page_word_count >= 60 and not structural_table_cues:
        plain_text_score = max(plain_text_score, min(1.0, page_text_strength + 0.08))
    image_visual_score = min(
        1.0,
        (
            (visual_like_cell_count / cell_count) * visual_cell_weight
            + ink_distribution * 0.16
            + max(0.0, ink_ratio - 0.02) * 1.55
        )
        * page_visual_word_penalty
        + page_callout_visual_boost,
    )

    scores = {
        "blank_candidate": round(max(0.0, blank_score), 4),
        "normal_text": round(max(0.0, plain_text_score), 4),
        "table": round(max(0.0, table_score), 4),
        "image_visual": round(max(0.0, image_visual_score), 4),
    }
    route_rank_bias = {"table": 0.10 if structural_table_cues and table_score >= 0.50 else 0.0}
    adjusted_scores = {route: round(min(1.0, score + route_rank_bias.get(route, 0.0)), 4) for route, score in scores.items()}
    ranked = sorted(adjusted_scores.items(), key=lambda item: (item[1], item[0]), reverse=True)
    top_route, top_adjusted_score = ranked[0]
    second_adjusted_score = ranked[1][1] if len(ranked) > 1 else 0.0
    confidence = round(max(0.0, top_adjusted_score - second_adjusted_score), 4)
    review_reasons: list[str] = []
    if top_adjusted_score < 0.35:
        review_reasons.append("low_top_route_score")
    if confidence < 0.08:
        review_reasons.append("low_route_margin")
    if top_route == "table" and not structural_table_cues:
        review_reasons.append("table_without_structural_cues")
    if top_route == "table" and confidence < 0.12:
        review_reasons.append("table_text_tie")
    review_required = bool(review_reasons)
    recommended_route = "review_required" if review_required else top_route
    reported_scores = {**scores}
    if review_required:
        reported_scores["review_required"] = 1.0
    reported_adjusted_scores = {**adjusted_scores}
    if review_required:
        reported_adjusted_scores["review_required"] = 1.0
    return {
        "route_scores": reported_scores,
        "route_adjusted_scores": reported_adjusted_scores,
        "best_route_candidate_before_review": top_route,
        "recommended_route_candidate": recommended_route,
        "route_confidence": confidence if not review_required else 0.0,
        "review_required": review_required,
        "route_review_reason_codes": review_reasons,
        "reason_counts": {
            "ocr_cell_count": ocr_cell_count,
            "dense_text_cell_count": dense_text_cell_count,
            "very_dense_text_cell_count": very_dense_text_cell_count,
            "table_like_cell_count": table_like_cell_count,
            "numeric_heavy_cell_count": numeric_heavy_cell_count,
            "part_heavy_cell_count": part_heavy_cell_count,
            "table_keyword_cell_count": table_keyword_cell_count,
            "visual_like_cell_count": visual_like_cell_count,
            "rows_with_ocr_count": len(rows_with_ocr),
            "cols_with_ocr_count": len(cols_with_ocr),
            "rows_with_ink_count": len(rows_with_ink),
            "cols_with_ink_count": len(cols_with_ink),
            "rows_with_table_like_count": len(rows_with_table_like),
            "cols_with_table_like_count": len(cols_with_table_like),
            "page_level_ocr_only": int(page_level_ocr_only),
            "page_table_keyword_count": page_table_keyword_count,
            "page_visual_keyword_count": page_visual_keyword_count,
            "page_ocr_word_box_count": word_box_count,
            "structural_table_cues": int(structural_table_cues),
            "strong_part_list": int(strong_part_list),
            "strong_numeric_list": int(strong_numeric_list),
            "strong_keyword_grid": int(strong_keyword_grid),
        },
    }


def _draw_overlay(image, page_record: Mapping[str, Any], output_path: Path) -> None:
    if ImageDraw is None:
        return
    overlay = image.copy()
    overlay.thumbnail((1400, 1800))
    scale_x = overlay.size[0] / max(1, int(page_record["image_width_px"]))
    scale_y = overlay.size[1] / max(1, int(page_record["image_height_px"]))
    draw = ImageDraw.Draw(overlay)
    for cell in page_record.get("cell_records", []):
        bbox = cell.get("bbox_px") or {}
        left = int(float(bbox.get("left", 0)) * scale_x)
        top = int(float(bbox.get("top", 0)) * scale_y)
        right = int(float(bbox.get("right", 0)) * scale_x)
        bottom = int(float(bbox.get("bottom", 0)) * scale_y)
        # Green grid lines indicate fishnet cells. Red-ish text is avoided to keep colors simple.
        draw.rectangle([left, top, right, bottom], outline=(0, 180, 0), width=2)
    draw.text((10, 10), str(page_record.get("page_id", "page")), fill=(0, 180, 0))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(output_path)


def _write_contact_sheet(overlay_paths: Sequence[Path], output_path: Path, *, thumb_width: int = 420) -> None:
    if Image is None or not overlay_paths:
        return
    thumbs = []
    for path in overlay_paths:
        try:
            img = Image.open(path).convert("RGB")
            ratio = thumb_width / max(1, img.size[0])
            img = img.resize((thumb_width, max(1, int(img.size[1] * ratio))))
            thumbs.append((path, img))
        except Exception:
            continue
    if not thumbs:
        return
    cols = min(4, len(thumbs))
    rows = math.ceil(len(thumbs) / cols)
    cell_h = max(img.size[1] for _, img in thumbs) + 28
    sheet = Image.new("RGB", (cols * thumb_width, rows * cell_h), "white")
    draw = ImageDraw.Draw(sheet) if ImageDraw is not None else None
    for idx, (path, img) in enumerate(thumbs):
        x = (idx % cols) * thumb_width
        y = (idx // cols) * cell_h
        sheet.paste(img, (x, y + 24))
        if draw is not None:
            draw.text((x + 5, y + 5), path.name[:56], fill=(0, 0, 0))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)


def analyze_page(
    source_package: Path,
    page: SourcePage,
    *,
    rows: int,
    cols: int,
    ocr_mode: str,
    ocr_scope: str,
    max_ocr_cells_per_page: int,
    tesseract_cmd: str | None = None,
    tesseract_config: str = "--psm 6",
) -> tuple[dict[str, Any], Any | None]:
    image = _open_page_image(source_package, page)
    width, height = image.size
    page_ink = _ink_features(image)
    page_text = ""
    page_ocr_status = "not_requested"
    ocr_error: str | None = None
    page_word_boxes: list[dict[str, Any]] = []
    word_box_status = "not_requested"
    word_box_error: str | None = None
    if ocr_scope == "page":
        page_text, page_ocr_status, ocr_error = _ocr_text(
            image,
            ocr_mode=ocr_mode,
            tesseract_cmd=tesseract_cmd,
            tesseract_config=tesseract_config,
        )
        if page_ocr_status == "ok":
            page_word_boxes, word_box_status, word_box_error = _ocr_word_boxes(
                image,
                ocr_mode=ocr_mode,
                tesseract_cmd=tesseract_cmd,
                tesseract_config=tesseract_config,
            )
    page_tokens = {**_token_features(page_text), **_word_box_features(page_word_boxes)}

    cell_records: list[dict[str, Any]] = []
    ocr_cell_budget = max_ocr_cells_per_page if max_ocr_cells_per_page >= 0 else rows * cols
    for row in range(rows):
        for col in range(cols):
            left, top, right, bottom = _cell_bbox(width, height, row, col, rows, cols)
            crop = image.crop((left, top, right, bottom))
            ink = _ink_features(crop)
            cell_text = ""
            cell_ocr_status = "not_requested"
            cell_ocr_error = None
            cell_word_boxes: list[Mapping[str, Any]] = []
            if ocr_scope == "page" and page_word_boxes:
                cell_word_boxes = _words_in_bbox(page_word_boxes, (left, top, right, bottom))
                cell_text = " ".join(str(word.get("text") or "") for word in cell_word_boxes if str(word.get("text") or "").strip())
                cell_ocr_status = "ok" if cell_text.strip() else "empty"
            elif ocr_scope == "cell" and ocr_cell_budget > 0:
                cell_text, cell_ocr_status, cell_ocr_error = _ocr_text(
                    crop,
                    ocr_mode=ocr_mode,
                    tesseract_cmd=tesseract_cmd,
                    tesseract_config=tesseract_config,
                )
                ocr_cell_budget -= 1
            tokens = {**_token_features(cell_text), **_word_box_features(cell_word_boxes)}
            cell_records.append(
                {
                    "page_id": page.page_id,
                    "cell_id": f"{page.page_id}_r{row:02d}_c{col:02d}",
                    "row_index": row,
                    "col_index": col,
                    "bbox_px": {"left": left, "top": top, "right": right, "bottom": bottom},
                    **ink,
                    **tokens,
                    "ocr_status": cell_ocr_status,
                    "ocr_error": cell_ocr_error,
                    "safety_contract": dict(SAFETY_CONTRACT),
                }
            )
    page_features = {
        "grid_rows": rows,
        "grid_cols": cols,
        "image_width_px": width,
        "image_height_px": height,
        **page_ink,
        **page_tokens,
    }
    route = _score_route(page_features, cell_records)
    statuses = [page_ocr_status] + [str(c.get("ocr_status")) for c in cell_records]
    if "ok" in statuses:
        ocr_engine_status = "ok"
    elif "failed" in statuses:
        ocr_engine_status = "failed"
    elif "unavailable" in statuses:
        ocr_engine_status = "unavailable"
    elif "empty" in statuses:
        ocr_engine_status = "empty"
    elif "disabled" in statuses:
        ocr_engine_status = "disabled"
    else:
        ocr_engine_status = "not_requested"

    if ocr_mode in {"available", "required"} and ocr_scope in {"page", "cell"} and ocr_engine_status in {"failed", "unavailable", "empty"}:
        route = {
            **route,
            "best_route_candidate_before_review": route.get("best_route_candidate_before_review") or route.get("recommended_route_candidate"),
            "recommended_route_candidate": "review_required",
            "route_confidence": 0.0,
            "review_required": True,
            "route_scores": {**dict(route.get("route_scores") or {}), "review_required": 1.0},
            "route_adjusted_scores": {**dict(route.get("route_adjusted_scores") or {}), "review_required": 1.0},
            "route_review_reason_codes": [*list(route.get("route_review_reason_codes") or []), "ocr_non_text_blocks_route_confidence"],
            "reason_counts": {
                **dict(route.get("reason_counts") or {}),
                "ocr_non_text_blocks_route_confidence": 1,
            },
        }

    record = {
        "module": MODULE_NAME,
        "version": VERSION,
        "record_type": "fishnet_page_grid_card",
        "page_id": page.page_id,
        "source_path": page.source_path,
        "file_name": page.file_name,
        "page_number": page.page_number,
        "image_width_px": width,
        "image_height_px": height,
        "grid_shape": {"rows": rows, "cols": cols},
        "cell_count": len(cell_records),
        "page_ink_features": page_ink,
        "page_ocr_features": page_tokens,
        "page_ocr_status": page_ocr_status,
        "page_ocr_error": ocr_error,
        "page_ocr_word_box_status": word_box_status,
        "page_ocr_word_box_error": word_box_error,
        "ocr_engine_status": ocr_engine_status,
        "route_signal_status": "FISHNET_ROUTE_SIGNALS_BUILT" if not route.get("review_required") else "FISHNET_ROUTE_SIGNALS_REVIEW_REQUIRED",
        **route,
        "cell_records": cell_records,
        "safety_contract": dict(SAFETY_CONTRACT),
        "can_answer_directly": False,
        "can_prove_claims": False,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }
    return record, image


def _summarize(records: Sequence[Mapping[str, Any]], *, source_page_count: int, rows: int, cols: int) -> dict[str, Any]:
    route_counts: dict[str, int] = {}
    best_route_counts: dict[str, int] = {}
    ocr_status_counts: dict[str, int] = {}
    ocr_error_counts: dict[str, int] = {}
    for record in records:
        route = str(record.get("recommended_route_candidate") or "unknown")
        route_counts[route] = route_counts.get(route, 0) + 1
        best_route = str(record.get("best_route_candidate_before_review") or route)
        best_route_counts[best_route] = best_route_counts.get(best_route, 0) + 1
        status = str(record.get("ocr_engine_status") or "unknown")
        ocr_status_counts[status] = ocr_status_counts.get(status, 0) + 1
        error_text = str(record.get("page_ocr_error") or "")[:240]
        if error_text:
            ocr_error_counts[error_text] = ocr_error_counts.get(error_text, 0) + 1
    unsafe_answer = sum(1 for r in records if r.get("answer_permission") or r.get("can_answer_directly") or r.get("can_prove_claims"))
    source_truth_mutation_allowed = sum(1 for r in records if r.get("source_truth_mutation_allowed"))
    pg_writes = sum(int(r.get("postgres_write_attempt_count") or 0) for r in records)
    qdrant_writes = sum(int(r.get("qdrant_write_attempt_count") or 0) for r in records)
    opensearch_writes = sum(int(r.get("opensearch_write_attempt_count") or 0) for r in records)
    total_cell_count = sum(int(r.get("cell_count") or 0) for r in records)
    review_required_count = sum(1 for r in records if r.get("review_required"))
    route_confidences = [float(r.get("route_confidence") or 0.0) for r in records]
    return {
        "source_page_count": source_page_count,
        "page_record_count": len(records),
        "grid_rows": rows,
        "grid_cols": cols,
        "expected_cells_per_page": rows * cols,
        "total_cell_count": total_cell_count,
        "route_candidate_counts": route_counts,
        "best_route_candidate_before_review_counts": best_route_counts,
        "ocr_engine_status_counts": ocr_status_counts,
        "ocr_ok_page_count": ocr_status_counts.get("ok", 0),
        "ocr_failed_page_count": ocr_status_counts.get("failed", 0),
        "ocr_unavailable_page_count": ocr_status_counts.get("unavailable", 0),
        "ocr_empty_page_count": ocr_status_counts.get("empty", 0),
        "ocr_nonempty_page_count": sum(1 for r in records if int((r.get("page_ocr_features") or {}).get("ocr_char_count") or 0) > 0),
        "total_ocr_text_char_count": sum(int((r.get("page_ocr_features") or {}).get("ocr_char_count") or 0) for r in records),
        "total_ocr_word_box_count": sum(int((r.get("page_ocr_features") or {}).get("ocr_word_box_count") or 0) for r in records),
        "pages_with_ocr_word_boxes_count": sum(1 for r in records if int((r.get("page_ocr_features") or {}).get("ocr_word_box_count") or 0) > 0),
        "ocr_error_examples": [
            {"error": error, "count": count}
            for error, count in sorted(ocr_error_counts.items(), key=lambda item: item[1], reverse=True)[:5]
        ],
        "review_required_count": review_required_count,
        "mean_route_confidence": round(statistics.mean(route_confidences), 4) if route_confidences else 0.0,
        "unsafe_record_count": unsafe_answer,
        "answer_permission_count": sum(1 for r in records if r.get("answer_permission")),
        "can_answer_directly_count": sum(1 for r in records if r.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for r in records if r.get("can_prove_claims")),
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed,
        "postgres_write_attempt_count": pg_writes,
        "qdrant_write_attempt_count": qdrant_writes,
        "opensearch_write_attempt_count": opensearch_writes,
    }


def _quality_status(summary: Mapping[str, Any], errors: Sequence[str]) -> str:
    if errors:
        return "FAIL"
    if int(summary.get("page_record_count") or 0) <= 0:
        return "FAIL"
    if int(summary.get("unsafe_record_count") or 0) != 0:
        return "FAIL"
    if int(summary.get("source_truth_mutation_allowed_count") or 0) != 0:
        return "FAIL"
    if int(summary.get("postgres_write_attempt_count") or 0) != 0:
        return "FAIL"
    if int(summary.get("qdrant_write_attempt_count") or 0) != 0:
        return "FAIL"
    if int(summary.get("opensearch_write_attempt_count") or 0) != 0:
        return "FAIL"
    return "PASS"


def build_fishnet_ocr_grid(
    *,
    source_package: Path,
    output_dir: Path,
    rows: int = 8,
    cols: int = 6,
    ocr_mode: str = "available",
    ocr_scope: str = "cell",
    max_ocr_cells_per_page: int = 48,
    page_limit: int = 0,
    write_overlays: bool = False,
    max_overlay_pages: int = 20,
    tesseract_cmd: str | None = None,
    tesseract_config: str = "--psm 6",
) -> dict[str, Any]:
    """Build fishnet OCR grid artifacts.

    This function is deliberately read-only relative to source truth and stores.
    It only writes JSON/JSONL/PNG artifacts under output_dir.
    """

    if rows <= 0 or cols <= 0:
        raise ValueError("rows and cols must be positive integers")
    if ocr_mode not in {"disabled", "available", "required"}:
        raise ValueError("ocr_mode must be disabled, available, or required")
    if ocr_scope not in {"none", "page", "cell"}:
        raise ValueError("ocr_scope must be none, page, or cell")
    if ocr_scope == "none":
        ocr_mode = "disabled"
    source_package = Path(source_package)
    output_dir = Path(output_dir)
    pages = discover_source_pages(source_package)
    source_page_count = len(pages)
    if page_limit and page_limit > 0:
        pages = pages[:page_limit]

    records: list[dict[str, Any]] = []
    errors: list[str] = []
    overlay_paths: list[Path] = []
    for page in pages:
        try:
            record, image = analyze_page(
                source_package,
                page,
                rows=rows,
                cols=cols,
                ocr_mode=ocr_mode,
                ocr_scope=ocr_scope,
                max_ocr_cells_per_page=max_ocr_cells_per_page,
                tesseract_cmd=tesseract_cmd,
                tesseract_config=tesseract_config,
            )
            records.append(record)
            if write_overlays and image is not None and len(overlay_paths) < max_overlay_pages:
                overlay_path = output_dir / "overlays" / f"{page.page_id}_fishnet_overlay_v1.png"
                _draw_overlay(image, record, overlay_path)
                overlay_paths.append(overlay_path)
        except Exception as exc:  # Keep building other pages and report failures.
            errors.append(f"{page.page_id}: {exc}")
    if write_overlays and overlay_paths:
        _write_contact_sheet(overlay_paths, output_dir / DEFAULT_CONTACT_SHEET_NAME)

    summary = _summarize(records, source_page_count=source_page_count, rows=rows, cols=cols)
    status = _quality_status(summary, errors)
    payload: dict[str, Any] = {
        "module": MODULE_NAME,
        "version": VERSION,
        "status": "FISHNET_OCR_GRID_BUILT" if status == "PASS" else "FISHNET_OCR_GRID_BUILT_WITH_ERRORS",
        "quality_status": status,
        "source_package": str(source_package),
        "output_dir": str(output_dir),
        "build_parameters": {
            "rows": rows,
            "cols": cols,
            "ocr_mode": ocr_mode,
            "ocr_scope": ocr_scope,
            "max_ocr_cells_per_page": max_ocr_cells_per_page,
            "page_limit": page_limit,
            "write_overlays": write_overlays,
            "max_overlay_pages": max_overlay_pages,
            "tesseract_cmd": tesseract_cmd,
            "tesseract_config": tesseract_config,
        },
        "summary": summary,
        "safety_contract": dict(SAFETY_CONTRACT),
        "errors": errors,
        "records": records,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _safe_json_dump(output_dir / DEFAULT_REPORT_NAME, payload)
    _jsonl_dump(output_dir / DEFAULT_CARDS_NAME, records)
    _safe_json_dump(output_dir / DEFAULT_SUMMARY_NAME, summary)
    _safe_json_dump(
        output_dir / DEFAULT_QUALITY_NAME,
        {
            "module": MODULE_NAME,
            "version": VERSION,
            "quality_status": status,
            "summary": summary,
            "errors": errors,
            "safety_contract": dict(SAFETY_CONTRACT),
        },
    )
    return payload


def evaluate_quality(
    payload: Mapping[str, Any],
    *,
    require_page_count: int | None = None,
    min_page_records: int = 1,
    min_total_cell_records: int = 1,
    min_grid_rows: int = 1,
    min_grid_cols: int = 1,
    max_unsafe: int = 0,
    require_all_pages_have_grid: bool = False,
    require_no_answer_permission: bool = True,
    require_no_source_truth_mutation: bool = True,
    min_ocr_ok_pages: int = 0,
    max_ocr_failed_pages: int | None = None,
    require_no_ocr_failures: bool = False,
    max_image_visual_ratio: float | None = None,
    max_table_ratio: float | None = None,
    max_review_required_ratio: float | None = None,
    min_ocr_nonempty_pages: int = 0,
    min_total_ocr_text_chars: int = 0,
    max_ocr_empty_pages: int | None = None,
    require_no_ocr_empty: bool = False,
    min_ocr_word_boxes: int = 0,
) -> dict[str, Any]:
    summary = dict(payload.get("summary") or {})
    records = list(payload.get("records") or [])
    errors: list[str] = list(payload.get("errors") or [])
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, observed: Any = None, expected: Any = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "observed": observed, "expected": expected})
        if not passed:
            errors.append(f"{name} failed: observed={observed!r} expected={expected!r}")

    if require_page_count is not None:
        check("require_page_count", int(summary.get("source_page_count") or 0) == require_page_count, summary.get("source_page_count"), require_page_count)
        check("require_page_record_count", int(summary.get("page_record_count") or 0) == require_page_count, summary.get("page_record_count"), require_page_count)
    check("min_page_records", int(summary.get("page_record_count") or 0) >= min_page_records, summary.get("page_record_count"), f">={min_page_records}")
    check("min_total_cell_records", int(summary.get("total_cell_count") or 0) >= min_total_cell_records, summary.get("total_cell_count"), f">={min_total_cell_records}")
    check("min_grid_rows", int(summary.get("grid_rows") or 0) >= min_grid_rows, summary.get("grid_rows"), f">={min_grid_rows}")
    check("min_grid_cols", int(summary.get("grid_cols") or 0) >= min_grid_cols, summary.get("grid_cols"), f">={min_grid_cols}")
    check("max_unsafe", int(summary.get("unsafe_record_count") or 0) <= max_unsafe, summary.get("unsafe_record_count"), f"<={max_unsafe}")

    if require_all_pages_have_grid:
        bad_pages = [r.get("page_id") for r in records if int(r.get("cell_count") or 0) != int(summary.get("expected_cells_per_page") or 0)]
        check("require_all_pages_have_grid", not bad_pages, bad_pages[:10], "all records cell_count == expected_cells_per_page")
    if require_no_answer_permission:
        check("require_no_answer_permission", int(summary.get("answer_permission_count") or 0) == 0, summary.get("answer_permission_count"), 0)
        check("require_no_direct_answer", int(summary.get("can_answer_directly_count") or 0) == 0, summary.get("can_answer_directly_count"), 0)
        check("require_no_claim_proof", int(summary.get("can_prove_claims_count") or 0) == 0, summary.get("can_prove_claims_count"), 0)
    if require_no_source_truth_mutation:
        check("require_no_source_truth_mutation", int(summary.get("source_truth_mutation_allowed_count") or 0) == 0, summary.get("source_truth_mutation_allowed_count"), 0)
    if min_ocr_ok_pages > 0:
        check("min_ocr_ok_pages", int(summary.get("ocr_ok_page_count") or 0) >= min_ocr_ok_pages, summary.get("ocr_ok_page_count"), f">={min_ocr_ok_pages}")
    if max_ocr_failed_pages is not None:
        check("max_ocr_failed_pages", int(summary.get("ocr_failed_page_count") or 0) <= max_ocr_failed_pages, summary.get("ocr_failed_page_count"), f"<={max_ocr_failed_pages}")
    if require_no_ocr_failures:
        check("require_no_ocr_failures", int(summary.get("ocr_failed_page_count") or 0) == 0 and int(summary.get("ocr_unavailable_page_count") or 0) == 0, {"failed": summary.get("ocr_failed_page_count"), "unavailable": summary.get("ocr_unavailable_page_count")}, {"failed": 0, "unavailable": 0})
    if min_ocr_nonempty_pages > 0:
        check("min_ocr_nonempty_pages", int(summary.get("ocr_nonempty_page_count") or 0) >= min_ocr_nonempty_pages, summary.get("ocr_nonempty_page_count"), f">={min_ocr_nonempty_pages}")
    if min_total_ocr_text_chars > 0:
        check("min_total_ocr_text_chars", int(summary.get("total_ocr_text_char_count") or 0) >= min_total_ocr_text_chars, summary.get("total_ocr_text_char_count"), f">={min_total_ocr_text_chars}")
    if min_ocr_word_boxes > 0:
        check("min_ocr_word_boxes", int(summary.get("total_ocr_word_box_count") or 0) >= min_ocr_word_boxes, summary.get("total_ocr_word_box_count"), f">={min_ocr_word_boxes}")
    if max_ocr_empty_pages is not None:
        check("max_ocr_empty_pages", int(summary.get("ocr_empty_page_count") or 0) <= max_ocr_empty_pages, summary.get("ocr_empty_page_count"), f"<={max_ocr_empty_pages}")
    if require_no_ocr_empty:
        check("require_no_ocr_empty", int(summary.get("ocr_empty_page_count") or 0) == 0, summary.get("ocr_empty_page_count"), 0)
    route_counts = dict(summary.get("route_candidate_counts") or {})
    page_count = max(1, int(summary.get("page_record_count") or 0))
    if max_image_visual_ratio is not None:
        observed_ratio = float(route_counts.get("image_visual", 0)) / page_count
        check("max_image_visual_ratio", observed_ratio <= max_image_visual_ratio, round(observed_ratio, 6), f"<={max_image_visual_ratio}")
    if max_table_ratio is not None:
        observed_ratio = float(route_counts.get("table", 0)) / page_count
        check("max_table_ratio", observed_ratio <= max_table_ratio, round(observed_ratio, 6), f"<={max_table_ratio}")
    if max_review_required_ratio is not None:
        observed_ratio = float(route_counts.get("review_required", 0)) / page_count
        check("max_review_required_ratio", observed_ratio <= max_review_required_ratio, round(observed_ratio, 6), f"<={max_review_required_ratio}")
    check("postgres_write_attempt_count", int(summary.get("postgres_write_attempt_count") or 0) == 0, summary.get("postgres_write_attempt_count"), 0)
    check("qdrant_write_attempt_count", int(summary.get("qdrant_write_attempt_count") or 0) == 0, summary.get("qdrant_write_attempt_count"), 0)
    check("opensearch_write_attempt_count", int(summary.get("opensearch_write_attempt_count") or 0) == 0, summary.get("opensearch_write_attempt_count"), 0)

    quality_status = "PASS" if all(c["passed"] for c in checks) and not list(payload.get("errors") or []) else "FAIL"
    return {
        "module": MODULE_NAME,
        "version": VERSION,
        "quality_status": quality_status,
        "summary": summary,
        "checks": checks,
        "errors": errors,
        "safety_contract": dict(SAFETY_CONTRACT),
    }


def main_build(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net fishnet OCR grid v1 artifacts.")
    parser.add_argument("--source-package", required=True, help="Metadata/source package zip or unpacked directory containing page images.")
    parser.add_argument("--output-dir", required=True, help="Output directory under local_data/organization/trace_net/.")
    parser.add_argument("--rows", type=int, default=8)
    parser.add_argument("--cols", type=int, default=6)
    parser.add_argument("--ocr-mode", choices=["disabled", "available", "required"], default="available")
    parser.add_argument("--ocr-scope", choices=["none", "page", "cell"], default="cell")
    parser.add_argument("--max-ocr-cells-per-page", type=int, default=48)
    parser.add_argument("--page-limit", type=int, default=0)
    parser.add_argument("--write-overlays", action="store_true")
    parser.add_argument("--max-overlay-pages", type=int, default=20)
    parser.add_argument("--tesseract-cmd", default=None, help="Optional full path to tesseract executable, e.g. C:/Program Files/Tesseract-OCR/tesseract.exe.")
    parser.add_argument("--tesseract-config", default="--psm 6", help="pytesseract config string.")
    parser.add_argument("--quality", action="store_true", help="Print quality status after build.")
    args = parser.parse_args(argv)
    payload = build_fishnet_ocr_grid(
        source_package=Path(args.source_package),
        output_dir=Path(args.output_dir),
        rows=args.rows,
        cols=args.cols,
        ocr_mode=args.ocr_mode,
        ocr_scope=args.ocr_scope,
        max_ocr_cells_per_page=args.max_ocr_cells_per_page,
        page_limit=args.page_limit,
        write_overlays=args.write_overlays,
        max_overlay_pages=args.max_overlay_pages,
        tesseract_cmd=args.tesseract_cmd,
        tesseract_config=args.tesseract_config,
    )
    print(f"Status: {payload['status']}")
    print(f"Quality status: {payload['quality_status']}")
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    if args.quality and payload["quality_status"] != "PASS":
        return 1
    return 0


def main_check(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net fishnet OCR grid v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--require-page-count", type=int, default=None)
    parser.add_argument("--min-page-records", type=int, default=1)
    parser.add_argument("--min-total-cell-records", type=int, default=1)
    parser.add_argument("--min-grid-rows", type=int, default=1)
    parser.add_argument("--min-grid-cols", type=int, default=1)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--require-all-pages-have-grid", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--min-ocr-ok-pages", type=int, default=0)
    parser.add_argument("--max-ocr-failed-pages", type=int, default=None)
    parser.add_argument("--require-no-ocr-failures", action="store_true")
    parser.add_argument("--max-image-visual-ratio", type=float, default=None)
    parser.add_argument("--max-table-ratio", type=float, default=None)
    parser.add_argument("--max-review-required-ratio", type=float, default=None)
    parser.add_argument("--min-ocr-nonempty-pages", type=int, default=0)
    parser.add_argument("--min-total-ocr-text-chars", type=int, default=0)
    parser.add_argument("--max-ocr-empty-pages", type=int, default=None)
    parser.add_argument("--require-no-ocr-empty", action="store_true")
    parser.add_argument("--min-ocr-word-boxes", type=int, default=0)
    args = parser.parse_args(argv)
    report_path = Path(args.report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    quality = evaluate_quality(
        payload,
        require_page_count=args.require_page_count,
        min_page_records=args.min_page_records,
        min_total_cell_records=args.min_total_cell_records,
        min_grid_rows=args.min_grid_rows,
        min_grid_cols=args.min_grid_cols,
        max_unsafe=args.max_unsafe,
        require_all_pages_have_grid=args.require_all_pages_have_grid,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        min_ocr_ok_pages=args.min_ocr_ok_pages,
        max_ocr_failed_pages=args.max_ocr_failed_pages,
        require_no_ocr_failures=args.require_no_ocr_failures,
        max_image_visual_ratio=args.max_image_visual_ratio,
        max_table_ratio=args.max_table_ratio,
        max_review_required_ratio=args.max_review_required_ratio,
        min_ocr_nonempty_pages=args.min_ocr_nonempty_pages,
        min_total_ocr_text_chars=args.min_total_ocr_text_chars,
        max_ocr_empty_pages=args.max_ocr_empty_pages,
        require_no_ocr_empty=args.require_no_ocr_empty,
        min_ocr_word_boxes=args.min_ocr_word_boxes,
    )
    print(f"Quality status: {quality['quality_status']}")
    print("Summary:", json.dumps(quality["summary"], sort_keys=True))
    failed = [check for check in quality["checks"] if not check["passed"]]
    if failed:
        print("Failed checks:", json.dumps(failed, indent=2))
    if args.write_json:
        out_path = report_path.with_name("trace_net_fishnet_ocr_grid_v1_quality_check.json")
        _safe_json_dump(out_path, quality)
        print(f"Wrote: {out_path}")
    return 0 if quality["quality_status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main_build(sys.argv[1:]))
