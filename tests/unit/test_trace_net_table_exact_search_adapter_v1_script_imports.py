from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_build_script_help_runs_from_repo_root():
    result = subprocess.run(
        [sys.executable, "scripts/build/tables/build_trace_net_table_exact_search_adapter_v1.py", "--help"],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "table-route-evidence-packager" in result.stdout


def test_quality_script_help_runs_from_repo_root():
    result = subprocess.run(
        [sys.executable, "scripts/maintenance/s6_retrieval/check_trace_net_table_exact_search_adapter_v1_quality.py", "--help"],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "report-path" in result.stdout
