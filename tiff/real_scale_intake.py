"""Read-only intake planning and source-package traceability helpers.

These helpers are intentionally conservative: they do not OCR pages, do not
mutate the search DB, and do not touch TIFF bytes except for ZIP entry metadata.
They are meant to prove that the raw source package lines up with the processed
organization layer and to plan the first production/server baseline pass.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import math
import re
import zipfile
from typing import Any, Iterable

TIFF_EXTENSIONS = {".tif", ".tiff"}
OCR_EXTENSIONS = {".txt"}
METADATA_EXTENSIONS = {".xml", ".json"}


@dataclass(frozen=True)
class ZipEntryInfo:
    """Basic information about a source-package ZIP entry."""

    name: str
    suffix: str
    size_bytes: int
    page_number: int | None = None


@dataclass(frozen=True)
class SourcePackageAudit:
    """Read-only summary for a ZIP source package."""

    zip_path: str
    status: str
    total_entries: int
    total_bytes: int
    tiff_files: int
    xml_files: int
    json_files: int
    ocr_text_files: int
    other_files: int
    metadata_xml_present: bool
    tiff_total_bytes: int
    avg_tiff_bytes: float
    median_tiff_bytes: float
    min_tiff_bytes: int
    max_tiff_bytes: int
    duplicate_page_numbers: int
    warnings: list[str]
    sample_tiff_files: list[str]
    sample_metadata_files: list[str]


@dataclass(frozen=True)
class OrganizationPageRef:
    """A page from the organization export with its normalized TIFF page number."""

    page_id: str
    page_label: str | None
    ata_code: str | None
    tiff_path: str | None
    source_url: str | None
    page_number: int | None


@dataclass(frozen=True)
class SourcePackageTraceabilityAudit:
    """Compares a raw source ZIP to the current organization export."""

    status: str
    zip_path: str
    export_dir: str
    zip_tiff_files: int
    organization_pages: int
    organization_pages_with_tiff_paths: int
    matched_pages_by_number: int
    zip_tiffs_without_organization_page: int
    organization_pages_without_zip_tiff: int
    duplicate_zip_page_numbers: int
    duplicate_organization_page_numbers: int
    metadata_xml_present: bool
    warnings: list[str]
    sample_matches: list[dict[str, Any]]
    sample_zip_only: list[str]
    sample_org_only: list[str]


@dataclass(frozen=True)
class RealScaleEstimate:
    """Rough estimate derived from the current public source package."""

    sample_tiff_files: int
    sample_total_tiff_bytes: int
    sample_avg_tiff_bytes: float
    target_total_bytes: int
    estimated_pages_at_target_size: int
    estimated_inventory_batches: int
    batch_size_pages: int
    estimated_context_hours_one_worker: float
    assumed_context_seconds_per_page: float
    warnings: list[str]


@dataclass(frozen=True)
class IntakePlanReport:
    """Combined report for real/server intake planning."""

    status: str
    source_package: SourcePackageAudit
    traceability: SourcePackageTraceabilityAudit | None
    scale_estimate: RealScaleEstimate | None
    stages: list[dict[str, Any]]
    readiness_notes: list[str]


def _suffix(name: str) -> str:
    return Path(name).suffix.lower()


def extract_page_number_from_name(name: str) -> int | None:
    """Extract a normalized page number from TIFF/OCR names.

    Supports both ZIP names like ``00000042.tif`` and ResCarta working-copy
    names like ``000042_00000042.tif``. We use the last numeric group because
    the long group is normally the physical page sequence.
    """

    stem = Path(name).stem
    groups = re.findall(r"\d+", stem)
    if not groups:
        return None
    try:
        return int(groups[-1])
    except ValueError:
        return None


def _median(values: list[int]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def audit_source_zip(zip_path: str | Path, sample_limit: int = 10) -> SourcePackageAudit:
    """Read a source ZIP manifest without extracting files."""

    path = Path(zip_path)
    warnings: list[str] = []
    if not path.exists():
        raise FileNotFoundError(f"Source ZIP not found: {path}")

    entries: list[ZipEntryInfo] = []
    with zipfile.ZipFile(path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            suffix = _suffix(info.filename)
            page_number = extract_page_number_from_name(info.filename) if suffix in TIFF_EXTENSIONS else None
            entries.append(
                ZipEntryInfo(
                    name=info.filename,
                    suffix=suffix,
                    size_bytes=int(info.file_size),
                    page_number=page_number,
                )
            )

    tiffs = [e for e in entries if e.suffix in TIFF_EXTENSIONS]
    xml_files = [e for e in entries if e.suffix == ".xml"]
    json_files = [e for e in entries if e.suffix == ".json"]
    txt_files = [e for e in entries if e.suffix in OCR_EXTENSIONS]
    known = TIFF_EXTENSIONS | OCR_EXTENSIONS | METADATA_EXTENSIONS
    other = [e for e in entries if e.suffix not in known]
    metadata_xml_present = any(Path(e.name).name.lower() == "metadata.xml" for e in entries)
    page_numbers = [e.page_number for e in tiffs if e.page_number is not None]
    duplicate_page_numbers = len(page_numbers) - len(set(page_numbers))
    tiff_sizes = [e.size_bytes for e in tiffs]

    if not metadata_xml_present:
        warnings.append("metadata.xml was not found in the source ZIP")
    if not tiffs:
        warnings.append("no TIFF files found in the source ZIP")
    if not txt_files:
        warnings.append("no OCR .txt files found in ZIP; OCR may need to be imported/generated separately")
    if duplicate_page_numbers:
        warnings.append(f"duplicate TIFF page numbers detected in ZIP: {duplicate_page_numbers}")
    if other:
        warnings.append(f"unexpected non-TIFF/OCR/metadata files in ZIP: {len(other)}")

    status = "ok" if tiffs and metadata_xml_present else "needs_attention"
    return SourcePackageAudit(
        zip_path=str(path),
        status=status,
        total_entries=len(entries),
        total_bytes=sum(e.size_bytes for e in entries),
        tiff_files=len(tiffs),
        xml_files=len(xml_files),
        json_files=len(json_files),
        ocr_text_files=len(txt_files),
        other_files=len(other),
        metadata_xml_present=metadata_xml_present,
        tiff_total_bytes=sum(tiff_sizes),
        avg_tiff_bytes=(sum(tiff_sizes) / len(tiff_sizes)) if tiff_sizes else 0.0,
        median_tiff_bytes=_median(tiff_sizes),
        min_tiff_bytes=min(tiff_sizes) if tiff_sizes else 0,
        max_tiff_bytes=max(tiff_sizes) if tiff_sizes else 0,
        duplicate_page_numbers=duplicate_page_numbers,
        warnings=warnings,
        sample_tiff_files=[e.name for e in tiffs[:sample_limit]],
        sample_metadata_files=[e.name for e in (xml_files + json_files)[:sample_limit]],
    )


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _iter_possible_page_records(obj: Any) -> Iterable[dict[str, Any]]:
    """Yield page-like dictionaries from unknown export JSON shapes."""

    if isinstance(obj, dict):
        # Common shapes: {page_id: {...}}, {"pages": [...]}, or one page record.
        if _page_id_from_record(obj) or any(k in obj for k in ("tiff_path", "source_image_path", "source_url")):
            yield obj
        for key, value in obj.items():
            if isinstance(value, dict):
                # Preserve mapping key as page_id when value has no explicit ID.
                candidate = dict(value)
                if "page_id" not in candidate and str(key).startswith("t_p_"):
                    candidate["page_id"] = str(key)
                yield from _iter_possible_page_records(candidate)
            elif isinstance(value, list):
                for item in value:
                    yield from _iter_possible_page_records(item)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_possible_page_records(item)


def _page_id_from_record(record: dict[str, Any]) -> str | None:
    for key in ("page_id", "id", "node_id"):
        value = record.get(key)
        if isinstance(value, str) and (value.startswith("t_p_") or value.startswith("page:")):
            return value.removeprefix("page:")
    return None


def _first_string(record: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    source = record.get("source")
    if isinstance(source, dict):
        for key in keys:
            value = source.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def load_organization_page_refs(export_dir: str | Path) -> list[OrganizationPageRef]:
    """Load page refs from organization export files.

    The current export writes ``page_index.json``. This function is tolerant of
    list, mapping, and nested shapes so older/newer exports can still be audited.
    """

    export_path = Path(export_dir)
    page_index = export_path / "page_index.json"
    if not page_index.exists():
        raise FileNotFoundError(f"Organization page_index.json not found: {page_index}")

    raw = _load_json(page_index)
    refs_by_id: dict[str, OrganizationPageRef] = {}
    for rec in _iter_possible_page_records(raw):
        page_id = _page_id_from_record(rec)
        if not page_id:
            continue
        tiff_path = _first_string(
            rec,
            (
                "tiff_path",
                "source_image_path",
                "source_tiff_path",
                "image_path",
                "tiff",
                "tiff_uri",
                "source_image_uri",
            ),
        )
        source_url = _first_string(rec, ("source_url", "rescarta_url", "url"))
        page_label = _first_string(rec, ("page_label", "label", "display_label"))
        ata_code = _first_string(rec, ("ata_code", "ata", "section_code"))
        refs_by_id[page_id] = OrganizationPageRef(
            page_id=page_id,
            page_label=page_label,
            ata_code=ata_code,
            tiff_path=tiff_path,
            source_url=source_url,
            page_number=extract_page_number_from_name(tiff_path or page_id),
        )
    return list(refs_by_id.values())


def _index_by_page_number(refs: Iterable[OrganizationPageRef]) -> tuple[dict[int, OrganizationPageRef], int]:
    indexed: dict[int, OrganizationPageRef] = {}
    duplicates = 0
    for ref in refs:
        if ref.page_number is None:
            continue
        if ref.page_number in indexed:
            duplicates += 1
            continue
        indexed[ref.page_number] = ref
    return indexed, duplicates


def audit_source_zip_traceability(
    zip_path: str | Path,
    export_dir: str | Path = "local_data/organization/export",
    sample_limit: int = 10,
) -> SourcePackageTraceabilityAudit:
    """Compare raw ZIP page numbers to organization page TIFF paths."""

    package = audit_source_zip(zip_path, sample_limit=sample_limit)
    refs = load_organization_page_refs(export_dir)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zip_tiff_entries = [info.filename for info in zf.infolist() if not info.is_dir() and _suffix(info.filename) in TIFF_EXTENSIONS]
    zip_by_number: dict[int, str] = {}
    duplicate_zip = 0
    for name in zip_tiff_entries:
        page_number = extract_page_number_from_name(name)
        if page_number is None:
            continue
        if page_number in zip_by_number:
            duplicate_zip += 1
            continue
        zip_by_number[page_number] = name

    org_by_number, duplicate_org = _index_by_page_number(refs)
    matched_numbers = sorted(set(zip_by_number).intersection(org_by_number))
    zip_only_numbers = sorted(set(zip_by_number).difference(org_by_number))
    org_only_numbers = sorted(set(org_by_number).difference(zip_by_number))

    sample_matches = []
    for number in matched_numbers[:sample_limit]:
        ref = org_by_number[number]
        sample_matches.append(
            {
                "page_number": number,
                "zip_entry": zip_by_number[number],
                "page_id": ref.page_id,
                "page_label": ref.page_label,
                "ata_code": ref.ata_code,
                "tiff_path": ref.tiff_path,
                "source_url": ref.source_url,
            }
        )

    warnings: list[str] = []
    if package.status != "ok":
        warnings.extend(package.warnings)
    if len(zip_tiff_entries) != len(refs):
        warnings.append(f"ZIP TIFF count ({len(zip_tiff_entries)}) does not match organization page count ({len(refs)})")
    if zip_only_numbers:
        warnings.append(f"ZIP TIFF pages without organization match: {len(zip_only_numbers)}")
    if org_only_numbers:
        warnings.append(f"Organization pages without ZIP match: {len(org_only_numbers)}")
    if duplicate_zip:
        warnings.append(f"duplicate normalized ZIP page numbers: {duplicate_zip}")
    if duplicate_org:
        warnings.append(f"duplicate normalized organization page numbers: {duplicate_org}")

    status = "ok" if not warnings or warnings == package.warnings and package.ocr_text_files == 0 else "needs_attention"
    # No OCR-in-ZIP is a warning for intake, not a traceability failure when TIFFs match.
    hard_warnings = [w for w in warnings if not w.startswith("no OCR .txt files")]
    status = "ok" if not hard_warnings else "needs_attention"

    return SourcePackageTraceabilityAudit(
        status=status,
        zip_path=str(zip_path),
        export_dir=str(export_dir),
        zip_tiff_files=len(zip_tiff_entries),
        organization_pages=len(refs),
        organization_pages_with_tiff_paths=sum(1 for r in refs if r.tiff_path),
        matched_pages_by_number=len(matched_numbers),
        zip_tiffs_without_organization_page=len(zip_only_numbers),
        organization_pages_without_zip_tiff=len(org_only_numbers),
        duplicate_zip_page_numbers=duplicate_zip,
        duplicate_organization_page_numbers=duplicate_org,
        metadata_xml_present=package.metadata_xml_present,
        warnings=warnings,
        sample_matches=sample_matches,
        sample_zip_only=[zip_by_number[n] for n in zip_only_numbers[:sample_limit]],
        sample_org_only=[org_by_number[n].page_id for n in org_only_numbers[:sample_limit]],
    )


def estimate_real_scale(
    package: SourcePackageAudit,
    target_total_bytes: int,
    batch_size_pages: int = 5000,
    context_seconds_per_page: float = 12.0,
) -> RealScaleEstimate:
    """Estimate rough full-server scale from a source-package sample."""

    warnings: list[str] = []
    avg = package.avg_tiff_bytes
    estimated_pages = int(target_total_bytes / avg) if avg > 0 else 0
    if avg <= 0:
        warnings.append("cannot estimate page count because average TIFF size is zero")
    if estimated_pages > 50_000_000:
        warnings.append("sample TIFF pages are small; 5 TB estimate may imply tens of millions of pages")
    if package.ocr_text_files == 0:
        warnings.append("source package has no OCR; production intake must import or generate OCR text")
    batches = math.ceil(estimated_pages / batch_size_pages) if batch_size_pages > 0 else 0
    hours = estimated_pages * context_seconds_per_page / 3600.0 if estimated_pages else 0.0
    return RealScaleEstimate(
        sample_tiff_files=package.tiff_files,
        sample_total_tiff_bytes=package.tiff_total_bytes,
        sample_avg_tiff_bytes=avg,
        target_total_bytes=target_total_bytes,
        estimated_pages_at_target_size=estimated_pages,
        estimated_inventory_batches=batches,
        batch_size_pages=batch_size_pages,
        estimated_context_hours_one_worker=hours,
        assumed_context_seconds_per_page=context_seconds_per_page,
        warnings=warnings,
    )


def build_intake_plan_report(
    zip_path: str | Path,
    export_dir: str | Path | None = None,
    target_total_bytes: int | None = None,
    batch_size_pages: int = 5000,
    context_seconds_per_page: float = 12.0,
) -> IntakePlanReport:
    """Build a source package traceability and real-scale intake plan report."""

    package = audit_source_zip(zip_path)
    trace = audit_source_zip_traceability(zip_path, export_dir) if export_dir else None
    estimate = estimate_real_scale(package, target_total_bytes, batch_size_pages, context_seconds_per_page) if target_total_bytes else None

    readiness_notes = [
        "Use this ZIP/package as the raw source baseline for the current 509-page sample.",
        "Do not store TIFF bytes in PostgreSQL, OpenSearch, or Qdrant; store IDs, paths, text, metadata, and vectors.",
        "First production pass should be read-only inventory first, then OCR/import, then extraction/indexing in batches.",
        "After baseline, switch to changed-file feeds or metadata comparison for incremental updates.",
    ]
    if package.ocr_text_files == 0:
        readiness_notes.append("OCR is not inside the ZIP; production workflow must import existing OCR from ResCarta or generate OCR.")
    if trace and trace.status == "ok":
        readiness_notes.append("Raw TIFF package matches the organization export by normalized page number.")

    stages = [
        {
            "stage": 1,
            "name": "read_only_inventory",
            "goal": "List files, count pages, record path/size/modified time/hash, and avoid OCR/index work.",
            "success_checks": ["file manifest written", "TIFF count known", "duplicates and empty files reported"],
        },
        {
            "stage": 2,
            "name": "ocr_coverage_plan",
            "goal": "Determine which pages already have OCR and which need OCR generation.",
            "success_checks": ["missing OCR count", "empty OCR count", "OCR backlog"],
        },
        {
            "stage": 3,
            "name": "batched_baseline_processing",
            "goal": "Process pages in resumable batches and commit state only after downstream work succeeds.",
            "success_checks": ["batch manifest", "retry queue", "safe commit state"],
        },
        {
            "stage": 4,
            "name": "index_and_graph_writers",
            "goal": "Write PostgreSQL graph/catalog, OpenSearch OCR index, Qdrant vectors, source links, and page contexts.",
            "success_checks": ["source coverage", "context coverage", "vector-to-graph traceability"],
        },
        {
            "stage": 5,
            "name": "quality_gate",
            "goal": "Run OCR/source/graph/realistic-query quality checks after each batch and full baseline.",
            "success_checks": ["quality status OK", "user query tests pass", "realistic trace tests pass"],
        },
        {
            "stage": 6,
            "name": "incremental_mode",
            "goal": "Process only new/changed/missing files using file state or a server change feed.",
            "success_checks": ["changed-page path used", "full rebuild avoided", "state commit safe"],
        },
    ]

    hard_statuses = [package.status]
    if trace:
        hard_statuses.append(trace.status)
    status = "ok" if all(s == "ok" for s in hard_statuses) else "needs_attention"
    return IntakePlanReport(
        status=status,
        source_package=package,
        traceability=trace,
        scale_estimate=estimate,
        stages=stages,
        readiness_notes=readiness_notes,
    )


def dataclass_to_jsonable(obj: Any) -> Any:
    """Convert dataclass reports into JSON-serializable objects."""

    if hasattr(obj, "__dataclass_fields__"):
        return {k: dataclass_to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): dataclass_to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [dataclass_to_jsonable(v) for v in obj]
    return obj


def write_json_report(report: Any, output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(dataclass_to_jsonable(report), f, indent=2, sort_keys=True)
    return path
