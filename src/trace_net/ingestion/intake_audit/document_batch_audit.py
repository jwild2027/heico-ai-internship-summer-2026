"""Read-only audit helpers for messy TIFF/ResCarta document batches.

This module intentionally does not OCR files, move files, rename files, or update
pipeline state. It gives a quick shape-of-the-folder report before a new folder
is pointed at the real backend pipeline.
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

TIFF_EXTENSIONS = {".tif", ".tiff"}
OCR_EXTENSIONS = {".txt"}
METADATA_EXTENSIONS = {".xml", ".json", ".csv", ".mets", ".mods"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".jp2"}
DOCUMENT_EXTENSIONS = {".pdf"}

DEFAULT_MAX_FILES = 250_000


@dataclass(frozen=True)
class FileRecord:
    path: str
    rel_path: str
    name: str
    stem: str
    suffix: str
    size_bytes: int
    depth: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class BatchAuditIssue:
    severity: str
    category: str
    message: str
    count: int = 1
    examples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class BatchAuditReport:
    ok: bool
    root: str
    files_seen: int
    directories_seen: int
    max_files_limit: int
    truncated: bool
    total_bytes: int
    extension_counts: dict[str, int]
    tiff_files: int
    ocr_text_files: int
    metadata_files: int
    other_image_files: int
    pdf_files: int
    other_files: int
    empty_files: int
    empty_file_extension_counts: dict[str, int]
    max_depth: int
    top_level_counts: dict[str, int]
    duplicate_filenames: int
    duplicate_stems: int
    tiff_stems_without_ocr: int
    ocr_stems_without_tiff: int
    likely_rescarta_layout: bool
    issues: list[BatchAuditIssue]
    sample_tiff_files: list[str]
    sample_ocr_files: list[str]
    sample_empty_files: list[str]
    sample_duplicate_filenames: list[str]
    sample_tiff_stems_without_ocr: list[str]
    sample_ocr_stems_without_tiff: list[str]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["issues"] = [issue.to_dict() for issue in self.issues]
        return data


def _safe_rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _norm_ext(path: Path) -> str:
    return path.suffix.lower()


def _norm_stem(value: str) -> str:
    """Normalize stems for loose TIFF/OCR pairing.

    ResCarta-style exports often use matching TIFF/TXT stems. This normalizer is
    intentionally conservative; it is a preview/audit helper, not a source-link
    builder.
    """

    stem = str(value or "").lower().strip()
    for token in ("_ocr", "-ocr", ".ocr"):
        if stem.endswith(token):
            stem = stem[: -len(token)]
    return stem


def iter_file_records(root: str | os.PathLike[str], *, max_files: int = DEFAULT_MAX_FILES) -> tuple[list[FileRecord], int, bool]:
    """Return file records, directory count, and whether scanning was truncated."""

    root_path = Path(root)
    records: list[FileRecord] = []
    directories_seen = 0
    truncated = False

    for current_root, dirnames, filenames in os.walk(root_path):
        dirnames.sort()
        filenames.sort()
        directories_seen += 1
        cur = Path(current_root)
        for filename in filenames:
            if len(records) >= max_files:
                truncated = True
                return records, directories_seen, truncated
            path = cur / filename
            try:
                stat = path.stat()
            except OSError:
                size = 0
            else:
                size = int(stat.st_size)
            rel = _safe_rel(path, root_path)
            rel_parts = Path(rel).parts
            records.append(
                FileRecord(
                    path=str(path),
                    rel_path=rel,
                    name=path.name,
                    stem=path.stem,
                    suffix=_norm_ext(path),
                    size_bytes=size,
                    depth=max(len(rel_parts) - 1, 0),
                )
            )
    return records, directories_seen, truncated


def _samples(values: Iterable[str], limit: int = 12) -> list[str]:
    return list(values)[:limit]


def _top_level(rel_path: str) -> str:
    parts = Path(rel_path).parts
    return parts[0] if parts else "."


def _build_issues(
    *,
    root_exists: bool,
    files_seen: int,
    tiff_files: int,
    ocr_text_files: int,
    tiff_stems_without_ocr: int,
    ocr_stems_without_tiff: int,
    duplicate_filenames: int,
    duplicate_stems: int,
    empty_files: int,
    truncated: bool,
    sample_tiff_stems_without_ocr: list[str],
    sample_ocr_stems_without_tiff: list[str],
    sample_duplicate_filenames: list[str],
    sample_empty_files: list[str],
) -> list[BatchAuditIssue]:
    issues: list[BatchAuditIssue] = []
    if not root_exists:
        return [BatchAuditIssue("error", "root_missing", "Audit root does not exist.")]
    if files_seen == 0:
        issues.append(BatchAuditIssue("error", "empty_batch", "No files were found under the audit root."))
    if tiff_files == 0:
        issues.append(BatchAuditIssue("error", "no_tiff_files", "No TIFF files were found under the audit root."))
    if ocr_text_files == 0:
        issues.append(BatchAuditIssue("review", "no_ocr_text_files", "No OCR text files were found. This batch may need OCR generation."))
    if tiff_files and tiff_stems_without_ocr:
        issues.append(
            BatchAuditIssue(
                "review",
                "tiff_without_obvious_ocr",
                "Some TIFF stems do not have an obvious matching OCR text stem.",
                count=tiff_stems_without_ocr,
                examples=sample_tiff_stems_without_ocr,
            )
        )
    if ocr_text_files and ocr_stems_without_tiff:
        issues.append(
            BatchAuditIssue(
                "info",
                "ocr_without_obvious_tiff",
                "Some OCR text stems do not have an obvious matching TIFF stem.",
                count=ocr_stems_without_tiff,
                examples=sample_ocr_stems_without_tiff,
            )
        )
    if duplicate_filenames:
        issues.append(
            BatchAuditIssue(
                "info",
                "duplicate_filenames",
                "Same filename appears in multiple directories. This is common in messy exports; use full path/object ID, not filename alone.",
                count=duplicate_filenames,
                examples=sample_duplicate_filenames,
            )
        )
    if duplicate_stems:
        issues.append(
            BatchAuditIssue(
                "info",
                "duplicate_stems",
                "Same file stem appears multiple times. Page matching should use full path plus source metadata, not stem alone.",
                count=duplicate_stems,
            )
        )
    if empty_files:
        issues.append(
            BatchAuditIssue(
                "review",
                "empty_files",
                "Some files are zero bytes. Inspect these before scaling, because empty TIFF/OCR/metadata files can break source review or OCR import.",
                count=empty_files,
                examples=sample_empty_files,
            )
        )
    if truncated:
        issues.append(BatchAuditIssue("review", "scan_truncated", "Audit stopped early because --max-files was reached."))
    return issues


def audit_document_batch(root: str | os.PathLike[str], *, max_files: int = DEFAULT_MAX_FILES) -> BatchAuditReport:
    """Audit a document batch folder without mutating it."""

    root_path = Path(root)
    root_exists = root_path.exists()
    if not root_exists:
        issues = _build_issues(
            root_exists=False,
            files_seen=0,
            tiff_files=0,
            ocr_text_files=0,
            tiff_stems_without_ocr=0,
            ocr_stems_without_tiff=0,
            duplicate_filenames=0,
            duplicate_stems=0,
            empty_files=0,
            truncated=False,
            sample_tiff_stems_without_ocr=[],
            sample_ocr_stems_without_tiff=[],
            sample_duplicate_filenames=[],
            sample_empty_files=[],
        )
        return BatchAuditReport(
            ok=False,
            root=str(root_path),
            files_seen=0,
            directories_seen=0,
            max_files_limit=max_files,
            truncated=False,
            total_bytes=0,
            extension_counts={},
            tiff_files=0,
            ocr_text_files=0,
            metadata_files=0,
            other_image_files=0,
            pdf_files=0,
            other_files=0,
            empty_files=0,
            empty_file_extension_counts={},
            max_depth=0,
            top_level_counts={},
            duplicate_filenames=0,
            duplicate_stems=0,
            tiff_stems_without_ocr=0,
            ocr_stems_without_tiff=0,
            likely_rescarta_layout=False,
            issues=issues,
            sample_tiff_files=[],
            sample_ocr_files=[],
            sample_empty_files=[],
            sample_duplicate_filenames=[],
            sample_tiff_stems_without_ocr=[],
            sample_ocr_stems_without_tiff=[],
        )

    records, directories_seen, truncated = iter_file_records(root_path, max_files=max_files)
    extension_counts = Counter(record.suffix or "[no_ext]" for record in records)
    filename_counts = Counter(record.name.lower() for record in records)
    stem_counts = Counter(_norm_stem(record.stem) for record in records)
    duplicate_filenames = sum(1 for _, count in filename_counts.items() if count > 1)
    duplicate_stems = sum(1 for _, count in stem_counts.items() if count > 1)

    tiffs = [record for record in records if record.suffix in TIFF_EXTENSIONS]
    ocrs = [record for record in records if record.suffix in OCR_EXTENSIONS]
    metadata = [record for record in records if record.suffix in METADATA_EXTENSIONS]
    other_images = [record for record in records if record.suffix in IMAGE_EXTENSIONS]
    pdfs = [record for record in records if record.suffix in DOCUMENT_EXTENSIONS]
    known_exts = TIFF_EXTENSIONS | OCR_EXTENSIONS | METADATA_EXTENSIONS | IMAGE_EXTENSIONS | DOCUMENT_EXTENSIONS
    other_files = [record for record in records if record.suffix not in known_exts]

    tiff_stems = {_norm_stem(record.stem) for record in tiffs}
    ocr_stems = {_norm_stem(record.stem) for record in ocrs}
    tiff_without_ocr = sorted(tiff_stems - ocr_stems)
    ocr_without_tiff = sorted(ocr_stems - tiff_stems)

    top_level_counts = Counter(_top_level(record.rel_path) for record in records)
    empty_records = [record for record in records if record.size_bytes == 0]
    empty_files = len(empty_records)
    empty_extension_counts = Counter(record.suffix or "[no_ext]" for record in empty_records)
    total_bytes = sum(record.size_bytes for record in records)
    max_depth = max((record.depth for record in records), default=0)

    lower_dirs = {part.lower() for record in records for part in Path(record.rel_path).parts[:-1]}
    likely_rescarta_layout = bool({"pages", "ocr"}.issubset(lower_dirs) and tiffs and ocrs)

    sample_duplicate_names = sorted(name for name, count in filename_counts.items() if count > 1)
    sample_tiff_files = _samples(record.rel_path for record in tiffs)
    sample_ocr_files = _samples(record.rel_path for record in ocrs)
    sample_empty_files = _samples(record.rel_path for record in empty_records)
    sample_tiff_without_ocr = _samples(tiff_without_ocr)
    sample_ocr_without_tiff = _samples(ocr_without_tiff)

    issues = _build_issues(
        root_exists=True,
        files_seen=len(records),
        tiff_files=len(tiffs),
        ocr_text_files=len(ocrs),
        tiff_stems_without_ocr=len(tiff_without_ocr),
        ocr_stems_without_tiff=len(ocr_without_tiff),
        duplicate_filenames=duplicate_filenames,
        duplicate_stems=duplicate_stems,
        empty_files=empty_files,
        truncated=truncated,
        sample_tiff_stems_without_ocr=sample_tiff_without_ocr,
        sample_ocr_stems_without_tiff=sample_ocr_without_tiff,
        sample_duplicate_filenames=_samples(sample_duplicate_names),
        sample_empty_files=sample_empty_files,
    )
    ok = not any(issue.severity == "error" for issue in issues)

    return BatchAuditReport(
        ok=ok,
        root=str(root_path),
        files_seen=len(records),
        directories_seen=directories_seen,
        max_files_limit=max_files,
        truncated=truncated,
        total_bytes=total_bytes,
        extension_counts=dict(sorted(extension_counts.items())),
        tiff_files=len(tiffs),
        ocr_text_files=len(ocrs),
        metadata_files=len(metadata),
        other_image_files=len(other_images),
        pdf_files=len(pdfs),
        other_files=len(other_files),
        empty_files=empty_files,
        empty_file_extension_counts=dict(sorted(empty_extension_counts.items())),
        max_depth=max_depth,
        top_level_counts=dict(top_level_counts.most_common(12)),
        duplicate_filenames=duplicate_filenames,
        duplicate_stems=duplicate_stems,
        tiff_stems_without_ocr=len(tiff_without_ocr),
        ocr_stems_without_tiff=len(ocr_without_tiff),
        likely_rescarta_layout=likely_rescarta_layout,
        issues=issues,
        sample_tiff_files=sample_tiff_files,
        sample_ocr_files=sample_ocr_files,
        sample_empty_files=sample_empty_files,
        sample_duplicate_filenames=_samples(sample_duplicate_names),
        sample_tiff_stems_without_ocr=sample_tiff_without_ocr,
        sample_ocr_stems_without_tiff=sample_ocr_without_tiff,
    )


def write_batch_audit_json(report: BatchAuditReport, output_path: str | os.PathLike[str]) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path


def format_batch_audit_report(report: BatchAuditReport, *, sample_limit: int = 10) -> str:
    lines: list[str] = []
    lines.append("Document batch intake audit")
    lines.append(f"  Status: {'OK' if report.ok else 'NEEDS ATTENTION'}")
    lines.append(f"  Root: {report.root}")
    lines.append(f"  Files seen: {report.files_seen}")
    lines.append(f"  Directories seen: {report.directories_seen}")
    lines.append(f"  Truncated: {report.truncated}")
    lines.append(f"  Total bytes: {report.total_bytes}")
    lines.append("")
    lines.append("File type counts:")
    lines.append(f"  TIFF files: {report.tiff_files}")
    lines.append(f"  OCR text files: {report.ocr_text_files}")
    lines.append(f"  Metadata files: {report.metadata_files}")
    lines.append(f"  Other image files: {report.other_image_files}")
    lines.append(f"  PDF files: {report.pdf_files}")
    lines.append(f"  Other files: {report.other_files}")
    lines.append(f"  Empty files: {report.empty_files}")
    if report.empty_file_extension_counts:
        lines.append("  Empty file types:")
        for ext, count in sorted(report.empty_file_extension_counts.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"    {ext}: {count}")
    lines.append("")
    lines.append("Organization shape:")
    lines.append(f"  Max directory depth: {report.max_depth}")
    lines.append(f"  Likely ResCarta pages/ocr layout: {report.likely_rescarta_layout}")
    lines.append(f"  Duplicate filenames: {report.duplicate_filenames}")
    lines.append(f"  Duplicate stems: {report.duplicate_stems}")
    lines.append(f"  TIFF stems without obvious OCR: {report.tiff_stems_without_ocr}")
    lines.append(f"  OCR stems without obvious TIFF: {report.ocr_stems_without_tiff}")

    if report.top_level_counts:
        lines.append("")
        lines.append("Top-level folder/file counts:")
        for name, count in report.top_level_counts.items():
            lines.append(f"  {name}: {count}")

    if report.extension_counts:
        lines.append("")
        lines.append("Extension counts:")
        for ext, count in sorted(report.extension_counts.items(), key=lambda item: (-item[1], item[0]))[:12]:
            lines.append(f"  {ext}: {count}")

    if report.issues:
        lines.append("")
        lines.append("Issues/warnings:")
        for issue in report.issues:
            lines.append(f"  - {issue.severity} {issue.category}: {issue.message} count={issue.count}")
            for example in issue.examples[:sample_limit]:
                lines.append(f"      example: {example}")

    if report.sample_tiff_files:
        lines.append("")
        lines.append("Sample TIFF files:")
        for item in report.sample_tiff_files[:sample_limit]:
            lines.append(f"  {item}")

    if report.sample_ocr_files:
        lines.append("")
        lines.append("Sample OCR files:")
        for item in report.sample_ocr_files[:sample_limit]:
            lines.append(f"  {item}")

    return "\n".join(lines)
