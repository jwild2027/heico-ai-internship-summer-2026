import subprocess
import sys
from pathlib import Path


def test_module_imports():
    import tiff.trace_net_leiden_category_summary_hydrator_v1 as module

    assert module.SCHEMA_VERSION == "trace_net_leiden_category_summary_hydrator_v1"


def test_build_script_help_runs():
    script = Path("scripts/build/graph/build_trace_net_leiden_category_summary_hydrator_v1.py")
    if not script.exists():
        script = Path(__file__).resolve().parents[5] / "scripts/build/graph/build_trace_net_leiden_category_summary_hydrator_v1.py"
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "leiden-communities" in result.stdout


def test_check_script_help_runs():
    script = Path("scripts/maintenance/s3_graph_store/check_trace_net_leiden_category_summary_hydrator_v1_quality.py")
    if not script.exists():
        script = Path(__file__).resolve().parents[5] / "scripts/maintenance/s3_graph_store/check_trace_net_leiden_category_summary_hydrator_v1_quality.py"
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "report-path" in result.stdout
