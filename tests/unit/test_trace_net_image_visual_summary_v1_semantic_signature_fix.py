from pathlib import Path
import json

from tiff.trace_net_image_visual_summary_v1 import build_image_visual_summary


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_semantic_validator_signature_accepts_ocr_text_lookup_in_dry_run(tmp_path: Path) -> None:
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

    report = build_image_visual_summary(
        route_dispatch_handoff_path=route_path,
        fishnet_ocr_grid_path=fishnet_path,
        output_dir=tmp_path / "out",
        vision_mode="dry_run",
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["visual_summary_card_count"] == 1
    assert report["records"][0]["semantic_validation_status"]
