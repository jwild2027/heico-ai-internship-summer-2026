from __future__ import annotations

import json
import zipfile
from pathlib import Path

from tiff.trace_net_e2e_corrected_visual_context_builder_v35_4 import build_corrected_visual_context, quality_checks


class Args:
    min_source_pages = 3
    min_route_decisions = 3
    min_visual_context_input_pages = 2
    min_visual_context_cards = 2
    min_visual_prompt_contexts = 2
    min_guidance_only_visual_contexts = 2
    max_fishnet_visual_review_pages_processed = 0
    max_overbroad_old_route_pages_processed = 0
    max_missing_source_page_records = 0
    max_visual_proof_authority_violations = 0
    max_post_gate_issue_count = 0
    max_answer_permission_count = 0
    max_source_truth_mutation_allowed = 0
    require_no_answer_permission = True


def _make_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("00000001.tif", b"fake1")
        zf.writestr("00000002.tif", b"fake2")
        zf.writestr("00000003.tif", b"fake3")


def _write_decisions(path: Path) -> None:
    rows = [
        {
            "schema_version": "trace_net_calibrated_cascade_route_brain_v35_3_decision",
            "page_id": "t_p_120_1176_p000001",
            "page_number": 1,
            "filename": "00000001.tif",
            "manual_label": "diagram",
            "manual_diagram_page": True,
            "primary_route": "image_visual",
            "dispatch_routes": ["image_visual"],
            "visual_context_eligible": True,
            "fishnet_visual_review_candidate": True,
            "fishnet_action": "accept_route",
            "route_scores": {"image_visual": 0.9, "normal_text": 0.2, "table": 0.1, "blank_candidate": 0.0},
            "feature_summary": {"edge_density": 0.2, "line_structure_score": 0.8, "text_score": 0.2, "connected_component_count": 80},
        },
        {
            "schema_version": "trace_net_calibrated_cascade_route_brain_v35_3_decision",
            "page_id": "t_p_120_1176_p000002",
            "page_number": 2,
            "filename": "00000002.tif",
            "manual_label": "non_diagram",
            "manual_diagram_page": False,
            "primary_route": "normal_text",
            "secondary_routes": ["image_visual"],
            "dispatch_routes": ["normal_text", "review"],
            "visual_context_eligible": False,
            "fishnet_visual_review_candidate": True,
            "fishnet_action": "dual_route_text_and_visual",
            "route_scores": {"image_visual": 0.55, "normal_text": 0.65, "table": 0.1, "blank_candidate": 0.0},
            "feature_summary": {"edge_density": 0.15, "line_structure_score": 0.6, "text_score": 0.9},
        },
        {
            "schema_version": "trace_net_calibrated_cascade_route_brain_v35_3_decision",
            "page_id": "t_p_120_1176_p000003",
            "page_number": 3,
            "filename": "00000003.tif",
            "manual_label": "non_diagram",
            "manual_diagram_page": False,
            "primary_route": "image_visual",
            "dispatch_routes": ["image_visual", "review"],
            "visual_context_eligible": True,
            "fishnet_visual_review_candidate": True,
            "fishnet_action": "review_required",
            "route_scores": {"image_visual": 0.6, "normal_text": 0.55, "table": 0.4, "blank_candidate": 0.0},
            "feature_summary": {"edge_density": 0.12, "line_structure_score": 0.55, "text_score": 0.86, "table_grid_score": 0.4},
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_build_corrected_visual_context_from_cascade_decisions(tmp_path: Path) -> None:
    zip_path = tmp_path / "metadata.zip"
    decisions = tmp_path / "decisions.jsonl"
    out = tmp_path / "out"
    _make_zip(zip_path)
    _write_decisions(decisions)

    report = build_corrected_visual_context(
        page_bundle_zip=zip_path,
        cascade_route_decisions=decisions,
        output_dir=out,
        page_id_prefix="t_p_120_1176",
    )

    assert report["source_page_count"] == 3
    assert report["route_decision_count"] == 3
    assert report["visual_context_input_page_count"] == 2
    assert report["visual_context_card_count"] == 2
    assert report["fishnet_visual_review_candidate_count"] == 1
    assert report["fishnet_visual_review_pages_processed_count"] == 0
    assert report["overbroad_old_route_pages_processed_count"] == 0
    assert Path(report["cards_jsonl_path"]).exists()
    assert Path(report["visual_prompt_context_jsonl_path"]).exists()


def test_quality_checks_pass(tmp_path: Path) -> None:
    zip_path = tmp_path / "metadata.zip"
    decisions = tmp_path / "decisions.jsonl"
    out = tmp_path / "out"
    _make_zip(zip_path)
    _write_decisions(decisions)
    report = build_corrected_visual_context(page_bundle_zip=zip_path, cascade_route_decisions=decisions, output_dir=out, page_id_prefix="t_p_120_1176")
    checks = quality_checks(report, Args())
    assert all(c["passed"] for c in checks), checks
