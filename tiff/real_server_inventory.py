"""Read-only TIFF archive inventory and scale estimator.

This module is intentionally dependency-light so it can run before the rest of the
backend is configured.  It never opens TIFF image bytes; it only reads directory
entries / ZIP central-directory metadata and optionally records lightweight file
statistics.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
import json
import math
import os
import statistics
import time
import zipfile
from typing import Any, Iterable

TIFF_EXTENSIONS = {".tif", ".tiff"}
OCR_EXTENSIONS = {".txt"}
METADATA_EXTENSIONS = {".xml", ".json", ".mets", ".mods"}
OTHER_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".jp2", ".j2k", ".webp", ".bmp"}

DEFAULT_OUTPUT = Path("local_data/batch_audit/real_server_inventory.json")
BYTES_PER_TIB = 1024 ** 4


@dataclass(slots=True)
class InventoryOptions:
    root: Path | None = None
    zip_path: Path | None = None
    target_total_tb: float | None = None
    batch_size_pages: int = 5000
    sample_limit: int = 10
    max_files: int | None = None
    max_stem_track: int = 500_000
    context_seconds_per_page: float = 12.0
    ocr_seconds_per_page: float = 1.0
    embedding_seconds_per_page: float = 0.25
    worker_count: int = 1
    write_json: bool = False
    json_output: Path = DEFAULT_OUTPUT


@dataclass(slots=True)
class FileEntryLite:
    rel_path: str
    size: int
    is_dir: bool = False


@dataclass(slots=True)
class InventoryAccumulator:
    source_kind: str
    source_path: str
    sample_limit: int
    max_stem_track: int
    start_time: float = field(default_factory=time.perf_counter)
    files_seen: int = 0
    directories_seen: int = 0
    total_bytes: int = 0
    tiff_files: int = 0
    tiff_bytes: int = 0
    ocr_text_files: int = 0
    ocr_text_bytes: int = 0
    metadata_files: int = 0
    metadata_bytes: int = 0
    pdf_files: int = 0
    other_image_files: int = 0
    other_files: int = 0
    empty_files: int = 0
    truncated: bool = False
    extension_counts: Counter[str] = field(default_factory=Counter)
    top_level_counts: Counter[str] = field(default_factory=Counter)
    sample_tiffs: list[str] = field(default_factory=list)
    sample_ocr: list[str] = field(default_factory=list)
    sample_metadata: list[str] = field(default_factory=list)
    empty_file_examples: list[str] = field(default_factory=list)
    tiff_sizes_sample: list[int] = field(default_factory=list)
    tiff_stems: set[str] = field(default_factory=set)
    ocr_stems: set[str] = field(default_factory=set)
    duplicate_filename_counter: Counter[str] = field(default_factory=Counter)
    duplicate_stem_counter: Counter[str] = field(default_factory=Counter)
    stem_tracking_truncated: bool = False

    def add_directory(self) -> None:
        self.directories_seen += 1

    def add_file(self, entry: FileEntryLite) -> None:
        self.files_seen += 1
        self.total_bytes += max(0, entry.size)
        rel = _normalize_rel_path(entry.rel_path)
        ext = Path(rel).suffix.lower()
        stem = Path(rel).stem.lower()
        filename = Path(rel).name.lower()
        top = _top_level(rel)

        self.extension_counts[ext or "<no_ext>"] += 1
        self.top_level_counts[top] += 1
        if entry.size == 0:
            self.empty_files += 1
            _append_sample(self.empty_file_examples, rel, self.sample_limit)

        self.duplicate_filename_counter[filename] += 1
        self.duplicate_stem_counter[stem] += 1

        if ext in TIFF_EXTENSIONS:
            self.tiff_files += 1
            self.tiff_bytes += entry.size
            _append_sample(self.sample_tiffs, rel, self.sample_limit)
            if len(self.tiff_sizes_sample) < 100_000:
                self.tiff_sizes_sample.append(entry.size)
            self._track_stem(self.tiff_stems, stem)
        elif ext in OCR_EXTENSIONS:
            self.ocr_text_files += 1
            self.ocr_text_bytes += entry.size
            _append_sample(self.sample_ocr, rel, self.sample_limit)
            self._track_stem(self.ocr_stems, stem)
        elif ext in METADATA_EXTENSIONS:
            self.metadata_files += 1
            self.metadata_bytes += entry.size
            _append_sample(self.sample_metadata, rel, self.sample_limit)
        elif ext == ".pdf":
            self.pdf_files += 1
        elif ext in OTHER_IMAGE_EXTENSIONS:
            self.other_image_files += 1
        else:
            self.other_files += 1

    def _track_stem(self, target: set[str], stem: str) -> None:
        if self.stem_tracking_truncated:
            return
        if len(self.tiff_stems) + len(self.ocr_stems) >= self.max_stem_track:
            self.stem_tracking_truncated = True
            return
        target.add(stem)


def audit_real_server_inventory(options: InventoryOptions) -> dict[str, Any]:
    """Audit a directory tree or ZIP package and return a JSON-serializable report."""
    if bool(options.root) == bool(options.zip_path):
        raise ValueError("Provide exactly one of root or zip_path.")

    if options.root:
        root = Path(options.root)
        accumulator = InventoryAccumulator(
            source_kind="directory",
            source_path=str(root),
            sample_limit=options.sample_limit,
            max_stem_track=options.max_stem_track,
        )
        if not root.exists():
            return _missing_source_report(accumulator, f"Root does not exist: {root}", options)
        _scan_directory(root, accumulator, options.max_files)
    else:
        zip_path = Path(options.zip_path or "")
        accumulator = InventoryAccumulator(
            source_kind="zip",
            source_path=str(zip_path),
            sample_limit=options.sample_limit,
            max_stem_track=options.max_stem_track,
        )
        if not zip_path.exists():
            return _missing_source_report(accumulator, f"ZIP does not exist: {zip_path}", options)
        _scan_zip(zip_path, accumulator, options.max_files)

    return _build_report(accumulator, options)


def _scan_directory(root: Path, accumulator: InventoryAccumulator, max_files: int | None) -> None:
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            accumulator.add_directory()
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            stat = entry.stat(follow_symlinks=False)
                            rel = str(Path(entry.path).relative_to(root))
                            accumulator.add_file(FileEntryLite(rel_path=rel, size=int(stat.st_size)))
                            if max_files is not None and accumulator.files_seen >= max_files:
                                accumulator.truncated = True
                                return
                    except OSError:
                        # If a file disappears or cannot be stated during a read-only walk, skip it.
                        continue
        except OSError:
            continue


def _scan_zip(zip_path: Path, accumulator: InventoryAccumulator, max_files: int | None) -> None:
    seen_dirs: set[str] = set()
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            rel = _normalize_rel_path(info.filename)
            if not rel:
                continue
            path = PurePosixPath(rel)
            for parent in path.parents:
                if str(parent) and str(parent) != ".":
                    seen_dirs.add(str(parent))
            if info.is_dir():
                seen_dirs.add(rel.rstrip("/"))
                continue
            accumulator.add_file(FileEntryLite(rel_path=rel, size=int(info.file_size)))
            if max_files is not None and accumulator.files_seen >= max_files:
                accumulator.truncated = True
                break
    accumulator.directories_seen = len(seen_dirs)


def _build_report(acc: InventoryAccumulator, options: InventoryOptions) -> dict[str, Any]:
    elapsed = time.perf_counter() - acc.start_time
    duplicate_filenames = sum(1 for count in acc.duplicate_filename_counter.values() if count > 1)
    duplicate_stems = sum(1 for count in acc.duplicate_stem_counter.values() if count > 1)
    stem_pairing = _build_stem_pairing(acc)
    tiff_stats = _build_tiff_stats(acc.tiff_sizes_sample, acc.tiff_files, acc.tiff_bytes)
    scale_estimate = _build_scale_estimate(acc, tiff_stats, options)
    storage_estimate = _build_storage_estimate(scale_estimate)
    processing_estimate = _build_processing_estimate(scale_estimate, options)

    warnings: list[str] = []
    errors: list[str] = []
    if acc.truncated:
        warnings.append("Inventory was truncated by --max-files; use results as a sample only.")
    if acc.tiff_files == 0:
        errors.append("No TIFF files found.")
    if acc.ocr_text_files == 0:
        warnings.append("No OCR .txt files found; OCR may need to be imported/generated separately.")
    if acc.empty_files:
        warnings.append(f"Empty files found: {acc.empty_files}.")
    if acc.stem_tracking_truncated:
        warnings.append("Stem tracking was truncated; TIFF/OCR pairing and duplicate-stem analysis are approximate.")
    if duplicate_filenames:
        warnings.append(f"Duplicate filenames found across folders: {duplicate_filenames} filename(s).")
    if duplicate_stems:
        warnings.append(f"Duplicate stems found across file types/folders: {duplicate_stems} stem(s).")

    status = "OK" if not errors else "NEEDS_ATTENTION"
    report: dict[str, Any] = {
        "status": status,
        "source": {
            "kind": acc.source_kind,
            "path": acc.source_path,
        },
        "scan": {
            "elapsed_seconds": round(elapsed, 3),
            "files_seen": acc.files_seen,
            "directories_seen": acc.directories_seen,
            "truncated": acc.truncated,
            "total_bytes": acc.total_bytes,
            "total_gib": round(acc.total_bytes / (1024 ** 3), 4),
        },
        "counts": {
            "tiff_files": acc.tiff_files,
            "ocr_text_files": acc.ocr_text_files,
            "metadata_files": acc.metadata_files,
            "pdf_files": acc.pdf_files,
            "other_image_files": acc.other_image_files,
            "other_files": acc.other_files,
            "empty_files": acc.empty_files,
        },
        "bytes": {
            "tiff_bytes": acc.tiff_bytes,
            "ocr_text_bytes": acc.ocr_text_bytes,
            "metadata_bytes": acc.metadata_bytes,
        },
        "tiff_stats": tiff_stats,
        "ocr_pairing": stem_pairing,
        "duplicates": {
            "duplicate_filenames": duplicate_filenames,
            "duplicate_stems": duplicate_stems,
            "stem_tracking_truncated": acc.stem_tracking_truncated,
        },
        "extension_counts": dict(acc.extension_counts.most_common()),
        "top_level_counts": dict(acc.top_level_counts.most_common(20)),
        "scale_estimate": scale_estimate,
        "storage_estimate": storage_estimate,
        "processing_estimate": processing_estimate,
        "samples": {
            "tiff_files": acc.sample_tiffs,
            "ocr_files": acc.sample_ocr,
            "metadata_files": acc.sample_metadata,
            "empty_files": acc.empty_file_examples,
        },
        "warnings": warnings,
        "errors": errors,
        "readiness_notes": _readiness_notes(acc, scale_estimate),
    }
    return report


def _missing_source_report(acc: InventoryAccumulator, message: str, options: InventoryOptions) -> dict[str, Any]:
    return {
        "status": "NEEDS_ATTENTION",
        "source": {"kind": acc.source_kind, "path": acc.source_path},
        "scan": {"files_seen": 0, "directories_seen": 0, "truncated": False, "total_bytes": 0},
        "counts": {},
        "warnings": [],
        "errors": [message],
        "scale_estimate": _build_empty_scale_estimate(options),
    }


def _build_stem_pairing(acc: InventoryAccumulator) -> dict[str, Any]:
    if acc.stem_tracking_truncated:
        return {
            "available": False,
            "reason": "stem tracking truncated",
            "tiff_stems_tracked": len(acc.tiff_stems),
            "ocr_stems_tracked": len(acc.ocr_stems),
        }
    tiff_without_ocr = sorted(acc.tiff_stems - acc.ocr_stems)[: acc.sample_limit]
    ocr_without_tiff = sorted(acc.ocr_stems - acc.tiff_stems)[: acc.sample_limit]
    return {
        "available": True,
        "tiff_stems": len(acc.tiff_stems),
        "ocr_stems": len(acc.ocr_stems),
        "tiff_stems_without_ocr_count": max(0, len(acc.tiff_stems - acc.ocr_stems)),
        "ocr_stems_without_tiff_count": max(0, len(acc.ocr_stems - acc.tiff_stems)),
        "tiff_stems_without_ocr_examples": tiff_without_ocr,
        "ocr_stems_without_tiff_examples": ocr_without_tiff,
    }


def _build_tiff_stats(sample: list[int], total_files: int, total_bytes: int) -> dict[str, Any]:
    if not sample or total_files == 0:
        return {
            "avg_bytes": 0,
            "median_bytes": 0,
            "min_bytes": 0,
            "max_bytes": 0,
            "sampled_sizes": 0,
            "total_tiff_bytes": total_bytes,
        }
    ordered = sorted(sample)
    return {
        "avg_bytes": round(total_bytes / total_files, 2),
        "median_bytes": round(statistics.median(ordered), 2),
        "min_bytes": min(ordered),
        "max_bytes": max(ordered),
        "p90_bytes": _percentile(ordered, 90),
        "sampled_sizes": len(sample),
        "total_tiff_bytes": total_bytes,
    }


def _build_empty_scale_estimate(options: InventoryOptions) -> dict[str, Any]:
    target_bytes = _target_bytes(options.target_total_tb)
    return {
        "target_total_tb": options.target_total_tb,
        "target_total_tib_bytes": target_bytes,
        "estimated_pages": 0,
        "batch_size_pages": options.batch_size_pages,
        "estimated_batches": 0,
    }


def _build_scale_estimate(acc: InventoryAccumulator, tiff_stats: dict[str, Any], options: InventoryOptions) -> dict[str, Any]:
    target_bytes = _target_bytes(options.target_total_tb)
    avg = float(tiff_stats.get("avg_bytes") or 0)
    estimated_pages = int(target_bytes / avg) if target_bytes and avg > 0 else 0
    batches = math.ceil(estimated_pages / options.batch_size_pages) if estimated_pages and options.batch_size_pages else 0
    current_estimated_batches = math.ceil(acc.tiff_files / options.batch_size_pages) if acc.tiff_files and options.batch_size_pages else 0
    return {
        "target_total_tb": options.target_total_tb,
        "target_total_tib_bytes": target_bytes,
        "estimated_pages": estimated_pages,
        "batch_size_pages": options.batch_size_pages,
        "estimated_batches": batches,
        "current_sample_pages": acc.tiff_files,
        "current_sample_batches": current_estimated_batches,
    }


def _build_storage_estimate(scale: dict[str, Any]) -> dict[str, Any]:
    pages = int(scale.get("estimated_pages") or 0)
    if not pages:
        return {}
    ocr_min = pages * 1_000
    ocr_max = pages * 5_000
    opensearch_min = int(ocr_min * 2)
    opensearch_max = int(ocr_max * 4)
    chunks_min = int(pages * 1.0)
    chunks_max = int(pages * 3.0)
    qdrant_min = chunks_min * 8_000
    qdrant_max = chunks_max * 20_000
    postgres_min = pages * 2_000
    postgres_max = pages * 10_000
    return {
        "ocr_text_bytes_range": [ocr_min, ocr_max],
        "opensearch_bytes_range": [opensearch_min, opensearch_max],
        "qdrant_bytes_range": [qdrant_min, qdrant_max],
        "postgres_catalog_bytes_range": [postgres_min, postgres_max],
        "assumptions": {
            "ocr_text_bytes_per_page": "1 KB to 5 KB",
            "opensearch_multiplier": "2x to 4x OCR text",
            "qdrant_chunks_per_page": "1 to 3",
            "qdrant_bytes_per_chunk": "8 KB to 20 KB",
            "postgres_catalog_bytes_per_page": "2 KB to 10 KB",
        },
    }


def _build_processing_estimate(scale: dict[str, Any], options: InventoryOptions) -> dict[str, Any]:
    pages = int(scale.get("estimated_pages") or 0)
    if not pages:
        return {}
    workers = max(1, options.worker_count)

    def hours(seconds_per_page: float) -> float:
        return round((pages * seconds_per_page) / 3600 / workers, 2)

    return {
        "worker_count": workers,
        "ocr_hours": hours(options.ocr_seconds_per_page),
        "page_context_llm_hours": hours(options.context_seconds_per_page),
        "embedding_hours": hours(options.embedding_seconds_per_page),
        "assumptions": {
            "ocr_seconds_per_page": options.ocr_seconds_per_page,
            "context_seconds_per_page": options.context_seconds_per_page,
            "embedding_seconds_per_page": options.embedding_seconds_per_page,
            "note": "Estimates are linear and do not include file-server bottlenecks, retries, QA, or queue overhead.",
        },
    }


def _readiness_notes(acc: InventoryAccumulator, scale: dict[str, Any]) -> list[str]:
    notes = [
        "This is a read-only inventory; it does not OCR, index, embed, or open TIFF image bytes.",
        "Use this report to size the first baseline pass before starting heavy processing.",
        "Do not store TIFF bytes in PostgreSQL, OpenSearch, or Qdrant; store paths, metadata, text, and vectors.",
        "After baseline, switch to changed-file feeds or metadata comparison for incremental updates.",
    ]
    if acc.ocr_text_files == 0:
        notes.append("No OCR text files were found in this source; OCR must be imported from another export or generated.")
    if int(scale.get("estimated_pages") or 0) > 10_000_000:
        notes.append("Estimated page count is very high; avoid full-page LLM context generation and use selective/on-demand context.")
    return notes


def write_inventory_json(report: dict[str, Any], path: Path = DEFAULT_OUTPUT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def format_inventory_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("Real-server TIFF inventory audit")
    lines.append(f"  Status: {report.get('status')}")
    source = report.get("source", {})
    lines.append(f"  Source: {source.get('kind')} {source.get('path')}")
    scan = report.get("scan", {})
    lines.append("")
    lines.append("Scan:")
    lines.append(f"  Files seen: {scan.get('files_seen', 0)}")
    lines.append(f"  Directories seen: {scan.get('directories_seen', 0)}")
    lines.append(f"  Truncated: {scan.get('truncated', False)}")
    lines.append(f"  Total bytes: {scan.get('total_bytes', 0)}")
    counts = report.get("counts", {})
    lines.append("")
    lines.append("File type counts:")
    lines.append(f"  TIFF files: {counts.get('tiff_files', 0)}")
    lines.append(f"  OCR text files: {counts.get('ocr_text_files', 0)}")
    lines.append(f"  Metadata files: {counts.get('metadata_files', 0)}")
    lines.append(f"  PDF files: {counts.get('pdf_files', 0)}")
    lines.append(f"  Other image files: {counts.get('other_image_files', 0)}")
    lines.append(f"  Other files: {counts.get('other_files', 0)}")
    lines.append(f"  Empty files: {counts.get('empty_files', 0)}")
    tiff_stats = report.get("tiff_stats", {})
    lines.append("")
    lines.append("TIFF size stats:")
    lines.append(f"  Avg bytes/page: {tiff_stats.get('avg_bytes', 0)}")
    lines.append(f"  Median bytes/page: {tiff_stats.get('median_bytes', 0)}")
    lines.append(f"  Min bytes/page: {tiff_stats.get('min_bytes', 0)}")
    lines.append(f"  Max bytes/page: {tiff_stats.get('max_bytes', 0)}")
    pairing = report.get("ocr_pairing", {})
    lines.append("")
    lines.append("OCR pairing:")
    lines.append(f"  Available: {pairing.get('available', False)}")
    if pairing.get("available"):
        lines.append(f"  TIFF stems without OCR: {pairing.get('tiff_stems_without_ocr_count', 0)}")
        lines.append(f"  OCR stems without TIFF: {pairing.get('ocr_stems_without_tiff_count', 0)}")
    else:
        lines.append(f"  Reason: {pairing.get('reason', '-')}")
    scale = report.get("scale_estimate", {})
    if scale.get("target_total_tb") is not None:
        lines.append("")
        lines.append(f"Rough scale estimate for {scale.get('target_total_tb')} TiB archive:")
        lines.append(f"  Estimated pages: {scale.get('estimated_pages', 0):,}")
        lines.append(f"  Batch size: {scale.get('batch_size_pages', 0):,} pages")
        lines.append(f"  Estimated batches: {scale.get('estimated_batches', 0):,}")
    processing = report.get("processing_estimate", {})
    if processing:
        lines.append("")
        lines.append("Processing time estimates:")
        lines.append(f"  Worker count: {processing.get('worker_count')}")
        lines.append(f"  OCR hours: {processing.get('ocr_hours')}")
        lines.append(f"  Page-context LLM hours: {processing.get('page_context_llm_hours')}")
        lines.append(f"  Embedding hours: {processing.get('embedding_hours')}")
    storage = report.get("storage_estimate", {})
    if storage:
        lines.append("")
        lines.append("Derived storage estimates:")
        for key in ["ocr_text_bytes_range", "opensearch_bytes_range", "qdrant_bytes_range", "postgres_catalog_bytes_range"]:
            rng = storage.get(key)
            if rng:
                lines.append(f"  {key}: {_bytes_range_to_human(rng)}")
    warnings = report.get("warnings") or []
    if warnings:
        lines.append("")
        lines.append("Warnings / planning risks:")
        for warning in warnings:
            lines.append(f"  - {warning}")
    errors = report.get("errors") or []
    if errors:
        lines.append("")
        lines.append("Errors:")
        for error in errors:
            lines.append(f"  - {error}")
    samples = report.get("samples", {})
    if samples.get("tiff_files"):
        lines.append("")
        lines.append("Sample TIFF files:")
        for sample in samples["tiff_files"]:
            lines.append(f"  {sample}")
    return "\n".join(lines)


def _append_sample(items: list[str], value: str, limit: int) -> None:
    if len(items) < limit:
        items.append(value)


def _normalize_rel_path(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def _top_level(rel_path: str) -> str:
    normalized = _normalize_rel_path(rel_path)
    if not normalized:
        return "<root>"
    return normalized.split("/", 1)[0]


def _target_bytes(target_total_tb: float | None) -> int:
    if target_total_tb is None:
        return 0
    return int(float(target_total_tb) * BYTES_PER_TIB)


def _percentile(ordered: list[int], percentile: int) -> float:
    if not ordered:
        return 0.0
    index = int(math.ceil((percentile / 100) * len(ordered))) - 1
    index = min(max(index, 0), len(ordered) - 1)
    return float(ordered[index])


def _bytes_range_to_human(rng: Iterable[int]) -> str:
    values = list(rng)
    if len(values) != 2:
        return str(values)
    return f"{_human_bytes(values[0])} to {_human_bytes(values[1])}"


def _human_bytes(num: int) -> str:
    value = float(num)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if value < 1024 or unit == "TB":
            return f"{value:.2f} {unit}"
        value /= 1024
