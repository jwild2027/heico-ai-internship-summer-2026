import subprocess
import sys
from pathlib import Path


def test_build_script_help_runs():
    result = subprocess.run([sys.executable, "scripts/build/ingestion/build_trace_net_answer_context_exact_row_proof_v1.py", "--help"], cwd=Path.cwd(), capture_output=True, text=True)
    assert result.returncode == 0
    assert "exact row proof" in result.stdout.lower()


def test_check_script_help_runs():
    result = subprocess.run([sys.executable, "scripts/maintenance/benchmark/check_trace_net_answer_context_exact_row_proof_v1_quality.py", "--help"], cwd=Path.cwd(), capture_output=True, text=True)
    assert result.returncode == 0
    assert "quality" in result.stdout.lower()
