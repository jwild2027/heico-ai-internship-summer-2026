from pathlib import Path

from PIL import Image

from tiff.json_report import scan_tiff_to_dict, scan_tiff_to_json_file


def test_scan_tiff_to_dict_contains_expected_sections(tmp_path: Path):
    tiff_path = tmp_path / "DWG-12345_REV-C_SHEET-1-OF-2.tif"
    Image.new("1", (64, 32), color=1).save(tiff_path)

    report = scan_tiff_to_dict(tiff_path, source_root=tmp_path, hash_file=True)

    assert report["schema_version"] == "tiff_scan_report.v3"
    assert report["scan_status"] == "ok"
    assert report["file"]["file_name"] == tiff_path.name
    assert report["file"]["sha256"] is not None
    assert len(report["file"]["sha256"]) == 64
    assert report["tiff"]["page_count"] == 1
    assert report["tiff"]["width_px"] == 64
    assert report["tiff"]["height_px"] == 32
    assert report["drawing_metadata"] is not None
    assert report["drawing_metadata"]["revision"] == "C"
    assert report["ocr"]["enabled"] is False
    assert "document_classification" in report
    assert "manual_metadata" in report
    assert "document_classification" in report
    assert "manual_metadata" in report


def test_scan_tiff_to_json_file_writes_report(tmp_path: Path):
    tiff_path = tmp_path / "part-1000.tiff"
    output_path = tmp_path / "out" / "part-1000.scan.json"
    Image.new("L", (20, 10), color=255).save(tiff_path)

    written = scan_tiff_to_json_file(tiff_path, output_path, source_root=tmp_path, hash_file=False)

    assert written == output_path
    assert output_path.exists()
    text = output_path.read_text(encoding="utf-8")
    assert '"schema_version": "tiff_scan_report.v3"' in text
    assert '"sha256": null' in text
