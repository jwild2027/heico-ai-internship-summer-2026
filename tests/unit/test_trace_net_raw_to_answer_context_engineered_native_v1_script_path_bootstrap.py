from pathlib import Path


def test_scripts_bootstrap_repo_root():
    build_text = Path("scripts/run_trace_net_raw_to_answer_context_engineered_native_v1.py").read_text(encoding="utf-8")
    check_text = Path("scripts/check_trace_net_raw_to_answer_context_engineered_native_v1_quality.py").read_text(encoding="utf-8")
    assert "sys.path.insert" in build_text
    assert "sys.path.insert" in check_text
    assert "parents[1]" in build_text
    assert "parents[1]" in check_text
