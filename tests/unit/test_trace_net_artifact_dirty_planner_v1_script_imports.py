import subprocess
import sys


def test_build_script_help_runs_directly():
    result = subprocess.run(
        [sys.executable, "scripts/build/ingestion/build_trace_net_artifact_dirty_planner_v1.py", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "artifact-registry" in result.stdout


def test_quality_script_help_runs_directly():
    result = subprocess.run(
        [sys.executable, "scripts/maintenance/benchmark/check_trace_net_artifact_dirty_planner_v1_quality.py", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "report-path" in result.stdout
