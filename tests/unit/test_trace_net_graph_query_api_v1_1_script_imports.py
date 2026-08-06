import subprocess
import sys


def test_run_script_help_imports():
    result = subprocess.run(
        [sys.executable, "scripts/operations/serving/run_trace_net_graph_query_api_v1_1.py", "--help"],
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0
    assert "Graph Query API v1.1" in result.stdout


def test_quality_script_help_imports():
    result = subprocess.run(
        [sys.executable, "scripts/maintenance/serving/check_trace_net_graph_query_api_v1_1_quality.py", "--help"],
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0
    assert "Graph Query API v1.1" in result.stdout
