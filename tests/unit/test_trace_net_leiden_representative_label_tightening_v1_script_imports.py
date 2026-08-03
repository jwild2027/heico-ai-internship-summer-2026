import subprocess
import sys
from pathlib import Path


def test_module_imports():
    import tiff.trace_net_leiden_representative_label_tightening_v1 as module

    assert module.SCHEMA_VERSION == "trace_net_leiden_representative_label_tightening_v1"


def test_build_script_help_runs():
    result = subprocess.run(
        [sys.executable, "scripts/build/graph/build_trace_net_leiden_representative_label_tightening_v1.py", "--help"],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0
    assert "leiden-category-summary-hydrator" in result.stdout


def test_quality_script_help_runs():
    result = subprocess.run(
        [sys.executable, "scripts/maintenance/graph/check_trace_net_leiden_representative_label_tightening_v1_quality.py", "--help"],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0
    assert "report-path" in result.stdout
