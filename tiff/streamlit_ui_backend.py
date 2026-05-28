"""Small backend helpers for the local TIFF Streamlit UI.

The Streamlit app intentionally consumes the same artifacts a future API/UI
would use:

* local_data/organization/export/*.json for browse/search
* local_data/pipeline_runs/latest_backend_pipeline.json for status
* local_data/pipeline_runs/latest_quality_gate.json for quality
* scripts/ask_tiff_rag.py for answer generation

The helpers in this module avoid importing Streamlit so they can be unit tested
without UI dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import subprocess
import sys
from typing import Any

from tiff.document_organization_query import (
    OrganizationExport,
    collect_ata_entries,
    collect_pages,
    collect_parts,
    format_ata,
    format_page,
    format_part,
    load_export,
    query_ata,
    query_page,
    query_part,
    summarize_export,
)

DEFAULT_EXPORT_DIR = Path("local_data/organization/export")
DEFAULT_CONFIG_PATH = Path("local_config.yaml")
DEFAULT_MANIFEST_PATH = Path("local_data/pipeline_runs/latest_backend_pipeline.json")
DEFAULT_QUALITY_PATH = Path("local_data/pipeline_runs/latest_quality_gate.json")
DEFAULT_ASK_SCRIPT = Path("scripts/ask_tiff_rag.py")

PART_KEYS = ("part_number", "part", "number", "canonical_part_number")
NOMENCLATURE_KEYS = ("nomenclature", "name", "title", "description")
PAGE_ID_KEYS = ("page_id", "pageId", "id")
PAGE_LABEL_KEYS = ("page_label", "page", "page_number", "label")
ATA_KEYS = ("ata", "ata_code", "ataCode")
SOURCE_KEYS = ("source_url", "rescarta_url", "url", "source")
TIFF_KEYS = ("tiff_path", "image_path", "tiff")
OCR_KEYS = ("ocr_text_path", "ocr_path", "ocr")


@dataclass(frozen=True)
class UiStatus:
    """Compact status object for the UI readiness/status panels."""

    export_ready: bool
    quality_status: str
    manifest_status: str
    manuals: int | None
    pages: int | None
    ata_groups: int | None
    parts: int | None
    part_mentions: int | None
    source_local_review_ready: bool | None
    real_rescarta_ready: bool | None
    ocr_empty_files: int | None
    incremental_smoke_ok: bool | None
    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        if self.errors:
            return False
        if not self.export_ready:
            return False
        if self.quality_status and self.quality_status.lower() not in {"ok", "pass", "passed"}:
            return False
        if self.manifest_status and self.manifest_status.lower() not in {"ok", "pass", "passed"}:
            return False
        return True


@dataclass(frozen=True)
class RagCliDisplay:
    """Parsed view of ask_tiff_rag.py stdout for cleaner UI rendering."""

    question: str
    llm_used: str
    embeddings_used: str
    answer: str
    sources: str
    raw: str


@dataclass(frozen=True)
class ParsedRagOutput:
    """Backward-compatible parsed RAG output with boolean flags."""

    question: str
    llm_used: bool | None
    embeddings_used: bool | None
    answer: str
    sources: str
    raw: str


def load_json_file(path: str | Path) -> dict[str, Any]:
    """Load a JSON object, returning an empty dict when the file is absent."""
    p = Path(path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def load_ui_status(
    *,
    export_dir: str | Path = DEFAULT_EXPORT_DIR,
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    quality_path: str | Path = DEFAULT_QUALITY_PATH,
) -> UiStatus:
    """Return compact status for Streamlit and CLI readiness checks."""
    errors: list[str] = []
    export_summary: dict[str, Any] = {}
    export_ready = False
    try:
        export = load_export(export_dir)
        export_summary = summarize_export(export)
        files_present = export_summary.get("files_present", {})
        export_ready = bool(files_present) and all(files_present.values())
    except Exception as exc:
        errors.append(f"organization export unavailable: {exc}")

    manifest = load_json_file(manifest_path)
    quality = load_json_file(quality_path)
    manifest_summary = _find_summary(manifest)
    quality_summary = _find_summary(quality)

    return UiStatus(
        export_ready=export_ready,
        quality_status=_status_value(quality, quality_summary),
        manifest_status=_status_value(manifest, manifest_summary),
        manuals=_int_value(export_summary, "manuals"),
        pages=_int_value(export_summary, "pages"),
        ata_groups=_int_value(export_summary, "ata_groups"),
        parts=_int_value(export_summary, "parts"),
        part_mentions=_int_value(export_summary, "part_mentions"),
        source_local_review_ready=_bool_value(quality_summary, "source_local_review_ready"),
        real_rescarta_ready=_bool_value(quality_summary, "source_real_rescarta_ready"),
        ocr_empty_files=_int_value(quality_summary, "ocr_empty_files"),
        incremental_smoke_ok=_bool_value(quality_summary, "incremental_smoke_ok"),
        errors=tuple(errors),
    )


def search_parts(export: OrganizationExport, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Search part tree by part number or nomenclature substring."""
    text = query.strip().lower()
    if not text:
        return []
    exact = query_part(export, query, limit=limit)
    if exact:
        return exact
    matches: list[dict[str, Any]] = []
    for row in collect_parts(export):
        haystack = " ".join(
            str(row.get(key, ""))
            for key in ("part_number", "part", "canonical_part_number", "nomenclature", "name", "title")
        ).lower()
        if text in haystack:
            matches.append(row)
            if len(matches) >= limit:
                break
    return matches


def search_ata(export: OrganizationExport, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Search ATA entries by exact code first, then substring."""
    text = query.strip().lower()
    if not text:
        return []
    exact = query_ata(export, query, limit=limit)
    if exact:
        return exact
    matches: list[dict[str, Any]] = []
    for row in collect_ata_entries(export):
        haystack = " ".join(str(row.get(key, "")) for key in ("ata", "ata_code", "title", "manual")).lower()
        if text in haystack:
            matches.append(row)
            if len(matches) >= limit:
                break
    return matches


def search_pages(export: OrganizationExport, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Search pages by page id, label, ATA, source URL, TIFF path, or OCR path."""
    text = query.strip().lower()
    if not text:
        return []
    exactish = query_page(export, query, limit=limit)
    if exactish:
        return exactish
    matches: list[dict[str, Any]] = []
    page_keys = (
        "page_id",
        "id",
        "page_label",
        "page",
        "ata",
        "ata_code",
        "source_url",
        "rescarta_url",
        "tiff_path",
        "ocr_path",
        "ocr_text_path",
    )
    for row in collect_pages(export):
        haystack = " ".join(str(row.get(key, "")) for key in page_keys).lower()
        if text in haystack:
            matches.append(row)
            if len(matches) >= limit:
                break
    return matches


def run_rag_question(
    question: str,
    *,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    ask_script: str | Path = DEFAULT_ASK_SCRIPT,
    timeout_seconds: int = 240,
) -> subprocess.CompletedProcess[str]:
    """Run the existing CLI RAG question path and return the completed process."""
    question_text = question.strip()
    if not question_text:
        raise ValueError("question must not be empty")
    script = Path(ask_script)
    if not script.exists():
        raise FileNotFoundError(f"ask script not found: {script}")
    command = [
        sys.executable,
        str(script),
        "--config",
        str(config_path),
        question_text,
    ]
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )


def parse_rag_cli_stdout(stdout: str) -> RagCliDisplay:
    """Parse ask_tiff_rag.py stdout into answer and source sections."""
    text = stdout or ""
    question = ""
    llm_used = ""
    embeddings_used = ""
    body_lines: list[str] = []
    in_body = False
    for line in text.splitlines():
        if line.startswith("Question:"):
            question = line.split(":", 1)[1].strip()
            continue
        if line.startswith("LLM used:"):
            llm_used = line.split(":", 1)[1].strip()
            continue
        if line.startswith("Embeddings used:"):
            embeddings_used = line.split(":", 1)[1].strip()
            continue
        if line.strip() == "Answer:":
            in_body = True
            continue
        if in_body:
            body_lines.append(line)
    body = "\n".join(body_lines).strip()
    answer, sources = _split_sources(body)
    return RagCliDisplay(
        question=question,
        llm_used=llm_used,
        embeddings_used=embeddings_used,
        answer=answer.strip(),
        sources=sources.strip(),
        raw=text,
    )


def parse_rag_stdout(stdout: str) -> ParsedRagOutput:
    """Backward-compatible parser returning boolean LLM/embedding flags."""
    parsed = parse_rag_cli_stdout(stdout)
    return ParsedRagOutput(
        question=parsed.question,
        llm_used=_bool_from_text(parsed.llm_used),
        embeddings_used=_bool_from_text(parsed.embeddings_used),
        answer=parsed.answer,
        sources=parsed.sources,
        raw=parsed.raw,
    )


def part_header(row: dict[str, Any]) -> dict[str, Any]:
    """Return a compact lowercase-key record for older tests/UI callers."""
    sources = source_table_rows(row, limit=1)
    return {
        "part_number": _first_text(row, *PART_KEYS),
        "nomenclature": _first_text(row, *NOMENCLATURE_KEYS),
        "pages": _count_value(row, "page_count", "pages"),
        "mentions": _count_value(row, "mention_count", "part_mentions", "mentions"),
        "source": sources[0]["source"] if sources else "",
    }


def ata_header(row: dict[str, Any]) -> dict[str, Any]:
    """Return a compact lowercase-key record for ATA results."""
    return {
        "ata": _first_text(row, *ATA_KEYS),
        "manual": _first_text(row, "manual", "publication_number", "manual_id", "title"),
        "pages": _count_value(row, "pages", "page_count"),
        "parts": _count_value(row, "distinct_part_count", "logical_distinct_parts", "parts", "part_count", "part_mentions"),
    }


def page_header(row: dict[str, Any]) -> dict[str, Any]:
    """Return a compact lowercase-key record for page/source results."""
    return {
        "page_id": _first_text(row, *PAGE_ID_KEYS),
        "ata": _first_text(row, *ATA_KEYS),
        "label": _first_text(row, *PAGE_LABEL_KEYS),
        "source": _first_text(row, *SOURCE_KEYS),
        "tiff": _first_text(row, *TIFF_KEYS),
        "ocr": _first_text(row, *OCR_KEYS),
    }


def source_table_rows(row: dict[str, Any], *, limit: int = 10) -> list[dict[str, str]]:
    """Return lowercase-key page/source rows nested under a part or page record."""
    nested = _nested_records(row, ("pages", "source_pages", "sources"))
    if not nested and any(row.get(key) for key in (*PAGE_ID_KEYS, *SOURCE_KEYS, *TIFF_KEYS, *OCR_KEYS)):
        nested = [row]
    records: list[dict[str, str]] = []
    for page in nested[:limit]:
        records.append(
            {
                "page": _first_text(page, *PAGE_ID_KEYS),
                "ata": _first_text(page, *ATA_KEYS),
                "label": _first_text(page, *PAGE_LABEL_KEYS),
                "source": _first_text(page, *SOURCE_KEYS),
                "tiff": _first_text(page, *TIFF_KEYS),
                "ocr": _first_text(page, *OCR_KEYS),
            }
        )
    return records


def page_table_rows(rows: list[dict[str, Any]], *, limit: int | None = None) -> list[dict[str, str]]:
    """Return lowercase-key table rows for page/source search results."""
    selected = rows if limit is None else rows[:limit]
    return [page_header(row) for row in selected]


def part_result_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return compact table records for part search results."""
    records: list[dict[str, Any]] = []
    for row in rows:
        sample_sources = part_source_records(row, limit=1)
        first_source = sample_sources[0]["Source"] if sample_sources else ""
        records.append(
            {
                "Part": _first_text(row, *PART_KEYS),
                "Nomenclature": _first_text(row, *NOMENCLATURE_KEYS),
                "Pages": _count_value(row, "page_count", "pages"),
                "Mentions": _count_value(row, "mention_count", "part_mentions", "mentions"),
                "First source": first_source,
            }
        )
    return records


def part_source_records(row: dict[str, Any], *, limit: int = 10) -> list[dict[str, Any]]:
    """Return source-page records nested under a part result."""
    records: list[dict[str, Any]] = []
    for page in _nested_records(row, ("pages", "source_pages", "sources"))[:limit]:
        records.append(
            {
                "Page ID": _first_text(page, *PAGE_ID_KEYS),
                "ATA": _first_text(page, *ATA_KEYS),
                "Label": _first_text(page, *PAGE_LABEL_KEYS),
                "Source": _first_text(page, *SOURCE_KEYS),
            }
        )
    return records


def ata_result_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return compact table records for ATA search results."""
    records: list[dict[str, Any]] = []
    for row in rows:
        records.append(
            {
                "ATA": _first_text(row, *ATA_KEYS),
                "Manual": _first_text(row, "manual", "publication_number", "manual_id", "title"),
                "Pages": _count_value(row, "pages", "page_count"),
                "Parts": _count_value(row, "distinct_part_count", "logical_distinct_parts", "parts", "part_count", "part_mentions"),
            }
        )
    return records


def page_result_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return compact table records for page/source results."""
    records: list[dict[str, Any]] = []
    for row in rows:
        records.append(
            {
                "Page ID": _first_text(row, *PAGE_ID_KEYS),
                "ATA": _first_text(row, *ATA_KEYS),
                "Label": _first_text(row, *PAGE_LABEL_KEYS),
                "Source": _first_text(row, *SOURCE_KEYS),
                "TIFF": _first_text(row, *TIFF_KEYS),
                "OCR": _first_text(row, *OCR_KEYS),
            }
        )
    return records


def format_status_text(status: UiStatus) -> str:
    """Format UI status for the readiness CLI."""
    lines = ["TIFF UI readiness", f"  Status: {'OK' if status.ok else 'NEEDS ATTENTION'}"]
    lines.append(f"  Organization export ready: {status.export_ready}")
    lines.append(f"  Quality gate status: {status.quality_status or '-'}")
    lines.append(f"  Pipeline manifest status: {status.manifest_status or '-'}")
    lines.append("  Counts:")
    for label, value in (
        ("Manuals", status.manuals),
        ("Pages", status.pages),
        ("ATA groups", status.ata_groups),
        ("Parts", status.parts),
        ("Part mentions", status.part_mentions),
    ):
        lines.append(f"    {label}: {value if value is not None else '-'}")
    lines.append("  Source/OCR/incremental:")
    lines.append(f"    Local source review ready: {status.source_local_review_ready}")
    lines.append(f"    Real ResCarta ready: {status.real_rescarta_ready}")
    lines.append(f"    Empty OCR files: {status.ocr_empty_files}")
    lines.append(f"    Incremental smoke OK: {status.incremental_smoke_ok}")
    if status.errors:
        lines.append("  Errors:")
        lines.extend(f"    - {error}" for error in status.errors)
    return "\n".join(lines)


def format_part_for_ui(row: dict[str, Any]) -> str:
    return format_part(row)


def format_ata_for_ui(row: dict[str, Any]) -> str:
    return format_ata(row)


def format_page_for_ui(row: dict[str, Any]) -> str:
    return format_page(row)


def _bool_from_text(value: str) -> bool | None:
    text = (value or "").strip().lower()
    if text in {"true", "yes", "1", "y"}:
        return True
    if text in {"false", "no", "0", "n"}:
        return False
    return None


def _split_sources(body: str) -> tuple[str, str]:
    marker = "\nSources:\n"
    if marker in body:
        before, after = body.split(marker, 1)
        return before.strip(), after.strip()
    if body.startswith("Sources:\n"):
        return "", body.removeprefix("Sources:\n").strip()
    return body.strip(), ""


def _nested_records(row: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    for key in keys:
        value = row.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _first_text(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _count_value(data: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return len(value)
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            pass
    return 0


def _find_summary(data: dict[str, Any]) -> dict[str, Any]:
    for key in ("summary", "quality_summary", "pipeline_summary"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return data


def _status_value(data: dict[str, Any], summary: dict[str, Any]) -> str:
    for source in (data, summary):
        for key in ("status", "quality_status", "pipeline_status"):
            value = source.get(key)
            if isinstance(value, str):
                return value
    return ""


def _int_value(data: dict[str, Any], key: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool_value(data: dict[str, Any], key: str) -> bool | None:
    value = data.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "ok"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return None
