from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_table_paddle_style_bbox_resolver_v1 import (
    Thresholds,
    build_table_paddle_style_bbox_resolver_report,
    normalize_bbox,
)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_normalize_bbox_variants() -> None:
    assert normalize_bbox({"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}) == [0.1, 0.2, 0.4, 0.6000000000000001]
    assert normalize_bbox({"left": 1, "top": 2, "right": 5, "bottom": 6}) == [1.0, 2.0, 5.0, 6.0]
    assert normalize_bbox([0.1, 0.2, 0.8, 0.9]) == [0.1, 0.2, 0.8, 0.9]


def test_paddle_style_bbox_resolver_selects_allowed_candidate(tmp_path: Path) -> None:
    contract = tmp_path / "contract.json"
    write_json(contract, {"quality_status": "PASS", "table_allowed_pages": ["p1"]})

    bbox = tmp_path / "bbox.json"
    full = tmp_path / "full.json"
    guard = tmp_path / "guard.json"
    geom = tmp_path / "geom.json"

    write_json(bbox, {
        "quality_status": "PASS",
        "table_bbox_resolver_cards": [
            {"page_id": "p1", "table_id": "t1", "selected_bbox": [0.1, 0.1, 0.8, 0.6], "horizontal_line_count": 4, "vertical_line_count": 3}
        ],
    })
    write_json(full, {"quality_status": "PASS", "table_full_region_recovery_cards": []})
    write_json(guard, {"quality_status": "PASS", "table_crop_completeness_guard_cards": []})
    write_json(geom, {
        "quality_status": "PASS",
        "table_geometry_cards": [
            {"page_id": "p1", "table_id": "t1", "cell_records": [{"bbox": [0.12, 0.12, 0.2, 0.2]}, {"bbox": [0.3, 0.3, 0.7, 0.5]}]}
        ],
    })

    report = build_table_paddle_style_bbox_resolver_report(
        table_bbox_resolver=bbox,
        table_full_region_recovery=full,
        table_crop_completeness_guard=guard,
        table_line_geometry=geom,
        route_dispatch_processor_contract=contract,
        output_dir=tmp_path / "out",
        thresholds=Thresholds(min_resolver_cards=1, min_selected_bbox_cards=1),
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["resolver_card_count"] == 1
    assert report["summary"]["selected_bbox_card_count"] == 1
    card = report["table_paddle_style_bbox_resolver_cards"][0]
    assert card["table_route_dispatch_allowed"] is True
    assert card["selected_bbox"]


def test_paddle_style_bbox_resolver_fails_route_blocked_output(tmp_path: Path) -> None:
    contract = tmp_path / "contract.json"
    write_json(contract, {"quality_status": "PASS", "table_allowed_pages": []})

    bbox = tmp_path / "bbox.json"
    empty = tmp_path / "empty.json"
    write_json(bbox, {"quality_status": "PASS", "table_bbox_resolver_cards": [{"page_id": "p1", "table_id": "t1", "selected_bbox": [0.1, 0.1, 0.8, 0.6]}]})
    write_json(empty, {"quality_status": "PASS", "records": []})

    report = build_table_paddle_style_bbox_resolver_report(
        table_bbox_resolver=bbox,
        table_full_region_recovery=empty,
        table_crop_completeness_guard=empty,
        table_line_geometry=empty,
        route_dispatch_processor_contract=contract,
        output_dir=tmp_path / "out",
        thresholds=Thresholds(min_resolver_cards=1, min_selected_bbox_cards=1),
    )

    assert report["quality_status"] == "FAIL"
    assert report["summary"]["route_blocked_card_count"] == 1
