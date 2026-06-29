import subprocess
import sys
from pathlib import Path


def test_build_script_help_runs_from_repo_root():
    script = Path("scripts/build_trace_net_route_unresolved_retry_probe_v1.py")
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "route-validator-runner" in result.stdout


def test_check_script_help_runs_from_repo_root():
    script = Path("scripts/check_trace_net_route_unresolved_retry_probe_v1_quality.py")
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "report-path" in result.stdout
