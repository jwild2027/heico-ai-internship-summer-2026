import subprocess
import sys
from pathlib import Path


def test_build_script_help_runs():
    script = Path("scripts/benchmark/build_trace_net_page_retrieval_large_eval_v1.py")
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "metadata-zip" in result.stdout


def test_check_script_help_runs():
    script = Path("scripts/benchmark/check_trace_net_page_retrieval_large_eval_v1_quality.py")
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "report-path" in result.stdout
