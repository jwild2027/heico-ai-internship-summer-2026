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


# --- Patch 2: role-based OCR-attempt selection -------------------------------
# PSM 3 is the primary whole-page reader for prose/procedures/captions. PSM 11 is
# supplemental sparse callout text; PSM 6 is a candidate uniform block. The old
# selector chose the primary purely by text volume (len(tokens)+15*parts), which
# let noisy diagram/grid callouts from PSM 6/11 replace clean PSM 3 output. The
# selection below is role-based, retains every attempt, and emits component
# metrics + explicit reason codes instead of one opaque score.
_PSM_ROLE: dict[int, str] = {
    3: "primary_full_page",
    11: "supplemental_sparse_callout",
    6: "candidate_uniform_block",
}
_NUMERIC_TOKEN_RE = re.compile(r"^\d+(?:[.\-/]\d+)*$")
_CONFIDENCE_OVERRIDE_MARGIN = 15.0  # min confidence advantage to beat a usable PSM 3


def _psm_role(psm: Any) -> str:
    try:
        return _PSM_ROLE.get(int(psm), "candidate")
    except (TypeError, ValueError):
        return "candidate"


def _as_optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _evaluate_ocr_attempt(attempt: Mapping[str, Any]) -> dict[str, Any]:
    """Deterministic component metrics for one PSM attempt (no opaque score)."""
    text = attempt.get("text") or ""
    tokens = _tokens(text)
    n = len(tokens)
    alpha_words = [t for t in tokens if len(t) >= 3 and any(c.isalpha() for c in t)]
    isolated_numeric = [t for t in tokens if _NUMERIC_TOKEN_RE.match(t)]
    short_tokens = [t for t in tokens if len(t) <= 2]
    non_space = [c for c in text if not c.isspace()]
    punct = [c for c in non_space if not c.isalnum()]
    garbage_ratio = round(len(punct) / len(non_space), 4) if non_space else 0.0
    isolated_numeric_ratio = round(len(isolated_numeric) / n, 4) if n else 0.0
    short_token_ratio = round(len(short_tokens) / n, 4) if n else 0.0
    ok = attempt.get("returncode") == 0
    conf = _as_optional_float(attempt.get("mean_confidence", attempt.get("confidence_mean")))
    low_conf = _as_optional_float(attempt.get("low_conf_word_ratio"))
    # "Real text" = enough natural-language words and not mostly punctuation noise.
    has_real_text = len(alpha_words) >= 2 and garbage_ratio < 0.5
    flags: list[str] = []
    if isolated_numeric_ratio >= 0.6 and len(alpha_words) < 3:
        flags.append("high_isolated_numeric_ratio")
    if short_token_ratio >= 0.6:
        flags.append("high_short_token_dispersion")
    if garbage_ratio >= 0.5:
        flags.append("high_garbage_ratio")
    return {
        "psm": attempt.get("psm"),
        "role": _psm_role(attempt.get("psm")),
        "returncode": attempt.get("returncode"),
        "ok": ok,
        "word_count": n,
        "alpha_word_count": len(alpha_words),
        "part_number_count": int(attempt.get("part_number_token_count", len(set(PART_RE.findall(text))))),
        "isolated_numeric_ratio": isolated_numeric_ratio,
        "short_token_ratio": short_token_ratio,
        "garbage_ratio": garbage_ratio,
        "mean_confidence": conf,
        "low_conf_word_ratio": low_conf,
        "has_real_text": has_real_text,
        "flags": flags,
    }


def _select_primary_attempt(attempts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Choose the primary OCR attempt by role, never by raw length.

    Returns primary_index, supplemental_indexes, per-attempt metrics, and explicit
    reason codes. PSM 3 is primary whenever it is usable; a non-PSM3 attempt wins
    only when PSM 3 is unusable, or when it has a genuinely higher confidence.
    """
    metrics = [_evaluate_ocr_attempt(a) for a in attempts]
    reason_codes: list[str] = []
    successful = [i for i, m in enumerate(metrics) if m["ok"]]

    def _find(psm: int) -> int | None:
        for i, m in enumerate(metrics):
            if m["psm"] == psm:
                return i
        return None

    i3 = _find(3)
    primary: int | None = None

    if i3 is not None and metrics[i3]["ok"] and metrics[i3]["has_real_text"]:
        primary = i3
        reason_codes.append("psm3_primary_by_role")
        for i, m in enumerate(metrics):
            if i != i3 and m["word_count"] > metrics[i3]["word_count"]:
                reason_codes.append(f"psm{m['psm']}_longer_than_psm3_not_promoted")
        # Confidence-based override: only a clearly higher-confidence usable attempt.
        if metrics[i3]["mean_confidence"] is not None:
            better = [
                i for i in successful
                if i != i3 and metrics[i]["has_real_text"]
                and metrics[i]["mean_confidence"] is not None
                and metrics[i]["mean_confidence"] >= metrics[i3]["mean_confidence"] + _CONFIDENCE_OVERRIDE_MARGIN
            ]
            if better:
                bi = max(better, key=lambda i: metrics[i]["mean_confidence"])
                primary = bi
                reason_codes = [c for c in reason_codes if not c.endswith("not_promoted")]
                reason_codes.append(f"higher_confidence_override_psm{metrics[bi]['psm']}")
    else:
        usable = [i for i in successful if metrics[i]["has_real_text"]]
        if usable:
            usable.sort(key=lambda i: (
                -(metrics[i]["mean_confidence"] if metrics[i]["mean_confidence"] is not None else 0.0),
                -metrics[i]["alpha_word_count"],
                metrics[i]["isolated_numeric_ratio"],
                metrics[i]["garbage_ratio"],
            ))
            primary = usable[0]
            reason_codes.append(f"psm3_unusable_fallback_psm{metrics[primary]['psm']}")
        elif successful:
            # No attempt has real text (blank/empty grid): keep PSM 3 if present and
            # never promote noisy grid/callout output just because it is longer.
            primary = i3 if i3 is not None else successful[0]
            reason_codes.append("no_real_text_no_noise_promotion")
        else:
            primary = 0 if metrics else None
            reason_codes.append("all_attempts_failed")

    supplemental = [i for i in range(len(metrics)) if i != primary]
    # Honest runtime metadata: the real Tesseract stdout path supplies no TSV
    # confidence, so selection runs on PSM role alone. When a supplied attempt
    # genuinely carries confidence, this flips to reflect it.
    confidence_available = any(m["mean_confidence"] is not None for m in metrics)
    selection_policy = (
        "psm_role_with_tsv_confidence" if confidence_available
        else "psm_role_without_tsv_confidence"
    )
    return {
        "primary_index": primary,
        "supplemental_indexes": supplemental,
        "metrics": metrics,
        "reason_codes": reason_codes,
        "confidence_available": confidence_available,
        "selection_policy": selection_policy,
    }


def _run_tesseract_on_bytes(
    image_bytes: bytes,
    *,
    suffix: str,
    tesseract_cmd: str,
    psm_modes: Sequence[int],
    request_timeout: int,
) -> dict[str, Any]:
    normalized_cmd = str(_normalize_git_bash_path(tesseract_cmd) or tesseract_cmd)
    attempts_full: list[dict[str, Any]] = []  # includes text, for selection
    with tempfile.TemporaryDirectory(prefix="trace_net_ocr_route_scan_") as tmp:
        input_path = Path(tmp) / f"page{suffix}"
        input_path.write_bytes(image_bytes)
        # Subprocess encoding/timeout behavior unchanged from the original runner.
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
                    # Retained for backward compatibility; no longer selects primary.
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
            attempts_full.append(attempt)

    selection = _select_primary_attempt(attempts_full)
    metrics = selection["metrics"]
    primary_index = selection["primary_index"]
    # Attach role/metric fields to each attempt record (text stripped for output).
    attempts = []
    for i, a in enumerate(attempts_full):
        row = {k: v for k, v in a.items() if k != "text"}
        m = metrics[i]
        row.update({
            "role": m["role"],
            "alpha_word_count": m["alpha_word_count"],
            "isolated_numeric_ratio": m["isolated_numeric_ratio"],
            "short_token_ratio": m["short_token_ratio"],
            "garbage_ratio": m["garbage_ratio"],
            "has_real_text": m["has_real_text"],
            "attempt_flags": m["flags"],
            "is_primary": i == primary_index,
        })
        attempts.append(row)

    primary = attempts_full[primary_index] if primary_index is not None else {"psm": None, "text": ""}
    primary_text = primary.get("text") or ""
    primary_ok = metrics[primary_index]["ok"] if primary_index is not None else False
    # Supplemental attempts (PSM 11 sparse callouts, PSM 6 blocks) are retained,
    # not discarded. Keep their text so route-specific processing can use them.
    supplemental_attempts = []
    for i in selection["supplemental_indexes"]:
        a = attempts_full[i]
        supplemental_attempts.append({
            "psm": a.get("psm"),
            "role": metrics[i]["role"],
            "returncode": a.get("returncode"),
            "ocr_text_char_count": a.get("ocr_text_char_count", 0),
            "ocr_text_word_count": a.get("ocr_text_word_count", 0),
            "part_number_tokens": a.get("part_number_tokens", []),
            "isolated_numeric_ratio": metrics[i]["isolated_numeric_ratio"],
            "garbage_ratio": metrics[i]["garbage_ratio"],
            "attempt_flags": metrics[i]["flags"],
            "ocr_text": a.get("text") or "",
        })
    # RAW, unfiltered PSM 11 whole-page text retained as a callout CANDIDATE only.
    # It is not filtered callouts (it still contains the page header/boilerplate);
    # actual callout extraction/filtering is Patch 5's figure-callout extractor.
    psm11_raw_text = next((a.get("text") or "" for a in attempts_full if a.get("psm") == 11), "")

    return {
        "tesseract_execution_status": "ok" if primary_ok else "error",
        "tesseract_cmd": normalized_cmd,
        "tesseract_attempt_count": len(attempts),
        "tesseract_attempts": attempts,
        # Compatibility fields: "best_*" now means the SELECTED PRIMARY attempt,
        # and supplemental attempts are preserved (not replaced) below.
        "best_psm": primary.get("psm"),
        "best_ocr_text": primary_text,
        "best_ocr_text_char_count": len(primary_text),
        "best_ocr_text_word_count": len(_tokens(primary_text)),
        "best_part_number_tokens": sorted(set(PART_RE.findall(primary_text)))[:50],
        # Patch 2 explicit contract:
        "primary_psm": primary.get("psm"),
        "primary_ocr_text": primary_text,
        "supplemental_ocr_attempts": supplemental_attempts,
        "supplemental_psm11_raw_text": psm11_raw_text,
        "supplemental_callout_text_is_filtered": False,
        "attempt_selection_metrics": metrics,
        "attempt_selection_reason_codes": selection["reason_codes"],
        "attempt_confidence_available": selection["confidence_available"],
        "attempt_selection_policy": selection["selection_policy"],
    }


def _tokens(text: str) -> list[str]:
    return WORD_RE.findall(text or "")


def _token_set(text: str) -> set[str]:
    return {t.lower() for t in WORD_RE.findall(text or "")}


def _supplemental_cross_psm_signal(primary_text: str, psm11_raw_text: str) -> dict[str, Any]:
    """Cross-PSM disagreement between PSM 3 (primary) and PSM 11 (sparse callout).

    Used by the Patch-4.2 diagram signal. PSM 11 remains a CANDIDATE stream only —
    this measures how many tokens PSM 11 surfaces that PSM 3 misses and their token
    overlap; it never confirms callouts as source truth.
    """
    s3 = _token_set(primary_text)
    s11 = _token_set(psm11_raw_text)
    union = s3 | s11
    agreement = round(len(s3 & s11) / len(union), 4) if union else 1.0
    return {
        "psm11_unique_token_count": len(s11 - s3),
        "psm3_psm11_agreement": agreement,
        "psm11_word_count": len(_tokens(psm11_raw_text)),
    }


def _keyword_count(tokens: Iterable[str], keywords: set[str]) -> int:
    normalized = [re.sub(r"[^a-z0-9]", "", t.lower()) for t in tokens]
    return sum(1 for t in normalized if t in keywords)


# --- Patch 3: text-only structural/prose/visual signals -----------------------
# Part numbers, numeric density, and table vocabulary are SUPPORTING signals; a
# confident table needs a text-structural cue (repeated columnar rows). Strong
# prose beats unsupported table vocabulary; dispersed diagram callouts strengthen
# image_visual. These are TEXT heuristics only; authoritative image geometry
# (fishnet word-boxes, table-line ruling) is applied downstream (Patch 4) and is
# not duplicated here.
_PROCEDURE_VERBS = frozenset({
    "remove", "install", "reinstall", "adjust", "torque", "tighten", "loosen",
    "apply", "replace", "inspect", "discard", "position", "rivet", "assemble",
    "disassemble", "connect", "disconnect", "secure", "align", "clean",
    "lubricate", "verify", "ensure", "perform", "repeat", "finish", "fit",
    "attach", "detach", "route", "torque",
})
_BARE_INT_RE = re.compile(r"^\d+$")
_HAS_DIGIT_RE = re.compile(r"\d")
_LEADING_ITEM_RE = re.compile(r"^\(?\d{1,3}[\).]?\s")
_TRAILING_NUM_RE = re.compile(r"\d+\s*$")
_FIGURE_RE = re.compile(r"\bfig(?:ure)?\b", re.I)


def _content_lines(text: str) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def _prose_signal(text: str, tokens: list[str]) -> dict[str, Any]:
    lines = _content_lines(text)
    alpha_words = [t for t in tokens if len(t) >= 3 and any(c.isalpha() for c in t)]
    isolated_numbers = [t for t in tokens if _BARE_INT_RE.match(t)]
    long_nl_lines = sum(
        1 for ln in lines
        if sum(1 for w in ln.split() if len(w) >= 3 and any(c.isalpha() for c in w)) >= 6
    )
    sentence_punct = text.count(". ") + text.count(".\n") + text.count("; ") + (1 if text.rstrip().endswith(".") else 0)
    verbs = sum(1 for t in tokens if t.lower() in _PROCEDURE_VERBS)
    alpha_to_number = len(alpha_words) / max(1, len(isolated_numbers))
    strong = long_nl_lines >= 3 and alpha_to_number >= 2.0 and (verbs >= 1 or sentence_punct >= 3)
    return {
        "strong": strong,
        "long_nl_lines": long_nl_lines,
        "sentence_punct": sentence_punct,
        "procedure_verbs": verbs,
        "alpha_to_number_ratio": round(alpha_to_number, 2),
        "alpha_word_count": len(alpha_words),
    }


def _table_structure_signal(text: str) -> dict[str, Any]:
    """Count repeated COLUMNAR rows in the OCR text (item/part/qty shape), not
    scattered callout numbers or prose lines. Text-only; no image geometry."""
    rows = 0
    for ln in _content_lines(text):
        toks = ln.split()
        if len(toks) < 2:
            continue
        alpha = [t for t in toks if len(t) >= 3 and any(c.isalpha() for c in t)]
        lower = " " + ln.lower() + " "
        is_prose_line = (
            len(alpha) >= 6
            or ln.rstrip().endswith((".", ";", ":"))
            or " the " in lower or " and " in lower or " with " in lower or " as " in lower
        )
        if is_prose_line:
            continue
        has_part = bool(PART_RE.search(ln))
        trailing_num = bool(_TRAILING_NUM_RE.search(ln))
        leading_item = bool(_LEADING_ITEM_RE.match(ln))
        row_like = (has_part and trailing_num) or (leading_item and 1 <= len(alpha) <= 4 and trailing_num)
        if row_like:
            rows += 1
    return {"rows": rows, "has_structure": rows >= 3}


def _dispersed_callout_signal(text: str, tokens: list[str]) -> dict[str, Any]:
    short_numeric = [t for t in tokens if _BARE_INT_RE.match(t) and len(t) <= 2]
    alpha_words = [t for t in tokens if len(t) >= 3 and any(c.isalpha() for c in t)]
    figure_caption = bool(_FIGURE_RE.search(text or ""))
    dispersed = (
        (len(short_numeric) >= 6 and len(alpha_words) < 14)
        or (figure_caption and len(short_numeric) >= 8 and len(alpha_words) < 20)
    )
    return {
        "dispersed": dispersed,
        "short_numeric_callouts": len(short_numeric),
        "figure_caption": figure_caption,
        "alpha_word_count": len(alpha_words),
    }


# --- Patch 4.2: index/TOC structure + sparse-diagram signals -------------------
# General, text-only structure signals (no page-number conditions). An index or
# table-of-contents is a real tabular structure even without visible ruling lines:
# repeated vendor-code/address rows, or repeated "subject <dotted leaders> page"
# rows, are columnar. A sparse technical diagram is prose-poor but carries a
# figure/drawing title and many PSM-11 candidate callout labels that PSM 3 misses
# (low PSM3/PSM11 agreement). Ordinary prose (no leaders, no leading code tokens,
# or high PSM agreement) must NOT trigger either signal.
_VENDOR_CODE_RE = re.compile(r"^[A-Z]{1,3}\d{4,}\b")
_VENDOR_CODE_ONLY_RE = re.compile(r"^[A-Z]{1,3}\d{4,}$")
_DOTTED_LEADER_RE = re.compile(r"\.{4,}\s*(?:\d{1,5}|NOT\s+APPLICABLE|[ivxlcdm]{1,6})\s*$", re.I)
# A real figure/drawing TITLE cue. Deliberately strict so a table column header such
# as "CH-SEC-UN-FIG" (which merely contains the letters FIG) is NOT read as a figure
# title: require the spelled-out word "figure", "fig" immediately followed by a
# number, an explicit drawing/exploded word, or a SECTION A-A style cutaway label.
_DRAWING_TITLE_RE = re.compile(
    r"\bfigure\b|\bfig\.?\s*\d|\bdrawing\b|\bexploded\b|\bsection\s+[A-Z]\s*-\s*[A-Z]\b", re.I
)
_DRAWING_NUMBER_RE = re.compile(r"\d+TP\d+|\.MC[A-Z]\b", re.I)
# Subject + trailing page target (page number / roman / NOT APPLICABLE). Used only
# when a TOC header cue is present, so ordinary lines ending in a number do not fire.
_TRAILING_PAGE_RE = re.compile(r"(?:\d{1,4}|NOT\s+APPLICABLE|[ivxlcdm]{1,6})\s*$", re.I)


def _index_structure_signal(text: str) -> dict[str, Any]:
    """Detect whitespace-aligned index/TOC/vendor structure (columnar, may lack
    ruling lines). Robust to noisy OCR: vendor codes read onto their own lines still
    count, and a TOC header with subject+trailing-page rows counts even when Tesseract
    mangles the dotted leaders into garbage. Returns counts + whether to fire."""
    dotted = vendor = vendor_only = trailing_page = 0
    for ln in _content_lines(text):
        s = ln.strip()
        if _DOTTED_LEADER_RE.search(ln):
            dotted += 1
        m = _VENDOR_CODE_RE.match(s)
        if m:
            rest = s[m.end():]
            if sum(1 for w in rest.split() if len(w) >= 3 and any(c.isalpha() for c in w)) >= 1:
                vendor += 1
        if _VENDOR_CODE_ONLY_RE.match(s):
            vendor_only += 1
        alpha = sum(1 for w in s.split() if len(w) >= 3 and any(c.isalpha() for c in w))
        if alpha >= 1 and _TRAILING_PAGE_RE.search(s):
            trailing_page += 1
    low = (text or "").lower()
    header_vendor = "vendor" in low and "code" in low and ("name" in low or "address" in low)
    header_toc = ("subject" in low and "page" in low) or "table of contents" in low
    header_cue = header_vendor or header_toc
    fires = (
        dotted >= 3
        or vendor >= 3
        or (header_vendor and vendor_only >= 2)
        or (header_cue and (dotted >= 1 or vendor >= 1))
        or (header_toc and trailing_page >= 3)
    )
    kind = "vendor_index" if max(vendor, vendor_only) >= dotted else "toc_leader_index"
    rows = max(dotted, vendor, vendor_only, trailing_page if header_toc else 0)
    return {
        "fires": fires, "dotted_leader_rows": dotted, "vendor_code_rows": vendor,
        "vendor_code_only_rows": vendor_only, "trailing_page_rows": trailing_page,
        "header_cue": header_cue, "rows": rows, "kind": kind,
    }


def _diagram_signal(
    text: str,
    tokens: list[str],
    structure: Mapping[str, Any],
    prose: Mapping[str, Any],
    supplemental: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Detect a sparse technical diagram: a figure/drawing title, prose-poor body,
    and strong PSM3/PSM11 disagreement (PSM 11 recovers many candidate callout
    labels PSM 3 misses). Requires supplemental PSM-11 evidence; without it, does
    not fire (so a page with no cross-PSM signal is never guessed as a diagram)."""
    title = bool(_DRAWING_TITLE_RE.search(text or "")) or bool(_DRAWING_NUMBER_RE.search(text or ""))
    alpha_words = [t for t in tokens if len(t) >= 3 and any(c.isalpha() for c in t)]
    sparse = int(prose.get("long_nl_lines", 0)) < 5 and len(alpha_words) < 70
    u11 = int((supplemental or {}).get("psm11_unique_token_count") or 0)
    agree = float((supplemental or {}).get("psm3_psm11_agreement") if supplemental and supplemental.get("psm3_psm11_agreement") is not None else 1.0)
    disagreement = u11 >= 12 and agree <= 0.60
    fires = bool(
        title and sparse and disagreement
        and not structure.get("has_structure")
        and not prose.get("strong")
    )
    return {
        "fires": fires, "title": title, "psm11_unique_token_count": u11,
        "psm3_psm11_agreement": round(agree, 4), "alpha_word_count": len(alpha_words),
    }


def _classify_route(
    *,
    text: str,
    image_features: Mapping[str, Any],
    tesseract_status: str | None,
    supplemental: Mapping[str, Any] | None = None,
) -> tuple[str, float, list[str]]:
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

    # Text-only signals. Supporting cues (parts / table vocab / numeric density)
    # never independently authorize a table; a confident table needs structure.
    structure = _table_structure_signal(text)
    prose = _prose_signal(text, tokens)
    callouts = _dispersed_callout_signal(text, tokens)
    index = _index_structure_signal(text)
    diagram = _diagram_signal(text, tokens, structure, prose, supplemental)
    # Numeric density alone (addresses, phone numbers, dates, ATA codes) is NOT
    # table evidence and may not authorize a table candidate; only genuine table
    # vocabulary (part numbers / table keywords) may.
    supporting_table = len(part_numbers) >= 2 or table_count >= 4

    # 1. Confident table: repeated columnar rows (structural evidence).
    if structure["has_structure"]:
        reasons.append(f"table_structural_rows:{structure['rows']}")
        return "table", min(0.95, 0.55 + 0.05 * structure["rows"] + 0.02 * table_count), reasons

    # 2. Index / table-of-contents / vendor structure (columnar without ruling).
    # A repeated vendor-code+name or subject+dotted-leader+page structure is a
    # searchable index and routes table/index primary. This runs before the prose
    # gate so a dotted-leader TOC is not misread as descriptive prose. Ordinary
    # prose lacks the leader/code shape and does not reach here.
    if index["fires"]:
        reasons.append(f"index_structural_rows:{index['rows']}:{index['kind']}")
        return "table", min(0.9, 0.6 + 0.04 * index["rows"] + (0.1 if index["header_cue"] else 0.0)), reasons

    # 3. Strong prose beats unsupported table vocabulary. This covers imperative
    # procedures (prose.strong) and descriptive prose (legends/descriptions) that
    # are heavily prose-dominated but carry no real part numbers — table keyword
    # density alone must not override obvious prose.
    descriptive_prose = (
        prose["long_nl_lines"] >= 5
        and prose["alpha_to_number_ratio"] >= 4.0
        and len(part_numbers) <= 1
    )
    if prose["strong"] or descriptive_prose:
        reasons.append("strong_prose_over_table_vocab" if prose["strong"] else "descriptive_prose_over_table_vocab")
        return "normal_text", min(0.95, 0.55 + min(token_count, 200) / 500), reasons

    # 4. Sparse technical diagram: figure/drawing title + prose-poor body + strong
    # PSM3/PSM11 disagreement (PSM 11 recovers many candidate callout labels PSM 3
    # misses). Runs after the prose gate so genuine procedures stay normal_text;
    # requires cross-PSM disagreement so a noisy-but-prose page is not flipped.
    if diagram["fires"]:
        reasons.append(f"diagram_sparse_callouts_psm_disagreement:{diagram['psm11_unique_token_count']}")
        return "image_visual", 0.85, reasons

    # 5. Mixed page (some table rows + dispersed callouts): defer to validator.
    if structure["rows"] >= 2 and callouts["dispersed"]:
        reasons.append("mixed_table_and_visual_requires_validator")
        return "image_visual", 0.5, reasons

    # 4. Dispersed diagram callouts strengthen image_visual, not table.
    if callouts["dispersed"]:
        reasons.append(f"dispersed_callouts_visual:{callouts['short_numeric_callouts']}")
        return "image_visual", min(0.9, 0.55 + 0.03 * callouts["short_numeric_callouts"]), reasons

    if visual_count >= 2 and token_count < 180:
        reasons.append("visual_keywords_with_limited_text")
        return "image_visual", min(0.9, 0.5 + 0.07 * visual_count), reasons

    if token_count < 8 and isinstance(ink_ratio, (int, float)) and ink_ratio > 0.02:
        reasons.append("low_ocr_text_nonblank_image")
        return "image_visual", 0.6, reasons

    # 5. Genuine table vocabulary (parts/keywords) but no structure: low-confidence
    # table CANDIDATE that preserves recall and defers to downstream geometry /
    # validator (Patch 4). Strong-prose and dispersed-callout pages were already
    # routed above, so this does not fire on procedures or diagrams.
    if supporting_table:
        reasons.append("table_supporting_only_no_structure_candidate")
        return "table", 0.5, reasons

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
    supplemental = _supplemental_cross_psm_signal(
        text, tesseract_payload.get("supplemental_psm11_raw_text") or ""
    )
    route, confidence, route_reasons = _classify_route(
        text=text,
        image_features=features,
        tesseract_status=tesseract_payload.get("tesseract_execution_status"),
        supplemental=supplemental,
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
        # Patch 2: role-based primary + retained supplemental attempts.
        "tesseract_primary_psm": tesseract_payload.get("primary_psm"),
        "tesseract_supplemental_ocr_attempts": tesseract_payload.get("supplemental_ocr_attempts", []),
        "tesseract_supplemental_psm11_raw_text": tesseract_payload.get("supplemental_psm11_raw_text", ""),
        "tesseract_supplemental_callout_text_is_filtered": False,
        "attempt_confidence_available": tesseract_payload.get("attempt_confidence_available", False),
        "attempt_selection_policy": tesseract_payload.get("attempt_selection_policy", "psm_role_without_tsv_confidence"),
        "tesseract_attempt_selection_reason_codes": tesseract_payload.get("attempt_selection_reason_codes", []),
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
