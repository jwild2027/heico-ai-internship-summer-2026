from __future__ import annotations

from pathlib import Path
import zipfile

from tiff.real_server_inventory import (
    InventoryOptions,
    audit_real_server_inventory,
    format_inventory_report,
)


def test_directory_inventory_counts_and_estimates(tmp_path: Path) -> None:
    root = tmp_path / "server"
    (root / "manual_a" / "pages").mkdir(parents=True)
    (root / "manual_a" / "ocr").mkdir(parents=True)
    (root / "manual_a" / "pages" / "000001.tif").write_bytes(b"a" * 100)
    (root / "manual_a" / "pages" / "000002.tif").write_bytes(b"b" * 300)
    (root / "manual_a" / "ocr" / "000001.txt").write_text("hello", encoding="utf-8")
    (root / "manual_a" / "metadata.xml").write_text("<m/>", encoding="utf-8")

    report = audit_real_server_inventory(
        InventoryOptions(root=root, target_total_tb=0.001, batch_size_pages=100, sample_limit=5)
    )

    assert report["status"] == "OK"
    assert report["counts"]["tiff_files"] == 2
    assert report["counts"]["ocr_text_files"] == 1
    assert report["counts"]["metadata_files"] == 1
    assert report["tiff_stats"]["avg_bytes"] == 200
    assert report["ocr_pairing"]["available"] is True
    assert report["ocr_pairing"]["tiff_stems_without_ocr_count"] == 1
    assert report["scale_estimate"]["estimated_pages"] > 0
    assert "Real-server TIFF inventory audit" in format_inventory_report(report)


def test_zip_inventory_counts(tmp_path: Path) -> None:
    zip_path = tmp_path / "metadata.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("00000001.tif", b"a" * 50)
        zf.writestr("00000002.tif", b"b" * 70)
        zf.writestr("metadata.xml", "<metadata/>")

    report = audit_real_server_inventory(InventoryOptions(zip_path=zip_path, target_total_tb=5))

    assert report["status"] == "OK"
    assert report["source"]["kind"] == "zip"
    assert report["counts"]["tiff_files"] == 2
    assert report["counts"]["ocr_text_files"] == 0
    assert any("No OCR" in warning for warning in report["warnings"])
    assert report["scale_estimate"]["estimated_pages"] > 0


def test_missing_root_needs_attention(tmp_path: Path) -> None:
    report = audit_real_server_inventory(InventoryOptions(root=tmp_path / "missing"))

    assert report["status"] == "NEEDS_ATTENTION"
    assert report["errors"]


def test_truncated_inventory(tmp_path: Path) -> None:
    root = tmp_path / "server"
    root.mkdir()
    for index in range(5):
        (root / f"{index:06d}.tif").write_bytes(b"x")

    report = audit_real_server_inventory(InventoryOptions(root=root, max_files=2))

    assert report["scan"]["truncated"] is True
    assert report["scan"]["files_seen"] == 2
    assert any("truncated" in warning.lower() for warning in report["warnings"])
