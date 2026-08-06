import zipfile
from pathlib import Path

from tiff.trace_net_ocr_route_scan_pack_v1 import build_ocr_route_scan_pack, check_quality


def test_quality_check_passes_for_comparison_manifest(tmp_path):
    source = tmp_path / "metadata.zip"
    with zipfile.ZipFile(source, "w") as z:
        z.writestr("00000001.tif", b"abc")
    out = tmp_path / "out"
    build_ocr_route_scan_pack(source_package=source, output_dir=out, quality=True)
    result = check_quality(
        report_path=out / "trace_net_ocr_route_scan_pack_v1.json",
        require_source_page_count=1,
        min_route_records=1,
        min_raw_image_hash_count=1,
        require_comparison_manifest=True,
        max_unsafe=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )
    assert result["quality_status"] == "PASS"
