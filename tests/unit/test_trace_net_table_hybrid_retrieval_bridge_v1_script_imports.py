from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_build_script_help_imports_from_repo_root():
    script = Path("scripts/benchmark/build_trace_net_table_hybrid_retrieval_bridge_v1.py")
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "table-exact-search-adapter" in result.stdout


def test_quality_script_help_imports_from_repo_root():
    script = Path("scripts/benchmark/check_trace_net_table_hybrid_retrieval_bridge_v1_quality.py")
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "report-path" in result.stdout
