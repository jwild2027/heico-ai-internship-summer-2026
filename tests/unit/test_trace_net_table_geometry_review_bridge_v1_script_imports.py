import subprocess
import sys
from pathlib import Path


def test_build_script_help_runs_from_repo_root():
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "scripts/build/tables/build_trace_net_table_geometry_review_bridge_v1.py", "--help"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "table-line-geometry" in result.stdout


def test_check_script_help_runs_from_repo_root():
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "scripts/maintenance/benchmark/check_trace_net_table_geometry_review_bridge_v1_quality.py", "--help"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "report-path" in result.stdout
