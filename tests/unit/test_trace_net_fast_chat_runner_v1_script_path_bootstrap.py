import subprocess
import sys
from pathlib import Path


def test_run_script_help_bootstraps_repo_root():
    script = Path("scripts/run_trace_net_fast_chat_runner_v1.py")
    assert script.exists()
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "--question" in result.stdout


def test_check_script_help_bootstraps_repo_root():
    script = Path("scripts/check_trace_net_fast_chat_runner_v1_quality.py")
    assert script.exists()
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "--report-path" in result.stdout
