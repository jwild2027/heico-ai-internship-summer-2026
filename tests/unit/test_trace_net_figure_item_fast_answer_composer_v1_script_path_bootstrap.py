from pathlib import Path


def test_scripts_exist():
    assert Path("scripts/build_trace_net_figure_item_fast_answer_composer_v1.py").exists()
    assert Path("scripts/check_trace_net_figure_item_fast_answer_composer_v1_quality.py").exists()
