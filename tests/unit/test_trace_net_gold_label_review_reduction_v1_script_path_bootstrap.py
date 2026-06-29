from pathlib import Path


def test_scripts_have_path_bootstrap():
    build = Path("scripts/build_trace_net_gold_label_review_reduction_v1.py").read_text(encoding="utf-8")
    check = Path("scripts/check_trace_net_gold_label_review_reduction_v1_quality.py").read_text(encoding="utf-8")
    assert "sys.path.insert" in build
    assert "sys.path.insert" in check
