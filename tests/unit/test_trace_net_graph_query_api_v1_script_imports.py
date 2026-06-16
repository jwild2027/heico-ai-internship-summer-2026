from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_module_imports() -> None:
    import tiff.trace_net_graph_query_api_v1 as module

    assert module.SCHEMA_VERSION == "trace_net_graph_query_api_v1"


def test_run_script_help_executes() -> None:
    script = Path("scripts/run_trace_net_graph_query_api_v1.py")
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "Graph Query API" in result.stdout


def test_check_script_help_executes() -> None:
    script = Path("scripts/check_trace_net_graph_query_api_v1_quality.py")
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "Graph Query API" in result.stdout
