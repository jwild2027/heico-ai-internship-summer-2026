from __future__ import annotations

import json
import zipfile
from pathlib import Path

from tiff.real_scale_intake import (
    audit_source_zip,
    audit_source_zip_traceability,
    build_intake_plan_report,
    extract_page_number_from_name,
)


def _make_zip(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("metadata.xml", "<metadata />")
        zf.writestr("00000001.tif", b"a" * 10)
        zf.writestr("00000002.tif", b"b" * 20)
        zf.writestr("00000003.tif", b"c" * 30)
    return path


def _make_export(path: Path) -> Path:
    path.mkdir(parents=True)
    page_index = {
        "pages": [
            {
                "page_id": "t_p_120_1176_p000001",
                "page_label": "1",
                "ata_code": "25-21-00",
                "source_image_path": "local_data/rescarta_exports/t_p_120_1176/pages/000001_00000001.tif",
                "source_url": "http://localhost:8080/rescarta/t_p_120_1176/000001",
            },
            {
                "page_id": "t_p_120_1176_p000002",
                "page_label": "2",
                "ata_code": "25-21-00",
                "source_image_path": "local_data/rescarta_exports/t_p_120_1176/pages/000002_00000002.tif",
                "source_url": "http://localhost:8080/rescarta/t_p_120_1176/000002",
            },
            {
                "page_id": "t_p_120_1176_p000003",
                "page_label": "3",
                "ata_code": "25-21-00",
                "source_image_path": "local_data/rescarta_exports/t_p_120_1176/pages/000003_00000003.tif",
                "source_url": "http://localhost:8080/rescarta/t_p_120_1176/000003",
            },
        ]
    }
    (path / "page_index.json").write_text(json.dumps(page_index), encoding="utf-8")
    return path


def test_extract_page_number_handles_zip_and_rescarta_names():
    assert extract_page_number_from_name("00000042.tif") == 42
    assert extract_page_number_from_name("pages/000042_00000042.tif") == 42
    assert extract_page_number_from_name("not_a_page.tif") is None


def test_audit_source_zip_counts_entries(tmp_path: Path):
    zip_path = _make_zip(tmp_path / "metadata.zip")
    report = audit_source_zip(zip_path)
    assert report.status == "ok"
    assert report.tiff_files == 3
    assert report.xml_files == 1
    assert report.metadata_xml_present is True
    assert report.ocr_text_files == 0
    assert report.avg_tiff_bytes == 20.0


def test_source_zip_traceability_matches_export(tmp_path: Path):
    zip_path = _make_zip(tmp_path / "metadata.zip")
    export_dir = _make_export(tmp_path / "export")
    report = audit_source_zip_traceability(zip_path, export_dir)
    assert report.status == "ok"
    assert report.zip_tiff_files == 3
    assert report.organization_pages == 3
    assert report.matched_pages_by_number == 3
    assert report.zip_tiffs_without_organization_page == 0
    assert report.organization_pages_without_zip_tiff == 0
    assert report.sample_matches[0]["page_id"] == "t_p_120_1176_p000001"


def test_source_zip_traceability_flags_mismatch(tmp_path: Path):
    zip_path = _make_zip(tmp_path / "metadata.zip")
    export_dir = _make_export(tmp_path / "export")
    page_index = json.loads((export_dir / "page_index.json").read_text(encoding="utf-8"))
    page_index["pages"].append(
        {
            "page_id": "t_p_120_1176_p000004",
            "source_image_path": "pages/000004_00000004.tif",
        }
    )
    (export_dir / "page_index.json").write_text(json.dumps(page_index), encoding="utf-8")
    report = audit_source_zip_traceability(zip_path, export_dir)
    assert report.status == "needs_attention"
    assert report.organization_pages_without_zip_tiff == 1


def test_build_intake_plan_report(tmp_path: Path):
    zip_path = _make_zip(tmp_path / "metadata.zip")
    export_dir = _make_export(tmp_path / "export")
    report = build_intake_plan_report(
        zip_path=zip_path,
        export_dir=export_dir,
        target_total_bytes=1024,
        batch_size_pages=2,
        context_seconds_per_page=10,
    )
    assert report.status == "ok"
    assert report.traceability is not None
    assert report.traceability.matched_pages_by_number == 3
    assert report.scale_estimate is not None
    assert report.scale_estimate.estimated_pages_at_target_size == 51
    assert len(report.stages) == 6
