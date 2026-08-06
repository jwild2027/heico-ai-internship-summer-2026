from pathlib import Path


def test_script_bootstrap_mentions_repo_root():
    for rel in [
        "scripts/benchmark/validation/run_trace_net_raw_to_answer_e2e_smoke_v1.py",
        "scripts/benchmark/validation/check_trace_net_raw_to_answer_e2e_smoke_v1_quality.py",
    ]:
        text = Path(rel).read_text(encoding="utf-8")
        assert "ROOT" in text
        assert "sys.path.insert" in text
