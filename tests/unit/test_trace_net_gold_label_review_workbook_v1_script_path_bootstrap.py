from pathlib import Path


def test_scripts_bootstrap_repo_root():
    build_script = Path("scripts/build/ingestion/build_trace_net_gold_label_review_workbook_v1.py").read_text(encoding="utf-8")
    check_script = Path("scripts/maintenance/validation/check_trace_net_gold_label_review_workbook_v1_quality.py").read_text(encoding="utf-8")
    assert "sys.path.insert" in build_script
    assert "sys.path.insert" in check_script
    assert "parents[1]" in build_script
    assert "parents[1]" in check_script
