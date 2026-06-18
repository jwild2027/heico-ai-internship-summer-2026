from pathlib import Path
import json

from tiff.trace_net_route_dispatch_manifest_v1 import build_route_dispatch_manifest
from tiff.trace_net_route_dispatch_manifest_v1_quality import RouteDispatchQualityThresholds


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_route_dispatch_manifest_builds_all_route_policies(tmp_path: Path) -> None:
    manifest = tmp_path / "page_route_manifest.json"
    _write_json(manifest, {
        "schema_version": "trace_net_page_route_manifest_v1",
        "quality_status": "PASS",
        "summary": {"quality_status": "PASS"},
        "page_route_cards": [
            {
                "page_id": "p1",
                "source_page_id": "metadata_page_000001",
                "page_number": 1,
                "primary_route": "table",
                "secondary_routes": ["normal_text"],
                "review_required": False,
                "safe_for_routing": True,
                "route_confidence": 0.91,
                "table_score": 0.9,
                "text_score": 0.6,
            },
            {
                "page_id": "p2",
                "source_page_id": "metadata_page_000002",
                "page_number": 2,
                "primary_route": "blank_candidate",
                "secondary_routes": ["image_visual"],
                "review_required": True,
                "safe_for_routing": True,
                "blank_score": 0.8,
            },
        ],
    })
    report = build_route_dispatch_manifest(
        page_route_manifest_path=manifest,
        output_dir=tmp_path / "out",
        thresholds=RouteDispatchQualityThresholds(
            min_dispatch_cards=2,
            min_source_page_dispatch_cards=2,
            min_primary_route_cards=2,
            require_page_route_manifest_quality_pass=True,
            require_no_answer_permission=True,
        ),
    )
    assert report["quality_status"] == "PASS"
    cards = report["route_dispatch_cards"]
    assert cards[0]["table_processing_allowed"] is True
    assert cards[0]["normal_text_processing_allowed"] is False
    assert cards[1]["blank_candidate_processing_allowed"] is True
    assert cards[1]["image_visual_processing_allowed"] is True
    assert cards[1]["review_processing_required"] is True


def test_unsafe_route_blocks_all_processing(tmp_path: Path) -> None:
    manifest = tmp_path / "page_route_manifest.json"
    _write_json(manifest, {
        "schema_version": "trace_net_page_route_manifest_v1",
        "quality_status": "PASS",
        "summary": {"quality_status": "PASS"},
        "page_route_cards": [
            {
                "page_id": "p1",
                "source_page_id": "metadata_page_000001",
                "primary_route": "table",
                "secondary_routes": [],
                "review_required": False,
                "safe_for_routing": False,
            }
        ],
    })
    report = build_route_dispatch_manifest(
        page_route_manifest_path=manifest,
        output_dir=tmp_path / "out",
        thresholds=RouteDispatchQualityThresholds(min_dispatch_cards=1, max_unsafe_dispatch_cards=1),
    )
    card = report["route_dispatch_cards"][0]
    assert card["unsafe_dispatch_card"] is True
    assert card["allowed_dispatch_routes"] == []
    assert card["table_processing_allowed"] is False
