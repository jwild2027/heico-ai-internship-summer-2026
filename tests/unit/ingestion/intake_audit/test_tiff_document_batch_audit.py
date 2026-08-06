from __future__ import annotations

from pathlib import Path

from tiff.document_batch_audit import audit_document_batch, format_batch_audit_report, write_batch_audit_json


def test_audit_detects_rescarta_like_pages_and_ocr(tmp_path: Path) -> None:
    root = tmp_path / "export"
    pages = root / "object_a" / "pages"
    ocr = root / "object_a" / "ocr"
    pages.mkdir(parents=True)
    ocr.mkdir(parents=True)
    (pages / "000001_00000001.tif").write_bytes(b"tiff")
    (ocr / "000001_00000001.txt").write_text("hello", encoding="utf-8")

    report = audit_document_batch(root)

    assert report.ok is True
    assert report.tiff_files == 1
    assert report.ocr_text_files == 1
    assert report.tiff_stems_without_ocr == 0
    assert report.ocr_stems_without_tiff == 0
    assert report.likely_rescarta_layout is True


def test_audit_flags_missing_ocr_for_tiff_batch(tmp_path: Path) -> None:
    root = tmp_path / "messy"
    root.mkdir()
    (root / "page001.tif").write_bytes(b"tiff")

    report = audit_document_batch(root)

    assert report.ok is True
    assert report.tiff_files == 1
    assert report.ocr_text_files == 0
    assert any(issue.category == "no_ocr_text_files" for issue in report.issues)
    assert any(issue.category == "tiff_without_obvious_ocr" for issue in report.issues)


def test_audit_flags_missing_root_as_error(tmp_path: Path) -> None:
    report = audit_document_batch(tmp_path / "missing")

    assert report.ok is False
    assert report.files_seen == 0
    assert any(issue.category == "root_missing" for issue in report.issues)


def test_audit_reports_duplicate_names_and_stems(tmp_path: Path) -> None:
    root = tmp_path / "batch"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir(parents=True)
    (root / "a" / "0001.tif").write_bytes(b"one")
    (root / "b" / "0001.tif").write_bytes(b"two")
    (root / "a" / "0001.txt").write_text("one", encoding="utf-8")
    (root / "b" / "0001.txt").write_text("two", encoding="utf-8")

    report = audit_document_batch(root)

    assert report.duplicate_filenames >= 2
    assert report.duplicate_stems >= 1
    assert report.sample_duplicate_filenames
    assert any(issue.category == "duplicate_filenames" for issue in report.issues)


def test_audit_respects_max_files_truncation(tmp_path: Path) -> None:
    root = tmp_path / "batch"
    root.mkdir()
    for index in range(5):
        (root / f"page{index}.tif").write_bytes(b"x")

    report = audit_document_batch(root, max_files=2)

    assert report.truncated is True
    assert report.files_seen == 2
    assert any(issue.category == "scan_truncated" for issue in report.issues)


def test_format_and_json_are_command_line_friendly(tmp_path: Path) -> None:
    root = tmp_path / "batch"
    root.mkdir()
    (root / "page001.tif").write_bytes(b"tiff")
    report = audit_document_batch(root)

    text = format_batch_audit_report(report)
    assert "Document batch intake audit" in text
    assert "TIFF files: 1" in text

    out = write_batch_audit_json(report, tmp_path / "out" / "audit.json")
    assert out.exists()
    assert "tiff_files" in out.read_text(encoding="utf-8")


def test_audit_prints_empty_file_examples_and_types(tmp_path: Path) -> None:
    root = tmp_path / "batch"
    (root / "obj" / "pages").mkdir(parents=True)
    (root / "obj" / "ocr").mkdir(parents=True)
    (root / "obj" / "pages" / "0001.tif").write_bytes(b"")
    (root / "obj" / "ocr" / "0001.txt").write_text("ocr", encoding="utf-8")

    report = audit_document_batch(root)
    text = format_batch_audit_report(report)

    assert report.empty_files == 1
    assert report.empty_file_extension_counts[".tif"] == 1
    assert report.sample_empty_files == [str(Path("obj") / "pages" / "0001.tif")]
    assert "Empty file types:" in text
    assert "example:" in text
