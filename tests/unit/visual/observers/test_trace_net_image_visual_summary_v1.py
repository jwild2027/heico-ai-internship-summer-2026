from __future__ import annotations

import json
import zipfile
from pathlib import Path

from tiff.trace_net_image_visual_summary_v1 import build_image_visual_summary


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_builds_dry_run_cards_from_image_visual_handoffs(tmp_path: Path) -> None:
    route = _write(
        tmp_path / "route.json",
        {
            "quality_status": "PASS",
            "records": [
                {"page_id": "source_p000004", "source_page_id": "metadata_page_000004", "accepted_route": "image_visual"},
                {"page_id": "source_p000005", "accepted_route": "normal_text"},
                {"page_id": "source_p000006", "accepted_route": "image_visual"},
            ],
        },
    )
    payload = build_image_visual_summary(route_dispatch_handoff_path=route, output_dir=tmp_path / "out", vision_mode="dry_run")

    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["image_visual_handoff_count"] == 2
    assert payload["summary"]["visual_summary_card_count"] == 2
    assert payload["summary"]["dry_run_card_count"] == 2
    assert payload["summary"]["answer_permission_count"] == 0
    assert payload["records"][0]["answer_permission"] is False
    assert payload["records"][0]["visual_observation_authority"] == "vision_derived_retrieval_guidance_not_source_truth"
    assert (tmp_path / "out" / "trace_net_image_visual_summary_v1.json").exists()
    assert (tmp_path / "out" / "trace_net_image_visual_summary_v1_records.jsonl").exists()


def test_extracts_image_from_source_package_when_page_number_matches(tmp_path: Path) -> None:
    route = _write(
        tmp_path / "route.json",
        {"quality_status": "PASS", "records": [{"page_id": "source_p000004", "accepted_route": "image_visual"}]},
    )
    package = tmp_path / "metadata.zip"
    with zipfile.ZipFile(package, "w") as zf:
        zf.writestr("pages/page_000004.png", b"notreallypng")

    payload = build_image_visual_summary(
        route_dispatch_handoff_path=route,
        source_package_path=package,
        output_dir=tmp_path / "out",
        vision_mode="dry_run",
        write_image_copies=True,
    )

    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["image_source_found_count"] == 1
    assert payload["records"][0]["image_source_status"] == "source_package_member"
    assert payload["records"][0]["image_path"]
    assert Path(payload["records"][0]["image_path"]).exists()


def test_limits_max_image_pages(tmp_path: Path) -> None:
    route = _write(
        tmp_path / "route.json",
        {
            "quality_status": "PASS",
            "records": [
                {"page_id": "source_p000001", "accepted_route": "image_visual"},
                {"page_id": "source_p000002", "accepted_route": "image_visual"},
            ],
        },
    )
    payload = build_image_visual_summary(
        route_dispatch_handoff_path=route,
        output_dir=tmp_path / "out",
        vision_mode="dry_run",
        max_image_pages=1,
    )
    assert payload["summary"]["image_visual_handoff_count"] == 2
    assert payload["summary"]["visual_summary_card_count"] == 1


def test_parent_directories_are_created_for_nested_output(tmp_path: Path) -> None:
    route = _write(
        tmp_path / "route.json",
        {"quality_status": "PASS", "records": [{"page_id": "source_p000004", "accepted_route": "image_visual"}]},
    )
    nested = tmp_path / "a" / "deep" / "nested" / "image_visual_summary"
    payload = build_image_visual_summary(route_dispatch_handoff_path=route, output_dir=nested, vision_mode="dry_run")
    assert payload["quality_status"] == "PASS"
    assert (nested / "trace_net_image_visual_summary_v1_records.jsonl").exists()
