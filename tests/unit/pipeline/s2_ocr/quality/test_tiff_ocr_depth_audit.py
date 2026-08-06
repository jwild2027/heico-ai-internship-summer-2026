from __future__ import annotations

import json
import zipfile
from pathlib import Path

from tiff.ocr_depth_audit import (
    OcrDepthThresholds,
    classify_ocr_text,
    run_ocr_depth_audit,
    source_records_from_page_index,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_classify_ocr_text_distinguishes_full_and_header_only() -> None:
    thresholds = OcrDepthThresholds(full_page_min_chars=120, full_page_min_lines=3, full_page_min_words=12)
    full_text = """
    FIGURE 12 SHEET 1 PARTS LIST
    ITEM PART NUMBER NOMENCLATURE QTY
    120-37313-001 HOLDER, MAGAZINE 1
    120-48023-001 PIN, ATTACH 2
    INSTALL FASTENER AND REPAIR DOUBLER AS REQUIRED.
    """
    header_text = "T.P. 120/1176 ATA 25-21-00 PAGE 1056 REV C"

    full_cls, full_metrics = classify_ocr_text(full_text, thresholds)
    header_cls, _ = classify_ocr_text(header_text, thresholds)

    assert full_cls == "likely_full_page"
    assert full_metrics["part_number_hits"] >= 1
    assert header_cls == "short_ocr" or header_cls == "likely_header_only"


def test_page_index_records_and_depth_summary(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    ocr_dir = tmp_path / "ocr"
    full_ocr = ocr_dir / "000001.txt"
    empty_ocr = ocr_dir / "000002.txt"
    header_ocr = ocr_dir / "000003.txt"
    _write(full_ocr, "FIGURE 1 PARTS LIST\n120-37313-001 HOLDER, MAGAZINE\nINSTALL REPAIR SEAT ASSEMBLY FASTENER")
    _write(empty_ocr, "")
    _write(header_ocr, "T.P. 120/1176 ATA 25-21-00 PAGE 10 REV A")
    page_index = {
        "pages": [
            {"page_id": "p1", "ocr_text_path": str(full_ocr), "source_image_path": "p1.tif", "ata_code": "25-21-00"},
            {"page_id": "p2", "ocr_text_path": str(empty_ocr), "source_image_path": "p2.tif"},
            {"page_id": "p3", "ocr_text_path": str(header_ocr), "source_image_path": "p3.tif"},
            {"page_id": "p4", "source_image_path": "p4.tif"},
        ]
    }
    export_dir.mkdir(parents=True)
    page_index_path = export_dir / "page_index.json"
    page_index_path.write_text(json.dumps(page_index), encoding="utf-8")

    records = source_records_from_page_index(page_index_path)
    assert len(records) == 4
    assert records[0].ocr_path == str(full_ocr)

    summary = run_ocr_depth_audit(export_dir=export_dir, sample_limit=10, repo_root=tmp_path, thresholds=OcrDepthThresholds(full_page_min_chars=80, full_page_min_lines=3, full_page_min_words=8))

    assert summary.pages_checked == 4
    assert summary.likely_full_page_ocr == 1
    assert summary.empty_ocr_files == 1
    assert summary.missing_ocr_paths == 1
    assert summary.short_ocr_files + summary.likely_header_only_ocr >= 1


def test_custom_export_dir_does_not_fall_back_to_local_sqlite(tmp_path: Path) -> None:
    export_dir = tmp_path / "custom_export"
    ocr_dir = tmp_path / "ocr"
    ocr_path = ocr_dir / "000001.txt"
    _write(ocr_path, "FIGURE 1 PARTS LIST\n120-37313-001 HOLDER, MAGAZINE\nINSTALL SEAT FASTENER")
    export_dir.mkdir(parents=True)
    (export_dir / "page_index.json").write_text(
        json.dumps({"pages": [{"page_id": "only_test_page", "ocr_text_path": str(ocr_path), "source_image_path": "p1.tif"}]}),
        encoding="utf-8",
    )

    summary = run_ocr_depth_audit(
        export_dir=export_dir,
        repo_root=tmp_path,
        thresholds=OcrDepthThresholds(min_visible_chars=40, full_page_min_chars=40, full_page_min_lines=2, full_page_min_words=5),
    )

    assert summary.source.startswith("page_index")
    assert summary.pages_checked == 1


def test_zip_without_ocr_marks_missing_paths(tmp_path: Path) -> None:
    zip_path = tmp_path / "metadata.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("00000001.tif", b"image")
        zf.writestr("00000002.tif", b"image")
        zf.writestr("metadata.xml", b"<metadata />")

    summary = run_ocr_depth_audit(zip_path=zip_path)

    assert summary.pages_checked == 2
    assert summary.missing_ocr_paths == 2
    assert summary.likely_full_page_ocr == 0


def test_root_pairs_tiff_and_ocr_by_exact_rescarta_stem(tmp_path: Path) -> None:
    _write(tmp_path / "manual" / "ocr" / "000001_00000001.txt", "PARTS LIST\n120-37313-001 HOLDER MAGAZINE\nFIGURE 1 SHEET 1")
    (tmp_path / "manual" / "pages").mkdir(parents=True)
    (tmp_path / "manual" / "pages" / "000001_00000001.tif").write_bytes(b"image")
    (tmp_path / "manual" / "pages" / "000002_00000002.tif").write_bytes(b"image")

    summary = run_ocr_depth_audit(root=tmp_path, repo_root=tmp_path, thresholds=OcrDepthThresholds(min_visible_chars=40, full_page_min_chars=40, full_page_min_lines=2, full_page_min_words=5))

    assert summary.pages_checked == 2
    assert summary.likely_header_only_ocr + summary.likely_full_page_ocr >= 1
    assert summary.missing_ocr_paths == 1
