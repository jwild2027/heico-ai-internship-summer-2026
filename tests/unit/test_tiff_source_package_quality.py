from __future__ import annotations

import json
from pathlib import Path

from tiff.source_package_quality import (
    SourcePackageQualityThresholds,
    build_source_package_quality_result,
    write_source_package_quality_json,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_source_package_quality_ok(tmp_path: Path) -> None:
    report = tmp_path / "trace.json"
    _write(
        report,
        {
            "status": "ok",
            "zip_path": "metadata.zip",
            "export_dir": "local_data/organization/export",
            "zip_tiff_files": 509,
            "organization_pages": 509,
            "organization_pages_with_tiff_paths": 509,
            "matched_pages_by_number": 509,
            "zip_tiffs_without_organization_page": 0,
            "organization_pages_without_zip_tiff": 0,
            "duplicate_zip_page_numbers": 0,
            "duplicate_organization_page_numbers": 0,
            "metadata_xml_present": True,
            "warnings": [],
        },
    )
    result = build_source_package_quality_result(report)
    assert result.status == "ok"
    assert result.summary["source_package_matched_pages"] == 509
    assert all(check.status == "OK" for check in result.checks)


def test_source_package_quality_fails_on_mismatch(tmp_path: Path) -> None:
    report = tmp_path / "trace.json"
    _write(
        report,
        {
            "status": "needs_attention",
            "zip_tiff_files": 509,
            "organization_pages": 508,
            "organization_pages_with_tiff_paths": 508,
            "matched_pages_by_number": 508,
            "zip_tiffs_without_organization_page": 1,
            "organization_pages_without_zip_tiff": 0,
            "duplicate_zip_page_numbers": 0,
            "duplicate_organization_page_numbers": 0,
            "metadata_xml_present": True,
        },
    )
    result = build_source_package_quality_result(report)
    assert result.status == "fail"
    assert any(check.name == "source_package_page_match" and check.status == "FAIL" for check in result.checks)


def test_source_package_quality_missing_report(tmp_path: Path) -> None:
    result = build_source_package_quality_result(tmp_path / "missing.json")
    assert result.status == "fail"
    assert result.summary["source_package_traceability_present"] is False


def test_source_package_quality_can_write_json(tmp_path: Path) -> None:
    report = tmp_path / "trace.json"
    _write(
        report,
        {
            "status": "ok",
            "zip_tiff_files": 2,
            "organization_pages": 2,
            "organization_pages_with_tiff_paths": 2,
            "matched_pages_by_number": 2,
            "zip_tiffs_without_organization_page": 0,
            "organization_pages_without_zip_tiff": 0,
            "duplicate_zip_page_numbers": 0,
            "duplicate_organization_page_numbers": 0,
            "metadata_xml_present": True,
        },
    )
    result = build_source_package_quality_result(report, thresholds=SourcePackageQualityThresholds(min_zip_tiff_files=1))
    out = write_source_package_quality_json(result, tmp_path / "quality.json")
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "ok"
