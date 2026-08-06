from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_page_route_manifest_v1 import build_page_route_manifest_report
from tiff.trace_net_page_route_manifest_v1_quality import PageRouteManifestQualityThresholds


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_page_route_manifest_joins_source_pages_and_artifact_evidence(tmp_path: Path) -> None:
    artifact_detector = tmp_path / "artifact_detector.json"
    _write_json(artifact_detector, {
        "schema_version": "trace_net_artifact_detector_v1",
        "quality_status": "PASS",
        "summary": {"artifact_card_count": 3, "page_artifact_card_count": 3, "source_page_card_count": 4},
        "source_page_cards": [
            {"source_page_id": "metadata_page_000001", "page_number": 1, "image_filename": "00000001.tif", "page_aliases": ["p000001"]},
            {"source_page_id": "metadata_page_000002", "page_number": 2, "image_filename": "00000002.tif", "page_aliases": ["p000002"]},
            {"source_page_id": "metadata_page_000003", "page_number": 3, "image_filename": "00000003.tif", "page_aliases": ["p000003"]},
            {"source_page_id": "metadata_page_000004", "page_number": 4, "image_filename": "00000004.tif", "page_aliases": ["p000004"]},
        ],
        "page_artifact_cards": [
            {
                "page_id": "t_p_doc_p000001",
                "page_artifact_detection_status": "PAGE_ARTIFACT_EVIDENCE_FOUND",
                "artifact_count": 3,
                "safe_artifact_count": 3,
                "unsafe_artifact_count": 0,
                "artifact_keys": ["table_line_geometry", "table_full_region_recovery", "table_bbox_resolver"],
                "evidence_category_counts": {"table": 3, "ocr_text": 1},
                "table_evidence_artifact_count": 3,
                "image_visual_evidence_artifact_count": 0,
                "ocr_text_evidence_artifact_count": 1,
            },
            {
                "page_id": "t_p_doc_p000002",
                "page_artifact_detection_status": "PAGE_ARTIFACT_EVIDENCE_FOUND",
                "artifact_count": 2,
                "safe_artifact_count": 2,
                "unsafe_artifact_count": 0,
                "artifact_keys": ["visual_diagram", "callout_visual_part_verifier"],
                "evidence_category_counts": {"image_visual": 2},
                "table_evidence_artifact_count": 0,
                "image_visual_evidence_artifact_count": 2,
                "ocr_text_evidence_artifact_count": 0,
            },
            {
                "page_id": "t_p_doc_p000003",
                "page_artifact_detection_status": "PAGE_ARTIFACT_EVIDENCE_FOUND",
                "artifact_count": 1,
                "safe_artifact_count": 1,
                "unsafe_artifact_count": 0,
                "artifact_keys": ["source_ingest"],
                "evidence_category_counts": {"ocr_text": 1},
                "table_evidence_artifact_count": 0,
                "image_visual_evidence_artifact_count": 0,
                "ocr_text_evidence_artifact_count": 1,
            },
        ],
    })

    report = build_page_route_manifest_report(
        artifact_detector=artifact_detector,
        output_dir=tmp_path / "out",
        thresholds=PageRouteManifestQualityThresholds(
            min_page_route_cards=4,
            min_source_page_route_cards=4,
            min_table_route_cards=1,
            require_artifact_detector_quality_pass=True,
            require_no_answer_permission=True,
        ),
    )

    assert report["quality_status"] == "PASS"
    cards = {card["source_page_id"]: card for card in report["page_route_cards"]}
    assert cards["metadata_page_000001"]["primary_route"] == "table"
    assert cards["metadata_page_000002"]["primary_route"] == "image_visual"
    assert cards["metadata_page_000003"]["primary_route"] == "normal_text"
    assert cards["metadata_page_000004"]["primary_route"] == "blank_candidate"
    assert report["summary"]["table_primary_route_count"] == 1
    assert report["summary"]["unsafe_route_card_count"] == 0


def test_artifact_detector_quality_required_can_fail(tmp_path: Path) -> None:
    artifact_detector = tmp_path / "artifact_detector.json"
    _write_json(artifact_detector, {
        "schema_version": "trace_net_artifact_detector_v1",
        "quality_status": "FAIL",
        "summary": {},
        "source_page_cards": [{"source_page_id": "metadata_page_000001", "page_number": 1}],
        "page_artifact_cards": [],
    })
    report = build_page_route_manifest_report(
        artifact_detector=artifact_detector,
        output_dir=tmp_path / "out",
        thresholds=PageRouteManifestQualityThresholds(
            min_page_route_cards=1,
            require_artifact_detector_quality_pass=True,
        ),
    )
    assert report["quality_status"] == "FAIL"
    assert "artifact_detector_quality_pass" in report["summary"]["quality_fail_reasons"]


def test_page_route_manifest_integrates_ink_route_evidence(tmp_path: Path) -> None:
    artifact_detector = tmp_path / "artifact_detector.json"
    _write_json(artifact_detector, {
        "schema_version": "trace_net_artifact_detector_v1",
        "quality_status": "PASS",
        "summary": {"artifact_card_count": 1, "page_artifact_card_count": 1, "source_page_card_count": 2},
        "source_page_cards": [
            {"source_page_id": "metadata_page_000001", "page_number": 1, "image_filename": "00000001.tif"},
            {"source_page_id": "metadata_page_000002", "page_number": 2, "image_filename": "00000002.tif"},
        ],
        "page_artifact_cards": [
            {
                "page_id": "t_p_doc_p000001",
                "page_artifact_detection_status": "PAGE_ARTIFACT_EVIDENCE_FOUND",
                "artifact_count": 1,
                "safe_artifact_count": 1,
                "unsafe_artifact_count": 0,
                "artifact_keys": ["table_line_geometry"],
                "evidence_category_counts": {"table": 1},
                "table_evidence_artifact_count": 1,
                "image_visual_evidence_artifact_count": 0,
                "ocr_text_evidence_artifact_count": 0,
            },
        ],
    })
    ink = tmp_path / "ink.json"
    _write_json(ink, {
        "schema_version": "trace_net_page_ink_route_evidence_v1",
        "quality_status": "PASS",
        "summary": {"ink_evidence_card_count": 2, "quality_status": "PASS"},
        "ink_evidence_cards": [
            {
                "page_id": "t_p_doc_p000001",
                "source_page_id": "metadata_page_000001",
                "page_number": 1,
                "ink_route_evidence_status": "INK_ROUTE_EVIDENCE_BUILT",
                "ink_primary_route": "table",
                "table_grid_likelihood": 0.95,
                "diagram_likelihood": 0.10,
                "text_likelihood": 0.50,
                "blank_likelihood": 0.0,
                "horizontal_line_count": 10,
                "vertical_line_count": 8,
                "intersection_count": 160,
            },
            {
                "page_id": "metadata_page_000002",
                "source_page_id": "metadata_page_000002",
                "page_number": 2,
                "ink_route_evidence_status": "INK_ROUTE_EVIDENCE_BUILT",
                "ink_primary_route": "blank_candidate",
                "table_grid_likelihood": 0.0,
                "diagram_likelihood": 0.0,
                "text_likelihood": 0.05,
                "blank_likelihood": 0.95,
                "horizontal_line_count": 0,
                "vertical_line_count": 0,
                "intersection_count": 0,
            },
        ],
    })

    report = build_page_route_manifest_report(
        artifact_detector=artifact_detector,
        page_ink_route_evidence=ink,
        output_dir=tmp_path / "out",
        thresholds=PageRouteManifestQualityThresholds(
            min_page_route_cards=2,
            min_source_page_route_cards=2,
            min_table_route_cards=1,
            min_page_ink_route_evidence_cards=2,
            require_artifact_detector_quality_pass=True,
            require_page_ink_route_evidence_quality_pass=True,
        ),
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["page_ink_route_evidence_quality_status"] == "PASS"
    assert report["summary"]["page_ink_route_evidence_available_card_count"] == 2
    cards = {card["source_page_id"]: card for card in report["page_route_cards"]}
    assert cards["metadata_page_000001"]["primary_route"] == "table"
    assert cards["metadata_page_000001"]["page_ink_route_evidence_available"] is True
    assert cards["metadata_page_000001"]["ink_primary_route"] == "table"
    assert "ink_table_grid_supports_table_route" in cards["metadata_page_000001"]["routing_reasons"]
    assert cards["metadata_page_000002"]["primary_route"] == "blank_candidate"
