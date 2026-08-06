import json
from pathlib import Path

from tiff.trace_net_table_margin_morphology_parity_v1 import build_report, Thresholds


def write(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_parity_detects_experiment_improved_but_production_kept_page(tmp_path):
    tlg = tmp_path / "tlg.json"
    exp = tmp_path / "exp.json"
    out = tmp_path / "out"
    write(tlg, {
        "quality_status": "PASS",
        "table_geometry_cards": [{
            "page_id": "p1",
            "table_id": "t1",
            "table_type": "parts_list_table",
            "selected_morphology_scope": "page",
            "margin_expansion_selected_for_crop_morphology": False,
            "margin_expansion_candidate_count": 2,
            "table_region_crop_comparison": {
                "margin_expansion_candidates": [
                    {"margin_pixels": 0, "horizontal_line_count": 1, "vertical_line_count": 0, "intersection_count": 0, "morphology_signal_strength": "WEAK_LINE_SIGNAL", "morphology_quality_score": 1.0},
                    {"margin_pixels": 50, "horizontal_line_count": 2, "vertical_line_count": 1, "intersection_count": 0, "morphology_signal_strength": "PARTIAL_GRID", "morphology_quality_score": 6.0},
                ]
            },
        }],
    })
    write(exp, {
        "quality_status": "PASS",
        "diagnostic_cards": [{
            "page_id": "p1",
            "table_id": "t1",
            "margin_expansion_improves_grid_evidence": True,
            "best_margin_candidate": {"margin_pixels": 50, "horizontal_line_count": 8, "vertical_line_count": 20, "intersection_count": 100, "morphology_signal_strength": "GRID", "morphology_quality_score": 1000.0},
        }],
    })
    report = build_report(
        table_line_geometry_path=tlg,
        margin_experiment_path=exp,
        output_dir=out,
        thresholds=Thresholds(min_parity_cards=1, min_experiment_improvement_cards=1, min_parity_gap_cards=1, require_table_line_geometry_quality_pass=True, require_margin_experiment_quality_pass=True, require_no_answer_permission=True),
        write_quality=True,
    )
    assert report["quality_status"] == "PASS"
    card = report["parity_cards"][0]
    assert card["margin_morphology_parity_gap"] is True
    assert "experiment_improved_but_production_did_not_select_margin" in card["parity_findings"]
    assert card["vertical_line_delta_experiment_minus_production"] == 19


def test_parity_passes_without_required_gap(tmp_path):
    tlg = tmp_path / "tlg.json"
    exp = tmp_path / "exp.json"
    out = tmp_path / "out"
    write(tlg, {"quality_status": "PASS", "table_geometry_cards": [{"page_id": "p1", "table_id": "t1", "selected_morphology_scope": "table_region_crop", "margin_expansion_selected_for_crop_morphology": True}]})
    write(exp, {"quality_status": "PASS", "diagnostic_cards": [{"page_id": "p1", "table_id": "t1", "margin_expansion_improves_grid_evidence": True, "best_margin_candidate": {"morphology_signal_strength": "GRID", "vertical_line_count": 2, "intersection_count": 5}}]})
    report = build_report(table_line_geometry_path=tlg, margin_experiment_path=exp, output_dir=out, thresholds=Thresholds(min_parity_cards=1), write_quality=False)
    assert report["summary"]["parity_card_count"] == 1
    assert report["summary"]["experiment_improvement_card_count"] == 1
    assert report["summary"]["production_margin_selected_card_count"] == 1
