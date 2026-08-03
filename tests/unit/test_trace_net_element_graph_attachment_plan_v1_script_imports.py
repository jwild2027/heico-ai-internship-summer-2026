import subprocess
import sys
from pathlib import Path


def test_build_script_help_runs():
    script = Path("scripts/build/graph/build_trace_net_element_graph_attachment_plan_v1.py")
    result = subprocess.run([sys.executable, str(script), "--help"], text=True, capture_output=True)
    assert result.returncode == 0
    assert "Element-to-Graph" in result.stdout or "element" in result.stdout.lower()


def test_quality_script_help_runs():
    script = Path("scripts/maintenance/benchmark/check_trace_net_element_graph_attachment_plan_v1_quality.py")
    result = subprocess.run([sys.executable, str(script), "--help"], text=True, capture_output=True)
    assert result.returncode == 0
    assert "quality" in result.stdout.lower()
