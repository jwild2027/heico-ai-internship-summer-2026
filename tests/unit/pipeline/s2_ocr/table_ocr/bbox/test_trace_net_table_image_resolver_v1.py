from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_table_image_resolver_v1 import (
    build_report,
    collect_path_hints,
    extract_page_token,
    score_image_path,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_extract_page_token_from_trace_net_page_id() -> None:
    token, number = extract_page_token("t_p_120_1176_p000003")
    assert token == "p000003"
    assert number == 3


def test_score_image_path_prefers_page_identifier() -> None:
    good = score_image_path("local_data/pages/t_p_120_1176_p000003.tif", "t_p_120_1176_p000003")
    weak = score_image_path("local_data/pages/random.tif", "t_p_120_1176_p000003")
    assert good > weak
    assert good >= 100


def test_collect_path_hints_finds_nested_image_fields() -> None:
    payload = {"tables": [{"rows": [{"cells": [{"page_image_path": "images/page_000003.png"}]}]}]}
    assert collect_path_hints(payload) == ["images/page_000003.png"]


def test_build_report_resolves_scanned_page_image(tmp_path: Path) -> None:
    image_root = tmp_path / "images"
    image_root.mkdir()
    (image_root / "page_000003.png").write_bytes(b"fake image bytes")

    table_line_geometry = tmp_path / "tlg.json"
    write_json(
        table_line_geometry,
        {
            "quality_status": "PASS",
            "table_geometry_cards": [
                {
                    "geometry_card_id": "geom1",
                    "page_id": "t_p_120_1176_p000003",
                    "table_id": "table1",
                    "table_type": "parts_list_table",
                    "cell_record_count": 10,
                    "row_record_count": 4,
                    "domain_validation": {"part_number_count": 2},
                    "geometry_confidence": 0.7,
                }
            ],
        },
    )

    report = build_report(
        table_line_geometry_path=table_line_geometry,
        output_dir=tmp_path / "out",
        image_root=image_root,
        thresholds={
            "min_source_cards": 1,
            "min_resolver_cards": 1,
            "min_resolved_image_cards": 1,
            "max_unsafe_resolution_cards": 0,
            "max_answer_permission_count": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_table_line_geometry_quality_pass": True,
            "require_no_answer_permission": True,
        },
    )

    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["resolved_image_card_count"] == 1
    card = report["table_image_resolution_cards"][0]
    assert card["image_resolution_status"] == "RESOLVED"
    assert card["resolved_image_path"].endswith("page_000003.png")
    assert card["can_answer_directly"] is False
    assert card["source_truth_mutation_allowed"] is False


def test_build_report_uses_explicit_nested_context_path(tmp_path: Path) -> None:
    image_root = tmp_path
    (tmp_path / "nested").mkdir()
    image = tmp_path / "nested" / "scan_p000004.tiff"
    image.write_bytes(b"fake")

    table_line_geometry = tmp_path / "tlg.json"
    normalizer = tmp_path / "normalizer.json"
    write_json(
        table_line_geometry,
        {
            "quality_status": "PASS",
            "table_geometry_cards": [
                {
                    "geometry_card_id": "geom2",
                    "page_id": "t_p_120_1176_p000004",
                    "table_id": "table2",
                    "cell_record_count": 1,
                    "row_record_count": 1,
                }
            ],
        },
    )
    write_json(
        normalizer,
        {
            "quality_status": "PASS",
            "tables": [
                {
                    "table_id": "table2",
                    "page_id": "t_p_120_1176_p000004",
                    "rows": [{"cells": [{"source_image_path": "nested/scan_p000004.tiff"}]}],
                }
            ],
        },
    )
    report = build_report(
        table_line_geometry_path=table_line_geometry,
        table_cell_normalizer_path=normalizer,
        output_dir=tmp_path / "out",
        image_root=image_root,
        thresholds={"min_source_cards": 1, "min_resolver_cards": 1, "min_resolved_image_cards": 1},
    )
    assert report["quality_status"] == "PASS"
    card = report["table_image_resolution_cards"][0]
    assert card["resolved_image_path"].endswith("nested/scan_p000004.tiff")
    assert card["candidate_image_count"] >= 1


def test_unresolved_images_can_pass_when_resolution_not_required(tmp_path: Path) -> None:
    table_line_geometry = tmp_path / "tlg.json"
    write_json(
        table_line_geometry,
        {
            "quality_status": "PASS",
            "table_geometry_cards": [{"geometry_card_id": "geom3", "page_id": "t_p_120_1176_p000005", "table_id": "table3"}],
        },
    )
    report = build_report(
        table_line_geometry_path=table_line_geometry,
        output_dir=tmp_path / "out",
        image_root=tmp_path / "missing",
        thresholds={"min_source_cards": 1, "min_resolver_cards": 1, "min_resolved_image_cards": 0},
    )
    assert report["quality_status"] == "PASS"
    card = report["table_image_resolution_cards"][0]
    assert card["image_resolution_status"] == "UNRESOLVED"
    assert "image_root_missing" in card["review_flags"]
