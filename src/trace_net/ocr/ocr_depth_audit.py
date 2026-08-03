"""OCR depth audit utilities for TIFF document intake.

This module is intentionally read-only.  It classifies OCR coverage as missing,
empty, header-only, likely full-page, or noisy/unknown so we can decide whether
full-page OCR generation is required before search/RAG/graph extraction.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable
import json
import math
import os
import re
import sqlite3
import statistics
import zipfile


PART_RE = re.compile(r"\b(?:[A-Z]{1,4}\d{2,6}-\d{1,4}|\d{2,4}-\d{3,6}-\d{1,4}|\d{3,6}/\d{3,6})\b", re.I)
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9./-]*")
HEADER_WORDS = {
    "ata",
    "page",
    "rev",
    "revision",
    "effectivity",
    "manual",
    "maintenance",
    "t.p.",
    "tp",
    "embraer",
}
BODY_WORDS = {
    "figure",
    "fig",
    "parts",
    "list",
    "install",
    "installation",
    "remove",
    "repair",
    "assembly",
    "assy",
    "seat",
    "fastener",
    "holder",
    "magazine",
    "doubler",
    "drill",
    "table",
    "armrest",
    "nomenclature",
}


@dataclass(frozen=True)
class OcrDepthThresholds:
    # Backward-compatible alias accepted by earlier tests/patches;
    # classification still uses short_max_chars/full_page_min_* thresholds.
    min_visible_chars: int = 0
    short_max_chars: int = 120
    header_only_max_chars: int = 450
    full_page_min_chars: int = 300
    full_page_min_lines: int = 6
    full_page_min_words: int = 30
    full_page_min_body_hits: int = 1


@dataclass
class OcrSourceRecord:
    page_id: str
    ocr_path: str | None = None
    tiff_path: str | None = None
    page_label: str | None = None
    ata_code: str | None = None
    source_url: str | None = None


@dataclass
class OcrDepthRecord:
    page_id: str
    classification: str
    reason: str
    ocr_path: str | None = None
    tiff_path: str | None = None
    page_label: str | None = None
    ata_code: str | None = None
    source_url: str | None = None
    visible_chars: int = 0
    line_count: int = 0
    word_count: int = 0
    part_count: int = 0
    sample_text: str = ""


@dataclass
class OcrDepthSummary:
    status: str
    source: str
    pages_checked: int = 0
    missing_ocr_paths: int = 0
    missing_ocr_files: int = 0
    unreadable_ocr_files: int = 0
    empty_ocr_files: int = 0
    short_ocr_files: int = 0
    likely_header_only_ocr: int = 0
    likely_full_page_ocr: int = 0
    noisy_or_unknown_ocr: int = 0
    readable_ocr_files: int = 0
    total_visible_chars: int = 0
    median_visible_chars: float = 0.0
    local_ocr_paths_ready: bool = False
    full_page_ocr_likely_ready: bool = False
    header_body_review_needed: bool = False
    sample_records: list[dict[str, Any]] = field(default_factory=list)
    by_classification: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


# ------------------------- source discovery -------------------------

def _as_pages(obj: Any) -> list[dict[str, Any]]:
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        pages = obj.get("pages") or obj.get("items") or obj.get("records") or []
        if isinstance(pages, list):
            return [x for x in pages if isinstance(x, dict)]
    return []


def _first_value(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return None


def source_records_from_page_index(page_index_path: str | Path) -> list[OcrSourceRecord]:
    path = Path(page_index_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    records: list[OcrSourceRecord] = []
    for idx, page in enumerate(_as_pages(data), start=1):
        page_id = str(_first_value(page, "page_id", "id", "node_id") or f"page_{idx:06d}")
        records.append(
            OcrSourceRecord(
                page_id=page_id,
                ocr_path=_first_value(page, "ocr_text_path", "ocr_path", "ocr", "ocr_file", "ocr_file_path"),
                tiff_path=_first_value(page, "source_image_path", "tiff_path", "image_path", "source_tiff_path", "tiff"),
                page_label=_first_value(page, "page_label", "label", "page"),
                ata_code=_first_value(page, "ata_code", "ata"),
                source_url=_first_value(page, "source_url", "rescarta_url", "url"),
            )
        )
    return records


def source_records_from_zip(zip_path: str | Path, max_files: int | None = None) -> list[OcrSourceRecord]:
    records: list[OcrSourceRecord] = []
    tiffs: dict[str, str] = {}
    texts: dict[str, str] = {}
    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()
        if max_files:
            infos = infos[:max_files]
        for info in infos:
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            suffix = Path(name).suffix.lower()
            stem = Path(name).stem.lower()
            if suffix in {".tif", ".tiff"}:
                tiffs[stem] = name
            elif suffix == ".txt":
                texts[stem] = name
    for idx, (stem, tiff_name) in enumerate(sorted(tiffs.items()), start=1):
        records.append(
            OcrSourceRecord(
                page_id=f"zip_page_{idx:06d}",
                ocr_path=texts.get(stem),
                tiff_path=tiff_name,
                page_label=str(idx),
            )
        )
    # Include orphan OCR text records too for completeness.
    for stem, text_name in sorted(texts.items()):
        if stem not in tiffs:
            records.append(OcrSourceRecord(page_id=f"zip_ocr_{stem}", ocr_path=text_name))
    return records


def source_records_from_root(root: str | Path, max_files: int | None = None) -> list[OcrSourceRecord]:
    root_path = Path(root)
    tiffs: dict[str, Path] = {}
    texts: dict[str, Path] = {}
    seen = 0
    for dirpath, _, filenames in os.walk(root_path):
        for filename in filenames:
            seen += 1
            if max_files and seen > max_files:
                break
            p = Path(dirpath) / filename
            suffix = p.suffix.lower()
            stem = p.stem.lower()
            if suffix in {".tif", ".tiff"}:
                tiffs[stem] = p
            elif suffix == ".txt":
                texts[stem] = p
        if max_files and seen > max_files:
            break
    records: list[OcrSourceRecord] = []
    for idx, (stem, tiff_path) in enumerate(sorted(tiffs.items()), start=1):
        records.append(
            OcrSourceRecord(
                page_id=f"root_page_{idx:06d}",
                ocr_path=str(texts[stem]) if stem in texts else None,
                tiff_path=str(tiff_path),
            )
        )
    for stem, text_path in sorted(texts.items()):
        if stem not in tiffs:
            records.append(OcrSourceRecord(page_id=f"root_ocr_{stem}", ocr_path=str(text_path)))
    return records


def _read_config_db_path(config_path: str | Path | None) -> str | None:
    if not config_path:
        return None
    p = Path(config_path)
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8", errors="replace")
    # Avoid requiring PyYAML for this small helper.
    for key in ("search_db", "search_db_path", "db_path", "sqlite_db", "tiff_search_db"):
        m = re.search(rf"(?im)^\s*{re.escape(key)}\s*:\s*['\"]?([^'\"\n#]+)", text)
        if m:
            return m.group(1).strip()
    m = re.search(r"(?im)local_data[/\\]db[/\\]tiff_search\.db", text)
    if m:
        return m.group(0)
    return None


def source_records_from_sqlite(db_path: str | Path, repo_root: str | Path | None = None) -> list[OcrSourceRecord]:
    db = Path(db_path)
    if repo_root and not db.is_absolute():
        candidate = Path(repo_root) / db
        if candidate.exists():
            db = candidate
    if not db.exists():
        raise FileNotFoundError(f"SQLite DB not found: {db}")
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM source_links").fetchall()
    finally:
        conn.close()
    records: list[OcrSourceRecord] = []
    for idx, row_obj in enumerate(rows, start=1):
        row = dict(row_obj)
        page_id = str(_first_value(row, "page_id", "id", "source_link_id") or f"db_page_{idx:06d}")
        records.append(
            OcrSourceRecord(
                page_id=page_id,
                ocr_path=_first_value(row, "ocr_path", "ocr_text_path", "ocr_file", "ocr_file_path"),
                tiff_path=_first_value(row, "tiff_path", "source_image_path", "image_path", "source_tiff_path"),
                page_label=_first_value(row, "page_label", "label", "display_page", "page"),
                ata_code=_first_value(row, "ata_code", "ata"),
                source_url=_first_value(row, "source_url", "rescarta_url", "url"),
            )
        )
    return records


# ------------------------- OCR classification -------------------------

def _clean_visible_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _sample(text: str, limit: int = 240) -> str:
    return re.sub(r"\s+", " ", text).strip()[:limit]


def classify_ocr_text(text: str, thresholds: OcrDepthThresholds | None = None) -> tuple[str, dict[str, Any]]:
    """Classify raw OCR text and return a test/API-friendly metrics mapping.

    This public wrapper is kept for backward compatibility with the first OCR-depth
    audit patch. Internally the audit uses _classify_text, which also returns a
    human-readable reason.
    """
    thresholds = thresholds or OcrDepthThresholds()
    classification, _reason, metrics = _classify_text(text, thresholds)
    return classification, {
        "visible_chars": metrics.get("chars", 0),
        "line_count": metrics.get("lines", 0),
        "word_count": metrics.get("words", 0),
        "part_number_hits": metrics.get("parts", 0),
        "body_word_hits": metrics.get("body_hits", 0),
        "header_word_hits": metrics.get("header_hits", 0),
    }


def _classify_text(text: str, thresholds: OcrDepthThresholds) -> tuple[str, str, dict[str, int]]:
    cleaned = _clean_visible_text(text)
    chars = len(cleaned)
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    words = WORD_RE.findall(cleaned)
    lowered = cleaned.lower()
    part_count = len(PART_RE.findall(cleaned))
    body_hits = sum(1 for w in BODY_WORDS if w in lowered)
    header_hits = sum(1 for w in HEADER_WORDS if w in lowered)
    metrics = {"chars": chars, "lines": len(lines), "words": len(words), "parts": part_count, "body_hits": body_hits, "header_hits": header_hits}

    if chars == 0:
        return "empty_ocr", "OCR text is empty after whitespace/control-character cleanup", metrics
    if chars <= thresholds.short_max_chars and len(words) < thresholds.full_page_min_words:
        if header_hits >= 2 and body_hits == 0:
            return "likely_header_only", "OCR is very short and mostly header/title-block words", metrics
        return "short_ocr", "OCR text is too short to be reliable full-page body text", metrics
    if chars <= thresholds.header_only_max_chars and header_hits >= 2 and body_hits == 0:
        return "likely_header_only", "OCR appears to contain title-block/header metadata only", metrics
    if (
        chars >= thresholds.full_page_min_chars
        and len(lines) >= thresholds.full_page_min_lines
        and len(words) >= thresholds.full_page_min_words
        and (body_hits >= thresholds.full_page_min_body_hits or part_count >= 1)
    ):
        return "likely_full_page", "OCR has enough text/body signals to look like full-page content", metrics
    return "noisy_or_unknown", "OCR is readable but did not clearly classify as header-only or full-page body text", metrics


def _resolve_path(path_value: str | None, repo_root: str | Path | None) -> Path | None:
    if not path_value:
        return None
    p = Path(path_value)
    if p.is_absolute():
        return p
    if repo_root:
        candidate = Path(repo_root) / p
        if candidate.exists():
            return candidate
    return p


def _read_ocr_for_record(record: OcrSourceRecord, zip_path: str | Path | None, repo_root: str | Path | None) -> tuple[str | None, str | None]:
    if not record.ocr_path:
        return None, "missing_ocr_path"
    if zip_path:
        try:
            with zipfile.ZipFile(zip_path) as zf:
                try:
                    data = zf.read(record.ocr_path)
                except KeyError:
                    return None, "missing_ocr_file"
            return data.decode("utf-8", errors="replace"), None
        except Exception as exc:  # pragma: no cover - rare zip/read failure
            return None, f"unreadable_ocr:{exc}"
    p = _resolve_path(record.ocr_path, repo_root)
    if p is None:
        return None, "missing_ocr_path"
    if not p.exists():
        return None, "missing_ocr_file"
    try:
        return p.read_text(encoding="utf-8", errors="replace"), None
    except Exception as exc:  # pragma: no cover - filesystem dependent
        return None, f"unreadable_ocr:{exc}"


# ------------------------- audit -------------------------

def run_ocr_depth_audit(
    *,
    export_dir: str | Path | None = None,
    page_index_path: str | Path | None = None,
    zip_path: str | Path | None = None,
    root: str | Path | None = None,
    db_path: str | Path | None = None,
    config_path: str | Path | None = None,
    sample_limit: int = 12,
    max_files: int | None = None,
    repo_root: str | Path | None = None,
    thresholds: OcrDepthThresholds | None = None,
) -> OcrDepthSummary:
    """Run the OCR depth audit.

    Source priority is intentional: explicit test/audit sources win over local DB
    fallback. This prevents tests with a temporary export_dir from accidentally
    reading the repository's real SQLite DB.
    """
    thresholds = thresholds or OcrDepthThresholds()
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()

    source = ""
    records: list[OcrSourceRecord]
    zip_for_reads: str | Path | None = None

    if page_index_path is not None:
        source = f"page_index {page_index_path}"
        records = source_records_from_page_index(page_index_path)
    elif export_dir is not None:
        export_path = Path(export_dir)
        page_index = export_path / "page_index.json"
        source = f"page_index {page_index}"
        records = source_records_from_page_index(page_index)
    elif zip_path is not None:
        source = f"zip {zip_path}"
        zip_for_reads = zip_path
        records = source_records_from_zip(zip_path, max_files=max_files)
    elif root is not None:
        source = f"root {root}"
        records = source_records_from_root(root, max_files=max_files)
    else:
        db = db_path or _read_config_db_path(config_path) or Path("local_data/db/tiff_search.db")
        source = f"sqlite {db}"
        records = source_records_from_sqlite(db, repo_root=repo_root)

    rows: list[OcrDepthRecord] = []
    visible_counts: list[int] = []
    by_class: dict[str, int] = {}

    for record in records:
        text, err = _read_ocr_for_record(record, zip_for_reads, repo_root)
        if err == "missing_ocr_path":
            classification = "missing_ocr_path"
            reason = "No OCR path is available for this page/source record"
            metrics = {"chars": 0, "lines": 0, "words": 0, "parts": 0}
            cleaned = ""
        elif err == "missing_ocr_file":
            classification = "missing_ocr_file"
            reason = "OCR path is present but the OCR file was not found"
            metrics = {"chars": 0, "lines": 0, "words": 0, "parts": 0}
            cleaned = ""
        elif err and err.startswith("unreadable_ocr"):
            classification = "unreadable_ocr"
            reason = err
            metrics = {"chars": 0, "lines": 0, "words": 0, "parts": 0}
            cleaned = ""
        else:
            cleaned = _clean_visible_text(text or "")
            classification, reason, metrics = _classify_text(text or "", thresholds)

        by_class[classification] = by_class.get(classification, 0) + 1
        if classification not in {"missing_ocr_path", "missing_ocr_file", "unreadable_ocr"}:
            visible_counts.append(metrics["chars"])

        rows.append(
            OcrDepthRecord(
                page_id=record.page_id,
                classification=classification,
                reason=reason,
                ocr_path=record.ocr_path,
                tiff_path=record.tiff_path,
                page_label=record.page_label,
                ata_code=record.ata_code,
                source_url=record.source_url,
                visible_chars=metrics["chars"],
                line_count=metrics["lines"],
                word_count=metrics["words"],
                part_count=metrics["parts"],
                sample_text=_sample(cleaned),
            )
        )

    pages_checked = len(records)
    missing_paths = by_class.get("missing_ocr_path", 0)
    missing_files = by_class.get("missing_ocr_file", 0)
    unreadable = by_class.get("unreadable_ocr", 0)
    empty = by_class.get("empty_ocr", 0)
    short = by_class.get("short_ocr", 0)
    header_only = by_class.get("likely_header_only", 0)
    full_page = by_class.get("likely_full_page", 0)
    noisy = by_class.get("noisy_or_unknown", 0)
    readable = pages_checked - missing_paths - missing_files - unreadable

    warnings: list[str] = []
    if missing_paths or missing_files or unreadable:
        warnings.append("Some pages do not have usable OCR paths/files.")
    if empty:
        warnings.append("Some OCR files are empty; these may be blank pages or OCR failures.")
    if header_only:
        warnings.append("Some OCR appears to be header/title-block only; full-page OCR may be needed.")
    if noisy:
        warnings.append("Some OCR is readable but did not clearly classify as full-page body text.")

    non_empty_readable = max(readable - empty, 0)
    ready_ratio = (full_page / non_empty_readable) if non_empty_readable else 0.0
    local_paths_ready = missing_paths == 0 and missing_files == 0 and unreadable == 0
    full_page_ready = local_paths_ready and ready_ratio >= 0.90 and header_only == 0
    status = "OK" if local_paths_ready and full_page > 0 else "NEEDS ATTENTION"

    priority = {
        "missing_ocr_path": 0,
        "missing_ocr_file": 1,
        "unreadable_ocr": 2,
        "empty_ocr": 3,
        "likely_header_only": 4,
        "short_ocr": 5,
        "noisy_or_unknown": 6,
        "likely_full_page": 7,
    }
    sample_rows = sorted(rows, key=lambda r: (priority.get(r.classification, 99), r.page_id))[:sample_limit]

    return OcrDepthSummary(
        status=status,
        source=source,
        pages_checked=pages_checked,
        missing_ocr_paths=missing_paths,
        missing_ocr_files=missing_files,
        unreadable_ocr_files=unreadable,
        empty_ocr_files=empty,
        short_ocr_files=short,
        likely_header_only_ocr=header_only,
        likely_full_page_ocr=full_page,
        noisy_or_unknown_ocr=noisy,
        readable_ocr_files=readable,
        total_visible_chars=sum(visible_counts),
        median_visible_chars=statistics.median(visible_counts) if visible_counts else 0.0,
        local_ocr_paths_ready=local_paths_ready,
        full_page_ocr_likely_ready=full_page_ready,
        header_body_review_needed=bool(empty or short or header_only or noisy or missing_paths or missing_files or unreadable),
        sample_records=[asdict(r) for r in sample_rows],
        by_classification=dict(sorted(by_class.items())),
        warnings=warnings,
    )


def write_summary_json(summary: OcrDepthSummary, output_path: str | Path) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary.to_json_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
