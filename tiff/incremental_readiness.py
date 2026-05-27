"""Incremental pipeline readiness checks for the local TIFF backend.

This module is intentionally read-only. It does not update the incremental
state database, does not write changed_tiffs.txt, and does not run OCR/backend
commands. It answers a simpler question: is the current repo/config ready to
use the safe incremental/change-page path?
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from tiff.incremental_pipeline import (
    IncrementalPipelineConfig,
    PipelineCommand,
    PipelineCommandResult,
    build_commands,
    load_pipeline_config,
    should_commit_state,
)
from tiff.incremental_state import ChangeDetectionSummary

TIFF_EXTENSIONS = {".tif", ".tiff"}
DEFAULT_QUALITY_PATH = Path("local_data/pipeline_runs/latest_quality_gate.json")
DEFAULT_MANIFEST_PATH = Path("local_data/pipeline_runs/latest_backend_pipeline.json")


def _normalize_hash_mode(hash_mode: str) -> str:
    value = (hash_mode or "stat").strip().lower()
    if value in {"sha256", "hash", "content", "file"}:
        return "content"
    if value in {"stat", "mtime", "size"}:
        return "stat"
    raise ValueError("hash_mode must be 'stat', 'content', or 'sha256'")


@dataclass(frozen=True)
class IncrementalPreview:
    files_seen: int = 0
    new_files: int = 0
    changed_files: int = 0
    unchanged_files: int = 0
    missing_files: int = 0
    changed_list_count: int = 0
    state_rows: int = 0
    state_db_exists: bool = False
    state_table_exists: bool = False
    sample_changed_paths: list[str] = field(default_factory=list)
    sample_missing_paths: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class IncrementalReadinessReport:
    config_path: str
    tiff_root: str
    state_db: str
    changed_list: str
    hash_mode: str
    backend_mode: str
    db_path: str
    rescarta_export_dir: str
    questions: str
    tiff_root_exists: bool
    state_db_exists: bool
    state_rows: int
    changed_list_parent_exists: bool
    db_path_exists: bool
    rescarta_export_dir_exists: bool
    questions_exists: bool
    changed_page_script_exists: bool
    changed_page_module_exists: bool
    changed_pages_backend_available: bool
    backend_mode_uses_changed_pages: bool
    changed_pages_command_planned: bool
    dry_run_state_commit_safe: bool
    failed_downstream_state_commit_safe: bool
    successful_downstream_state_commit_allowed: bool
    files_seen: int
    preview_new_files: int
    preview_changed_files: int
    preview_unchanged_files: int
    preview_missing_files: int
    preview_changed_list_count: int
    quality_status: str | None = None
    manifest_status: str | None = None
    manifest_run_id: str | None = None
    manifest_has_source_link_audit: bool | None = None
    source_local_review_ready: bool | None = None
    source_real_rescarta_ready: bool | None = None
    ok: bool = False
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def read_json(path: str | os.PathLike[str]) -> dict[str, Any] | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _iter_tiff_paths(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in TIFF_EXTENSIONS)


def _fingerprint(path: Path, hash_mode: str) -> str:
    mode = _normalize_hash_mode(hash_mode)
    if mode == "content":
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for block in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(block)
        return "sha256:" + digest.hexdigest()
    st = path.stat()
    return f"stat:{st.st_size}:{st.st_mtime_ns}"


def _read_previous_state(state_db: Path) -> tuple[dict[str, Mapping[str, Any]], bool, bool]:
    if not state_db.exists():
        return {}, False, False
    uri = f"file:{state_db.as_posix()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error:
        return {}, True, False
    conn.row_factory = sqlite3.Row
    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='incremental_file_state'"
        ).fetchone()
        if table is None:
            return {}, True, False
        rows = conn.execute("SELECT * FROM incremental_file_state").fetchall()
        return {str(row["rel_path"]): dict(row) for row in rows}, True, True
    finally:
        conn.close()


def preview_incremental_changes(
    *,
    tiff_root: str | os.PathLike[str],
    state_db: str | os.PathLike[str],
    hash_mode: str = "stat",
    sample_limit: int = 5,
) -> IncrementalPreview:
    """Preview changed TIFFs without mutating state or changed_tiffs.txt."""

    root = Path(tiff_root)
    root_resolved = root.resolve() if root.exists() else root
    previous, state_exists, table_exists = _read_previous_state(Path(state_db))
    current_rel_paths: set[str] = set()
    files_seen = new_files = changed_files = unchanged_files = 0
    changed_paths: list[str] = []

    for path in _iter_tiff_paths(root):
        files_seen += 1
        resolved = path.resolve()
        try:
            rel_path = resolved.relative_to(root_resolved).as_posix()
        except ValueError:
            rel_path = path.name
        current_rel_paths.add(rel_path)
        old = previous.get(rel_path)
        fingerprint = _fingerprint(resolved, hash_mode)
        if old is None:
            new_files += 1
            changed_paths.append(str(resolved))
        elif str(old.get("fingerprint", "")) != fingerprint:
            changed_files += 1
            changed_paths.append(str(resolved))
        else:
            unchanged_files += 1

    missing_paths = sorted(set(previous) - current_rel_paths)
    return IncrementalPreview(
        files_seen=files_seen,
        new_files=new_files,
        changed_files=changed_files,
        unchanged_files=unchanged_files,
        missing_files=len(missing_paths),
        changed_list_count=len(changed_paths),
        state_rows=len(previous),
        state_db_exists=state_exists,
        state_table_exists=table_exists,
        sample_changed_paths=changed_paths[:sample_limit],
        sample_missing_paths=missing_paths[:sample_limit],
    )


def _uses_changed_pages(value: str | None) -> bool:
    mode = (value or "").strip().lower().replace("_", "-")
    return mode in {"changed-pages", "changed-page", "changed-page-update", "incremental"}


def _planned_changed_pages_command(cfg: IncrementalPipelineConfig) -> bool:
    summary = ChangeDetectionSummary(files_seen=1, new_files=1, changed_paths=["dummy_changed_page.tif"])
    commands = build_commands(cfg, summary, skip_ocr=True, run_backend_when_unchanged=False)
    for command in commands:
        if command.name == "backend_pipeline" and command.will_run:
            return any("update_changed_page_backend.py" in str(part) for part in command.argv)
    return False


def _safe_commit_probe() -> tuple[bool, bool, bool]:
    summary = ChangeDetectionSummary(files_seen=1, new_files=1, changed_paths=["dummy_changed_page.tif"])
    runnable = [PipelineCommand("backend_pipeline", "dummy", ["python", "dummy.py"])]
    skipped = [PipelineCommand("backend_pipeline", "dummy", ["python", "dummy.py"], skip_reason="skip")]
    failed_results = [PipelineCommandResult("backend_pipeline", "FAILED", returncode=1)]
    ok_results = [PipelineCommandResult("backend_pipeline", "OK", returncode=0)]

    dry_run_safe, _ = should_commit_state(summary, skipped, [])
    failed_safe, _ = should_commit_state(summary, runnable, failed_results)
    success_allowed, _ = should_commit_state(summary, runnable, ok_results)
    return (not dry_run_safe, not failed_safe, success_allowed)


def _quality_status(path: str | os.PathLike[str]) -> str | None:
    data = read_json(path)
    if not data:
        return None
    status = data.get("status")
    return str(status) if status is not None else None


def _status_is_ok(value: str | None) -> bool:
    """Accept the status spellings used by the pipeline and quality gate."""
    return str(value or "").strip().lower() == "ok"


def _as_bool(value: Any) -> bool | None:
    """Coerce JSON readiness fields without turning the string 'False' into True."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "y", "1", "ok"}:
            return True
        if lowered in {"false", "no", "n", "0", ""}:
            return False
    return bool(value)


def _first_present(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in mapping:
            return mapping.get(key)
    return None


def _manifest_status(path: str | os.PathLike[str]) -> tuple[str | None, str | None, bool | None, bool | None, bool | None]:
    data = read_json(path)
    if not data:
        return None, None, None, None, None
    status = data.get("status")
    run_id = data.get("run_id")
    steps = data.get("steps") or []
    has_source_step = any(str(step.get("name")) == "source_link_audit" for step in steps if isinstance(step, dict))
    source_summary = data.get("source_link_summary") or data.get("source_links") or {}
    if not isinstance(source_summary, dict):
        source_summary = {}

    # Current pipeline manifests use the fields emitted by source_link_audit.py:
    # ready_for_local_source_review and ready_for_real_rescarta_deeplinks.
    # Older patches used local_source_review_ready and
    # real_rescarta_deep_link_ready. Accept both so the audit remains stable
    # across local handoff states.
    local_ready = _first_present(
        source_summary,
        (
            "ready_for_local_source_review",
            "local_source_review_ready",
            "source_local_review_ready",
            "local_review_ready",
        ),
    )
    real_ready = _first_present(
        source_summary,
        (
            "ready_for_real_rescarta_deeplinks",
            "ready_for_real_rescarta_deep_links",
            "real_rescarta_deep_link_ready",
            "source_real_rescarta_ready",
            "real_rescarta_ready",
        ),
    )
    return (
        str(status) if status is not None else None,
        str(run_id) if run_id is not None else None,
        has_source_step,
        _as_bool(local_ready),
        _as_bool(real_ready),
    )


def audit_incremental_readiness(
    *,
    config_path: str | os.PathLike[str] = "local_config.yaml",
    backend_mode: str | None = "changed-pages",
    require_clean_quality: bool = True,
    quality_path: str | os.PathLike[str] = DEFAULT_QUALITY_PATH,
    manifest_path: str | os.PathLike[str] = DEFAULT_MANIFEST_PATH,
) -> IncrementalReadinessReport:
    cfg = load_pipeline_config(str(config_path), backend_mode=backend_mode)
    preview = preview_incremental_changes(
        tiff_root=cfg.tiff_root,
        state_db=cfg.state_db,
        hash_mode=cfg.hash_mode,
    )

    changed_page_script = Path("scripts/update_changed_page_backend.py")
    changed_page_module = Path("tiff/changed_page_update.py")
    dry_run_safe, failed_safe, success_allowed = _safe_commit_probe()
    planned_changed_pages = _planned_changed_pages_command(cfg)
    quality = _quality_status(quality_path)
    manifest, run_id, has_source_audit, source_local_ready, source_real_ready = _manifest_status(manifest_path)

    errors: list[str] = []
    warnings: list[str] = []

    if not Path(cfg.tiff_root).exists():
        errors.append(f"TIFF root does not exist: {cfg.tiff_root}")
    if not Path(cfg.db_path).exists():
        errors.append(f"Search DB does not exist: {cfg.db_path}")
    if not Path(cfg.rescarta_export_dir).exists():
        errors.append(f"ResCarta export directory does not exist: {cfg.rescarta_export_dir}")
    if not Path(cfg.questions).exists():
        errors.append(f"RAG eval questions file does not exist: {cfg.questions}")
    if not Path(cfg.changed_list).parent.exists():
        errors.append(f"Changed-list parent directory does not exist: {Path(cfg.changed_list).parent}")
    if not (changed_page_script.exists() and changed_page_module.exists()):
        errors.append("Changed-page backend files are missing.")
    if not _uses_changed_pages(cfg.backend_mode):
        errors.append(f"backend_mode is not changed-pages/incremental: {cfg.backend_mode}")
    if not planned_changed_pages:
        errors.append("A changed-page backend command was not planned for a synthetic changed TIFF.")
    if not (dry_run_safe and failed_safe and success_allowed):
        errors.append("Safe-commit probe failed; incremental state commit rules need review.")
    if require_clean_quality and not _status_is_ok(quality):
        errors.append(f"Latest quality gate is not OK: {quality or 'missing'}")
    if require_clean_quality and not _status_is_ok(manifest):
        errors.append(f"Latest backend manifest is not ok: {manifest or 'missing'}")

    if not preview.state_db_exists:
        warnings.append("Incremental state DB does not exist yet; the first real incremental run will treat TIFFs as new.")
    elif not preview.state_table_exists:
        warnings.append("Incremental state DB exists but does not contain incremental_file_state yet.")
    if preview.changed_list_count:
        warnings.append(f"Preview sees {preview.changed_list_count} changed/new TIFF(s); the next real run will process them.")
    if preview.missing_files:
        warnings.append(f"Preview sees {preview.missing_files} missing TIFF(s) that would be removed from committed state after a successful run.")
    if source_real_ready is False:
        warnings.append("Real ResCarta deep links are still placeholders; this is allowed for the local MVP.")

    return IncrementalReadinessReport(
        config_path=str(config_path),
        tiff_root=cfg.tiff_root,
        state_db=cfg.state_db,
        changed_list=cfg.changed_list,
        hash_mode=cfg.hash_mode,
        backend_mode=cfg.backend_mode,
        db_path=cfg.db_path,
        rescarta_export_dir=cfg.rescarta_export_dir,
        questions=cfg.questions,
        tiff_root_exists=Path(cfg.tiff_root).exists(),
        state_db_exists=preview.state_db_exists,
        state_rows=preview.state_rows,
        changed_list_parent_exists=Path(cfg.changed_list).parent.exists(),
        db_path_exists=Path(cfg.db_path).exists(),
        rescarta_export_dir_exists=Path(cfg.rescarta_export_dir).exists(),
        questions_exists=Path(cfg.questions).exists(),
        changed_page_script_exists=changed_page_script.exists(),
        changed_page_module_exists=changed_page_module.exists(),
        changed_pages_backend_available=changed_page_script.exists() and changed_page_module.exists(),
        backend_mode_uses_changed_pages=_uses_changed_pages(cfg.backend_mode),
        changed_pages_command_planned=planned_changed_pages,
        dry_run_state_commit_safe=dry_run_safe,
        failed_downstream_state_commit_safe=failed_safe,
        successful_downstream_state_commit_allowed=success_allowed,
        files_seen=preview.files_seen,
        preview_new_files=preview.new_files,
        preview_changed_files=preview.changed_files,
        preview_unchanged_files=preview.unchanged_files,
        preview_missing_files=preview.missing_files,
        preview_changed_list_count=preview.changed_list_count,
        quality_status=quality,
        manifest_status=manifest,
        manifest_run_id=run_id,
        manifest_has_source_link_audit=has_source_audit,
        source_local_review_ready=source_local_ready,
        source_real_rescarta_ready=source_real_ready,
        ok=not errors,
        warnings=warnings,
        errors=errors,
    )


def format_incremental_readiness_report(report: IncrementalReadinessReport) -> str:
    lines = [
        "Incremental pipeline readiness audit",
        f"  Status: {'OK' if report.ok else 'NEEDS ATTENTION'}",
        f"  Config: {report.config_path}",
        f"  TIFF root: {report.tiff_root}",
        f"  State DB: {report.state_db}",
        f"  Changed list: {report.changed_list}",
        f"  Hash mode: {report.hash_mode}",
        f"  Backend mode: {report.backend_mode}",
        "",
        "Path/config checks:",
        f"  TIFF root exists: {report.tiff_root_exists}",
        f"  Search DB exists: {report.db_path_exists}",
        f"  ResCarta export dir exists: {report.rescarta_export_dir_exists}",
        f"  Eval questions exist: {report.questions_exists}",
        f"  Changed-page backend available: {report.changed_pages_backend_available}",
        f"  Changed-page command planned: {report.changed_pages_command_planned}",
        "",
        "Safe-commit checks:",
        f"  Dry run does not commit state: {report.dry_run_state_commit_safe}",
        f"  Failed downstream work does not commit state: {report.failed_downstream_state_commit_safe}",
        f"  Successful downstream work may commit state: {report.successful_downstream_state_commit_allowed}",
        "",
        "Read-only change preview:",
        f"  Files seen: {report.files_seen}",
        f"  State rows: {report.state_rows}",
        f"  New files: {report.preview_new_files}",
        f"  Changed files: {report.preview_changed_files}",
        f"  Unchanged files: {report.preview_unchanged_files}",
        f"  Missing files: {report.preview_missing_files}",
        f"  Changed-list count if run now: {report.preview_changed_list_count}",
        "",
        "Latest backend health:",
        f"  Quality gate status: {report.quality_status or 'missing'}",
        f"  Manifest status: {report.manifest_status or 'missing'}",
        f"  Manifest run id: {report.manifest_run_id or 'missing'}",
        f"  Source-link audit in manifest: {report.manifest_has_source_link_audit}",
        f"  Local source review ready: {report.source_local_review_ready}",
        f"  Real ResCarta deep-link ready: {report.source_real_rescarta_ready}",
    ]
    if report.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"  - {item}" for item in report.warnings)
    if report.errors:
        lines.append("")
        lines.append("Errors:")
        lines.extend(f"  - {item}" for item in report.errors)
    return "\n".join(lines)
