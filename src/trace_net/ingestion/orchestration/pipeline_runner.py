"""Utilities for running the local TIFF search/RAG backend pipeline.

The runner shells out to the existing scripts instead of reimplementing their
logic. That keeps the orchestration layer small and makes it useful for the
current SQLite/Ollama MVP.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import subprocess
import sys
import time
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class PipelineStep:
    """One command in the backend rebuild pipeline."""

    name: str
    command: tuple[str, ...]
    description: str = ""


@dataclass
class PipelineConfig:
    """Configuration used by the pipeline wrapper."""

    db_path: str = "local_data/db/tiff_search.db"
    rescarta_export_dir: str = "local_data/rescarta_exports"
    embed_model: str = "bge-m3:latest"
    config_path: str = "local_config.yaml"
    questions_path: str = "local_data/evals/rag_eval_questions.json"
    reset_embeddings: bool = False
    skip_search_index: bool = False
    skip_part_catalog: bool = False
    skip_rag_chunks: bool = False
    skip_embeddings: bool = False
    skip_qa: bool = False
    skip_qa_triage: bool = False
    skip_eval: bool = False
    skip_source_audit: bool = False
    skip_ocr_coverage_audit: bool = False
    skip_document_organization_audit: bool = False
    skip_document_organization_export: bool = False
    python_executable: str = field(default_factory=lambda: sys.executable or "python")


@dataclass
class PipelineRunResult:
    """Result for a single pipeline command."""

    step: PipelineStep
    returncode: int
    skipped: bool = False
    elapsed_seconds: float = 0.0


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def read_simple_yaml(path: str | Path) -> dict[str, str]:
    """Read a small flat YAML config file without requiring PyYAML."""
    config_path = Path(path)
    if not config_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.split(" #", 1)[0].strip()
        if key and value:
            values[key] = _strip_quotes(value)
    return values


def config_from_file(path: str | Path = "local_config.yaml") -> PipelineConfig:
    """Create a PipelineConfig using defaults plus values from local_config.yaml."""
    raw = read_simple_yaml(path)
    embed_model = raw.get("embed_model") or raw.get("embedding_model") or raw.get("rag_embed_model")
    return PipelineConfig(
        db_path=raw.get("db_path", PipelineConfig.db_path),
        rescarta_export_dir=raw.get(
            "rescarta_export_dir",
            raw.get("rescarta_export_root", PipelineConfig.rescarta_export_dir),
        ),
        embed_model=embed_model or PipelineConfig.embed_model,
        config_path=str(path),
        questions_path=raw.get("questions_path", raw.get("eval_questions_path", PipelineConfig.questions_path)),
    )


def merge_config(base: PipelineConfig, **overrides: object) -> PipelineConfig:
    """Return a copy of base with non-None override values applied."""
    values = dict(base.__dict__)
    for key, value in overrides.items():
        if value is not None:
            values[key] = value
    return PipelineConfig(**values)


def _python_cmd(config: PipelineConfig, script: str, *args: str) -> tuple[str, ...]:
    return (config.python_executable, script, *args)


def build_pipeline_steps(config: PipelineConfig) -> list[PipelineStep]:
    """Build the default backend pipeline command list."""
    steps: list[PipelineStep] = []

    if not config.skip_search_index:
        steps.append(
            PipelineStep(
                name="search_index",
                description="Build SQLite search index from ResCarta staging export.",
                command=_python_cmd(
                    config,
                    "scripts/build/ingestion/build_tiff_search_index.py",
                    "--rescarta-export-dir",
                    config.rescarta_export_dir,
                    "--output-db",
                    config.db_path,
                ),
            )
        )

    if not config.skip_part_catalog:
        steps.append(
            PipelineStep(
                name="part_catalog",
                description="Clean OCR and rebuild the part catalog/nomenclature tables.",
                command=_python_cmd(
                    config,
                    "scripts/build/ingestion/rebuild_clean_part_catalog.py",
                    "--db-path",
                    config.db_path,
                ),
            )
        )

    if not config.skip_rag_chunks:
        steps.append(
            PipelineStep(
                name="rag_chunks",
                description="Build RAG chunks from cleaned OCR/search records.",
                command=_python_cmd(
                    config,
                    "scripts/build/ingestion/build_rag_chunks.py",
                    "--db-path",
                    config.db_path,
                ),
            )
        )

    if not config.skip_embeddings:
        embedding_args = [
            "scripts/build/embeddings/build_rag_embeddings.py",
            "--db-path",
            config.db_path,
            "--model",
            config.embed_model,
        ]
        if config.reset_embeddings:
            embedding_args.append("--reset")
        steps.append(
            PipelineStep(
                name="rag_embeddings",
                description="Build local Ollama embeddings for RAG chunks.",
                command=_python_cmd(config, *embedding_args),
            )
        )

    config_path = Path(config.config_path)
    questions_path = Path(config.questions_path)

    if not config.skip_qa:
        qa_args = ["scripts/maintenance/ingestion/report_part_catalog_qa.py"]
        if config_path.exists():
            qa_args.extend(["--config", config.config_path])
        else:
            qa_args.extend(["--db-path", config.db_path])
        steps.append(
            PipelineStep(
                name="part_catalog_qa",
                description="Write raw part catalog QA reports.",
                command=_python_cmd(config, *qa_args),
            )
        )

        if not config.skip_qa_triage:
            steps.append(
                PipelineStep(
                    name="part_catalog_qa_triage",
                    description="Apply command-line QA severity triage and rewrite the normal QA CSV/JSON report.",
                    command=_python_cmd(
                        config,
                        "scripts/maintenance/ingestion/triage_part_catalog_qa.py",
                        "--replace-all-report",
                        "--limit",
                        "12",
                    ),
                )
            )

    if not config.skip_source_audit:
        source_audit_args = [
            "scripts/maintenance/ingestion/audit_source_links.py",
            "--strict",
            "--write-json",
            "--json-output",
            "local_data/source_links/source_link_audit.json",
            "--print-limit",
            "5",
        ]
        if config_path.exists():
            source_audit_args.extend(["--config", config.config_path])
        else:
            source_audit_args.extend(["--db-path", config.db_path])
        steps.append(
            PipelineStep(
                name="source_link_audit",
                description="Verify every indexed page has auditable TIFF/OCR/ResCarta source links.",
                command=_python_cmd(config, *source_audit_args),
            )
        )



    if not config.skip_ocr_coverage_audit:
        ocr_audit_args = [
            "scripts/maintenance/ingestion/audit_ocr_coverage.py",
            "--strict",
            "--write-json",
            "--json-output",
            "local_data/ocr/ocr_coverage_audit.json",
            "--sample-limit",
            "12",
            "--no-refresh-manifest",
        ]
        if config_path.exists():
            ocr_audit_args.extend(["--config", config.config_path])
        else:
            ocr_audit_args.extend(["--db-path", config.db_path])
        steps.append(
            PipelineStep(
                name="ocr_coverage_audit",
                description="Verify source-linked pages have readable OCR text files and flag empty OCR pages for review.",
                command=_python_cmd(config, *ocr_audit_args),
            )
        )


    if not config.skip_document_organization_audit:
        org_audit_args = [
            "scripts/maintenance/ingestion/audit_document_organization.py",
            "--strict",
            "--write-json",
            "--json-output",
            "local_data/organization/document_organization_audit.json",
            "--top-ata",
            "20",
            "--top-parts",
            "20",
            "--no-refresh-manifest",
        ]
        if config_path.exists():
            org_audit_args.extend(["--config", config.config_path])
        else:
            org_audit_args.extend(["--db-path", config.db_path])
        steps.append(
            PipelineStep(
                name="document_organization_audit",
                description="Verify the logical manual/ATA/part organization layer is ready.",
                command=_python_cmd(config, *org_audit_args),
            )
        )

    if not config.skip_document_organization_export:
        org_export_args = [
            "scripts/build/ingestion/export_document_organization.py",
            "--strict",
            "--output-dir",
            "local_data/organization/export",
        ]
        if config_path.exists():
            org_export_args.extend(["--config", config.config_path])
        else:
            org_export_args.extend(["--db-path", config.db_path])
        steps.append(
            PipelineStep(
                name="document_organization_export",
                description="Write UI/API-ready logical organization JSON artifacts.",
                command=_python_cmd(config, *org_export_args),
            )
        )

    if not config.skip_eval:
        if not questions_path.exists():
            steps.append(
                PipelineStep(
                    name="write_default_eval_questions",
                    description="Create the starter RAG evaluation question set.",
                    command=_python_cmd(
                        config,
                        "scripts/benchmark/ingestion/evaluate_rag_questions.py",
                        "--write-default-questions",
                        config.questions_path,
                    ),
                )
            )

        eval_args = ["scripts/benchmark/ingestion/evaluate_rag_questions.py"]
        if config_path.exists():
            eval_args.extend(["--config", config.config_path])
        else:
            eval_args.extend(["--db-path", config.db_path, "--embed-model", config.embed_model])
        eval_args.extend(["--questions", config.questions_path, "--no-refresh-manifest"])
        steps.append(
            PipelineStep(
                name="rag_eval",
                description="Run repeatable RAG evaluation questions.",
                command=_python_cmd(config, *eval_args),
            )
        )

    return steps


def format_command(command: Sequence[str]) -> str:
    """Format a command for human-readable logs."""
    parts: list[str] = []
    for part in command:
        if any(ch.isspace() for ch in part):
            parts.append('"' + part.replace('"', '\\"') + '"')
        else:
            parts.append(part)
    return " ".join(parts)


def run_pipeline(
    config: PipelineConfig,
    *,
    dry_run: bool = False,
    continue_on_error: bool = False,
    cwd: str | Path | None = None,
) -> list[PipelineRunResult]:
    """Run the configured backend pipeline."""
    results: list[PipelineRunResult] = []
    steps = build_pipeline_steps(config)
    run_cwd = str(cwd) if cwd is not None else None
    for step in steps:
        if dry_run:
            results.append(PipelineRunResult(step=step, returncode=0, skipped=True, elapsed_seconds=0.0))
            continue
        started = time.perf_counter()
        completed = subprocess.run(step.command, cwd=run_cwd, check=False)
        elapsed = time.perf_counter() - started
        result = PipelineRunResult(step=step, returncode=completed.returncode, elapsed_seconds=elapsed)
        results.append(result)
        if completed.returncode != 0 and not continue_on_error:
            break
    return results


def successful(results: Iterable[PipelineRunResult]) -> bool:
    """Return True if every executed step succeeded."""
    return all(item.returncode == 0 for item in results)
