"""Read-only backend helpers for the TIFF/RAG API.

The API layer intentionally reads the same artifacts used by the Streamlit UI:
organization-export JSON, latest pipeline manifest, and latest quality gate.
It does not rebuild OCR, modify source files, or mutate the SQLite database.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import subprocess
import sys
from typing import Any

DEFAULT_EXPORT_DIR = Path("local_data/organization/export")
DEFAULT_MANIFEST_PATH = Path("local_data/pipeline_runs/latest_backend_pipeline.json")
DEFAULT_QUALITY_PATH = Path("local_data/pipeline_runs/latest_quality_gate.json")
DEFAULT_CONFIG_PATH = Path("local_config.yaml")

REQUIRED_EXPORT_FILES = (
    "manual_ata_tree.json",
    "ata_tree.json",
    "part_tree.json",
    "page_index.json",
    "organization_summary.json",
)


@dataclass(frozen=True)
class ApiDataPaths:
    """Filesystem paths used by the read-only API backend."""

    repo_root: Path
    export_dir: Path
    manifest_path: Path
    quality_path: Path
    config_path: Path


@dataclass(frozen=True)
class ApiData:
    """Loaded API artifacts."""

    paths: ApiDataPaths
    manual_ata_tree: Any
    ata_tree: Any
    part_tree: Any
    page_index: Any
    organization_summary: dict[str, Any]
    manifest: dict[str, Any]
    quality_gate: dict[str, Any]


def make_paths(
    *,
    repo_root: str | Path = ".",
    export_dir: str | Path = DEFAULT_EXPORT_DIR,
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    quality_path: str | Path = DEFAULT_QUALITY_PATH,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
) -> ApiDataPaths:
    """Create normalized API data paths relative to *repo_root*."""
    root = Path(repo_root).resolve()
    return ApiDataPaths(
        repo_root=root,
        export_dir=_resolve(root, export_dir),
        manifest_path=_resolve(root, manifest_path),
        quality_path=_resolve(root, quality_path),
        config_path=_resolve(root, config_path),
    )


def check_api_ready(paths: ApiDataPaths | None = None) -> dict[str, Any]:
    """Return readiness information for the API layer."""
    paths = paths or make_paths()
    export_files = {name: (paths.export_dir / name).exists() for name in REQUIRED_EXPORT_FILES}
    manifest_exists = paths.manifest_path.exists()
    quality_exists = paths.quality_path.exists()
    config_exists = paths.config_path.exists()

    errors: list[str] = []
    missing_exports = [name for name, exists in export_files.items() if not exists]
    if missing_exports:
        errors.append("missing organization export files: " + ", ".join(missing_exports))
    if not manifest_exists:
        errors.append(f"missing pipeline manifest: {paths.manifest_path}")
    if not quality_exists:
        errors.append(f"missing quality gate JSON: {paths.quality_path}")
    if not config_exists:
        errors.append(f"missing config: {paths.config_path}")

    status = "OK" if not errors else "NEEDS_ATTENTION"
    summary: dict[str, Any] = {}
    quality_status = None
    manifest_status = None
    if not errors:
        try:
            data = load_api_data(paths)
            summary = get_organization_summary(data)
            quality_status = _first_text(data.quality_gate, "status", "quality_status")
            manifest_status = _first_text(data.manifest, "status", "pipeline_status")
        except Exception as exc:  # pragma: no cover - defensive boundary
            errors.append(str(exc))
            status = "NEEDS_ATTENTION"

    return {
        "status": status,
        "paths": {
            "repo_root": str(paths.repo_root),
            "export_dir": str(paths.export_dir),
            "manifest_path": str(paths.manifest_path),
            "quality_path": str(paths.quality_path),
            "config_path": str(paths.config_path),
        },
        "files_present": {
            "manifest": manifest_exists,
            "quality_gate": quality_exists,
            "config": config_exists,
            **export_files,
        },
        "quality_status": quality_status,
        "manifest_status": manifest_status,
        "organization_summary": summary,
        "errors": errors,
    }


def load_api_data(paths: ApiDataPaths | None = None) -> ApiData:
    """Load organization, manifest, and quality artifacts for the API."""
    paths = paths or make_paths()
    missing_exports = [name for name in REQUIRED_EXPORT_FILES if not (paths.export_dir / name).exists()]
    if missing_exports:
        raise FileNotFoundError("Missing organization export files: " + ", ".join(missing_exports))
    if not paths.manifest_path.exists():
        raise FileNotFoundError(f"Missing pipeline manifest: {paths.manifest_path}")
    if not paths.quality_path.exists():
        raise FileNotFoundError(f"Missing quality gate JSON: {paths.quality_path}")
    return ApiData(
        paths=paths,
        manual_ata_tree=_load_json(paths.export_dir / "manual_ata_tree.json"),
        ata_tree=_load_json(paths.export_dir / "ata_tree.json"),
        part_tree=_load_json(paths.export_dir / "part_tree.json"),
        page_index=_load_json(paths.export_dir / "page_index.json"),
        organization_summary=_as_dict(_load_json(paths.export_dir / "organization_summary.json")),
        manifest=_as_dict(_load_json(paths.manifest_path)),
        quality_gate=_as_dict(_load_json(paths.quality_path)),
    )


def get_status(data: ApiData) -> dict[str, Any]:
    """Return a compact operational status payload."""
    manifest = data.manifest
    quality = data.quality_gate
    return {
        "quality_status": _first_text(quality, "status", "quality_status"),
        "manifest_status": _first_text(manifest, "status", "pipeline_status"),
        "run_id": _first_text(manifest, "run_id", "id"),
        "pipeline": _first_text(manifest, "pipeline", "pipeline_name"),
        "sqlite_counts": _first_dict(manifest, "sqlite_counts", "counts"),
        "eval_summary": _first_dict(manifest, "eval_summary", "rag_eval_summary"),
        "qa_summary": _first_dict(manifest, "qa_summary"),
        "source_link_summary": _first_dict(manifest, "source_link_summary"),
        "ocr_coverage_summary": _first_dict(manifest, "ocr_coverage_summary"),
        "document_organization_summary": _first_dict(manifest, "document_organization_summary"),
        "document_organization_export_summary": _first_dict(manifest, "document_organization_export_summary"),
        "incremental_smoke_summary": _first_dict(manifest, "incremental_smoke_summary"),
        "quality_summary": _first_dict(quality, "summary"),
        "quality_checks": _first_list(quality, "checks"),
    }


def get_organization_summary(data: ApiData) -> dict[str, Any]:
    """Return normalized organization counts."""
    summary = data.organization_summary
    counts = _first_dict(summary, "counts") or summary
    return {
        "manuals": _first_int(counts, "manuals", "manual_count"),
        "pages": _first_int(counts, "pages", "page_count"),
        "ata_groups": _first_int(counts, "ata_groups", "ata_count"),
        "parts": _first_int(counts, "parts", "distinct_parts", "logical_distinct_parts"),
        "part_mentions": _first_int(counts, "part_mentions", "mentions", "logical_part_mentions"),
        "pages_with_parts": _first_int(counts, "pages_with_parts"),
        "empty_ocr_pages": _first_int(counts, "empty_ocr_pages"),
        "part_tree_source": _first_text(counts, "part_tree_source"),
        "raw_distinct_parts": _first_int(counts, "raw_distinct_parts", "raw_parts_seen"),
        "raw_part_mentions": _first_int(counts, "raw_part_mentions", "raw_mentions_seen"),
        "raw_mentions_excluded": _first_int(counts, "raw_mentions_excluded", "raw_mentions_excluded_from_part_tree"),
        "files": _first_dict(summary, "files", "files_written") or {},
    }


def find_part(data: ApiData, part_number: str, *, limit_pages: int = 10) -> dict[str, Any] | None:
    """Find a part in the exported part tree."""
    needle = _norm(part_number)
    for part in _collect_records(data.part_tree, key_field="part_number"):
        if _norm(_first_text(part, "part_number", "part", "number", "canonical_part_number")) == needle:
            result = dict(part)
            pages = _nested_records(result, "pages", "source_pages", "sources")
            if pages:
                result["sample_pages"] = pages[:limit_pages]
            return result
    return None


def find_ata(data: ApiData, ata_code: str, *, limit_pages: int = 10) -> dict[str, Any] | None:
    """Find an ATA section in the exported ATA tree."""
    needle = _norm(ata_code)
    matches = []
    for ata in _collect_records(data.ata_tree, key_field="ata"):
        if _norm(_first_text(ata, "ata", "ata_code", "ataCode")) == needle:
            matches.append(ata)
    if not matches:
        return None
    # Prefer populated entries.
    matches.sort(key=lambda row: (_count(row, "pages", "page_count"), _count(row, "parts", "part_count", "part_mentions")), reverse=True)
    result = dict(matches[0])
    pages = _nested_records(result, "pages", "source_pages", "sources")
    if pages:
        result["sample_pages"] = pages[:limit_pages]
    return result


def find_page(data: ApiData, page_id: str) -> dict[str, Any] | None:
    """Find a page by exact page id."""
    needle = _norm(page_id)
    for page in _collect_records(data.page_index, key_field="page_id"):
        if _norm(_first_text(page, "page_id", "pageId", "id")) == needle:
            return page
    return None


def ask_question(
    question: str,
    *,
    repo_root: str | Path = ".",
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    """Run the existing RAG CLI and return stdout/stderr details.

    This keeps the first API thin: it calls the trusted CLI path rather than
    reimplementing RAG routing inside the API app.
    """
    root = Path(repo_root).resolve()
    cmd = [
        sys.executable,
        "scripts/ask_tiff_rag.py",
        "--config",
        str(config_path),
        question,
    ]
    proc = subprocess.run(
        cmd,
        cwd=root,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    return {
        "question": question,
        "returncode": proc.returncode,
        "ok": proc.returncode == 0,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "command": cmd,
    }


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _norm(value: Any) -> str:
    return str(value or "").strip().upper()


def _first_text(mapping: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, (str, int, float, bool)):
            text = str(value)
            if text:
                return text
    return None


def _first_int(mapping: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _first_dict(mapping: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _first_list(mapping: dict[str, Any], *keys: str) -> list[Any]:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, list):
            return value
    return []


def _count(mapping: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return 0


def _nested_records(mapping: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return [item for item in value.values() if isinstance(item, dict)]
    return []


def _collect_records(data: Any, *, key_field: str) -> list[dict[str, Any]]:
    """Collect dict records from common list/dict export shapes."""
    records: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(record: dict[str, Any], fallback_key: str | None = None) -> None:
        row = dict(record)
        if fallback_key and key_field not in row:
            row[key_field] = fallback_key
        identity = json.dumps(row, sort_keys=True, default=str)
        if identity not in seen:
            seen.add(identity)
            records.append(row)

    def visit(node: Any, fallback_key: str | None = None, depth: int = 0) -> None:
        if depth > 8:
            return
        if isinstance(node, list):
            for item in node:
                visit(item, fallback_key, depth + 1)
        elif isinstance(node, dict):
            if key_field in node:
                add(node, fallback_key)
            for key, value in node.items():
                key_text = str(key)
                if isinstance(value, dict):
                    if _looks_like_key(key_text, key_field):
                        add(value, key_text)
                    visit(value, key_text, depth + 1)
                elif isinstance(value, list):
                    visit(value, key_text, depth + 1)

    visit(data)
    return records


def _looks_like_key(value: str, key_field: str) -> bool:
    if key_field == "ata":
        return "-" in value and any(ch.isdigit() for ch in value)
    if key_field == "part_number":
        return any(ch.isdigit() for ch in value) and len(value) >= 4
    if key_field == "page_id":
        return bool(value)
    return False
