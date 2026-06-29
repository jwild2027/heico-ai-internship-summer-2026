from pathlib import Path


def test_scripts_have_path_bootstrap():
    for path in [
        Path("scripts/build_trace_net_answer_quality_gate_v1.py"),
        Path("scripts/check_trace_net_answer_quality_gate_v1_quality.py"),
    ]:
        text = path.read_text(encoding="utf-8")
        assert "sys.path.insert" in text
        assert "Path(__file__).resolve().parents[1]" in text
