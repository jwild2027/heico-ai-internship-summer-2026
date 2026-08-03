import subprocess
import sys
from pathlib import Path


def test_build_script_imports() -> None:
    script = Path("scripts/build/graph/build_trace_net_leiden_graph_communities_v1.py")
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "Leiden graph communities" in result.stdout or "TRACE-Net" in result.stdout


def test_quality_script_imports() -> None:
    script = Path("scripts/maintenance/graph/check_trace_net_leiden_graph_communities_v1_quality.py")
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "quality" in result.stdout.lower()
