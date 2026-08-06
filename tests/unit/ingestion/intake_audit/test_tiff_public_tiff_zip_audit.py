from __future__ import annotations

from pathlib import Path
import zipfile

from tiff.public_tiff_zip_audit import audit_public_tiff_zip, format_public_tiff_zip_audit


def test_public_tiff_zip_audit_counts_tiffs_and_metadata(tmp_path: Path):
    zip_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("metadata.xml", "<mets/>")
        zf.writestr("00000001.tif", b"fake")
        zf.writestr("00000002.tif", b"fake")
    audit = audit_public_tiff_zip(zip_path)
    assert audit.status == "OK"
    assert audit.tiff_files == 2
    assert audit.xml_files == 1
    assert audit.has_metadata_xml is True
    assert "no OCR .txt files" in " ".join(audit.warnings)
    text = format_public_tiff_zip_audit(audit)
    assert "TIFF files: 2" in text


def test_public_tiff_zip_audit_needs_attention_without_metadata(tmp_path: Path):
    zip_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("00000001.tif", b"fake")
    audit = audit_public_tiff_zip(zip_path)
    assert audit.status == "NEEDS ATTENTION"
    assert "metadata.xml not found" in audit.warnings
