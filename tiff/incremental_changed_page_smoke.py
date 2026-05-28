"""Controlled changed-page smoke test helpers.

The smoke test uses a temporary one-file TIFF root so it does not need to touch
or corrupt the real sample TIFF tree. It copies one known indexed source TIFF,
seeds a temporary incremental state database, mutates the copy, and then runs
the normal safe incremental pipeline in changed-pages mode with OCR skipped.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from tiff.incremental_pipeline import IncrementalPipelineConfig, load_pipeline_config, run_incremental_pipeline
from tiff.incremental_state import IncrementalStateDB, read_changed_list

DEFAULT_WORK_DIR = Path("local_data/incremental_smoke")


@dataclass(frozen=True)
class SmokeSourcePage:
    page_id: str
    manual_id: str
    page_label: str
    ata_code: str
    tiff_path: str
    ocr_text_path: str
    rescarta_url: str
    source_url: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SmokePreparedChange:
    source_page: SmokeSourcePage
    work_dir: str
    temp_tiff_root: str
    temp_tiff_path: str
    temp_state_db: str
    temp_changed_list: str
    initial_state_rows: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChangedPageSmokeReport:
    ok: bool
    config_path: str
    db_path: str
    work_dir: str
    dry_run: bool
    source_page: dict[str, Any]
    temp_tiff_path: str
    changed_list: str
    changed_list_count: int
    changed_list_rows: list[str]
    new_files: int
    changed_files: int
    unchanged_files: int
    state_committed: bool
    commit_message: str
    backend_command_planned: bool
    changed_page_command_used: bool
    full_backend_command_used: bool
    ocr_command_skipped: bool
    failed_commands: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _connect_ro(db_path: str | os.PathLike[str]) -> sqlite3.Connection:
    path = Path(db_path)
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?", (table_name,)).fetchone()
    return row is not None


def _normalize_part(value: str) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _row_to_source_page(row: Mapping[str, Any]) -> SmokeSourcePage:
    return SmokeSourcePage(
        page_id=str(row.get("page_id") or ""),
        manual_id=str(row.get("manual_id") or ""),
        page_label=str(row.get("page_label") or ""),
        ata_code=str(row.get("ata_code") or ""),
        tiff_path=str(row.get("tiff_path") or ""),
        ocr_text_path=str(row.get("ocr_text_path") or ""),
        rescarta_url=str(row.get("rescarta_url") or ""),
        source_url=str(row.get("source_url") or ""),
    )


def select_smoke_source_page(
    db_path: str | os.PathLike[str],
    *,
    sample_part: str | None = "120-37313-001",
) -> SmokeSourcePage:
    """Select an indexed page with a real TIFF path for the smoke test."""

    with _connect_ro(db_path) as conn:
        if not _table_exists(conn, "source_links"):
            raise RuntimeError("source_links table does not exist")

        if sample_part and _table_exists(conn, "part_mentions"):
            norm = _normalize_part(sample_part)
            row = conn.execute(
                """
                SELECT
                    sl.page_id,
                    sl.manual_id,
                    COALESCE(sl.page_label, p.page_label, '') AS page_label,
                    COALESCE(sl.ata_code, p.ata_code, '') AS ata_code,
                    COALESCE(sl.tiff_path, p.tiff_path, '') AS tiff_path,
                    COALESCE(sl.ocr_text_path, p.ocr_text_path, '') AS ocr_text_path,
                    COALESCE(sl.rescarta_url, '') AS rescarta_url,
                    COALESCE(sl.source_url, '') AS source_url
                FROM part_mentions pm
                JOIN source_links sl ON sl.page_id = pm.page_id
                LEFT JOIN pages p ON p.page_id = sl.page_id
                WHERE pm.part_number_normalized = ?
                  AND COALESCE(sl.tiff_path, p.tiff_path, '') <> ''
                ORDER BY p.page_sequence, sl.page_id
                LIMIT 1
                """,
                (norm,),
            ).fetchone()
            if row is not None:
                return _row_to_source_page(dict(row))

        row = conn.execute(
            """
            SELECT
                sl.page_id,
                sl.manual_id,
                COALESCE(sl.page_label, p.page_label, '') AS page_label,
                COALESCE(sl.ata_code, p.ata_code, '') AS ata_code,
                COALESCE(sl.tiff_path, p.tiff_path, '') AS tiff_path,
                COALESCE(sl.ocr_text_path, p.ocr_text_path, '') AS ocr_text_path,
                COALESCE(sl.rescarta_url, '') AS rescarta_url,
                COALESCE(sl.source_url, '') AS source_url
            FROM source_links sl
            LEFT JOIN pages p ON p.page_id = sl.page_id
            WHERE COALESCE(sl.tiff_path, p.tiff_path, '') <> ''
            ORDER BY p.page_sequence, sl.page_id
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            raise RuntimeError("No source_links row with a TIFF path was found")
        return _row_to_source_page(dict(row))


def _state_row_count(state_db: str | os.PathLike[str]) -> int:
    path = Path(state_db)
    if not path.exists():
        return 0
    try:
        with sqlite3.connect(path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM incremental_file_state").fetchone()
            return int(row[0] if row else 0)
    except sqlite3.Error:
        return 0


def prepare_smoke_change(
    *,
    db_path: str | os.PathLike[str],
    work_dir: str | os.PathLike[str] = DEFAULT_WORK_DIR,
    sample_part: str | None = "120-37313-001",
    reset_work_dir: bool = True,
    hash_mode: str = "stat",
) -> SmokePreparedChange:
    """Create a temporary changed TIFF and seeded temporary state DB."""

    source = select_smoke_source_page(db_path, sample_part=sample_part)
    source_tiff = Path(source.tiff_path)
    if not source_tiff.exists():
        raise FileNotFoundError(f"Source TIFF does not exist: {source_tiff}")

    work = Path(work_dir)
    if reset_work_dir and work.exists():
        shutil.rmtree(work)
    temp_root = work / "sample_tiffs"
    temp_root.mkdir(parents=True, exist_ok=True)
    temp_tiff = temp_root / source_tiff.name
    shutil.copy2(source_tiff, temp_tiff)

    state_db = work / "state.db"
    changed_list = work / "changed_tiffs.txt"
    state = IncrementalStateDB(state_db)
    initial = state.detect_changes(temp_root, hash_mode=hash_mode)
    state.commit_summary(initial, status="smoke_seed")

    # Mutate the temp copy only. The changed-page backend matches by filename/stem
    # and reads authoritative content from the ResCarta export, so OCR is skipped.
    with temp_tiff.open("ab") as fh:
        fh.write(b"\nINCREMENTAL_SMOKE_TEST_CHANGE\n")

    return SmokePreparedChange(
        source_page=source,
        work_dir=str(work),
        temp_tiff_root=str(temp_root),
        temp_tiff_path=str(temp_tiff),
        temp_state_db=str(state_db),
        temp_changed_list=str(changed_list),
        initial_state_rows=_state_row_count(state_db),
    )


def build_smoke_pipeline_config(
    base: IncrementalPipelineConfig,
    prepared: SmokePreparedChange,
    *,
    backend_mode: str = "changed-pages",
) -> IncrementalPipelineConfig:
    """Build the one-file smoke-test incremental config.

    ``IncrementalPipelineConfig`` still has backward-compatible alias fields
    such as ``root``, ``state_db_path``, ``changed_list_path``,
    ``scan_db_path``, and ``search_db_path``. ``load_pipeline_config()`` calls
    ``__post_init__()`` after applying overrides, so primary fields can be
    overwritten by stale alias values if only the primary names are supplied.

    Pass both the current field names and their aliases so the smoke test really
    scans the temporary one-file TIFF root instead of the real sample tree.
    """

    smoke_scan_db = str(Path(prepared.work_dir) / "scan.db")
    cfg = load_pipeline_config(
        base.config_path,
        tiff_root=prepared.temp_tiff_root,
        root=prepared.temp_tiff_root,
        state_db=prepared.temp_state_db,
        state_db_path=prepared.temp_state_db,
        changed_list=prepared.temp_changed_list,
        changed_list_path=prepared.temp_changed_list,
        hash_mode=base.hash_mode,
        db_path=base.db_path,
        search_db_path=base.db_path,
        rescarta_export_dir=base.rescarta_export_dir,
        embed_model=base.embed_model,
        questions=base.questions,
        json_dir=str(Path(prepared.work_dir) / "json_scans"),
        scan_db=smoke_scan_db,
        scan_db_path=smoke_scan_db,
        tesseract_cmd=base.tesseract_cmd,
        backend_mode=backend_mode,
    )
    return cfg


def run_changed_page_smoke_test(
    *,
    config_path: str | os.PathLike[str] = "local_config.yaml",
    work_dir: str | os.PathLike[str] = DEFAULT_WORK_DIR,
    sample_part: str | None = "120-37313-001",
    dry_run: bool = False,
    reset_work_dir: bool = True,
) -> ChangedPageSmokeReport:
    """Run the controlled smoke test and return a structured report."""

    base = load_pipeline_config(str(config_path), backend_mode="changed-pages")
    prepared = prepare_smoke_change(
        db_path=base.db_path,
        work_dir=work_dir,
        sample_part=sample_part,
        reset_work_dir=reset_work_dir,
        hash_mode=base.hash_mode,
    )
    cfg = build_smoke_pipeline_config(base, prepared, backend_mode="changed-pages")
    result = run_incremental_pipeline(cfg, dry_run=dry_run, skip_ocr=True)

    changed_rows = list(read_changed_list(prepared.temp_changed_list))
    failed = [item.name for item in result.results if item.status == "FAILED"]
    backend_command = next((cmd for cmd in result.commands if cmd.name == "backend_pipeline"), None)
    ocr_command = next((cmd for cmd in result.commands if cmd.name == "ocr_changed_tiffs"), None)
    backend_command_text = " ".join(backend_command.argv) if backend_command else ""

    errors: list[str] = []
    warnings: list[str] = []
    if result.summary.changed_list_count != 1:
        errors.append(f"Expected exactly 1 changed TIFF, found {result.summary.changed_list_count}.")
    if not backend_command or backend_command.skip_reason:
        errors.append("Changed-page backend command was not planned.")
    if "update_changed_page_backend.py" not in backend_command_text:
        errors.append("Backend command did not use scripts/update_changed_page_backend.py.")
    if "run_tiff_backend_pipeline.py" in backend_command_text:
        errors.append("Smoke test unexpectedly planned the full backend pipeline.")
    if ocr_command is not None and ocr_command.will_run:
        errors.append("OCR command was not skipped for the smoke test.")
    if failed:
        errors.append("Failed commands: " + ", ".join(failed))
    if not dry_run and not result.state_committed:
        errors.append("Incremental state was not committed after successful changed-page processing.")
    if dry_run and result.state_committed:
        errors.append("Dry run committed state unexpectedly.")
    if len(changed_rows) != result.summary.changed_list_count:
        warnings.append("changed_tiffs.txt row count did not match the detection summary.")

    ok = not errors
    return ChangedPageSmokeReport(
        ok=ok,
        config_path=str(config_path),
        db_path=str(base.db_path),
        work_dir=str(work_dir),
        dry_run=bool(dry_run),
        source_page=prepared.source_page.to_dict(),
        temp_tiff_path=prepared.temp_tiff_path,
        changed_list=prepared.temp_changed_list,
        changed_list_count=result.summary.changed_list_count,
        changed_list_rows=changed_rows,
        new_files=result.summary.new_files,
        changed_files=result.summary.changed_files,
        unchanged_files=result.summary.unchanged_files,
        state_committed=result.state_committed,
        commit_message=result.commit_message,
        backend_command_planned=bool(backend_command and backend_command.will_run),
        changed_page_command_used="update_changed_page_backend.py" in backend_command_text,
        full_backend_command_used="run_tiff_backend_pipeline.py" in backend_command_text,
        ocr_command_skipped=bool(ocr_command is None or not ocr_command.will_run),
        failed_commands=failed,
        warnings=warnings,
        errors=errors,
    )


def format_changed_page_smoke_report(report: ChangedPageSmokeReport) -> str:
    lines = [
        "Changed-page incremental smoke test",
        f"  Status: {'OK' if report.ok else 'NEEDS ATTENTION'}",
        f"  Config: {report.config_path}",
        f"  Work dir: {report.work_dir}",
        f"  DB: {report.db_path}",
        f"  Dry run: {report.dry_run}",
        "",
        "Sample source page:",
        f"  Page ID: {report.source_page.get('page_id', '-')}",
        f"  Manual: {report.source_page.get('manual_id', '-')}",
        f"  ATA: {report.source_page.get('ata_code', '-')}",
        f"  Page label: {report.source_page.get('page_label', '-')}",
        f"  Source TIFF: {report.source_page.get('tiff_path', '-')}",
        f"  Temp changed TIFF: {report.temp_tiff_path}",
        "",
        "Change detection:",
        f"  New files: {report.new_files}",
        f"  Changed files: {report.changed_files}",
        f"  Unchanged files: {report.unchanged_files}",
        f"  Changed list count: {report.changed_list_count}",
        f"  Changed list: {report.changed_list}",
        "",
        "Pipeline behavior:",
        f"  OCR skipped: {report.ocr_command_skipped}",
        f"  Changed-page backend planned: {report.backend_command_planned}",
        f"  Used changed-page update script: {report.changed_page_command_used}",
        f"  Used full backend rebuild: {report.full_backend_command_used}",
        f"  State committed: {report.state_committed}",
        f"  Commit message: {report.commit_message}",
    ]
    if report.failed_commands:
        lines.extend(["", "Failed commands:"])
        lines.extend(f"  - {item}" for item in report.failed_commands)
    if report.warnings:
        lines.extend(["", "Warnings:"])
        lines.extend(f"  - {item}" for item in report.warnings)
    if report.errors:
        lines.extend(["", "Errors:"])
        lines.extend(f"  - {item}" for item in report.errors)
    return "\n".join(lines)


def write_changed_page_smoke_json(report: ChangedPageSmokeReport, output_path: str | os.PathLike[str]) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
