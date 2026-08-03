from pathlib import Path


def test_scripts_bootstrap_repo_root():
    for script in [
        Path("scripts/benchmark/build_trace_net_part_number_exact_retrieval_probe_v1.py"),
        Path("scripts/benchmark/check_trace_net_part_number_exact_retrieval_probe_v1_quality.py"),
    ]:
        text = script.read_text(encoding="utf-8")
        assert "ROOT = Path(__file__).resolve().parents[1]" in text
        assert "sys.path.insert" in text
