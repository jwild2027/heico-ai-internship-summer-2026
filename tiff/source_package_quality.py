"""Quality checks for raw source-package to organization traceability.

This module is intentionally read-only. It validates the report written by
``scripts/audit_source_package_traceability.py`` and turns it into a compact
quality-gate result that can be embedded into the pipeline manifest.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
from typing import Any, Mapping

DEFAULT_SOURCE_TRACEABILITY_JSON = "local_data/batch_audit/source_package_traceability.json"
DEFAULT_SOURCE_PACKAGE_QUALITY_JSON = "local_data/batch_audit/source_package_quality.json"


@dataclass(frozen=True)
class SourcePackageQualityThresholds:
    """Thresholds for raw source package traceability checks."""

    min_zip_tiff_files: int = 1
    min_organization_pages: int = 1
    max_zip_tiffs_without_organization_page: int = 0
    max_organization_pages_without_zip_tiff: int = 0
    max_duplicate_zip_page_numbers: int = 0
    max_duplicate_organization_page_numbers: int = 0
    require_metadata_xml: bool = True


@dataclass(frozen=True)
class SourcePackageQualityCheck:
    name: str
    status: str
    message: str


@dataclass(frozen=True)
class SourcePackageQualityResult:
    status: str
    summary: dict[str, Any]
    checks: list[SourcePackageQualityCheck] = field(default_factory=list)


def _load_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "ok"}


def _str_status(value: Any) -> str:
    return str(value or "missing").strip().lower().replace(" ", "_")


def _add_check(checks: list[SourcePackageQualityCheck], name: str, ok: bool, message: str) -> None:
    checks.append(SourcePackageQualityCheck(name=name, status="OK" if ok else "FAIL", message=message))


def build_source_package_quality_result(
    traceability_json: str | Path = DEFAULT_SOURCE_TRACEABILITY_JSON,
    *,
    thresholds: SourcePackageQualityThresholds | None = None,
) -> SourcePackageQualityResult:
    """Build a quality result from a source-package traceability JSON report."""

    limits = thresholds or SourcePackageQualityThresholds()
    payload = _load_json(traceability_json)
    checks: list[SourcePackageQualityCheck] = []
    present = bool(payload)

    raw_status = _str_status(payload.get("status"))
    status_ok = raw_status in {"ok", "pass", "passed"}
    zip_tiff_files = _as_int(payload.get("zip_tiff_files") or payload.get("tiff_files"))
    org_pages = _as_int(payload.get("organization_pages") or payload.get("organization_page_count"))
    org_pages_with_tiff = _as_int(payload.get("organization_pages_with_tiff_paths"))
    matched_pages = _as_int(payload.get("matched_pages_by_number") or payload.get("matched_pages"))
    zip_only = _as_int(payload.get("zip_tiffs_without_organization_page"))
    org_only = _as_int(payload.get("organization_pages_without_zip_tiff"))
    dup_zip = _as_int(payload.get("duplicate_zip_page_numbers"))
    dup_org = _as_int(payload.get("duplicate_organization_page_numbers"))
    metadata_xml = _as_bool(payload.get("metadata_xml_present"))

    _add_check(
        checks,
        "source_package_traceability_present",
        present,
        f"Source-package traceability report is present at {traceability_json}."
        if present
        else f"Source-package traceability report is missing at {traceability_json}; run scripts/audit_source_package_traceability.py --write-json.",
    )
    _add_check(
        checks,
        "source_package_traceability_status",
        status_ok,
        f"Source-package traceability status is {raw_status}.",
    )
    _add_check(
        checks,
        "source_package_page_counts",
        zip_tiff_files >= limits.min_zip_tiff_files and org_pages >= limits.min_organization_pages,
        f"ZIP TIFF files={zip_tiff_files}, organization pages={org_pages}; minimums are {limits.min_zip_tiff_files} and {limits.min_organization_pages}.",
    )
    _add_check(
        checks,
        "source_package_metadata_xml",
        metadata_xml or not limits.require_metadata_xml,
        "metadata.xml is present in the raw source package."
        if metadata_xml
        else "metadata.xml is missing from the raw source package.",
    )
    _add_check(
        checks,
        "source_package_page_match",
        zip_only <= limits.max_zip_tiffs_without_organization_page
        and org_only <= limits.max_organization_pages_without_zip_tiff
        and matched_pages >= min(zip_tiff_files, org_pages),
        f"Matched pages={matched_pages}; ZIP-only={zip_only}; organization-only={org_only}.",
    )
    _add_check(
        checks,
        "source_package_duplicate_pages",
        dup_zip <= limits.max_duplicate_zip_page_numbers and dup_org <= limits.max_duplicate_organization_page_numbers,
        f"Duplicate ZIP page numbers={dup_zip}; duplicate organization page numbers={dup_org}.",
    )
    _add_check(
        checks,
        "source_package_org_tiff_paths",
        org_pages_with_tiff >= org_pages if org_pages else present,
        f"Organization pages with TIFF paths={org_pages_with_tiff}/{org_pages}.",
    )

    summary = {
        "source_package_traceability_present": present,
        "source_package_traceability_status": raw_status,
        "source_package_zip_path": str(payload.get("zip_path") or ""),
        "source_package_export_dir": str(payload.get("export_dir") or ""),
        "source_package_zip_tiff_files": zip_tiff_files,
        "source_package_organization_pages": org_pages,
        "source_package_organization_pages_with_tiff_paths": org_pages_with_tiff,
        "source_package_matched_pages": matched_pages,
        "source_package_zip_only_pages": zip_only,
        "source_package_organization_only_pages": org_only,
        "source_package_duplicate_zip_page_numbers": dup_zip,
        "source_package_duplicate_organization_page_numbers": dup_org,
        "source_package_metadata_xml_present": metadata_xml,
        "source_package_warnings": payload.get("warnings") if isinstance(payload.get("warnings"), list) else [],
    }
    status = "ok" if all(check.status == "OK" for check in checks) else "fail"
    return SourcePackageQualityResult(status=status, summary=summary, checks=checks)


def source_package_quality_result_to_dict(result: SourcePackageQualityResult) -> dict[str, Any]:
    return asdict(result)


def write_source_package_quality_json(result: SourcePackageQualityResult, path: str | Path = DEFAULT_SOURCE_PACKAGE_QUALITY_JSON) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(source_package_quality_result_to_dict(result), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def format_source_package_quality_result(result: SourcePackageQualityResult) -> str:
    lines = [
        "Source-package traceability quality gate",
        f"  Status: {result.status.upper()}",
        "  Summary:",
    ]
    for key, value in result.summary.items():
        if key == "source_package_warnings":
            continue
        lines.append(f"    {key}: {value}")
    warnings = result.summary.get("source_package_warnings")
    if isinstance(warnings, list) and warnings:
        lines.append("  Warnings:")
        for warning in warnings:
            lines.append(f"    - {warning}")
    lines.append("  Checks:")
    for check in result.checks:
        lines.append(f"    {check.status} {check.name}: {check.message}")
    return "\n".join(lines)
