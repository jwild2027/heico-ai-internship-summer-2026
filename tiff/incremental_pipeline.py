from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .incremental_state import (
    ChangeDetectionSummary,
    IncrementalStateDB,
    build_changed_tiff_list,
    write_changed_list,
)


def _parse_scalar(value: str) -> Any:
    value = value.strip().strip('"').strip("'")
    if value.lower() in {"true", "yes", "on"}:
        return True
    if value.lower() in {"false", "no", "off"}:
        return False
    return value


def _read_simple_yaml(path: str | os.PathLike[str] | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    data: dict[str, Any] = {}
    for raw_line in p.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line or ":" not in line or line.startswith(" ") or line.startswith("-"):
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value:
            data[key] = _parse_scalar(value)
    return data


def _cfg(config: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in config and config[key] not in (None, ""):
            return config[key]
    return default


@dataclass
class PipelineCommand:
    name: str
    description: str
    argv: list[str]
    skip_reason: str | None = None

    @property
    def will_run(self) -> bool:
        return self.skip_reason is None

    @property
    def command(self) -> str:
        return format_command(self.argv)


@dataclass
class PipelineCommandResult:
    name: str
    status: str
    returncode: int | None = None
    skip_reason: str | None = None


@dataclass
class IncrementalPipelineConfig:
    config_path: str | None = None

    # New field names used by the safe-commit pipeline.
    tiff_root: str = "local_data/sample_tiffs"
    state_db: str = "local_data/db/tiff_incremental_state.db"
    changed_list: str = "local_data/changed_tiffs.txt"
    hash_mode: str = "stat"
    json_dir: str = "local_data/json_scans_incremental"
    scan_db: str = "local_data/db/tiff_scans_full.db"
    db_path: str = "local_data/db/tiff_search.db"
    rescarta_export_dir: str = "local_data/rescarta_exports"
    embed_model: str = "bge-m3:latest"
    questions: str = "local_data/evals/rag_eval_questions.json"
    tesseract_cmd: str | None = None
    backend_mode: str = "full"  # full or changed-pages

    # Backward-compatible aliases used by earlier tests/scripts.
    root: str | None = None
    state_db_path: str | None = None
    changed_list_path: str | None = None
    scan_db_path: str | None = None
    search_db_path: str | None = None
    run_backend_when_unchanged: bool = False
    run_ocr: bool = True

    def __post_init__(self) -> None:
        # Old aliases override defaults when explicitly supplied.
        if self.root is not None:
            self.tiff_root = self.root
        else:
            self.root = self.tiff_root
        if self.state_db_path is not None:
            self.state_db = self.state_db_path
        else:
            self.state_db_path = self.state_db
        if self.changed_list_path is not None:
            self.changed_list = self.changed_list_path
        else:
            self.changed_list_path = self.changed_list
        if self.scan_db_path is not None:
            self.scan_db = self.scan_db_path
        else:
            self.scan_db_path = self.scan_db
        if self.search_db_path is not None:
            self.db_path = self.search_db_path
        else:
            self.search_db_path = self.db_path


@dataclass
class IncrementalPipelineRunResult:
    summary: ChangeDetectionSummary
    commands: list[PipelineCommand]
    results: list[PipelineCommandResult]
    state_committed: bool
    commit_message: str


def format_command(argv: list[str] | tuple[str, ...]) -> str:
    parts: list[str] = []
    for item in argv:
        text = str(item)
        if not text:
            parts.append('""')
        elif any(ch.isspace() for ch in text):
            parts.append('"' + text.replace('"', '\\"') + '"')
        else:
            parts.append(text)
    return " ".join(parts)


def load_pipeline_config(config_path: str | None = None, **overrides: Any) -> IncrementalPipelineConfig:
    raw = _read_simple_yaml(config_path)
    cfg = IncrementalPipelineConfig(
        config_path=config_path,
        tiff_root=str(_cfg(raw, "tiff_root", "source_tiff_root", default="local_data/sample_tiffs")),
        state_db=str(_cfg(raw, "incremental_state_db", "state_db", default="local_data/db/tiff_incremental_state.db")),
        changed_list=str(_cfg(raw, "changed_tiffs", "changed_tiffs_path", "changed_list", default="local_data/changed_tiffs.txt")),
        hash_mode=str(_cfg(raw, "hash_mode", "incremental_hash_mode", default="stat")),
        json_dir=str(_cfg(raw, "json_dir", "json_scan_dir", "incremental_json_dir", default="local_data/json_scans_incremental")),
        scan_db=str(_cfg(raw, "scan_db", "scan_db_path", "tiff_scan_db", default="local_data/db/tiff_scans_full.db")),
        db_path=str(_cfg(raw, "db_path", "search_db", "search_db_path", default="local_data/db/tiff_search.db")),
        rescarta_export_dir=str(_cfg(raw, "rescarta_export_dir", "rescarta_exports", default="local_data/rescarta_exports")),
        embed_model=str(_cfg(raw, "embed_model", "embedding_model", default="bge-m3:latest")),
        questions=str(_cfg(raw, "eval_questions", "questions", default="local_data/evals/rag_eval_questions.json")),
        tesseract_cmd=_cfg(raw, "tesseract_cmd", default=None),
        backend_mode=str(_cfg(raw, "backend_mode", "incremental_backend_mode", default="full")),
    )
    for key, value in overrides.items():
        if value not in (None, "") and hasattr(cfg, key):
            setattr(cfg, key, str(value))
    cfg.__post_init__()
    return cfg


# Backward-compatible public name.
def config_from_file(config_path: str | os.PathLike[str]) -> IncrementalPipelineConfig:
    return load_pipeline_config(str(config_path))


def merge_config(base: IncrementalPipelineConfig, **overrides: Any) -> IncrementalPipelineConfig:
    values = {key: value for key, value in overrides.items() if value is not None}
    merged = replace(base, **values)
    merged.__post_init__()
    return merged


def build_commands(
    cfg: IncrementalPipelineConfig,
    summary: ChangeDetectionSummary,
    *,
    skip_ocr: bool = False,
    skip_backend: bool = False,
    run_backend_when_unchanged: bool = False,
    reset_embeddings: bool = False,
) -> list[PipelineCommand]:
    commands: list[PipelineCommand] = []

    ocr_argv = [
        sys.executable,
        "scripts/batch_scan_tiffs_to_json.py",
        "--input-dir",
        cfg.tiff_root,
        "--input-list",
        cfg.changed_list,
        "--output-dir",
        cfg.json_dir,
        "--db-path",
        cfg.scan_db,
        "--ocr",
    ]
    if cfg.tesseract_cmd:
        ocr_argv.extend(["--tesseract-cmd", cfg.tesseract_cmd])
    ocr_skip = None
    if skip_ocr:
        ocr_skip = "--skip-ocr was set."
    elif summary.changed_list_count == 0:
        ocr_skip = "No changed TIFF files."
    commands.append(
        PipelineCommand(
            name="ocr_changed_tiffs",
            description="OCR/scan only changed TIFF files.",
            argv=ocr_argv,
            skip_reason=ocr_skip,
        )
    )

    backend_mode = (cfg.backend_mode or "full").strip().lower()
    if backend_mode in {"changed-pages", "changed_page", "changed_page_update", "incremental"} and summary.changed_list_count > 0:
        backend_argv = [
            sys.executable,
            "scripts/update_changed_page_backend.py",
            "--config",
            cfg.config_path or "local_config.yaml",
            "--db-path",
            cfg.db_path,
            "--rescarta-export-dir",
            cfg.rescarta_export_dir,
            "--changed-list",
            cfg.changed_list,
            "--embed-model",
            cfg.embed_model,
            "--questions",
            cfg.questions,
        ]
    else:
        backend_argv = [
            sys.executable,
            "scripts/run_tiff_backend_pipeline.py",
            "--config",
            cfg.config_path or "local_config.yaml",
            "--db-path",
            cfg.db_path,
            "--rescarta-export-dir",
            cfg.rescarta_export_dir,
            "--embed-model",
            cfg.embed_model,
            "--questions",
            cfg.questions,
        ]
        if reset_embeddings:
            backend_argv.append("--reset-embeddings")
    backend_skip = None
    if skip_backend:
        backend_skip = "--skip-backend was set."
    elif summary.changed_list_count == 0 and not run_backend_when_unchanged:
        backend_skip = "No changed TIFF files and --run-backend-when-unchanged was not set."
    commands.append(
        PipelineCommand(
            name="backend_pipeline",
            description="Run backend pipeline after changed files are processed.",
            argv=backend_argv,
            skip_reason=backend_skip,
        )
    )
    return commands


def build_incremental_commands(cfg: IncrementalPipelineConfig, changed_count: int) -> list[PipelineCommand]:
    """Compatibility wrapper for earlier tests/scripts."""
    summary = ChangeDetectionSummary(files_seen=changed_count, changed_paths=["changed.tif"] * changed_count)
    commands = build_commands(
        cfg,
        summary,
        skip_ocr=not cfg.run_ocr,
        run_backend_when_unchanged=cfg.run_backend_when_unchanged,
    )
    # Original behavior omitted the skipped OCR command when run_ocr=False.
    if not cfg.run_ocr:
        commands = [cmd for cmd in commands if cmd.name != "ocr_changed_tiffs"]
    return commands


def run_commands(commands: list[PipelineCommand]) -> list[PipelineCommandResult]:
    results: list[PipelineCommandResult] = []
    for command in commands:
        if command.skip_reason:
            results.append(PipelineCommandResult(command.name, "SKIPPED", skip_reason=command.skip_reason))
            continue
        proc = subprocess.run(command.argv, check=False)
        if proc.returncode != 0:
            results.append(PipelineCommandResult(command.name, "FAILED", returncode=proc.returncode))
            return results
        results.append(PipelineCommandResult(command.name, "OK", returncode=0))
    return results


def should_commit_state(summary: ChangeDetectionSummary, commands: list[PipelineCommand], results: list[PipelineCommandResult]) -> tuple[bool, str]:
    """Commit state only after changed files were successfully handled."""
    if not summary.has_changes:
        return False, "No file-state changes to commit."
    failed = [r for r in results if r.status == "FAILED"]
    if failed:
        return False, "A downstream command failed; state was not committed."
    runnable = [c.name for c in commands if c.will_run]
    if not runnable:
        return False, "Changed files were detected, but no processing commands ran; state was not committed."
    return True, "Changed files were processed successfully."


def run_changed_detection(cfg: IncrementalPipelineConfig, *, commit_state: bool = True):
    """Compatibility helper for older tests.

    Writes changed_tiffs.txt for inspection.  State commit is controlled by
    commit_state.
    """
    return build_changed_tiff_list(
        root=cfg.tiff_root,
        state_db_path=cfg.state_db,
        changed_list_path=cfg.changed_list,
        hash_mode=cfg.hash_mode,
        commit_state=commit_state,
        write_list=True,
    )


def run_incremental_pipeline(
    cfg: IncrementalPipelineConfig,
    *,
    dry_run: bool = False,
    skip_ocr: bool = False,
    skip_backend: bool = False,
    run_backend_when_unchanged: bool = False,
    reset_embeddings: bool = False,
) -> IncrementalPipelineRunResult:
    state = IncrementalStateDB(cfg.state_db)
    summary = state.detect_changes(cfg.tiff_root, hash_mode=cfg.hash_mode)
    write_changed_list(summary.changed_paths, cfg.changed_list)
    commands = build_commands(
        cfg,
        summary,
        skip_ocr=skip_ocr,
        skip_backend=skip_backend,
        run_backend_when_unchanged=run_backend_when_unchanged,
        reset_embeddings=reset_embeddings,
    )
    if dry_run:
        return IncrementalPipelineRunResult(summary, commands, [], False, "Dry run: state DB was not updated.")
    results = run_commands(commands)
    commit, message = should_commit_state(summary, commands, results)
    if commit:
        state.commit_summary(summary)
    return IncrementalPipelineRunResult(summary, commands, results, commit, message)
