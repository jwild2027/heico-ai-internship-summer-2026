import zipfile
from pathlib import Path

from tiff.trace_net_ocr_route_scan_pack_v1 import build_ocr_route_scan_pack


def test_build_scan_pack_from_zip_without_tesseract(tmp_path):
    source = tmp_path / "metadata.zip"
    with zipfile.ZipFile(source, "w") as z:
        z.writestr("00000001.tif", b"not-a-real-tiff")
        z.writestr("00000002.tif", b"not-a-real-tiff-2")
    out = tmp_path / "out"
    payload = build_ocr_route_scan_pack(source_package=source, output_dir=out, quality=True)
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["scan_record_count"] == 2
    assert payload["summary"]["raw_image_hash_count"] == 2
    assert (out / "trace_net_ocr_route_scan_pack_v1.json").exists()
    assert (out / "trace_net_ocr_route_scan_pack_v1_page_comparison_manifest.jsonl").exists()
    assert all(r["answer_permission"] is False for r in payload["records"])
