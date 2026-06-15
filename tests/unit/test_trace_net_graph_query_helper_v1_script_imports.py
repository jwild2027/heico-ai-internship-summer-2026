from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_build_script_help_runs_directly() -> None:
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(repo / "scripts" / "build_trace_net_graph_query_helper_v1.py"), "--help"],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Graph Query Helper" in result.stdout


def test_quality_script_help_runs_directly() -> None:
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(repo / "scripts" / "check_trace_net_graph_query_helper_v1_quality.py"), "--help"],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Graph Query Helper" in result.stdout
