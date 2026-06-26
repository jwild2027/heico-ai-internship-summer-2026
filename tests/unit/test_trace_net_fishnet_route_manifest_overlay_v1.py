import json
from pathlib import Path

from tiff.trace_net_fishnet_route_manifest_overlay_v1 import (
    build_route_manifest_overlay,
    extract_current_routes,
    page_suffix,
)


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_page_suffix_handles_source_and_canonical_ids():
    assert page_suffix("source_p000004") == "p000004"
    assert page_suffix("t_p_120_1176_p000004") == "p000004"
    assert page_suffix("no-page") is None


def test_extract_current_routes_supports_nested_manifest():
    payload = {
        "records": [
            {"page_route_card": {"page_id": "t_p_120_1176_p000004", "selected_route": "image_visual"}},
            {"page_id": "t_p_120_1176_p000490", "route": "blank_candidate"},
        ]
    }
    idx = extract_current_routes(payload)
    assert idx["source_p000004"]["current_route"] == "image_visual"
    assert idx["p000490"]["current_route"] == "blank_candidate"


def test_build_overlay_is_read_only_and_matches_aliases(tmp_path):
    policy = {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "source_p000004",
                "current_route": "image_visual",
                "recommended_target_route": "normal_text",
                "recommendation_type": "normal_text_review_promotion",
                "recommendation_status": "review_required_before_route_manifest_change",
                "review_priority": "high",
                "fishnet_route_confidence": 0.93,
                "fishnet_ocr_text_length": 892,
                "fishnet_ocr_word_box_count": 129,
                "fishnet_ocr_sample_text": "INTRODUCTION manual text",
                "overlay_candidates": ["overlay.png"],
                "route_change_authorized": False,
                "route_manifest_write_allowed": False,
            }
        ],
    }
    manifest = {"records": [{"page_id": "t_p_120_1176_p000004", "selected_route": "image_visual"}]}
    policy_path = tmp_path / "policy.json"
    manifest_path = tmp_path / "manifest.json"
    out = tmp_path / "out"
    write_json(policy_path, policy)
    write_json(manifest_path, manifest)

    payload = build_route_manifest_overlay(
        policy_path=policy_path,
        current_route_manifest_path=manifest_path,
        output_dir=out,
        quality=True,
    )

    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["overlay_record_count"] == 1
    assert payload["summary"]["normal_text_overlay_proposal_count"] == 1
    assert payload["summary"]["route_change_authorized_count"] == 0
    rec = payload["records"][0]
    assert rec["current_route_match_ok"] is True
    assert rec["current_route_manifest_page_id"] == "t_p_120_1176_p000004"
    assert rec["route_change_authorized"] is False
    assert rec["route_manifest_write_allowed"] is False
    assert (out / "trace_net_fishnet_route_manifest_overlay_v1.json").exists()
    assert (out / "trace_net_fishnet_route_manifest_overlay_v1.md").exists()
