import subprocess
import sys
from pathlib import Path


def run_help(script: str) -> None:
    result = subprocess.run([sys.executable, script, "--help"], cwd=Path(__file__).resolve().parents[2], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()


def test_init_script_imports() -> None:
    run_help("scripts/operations/feedback/init_trace_net_feedback_memory_v1.py")


def test_record_script_imports() -> None:
    run_help("scripts/maintenance/feedback/record_trace_net_feedback_v1.py")


def test_build_script_imports() -> None:
    run_help("scripts/build/feedback/build_trace_net_feedback_memory_v1.py")


def test_quality_script_imports() -> None:
    run_help("scripts/maintenance/feedback/check_trace_net_feedback_memory_v1_quality.py")
