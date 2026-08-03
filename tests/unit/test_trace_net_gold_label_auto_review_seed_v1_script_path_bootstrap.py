from pathlib import Path


def test_scripts_bootstrap_repo_root():
    for script in [
        Path("scripts/build/ingestion/build_trace_net_gold_label_auto_review_seed_v1.py"),
        Path("scripts/maintenance/benchmark/check_trace_net_gold_label_auto_review_seed_v1_quality.py"),
    ]:
        text = script.read_text(encoding="utf-8")
        assert "parents[1]" in text
        assert "sys.path.insert" in text
