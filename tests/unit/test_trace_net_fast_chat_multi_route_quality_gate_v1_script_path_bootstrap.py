from pathlib import Path


def test_scripts_have_path_bootstrap():
    for path in [
        Path("scripts/benchmark/validation/build_trace_net_fast_chat_multi_route_quality_gate_v1.py"),
        Path("scripts/benchmark/validation/check_trace_net_fast_chat_multi_route_quality_gate_v1_quality.py"),
    ]:
        text = path.read_text(encoding="utf-8")
        assert "sys.path.insert" in text
        assert "REPO_ROOT" in text
