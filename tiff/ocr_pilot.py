"""Safe OCR pilot utilities for TIFF source packages.

The pilot is intentionally isolated from the production/search database.  It
extracts or copies a small TIFF sample into a pilot folder, optionally runs a
configured OCR engine, classifies the generated text with the OCR-depth rules,
and writes a resumable report that can be reviewed before any large baseline OCR
job is attempted.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import json
import math
import os
import re
import shutil
import subprocess
import time
import zipfile

try:  # The OCR-depth module already exists in the project.
    from tiff.ocr_depth_audit import OcrDepthThresholds, classify_ocr_text
except Exception:  # pragma: no cover - only for partial installs during dev
    @dataclass(frozen=True)
    class OcrDepthThresholds:  # type: ignore[no-redef]
        short_max_chars: int = 120
        full_page_min_chars: int = 300

    def classify_ocr_text(text: str, thresholds: OcrDepthThresholds | None = None) -> tuple[str, dict[str, Any]]:  # type: ignore[no-redef]
        text = text.strip()
        if not text:
            return "empty_ocr", {"visible_chars": 0, "line_count": 0, "word_count": 0, "part_number_hits": 0}
        words = re.findall(r"\w+", text)
        return "likely_full_page" if len(text) >= 300 else "short_ocr", {
            "visible_chars": len(text),
            "line_count": len([x for x in text.splitlines() if x.strip()]),
            "word_count": len(words),
            "part_number_hits": 0,
        }


TIFF_EXTS = {".tif", ".tiff"}
TEXT_EXTS = {".txt"}
PART_RE = re.compile(r"\b(?:[A-Z]{1,4}\d{2,6}-\d{1,4}|\d{2,4}-\d{3,6}-\d{1,4}|\d{3,6}/\d{3,6})\b", re.I)


@dataclass
class OcrPilotSourcePage:
    page_id: str
    source_name: str
    tiff_path: str | None = None
    existing_ocr_path: str | None = None
    page_label: str | None = None
    ata_code: str | None = None


@dataclass
class OcrPilotRecord:
    page_id: str
    source_name: str
    status: str
    engine: str
    tiff_path: str | None = None
    ocr_path: str | None = None
    existing_ocr_path: str | None = None
    page_label: str | None = None
    ata_code: str | None = None
    elapsed_seconds: float = 0.0
    returncode: int | None = None
    classification: str | None = None
    visible_chars: int = 0
    line_count: int = 0
    word_count: int = 0
    part_count: int = 0
    error: str | None = None
    command: list[str] = field(default_factory=list)


@dataclass
class OcrPilotSummary:
    status: str
    source: str
    output_dir: str
    engine_requested: str
    engine_used: str
    tesseract_available: bool
    pages_selected: int = 0
    ocr_attempted: int = 0
    ocr_succeeded: int = 0
    ocr_failed: int = 0
    copied_existing: int = 0
    cached_existing: int = 0
    missing_ocr_engine: int = 0
    skipped_no_input: int = 0
    elapsed_seconds: float = 0.0
    by_status: dict[str, int] = field(default_factory=dict)
    by_classification: dict[str, int] = field(default_factory=dict)
    sample_records: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    files_written: dict[str, str] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


# ----------------------------- source discovery -----------------------------

def natural_key(text: str) -> list[Any]:
    return [int(chunk) if chunk.isdigit() else chunk.lower() for chunk in re.split(r"(\d+)", text)]


def _first_value(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return None


def _as_pages(obj: Any) -> list[dict[str, Any]]:
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        pages = obj.get("pages") or obj.get("items") or obj.get("records") or []
        if isinstance(pages, list):
            return [x for x in pages if isinstance(x, dict)]
    return []


def source_pages_from_zip(zip_path: str | Path, *, limit: int | None = None, offset: int = 0) -> list[OcrPilotSourcePage]:
    pages: list[OcrPilotSourcePage] = []
    with zipfile.ZipFile(zip_path) as zf:
        names = [info.filename for info in zf.infolist() if not info.is_dir() and Path(info.filename).suffix.lower() in TIFF_EXTS]
    names = sorted(names, key=natural_key)
    selected = names[offset : offset + limit if limit is not None else None]
    for idx, name in enumerate(selected, start=offset + 1):
        pages.append(
            OcrPilotSourcePage(
                page_id=f"zip_page_{idx:06d}",
                source_name=name,
                tiff_path=None,
                existing_ocr_path=None,
                page_label=str(idx),
            )
        )
    return pages


def source_pages_from_root(root: str | Path, *, limit: int | None = None, offset: int = 0) -> list[OcrPilotSourcePage]:
    root_path = Path(root)
    tiffs: list[Path] = []
    texts_by_stem: dict[str, Path] = {}
    for dirpath, _, filenames in os.walk(root_path):
        for filename in filenames:
            p = Path(dirpath) / filename
            suffix = p.suffix.lower()
            if suffix in TIFF_EXTS:
                tiffs.append(p)
            elif suffix in TEXT_EXTS:
                texts_by_stem[p.stem.lower()] = p
    tiffs = sorted(tiffs, key=lambda p: natural_key(str(p.relative_to(root_path))))
    selected = tiffs[offset : offset + limit if limit is not None else None]
    pages: list[OcrPilotSourcePage] = []
    for idx, path in enumerate(selected, start=offset + 1):
        rel = str(path.relative_to(root_path))
        pages.append(
            OcrPilotSourcePage(
                page_id=f"root_page_{idx:06d}",
                source_name=rel,
                tiff_path=str(path),
                existing_ocr_path=str(texts_by_stem[path.stem.lower()]) if path.stem.lower() in texts_by_stem else None,
                page_label=str(idx),
            )
        )
    return pages


def source_pages_from_export(export_dir: str | Path, *, limit: int | None = None, offset: int = 0, repo_root: str | Path | None = None) -> list[OcrPilotSourcePage]:
    export_path = Path(export_dir)
    page_index_path = export_path / "page_index.json"
    data = json.loads(page_index_path.read_text(encoding="utf-8"))
    repo_root_path = Path(repo_root) if repo_root is not None else Path.cwd()
    pages: list[OcrPilotSourcePage] = []
    page_rows = _as_pages(data)
    selected = page_rows[offset : offset + limit if limit is not None else None]
    for idx, row in enumerate(selected, start=offset + 1):
        page_id = str(_first_value(row, "page_id", "id", "node_id") or f"export_page_{idx:06d}")
        tiff_path = _first_value(row, "source_image_path", "tiff_path", "image_path", "source_tiff_path", "tiff")
        ocr_path = _first_value(row, "ocr_text_path", "ocr_path", "ocr", "ocr_file", "ocr_file_path")
        tiff_abs = _resolve_existing_path(tiff_path, repo_root_path)
        ocr_abs = _resolve_existing_path(ocr_path, repo_root_path)
        pages.append(
            OcrPilotSourcePage(
                page_id=page_id,
                source_name=str(tiff_path or page_id),
                tiff_path=str(tiff_abs) if tiff_abs else str(tiff_path) if tiff_path else None,
                existing_ocr_path=str(ocr_abs) if ocr_abs else str(ocr_path) if ocr_path else None,
                page_label=str(_first_value(row, "page_label", "label", "page") or ""),
                ata_code=str(_first_value(row, "ata_code", "ata") or ""),
            )
        )
    return pages


def _resolve_existing_path(value: Any, repo_root: Path) -> Path | None:
    if value in (None, ""):
        return None
    p = Path(str(value))
    if p.is_absolute():
        return p if p.exists() else p
    candidate = repo_root / p
    if candidate.exists():
        return candidate
    return p


# ----------------------------- OCR execution -----------------------------

def _safe_name(name: str) -> str:
    stem = Path(name.replace("\\", "/")).stem
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("_")
    return stem or "page"


def _extract_or_copy_tiff(page: OcrPilotSourcePage, *, zip_path: str | Path | None, pages_dir: Path, force: bool) -> Path | None:
    pages_dir.mkdir(parents=True, exist_ok=True)
    out_name = f"{page.page_id}_{_safe_name(page.source_name)}.tif"
    out_path = pages_dir / out_name
    if out_path.exists() and not force:
        return out_path
    if zip_path:
        with zipfile.ZipFile(zip_path) as zf:
            with zf.open(page.source_name) as src, out_path.open("wb") as dst:
                shutil.copyfileobj(src, dst)
        return out_path
    if page.tiff_path:
        src = Path(page.tiff_path)
        if src.exists():
            if src.resolve() != out_path.resolve():
                shutil.copy2(src, out_path)
            return out_path
    return None


def _read_text(path: Path | None) -> str:
    if not path or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _write_page_index(output_dir: Path, records: list[OcrPilotRecord]) -> Path:
    pages: list[dict[str, Any]] = []
    for rec in records:
        pages.append(
            {
                "page_id": rec.page_id,
                "page_label": rec.page_label,
                "ata_code": rec.ata_code,
                "source_image_path": rec.tiff_path,
                "ocr_text_path": rec.ocr_path,
                "ocr_pilot_status": rec.status,
                "ocr_depth_classification": rec.classification,
                "source_name": rec.source_name,
            }
        )
    path = output_dir / "page_index.json"
    path.write_text(json.dumps({"pages": pages}, indent=2), encoding="utf-8")
    return path


def _run_tesseract(tiff_path: Path, ocr_path: Path, *, tesseract_cmd: str, lang: str, psm: int | None, timeout_seconds: int) -> tuple[int, list[str], str | None]:
    base = ocr_path.with_suffix("")
    cmd = [tesseract_cmd, str(tiff_path), str(base), "-l", lang]
    if psm is not None:
        cmd.extend(["--psm", str(psm)])
    try:
        completed = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        return 127, cmd, f"OCR engine not found: {tesseract_cmd}"
    except subprocess.TimeoutExpired:
        return 124, cmd, f"OCR timed out after {timeout_seconds}s"
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "tesseract failed").strip()
        return completed.returncode, cmd, err[:500]
    if not ocr_path.exists():
        return completed.returncode, cmd, "OCR command finished but no .txt file was produced"
    return completed.returncode, cmd, None


def _classify_output_text(text: str, thresholds: OcrDepthThresholds | None = None) -> tuple[str, dict[str, Any]]:
    classification, metrics = classify_ocr_text(text, thresholds or OcrDepthThresholds())
    # Normalize both old/new metric names from OCR-depth implementations.
    return classification, {
        "visible_chars": int(metrics.get("visible_chars", metrics.get("chars", 0)) or 0),
        "line_count": int(metrics.get("line_count", metrics.get("lines", 0)) or 0),
        "word_count": int(metrics.get("word_count", metrics.get("words", 0)) or 0),
        "part_count": int(metrics.get("part_number_hits", metrics.get("parts", len(PART_RE.findall(text)))) or 0),
    }


def run_ocr_pilot(
    *,
    zip_path: str | Path | None = None,
    root: str | Path | None = None,
    export_dir: str | Path | None = None,
    output_dir: str | Path = "local_data/ocr/pilot",
    limit: int = 25,
    offset: int = 0,
    engine: str = "auto",
    tesseract_cmd: str = "tesseract",
    lang: str = "eng",
    psm: int | None = None,
    timeout_seconds: int = 120,
    force: bool = False,
    repo_root: str | Path | None = None,
    sample_limit: int = 10,
) -> OcrPilotSummary:
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    output_path = Path(output_dir)
    pages_dir = output_path / "pages"
    ocr_dir = output_path / "ocr"
    reports_dir = output_path / "reports"
    for d in (pages_dir, ocr_dir, reports_dir):
        d.mkdir(parents=True, exist_ok=True)

    source_count = sum(1 for x in (zip_path, root, export_dir) if x is not None)
    if source_count != 1:
        raise ValueError("Specify exactly one of --zip, --root, or --export-dir")

    if zip_path is not None:
        source = f"zip {zip_path}"
        pages = source_pages_from_zip(zip_path, limit=limit, offset=offset)
    elif root is not None:
        source = f"root {root}"
        pages = source_pages_from_root(root, limit=limit, offset=offset)
    else:
        source = f"export {export_dir}"
        pages = source_pages_from_export(export_dir or "", limit=limit, offset=offset, repo_root=repo_root)

    tesseract_available = shutil.which(tesseract_cmd) is not None
    engine_used = engine
    if engine == "auto":
        engine_used = "tesseract" if tesseract_available else "existing"

    records: list[OcrPilotRecord] = []
    started = time.monotonic()

    for page in pages:
        per_started = time.monotonic()
        tiff_out = _extract_or_copy_tiff(page, zip_path=zip_path, pages_dir=pages_dir, force=force)
        ocr_out = ocr_dir / f"{page.page_id}_{_safe_name(page.source_name)}.txt"
        status = "unknown"
        err: str | None = None
        cmd: list[str] = []
        returncode: int | None = None

        if not tiff_out:
            status = "skipped_no_input"
            err = "No TIFF input could be extracted or copied for this page"
        elif ocr_out.exists() and not force:
            status = "cached"
        elif engine_used == "existing":
            if page.existing_ocr_path and Path(page.existing_ocr_path).exists():
                shutil.copy2(page.existing_ocr_path, ocr_out)
                status = "copied_existing"
            else:
                status = "missing_ocr_engine"
                err = "No OCR engine is available and no existing OCR text was found for this page"
        elif engine_used == "none":
            status = "missing_ocr_engine"
            err = "OCR engine disabled by --engine none"
        elif engine_used == "tesseract":
            returncode, cmd, err = _run_tesseract(
                tiff_out,
                ocr_out,
                tesseract_cmd=tesseract_cmd,
                lang=lang,
                psm=psm,
                timeout_seconds=timeout_seconds,
            )
            status = "ocr_succeeded" if err is None and ocr_out.exists() else "ocr_failed"
        else:
            status = "ocr_failed"
            err = f"Unknown OCR engine: {engine_used}"

        text = _read_text(ocr_out)
        classification: str | None = None
        metrics = {"visible_chars": 0, "line_count": 0, "word_count": 0, "part_count": 0}
        if text or ocr_out.exists():
            classification, metrics = _classify_output_text(text)

        records.append(
            OcrPilotRecord(
                page_id=page.page_id,
                source_name=page.source_name,
                status=status,
                engine=engine_used,
                tiff_path=str(tiff_out) if tiff_out else None,
                ocr_path=str(ocr_out) if ocr_out.exists() else None,
                existing_ocr_path=page.existing_ocr_path,
                page_label=page.page_label,
                ata_code=page.ata_code,
                elapsed_seconds=round(time.monotonic() - per_started, 3),
                returncode=returncode,
                classification=classification,
                visible_chars=metrics["visible_chars"],
                line_count=metrics["line_count"],
                word_count=metrics["word_count"],
                part_count=metrics["part_count"],
                error=err,
                command=cmd,
            )
        )

    by_status: dict[str, int] = {}
    by_class: dict[str, int] = {}
    for rec in records:
        by_status[rec.status] = by_status.get(rec.status, 0) + 1
        if rec.classification:
            by_class[rec.classification] = by_class.get(rec.classification, 0) + 1

    warnings: list[str] = []
    if by_status.get("missing_ocr_engine", 0):
        warnings.append("No usable OCR engine/existing OCR was available for some selected pages.")
    if by_status.get("ocr_failed", 0):
        warnings.append("Some OCR commands failed; inspect per-page errors before scaling.")
    if by_class.get("empty_ocr", 0):
        warnings.append("Some pilot OCR outputs are empty.")
    if by_class.get("likely_header_only", 0):
        warnings.append("Some pilot OCR outputs look header-only; full-page OCR quality may be insufficient.")

    ocr_succeeded = by_status.get("ocr_succeeded", 0)
    copied_existing = by_status.get("copied_existing", 0)
    cached_existing = by_status.get("cached", 0)
    missing_engine = by_status.get("missing_ocr_engine", 0)
    ocr_failed = by_status.get("ocr_failed", 0)
    skipped_no_input = by_status.get("skipped_no_input", 0)
    attempted = ocr_succeeded + ocr_failed
    usable = ocr_succeeded + copied_existing + cached_existing
    status = "OK" if pages and usable > 0 and ocr_failed == 0 and missing_engine == 0 else "NEEDS ATTENTION"

    manifest_path = reports_dir / "ocr_pilot_manifest.json"
    report_path = reports_dir / "ocr_pilot_report.json"
    page_index_path = _write_page_index(output_path, records)

    summary = OcrPilotSummary(
        status=status,
        source=source,
        output_dir=str(output_path),
        engine_requested=engine,
        engine_used=engine_used,
        tesseract_available=tesseract_available,
        pages_selected=len(pages),
        ocr_attempted=attempted,
        ocr_succeeded=ocr_succeeded,
        ocr_failed=ocr_failed,
        copied_existing=copied_existing,
        cached_existing=cached_existing,
        missing_ocr_engine=missing_engine,
        skipped_no_input=skipped_no_input,
        elapsed_seconds=round(time.monotonic() - started, 3),
        by_status=by_status,
        by_classification=by_class,
        sample_records=[asdict(r) for r in records[:sample_limit]],
        warnings=warnings,
        files_written={
            "manifest": str(manifest_path),
            "report": str(report_path),
            "page_index": str(page_index_path),
        },
    )

    manifest_path.write_text(json.dumps([asdict(r) for r in records], indent=2), encoding="utf-8")
    report_path.write_text(json.dumps(summary.to_json_dict(), indent=2), encoding="utf-8")
    return summary
