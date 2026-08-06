import json
from pathlib import Path

from tiff.trace_net_table_margin_morphology_parity_v1 import Thresholds, build_report
from tiff.trace_net_table_margin_morphology_parity_v1_quality import check_quality


def write(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_quality_checker_writes_json(tmp_path):
    tlg = tmp_path / "tlg.json"
    exp = tmp_path / "exp.json"
    out = tmp_path / "out"
    write(tlg, {"quality_status": "PASS", "table_geometry_cards": [{"page_id": "p", "table_id": "t", "selected_morphology_scope": "page"}]})
    write(exp, {"quality_status": "PASS", "diagnostic_cards": [{"page_id": "p", "table_id": "t", "margin_expansion_improves_grid_evidence": False}]})
    report = build_report(table_line_geometry_path=tlg, margin_experiment_path=exp, output_dir=out, thresholds=Thresholds(min_parity_cards=1), write_quality=True)
    quality = check_quality(out / "trace_net_table_margin_morphology_parity_v1.json", Thresholds(min_parity_cards=1, require_no_answer_permission=True), write_quality=True)
    assert quality["quality_status"] == "PASS"
    assert (out / "trace_net_table_margin_morphology_parity_v1_quality.json").exists()
