"""Progress-enabled OCR pilot runner.

This module intentionally reuses the existing OCR pilot source discovery,
TIFF extraction, OCR execution, and OCR-depth classification helpers. It adds
only streaming progress output so long OCR runs show page-by-page status.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, TextIO
import json
import shutil
import time

from tiff.ocr_pilot import (
    OcrPilotRecord,
    OcrPilotSummary,
    _classify_output_text,
    _extract_or_copy_tiff,
    _read_text,
    _run_tesseract,
    _safe_name,
    _write_page_index,
    source_pages_from_export,
    source_pages_from_root,
    source_pages_from_zip,
)


def _format_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "-"
    seconds = max(0, int(round(float(seconds))))
    if seconds < 60:
        return f"{seconds}s"
    minutes, rem = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {rem}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m {rem}s"


def _write_progress(line: str, *, progress_file: TextIO | None = None) -> None:
    stream = progress_file
    if stream is None:
        print(line, flush=True)
    else:
        print(line, file=stream, flush=True)


def _tesseract_available(tesseract_cmd: str) -> bool:
    # shutil.which works for PATH commands. Some Git Bash invocations pass a
    # direct /c/... path to Windows Python; if which fails, keep the legacy
    # behavior safe and let _run_tesseract produce the real error if needed.
    return shutil.which(tesseract_cmd) is not None or Path(tesseract_cmd).exists()


def run_ocr_pilot_with_progress(
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
    progress: bool = True,
    progress_every: int = 1,
    progress_file: TextIO | None = None,
) -> OcrPilotSummary:
    """Run OCR pilot and emit streaming page progress.

    Progress lines are emitted after each selected page, for example:

        [1/509] zip_page_000001 -> ocr_succeeded class=likely_full_page chars=487 page_time=2s avg=2s eta=17m 4s
    """

    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    output_path = Path(output_dir)
    pages_dir = output_path / "pages"
    ocr_dir = output_path / "ocr"
    reports_dir = output_path / "reports"
    for directory in (pages_dir, ocr_dir, reports_dir):
        directory.mkdir(parents=True, exist_ok=True)

    source_count = sum(1 for value in (zip_path, root, export_dir) if value is not None)
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

    total = len(pages)
    tesseract_available = _tesseract_available(tesseract_cmd)
    engine_used = engine
    if engine == "auto":
        engine_used = "tesseract" if tesseract_available else "existing"

    records: list[OcrPilotRecord] = []
    started = time.monotonic()
    progress_every = max(1, int(progress_every or 1))

    if progress:
        _write_progress(
            "OCR pilot progress: "
            f"selected_pages={total} engine={engine_used} psm={psm if psm is not None else '-'} "
            f"output_dir={output_path}",
            progress_file=progress_file,
        )

    for index, page in enumerate(pages, start=1):
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

        elapsed = round(time.monotonic() - per_started, 3)
        record = OcrPilotRecord(
            page_id=page.page_id,
            source_name=page.source_name,
            status=status,
            engine=engine_used,
            tiff_path=str(tiff_out) if tiff_out else None,
            ocr_path=str(ocr_out) if ocr_out.exists() else None,
            existing_ocr_path=page.existing_ocr_path,
            page_label=page.page_label,
            ata_code=page.ata_code,
            elapsed_seconds=elapsed,
            returncode=returncode,
            classification=classification,
            visible_chars=int(metrics["visible_chars"]),
            line_count=int(metrics["line_count"]),
            word_count=int(metrics["word_count"]),
            part_count=int(metrics["part_count"]),
            error=err,
            command=cmd,
        )
        records.append(record)

        if progress and (index == 1 or index == total or index % progress_every == 0):
            elapsed_total = time.monotonic() - started
            avg = elapsed_total / max(index, 1)
            eta = avg * max(total - index, 0)
            classification_label = record.classification or "-"
            _write_progress(
                f"[{index}/{total}] {record.page_id} -> {record.status} "
                f"class={classification_label} chars={record.visible_chars} "
                f"page_time={_format_duration(record.elapsed_seconds)} "
                f"avg={_format_duration(avg)} eta={_format_duration(eta)}",
                progress_file=progress_file,
            )
            if record.error:
                _write_progress(f"  error: {record.error}", progress_file=progress_file)

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
    summary_status = "OK" if pages and usable > 0 and ocr_failed == 0 and missing_engine == 0 else "NEEDS ATTENTION"

    manifest_path = reports_dir / "ocr_pilot_manifest.json"
    report_path = reports_dir / "ocr_pilot_report.json"
    page_index_path = _write_page_index(output_path, records)

    summary = OcrPilotSummary(
        status=summary_status,
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
