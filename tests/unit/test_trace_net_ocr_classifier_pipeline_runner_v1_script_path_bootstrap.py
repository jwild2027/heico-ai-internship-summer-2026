from __future__ import annotations

from pathlib import Path


def test_scripts_bootstrap_repo_root():
    for script in [
        Path("scripts/operations/ocr/run_trace_net_ocr_classifier_pipeline_v1.py"),
        Path("scripts/maintenance/benchmark/check_trace_net_ocr_classifier_pipeline_v1_quality.py"),
    ]:
        text = script.read_text(encoding="utf-8")
        assert "ROOT = Path(__file__).resolve().parents[1]" in text
        assert "sys.path.insert(0, str(ROOT))" in text
