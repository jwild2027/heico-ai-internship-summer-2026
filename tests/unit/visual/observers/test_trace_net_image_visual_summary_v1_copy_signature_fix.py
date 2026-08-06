import json
from pathlib import Path
import zipfile

from tiff.trace_net_image_visual_summary_v1 import build_image_visual_summary


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_copy_or_extract_image_receives_ocr_lookup_and_resolves_zip_member(tmp_path: Path) -> None:
    route_path = _write_json(
        tmp_path / "route.json",
        {
            "quality_status": "PASS",
            "records": [
                {"page_id": "t_p_120_1176_p000001", "accepted_route": "image_visual"},
            ],
        },
    )
    fishnet_path = _write_json(
        tmp_path / "fishnet.json",
        {
            "quality_status": "PASS",
            "records": [
                {
                    "page_id": "t_p_120_1176_p000001",
                    "canonical_page_number": 1,
                    "ocr_text": "Passenger Seats Component Maintenance Manual",
                }
            ],
        },
    )
    source_zip = tmp_path / "metadata.zip"
    with zipfile.ZipFile(source_zip, "w") as zf:
        zf.writestr("00000001.tif", b"fake tiff bytes")

    report = build_image_visual_summary(
        route_dispatch_handoff_path=route_path,
        fishnet_ocr_grid_path=fishnet_path,
        source_package_path=source_zip,
        output_dir=tmp_path / "out",
        vision_mode="dry_run",
        write_image_copies=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["image_source_found_count"] == 1
    record = report["records"][0]
    assert record["image_source_status"] == "source_package_member"
    assert record["image_source_candidates"]["source_package_member"] == "00000001.tif"
    assert record["ocr_text_available_for_visual_validation"] is True
