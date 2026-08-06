import json
import zipfile
from pathlib import Path

from tiff.trace_net_image_visual_summary_v1 import build_image_visual_summary


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_resolves_bare_eight_digit_tiff_members_from_metadata_zip(tmp_path):
    route_path = tmp_path / "route.json"
    _write_json(
        route_path,
        {
            "quality_status": "PASS",
            "records": [
                {"page_id": "t_p_120_1176_p000001", "accepted_route": "image_visual"},
                {"page_id": "t_p_120_1176_p000012", "accepted_route": "image_visual"},
            ],
        },
    )

    source_zip = tmp_path / "metadata.zip"
    with zipfile.ZipFile(source_zip, "w") as zf:
        zf.writestr("metadata.xml", "<metadata/>")
        zf.writestr("00000001.tif", b"page one")
        zf.writestr("00000012.tif", b"page twelve")

    report = build_image_visual_summary(
        route_dispatch_handoff_path=route_path,
        source_package_path=source_zip,
        output_dir=tmp_path / "out",
        vision_mode="dry_run",
        write_image_copies=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["image_visual_handoff_count"] == 2
    assert report["summary"]["image_source_found_count"] == 2
    assert report["summary"]["missing_image_source_count"] == 0
    records = report["records"]
    assert records[0]["image_source_status"] == "source_package_member"
    assert records[0]["image_source_candidates"]["source_package_member"] == "00000001.tif"
    assert records[1]["image_source_candidates"]["source_package_member"] == "00000012.tif"
    assert Path(records[0]["image_path"]).exists()
    assert Path(records[1]["image_path"]).exists()
