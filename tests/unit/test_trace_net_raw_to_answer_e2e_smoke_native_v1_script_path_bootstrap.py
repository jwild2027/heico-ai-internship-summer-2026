from pathlib import Path


def test_script_path_bootstrap_present():
    root = Path(__file__).resolve().parents[2]
    for rel in [
        "scripts/run_trace_net_raw_to_answer_e2e_smoke_native_v1.py",
        "scripts/check_trace_net_raw_to_answer_e2e_smoke_native_v1_quality.py",
    ]:
        text = (root / rel).read_text(encoding="utf-8")
        assert "sys.path.insert" in text
        assert "parents[1]" in text
