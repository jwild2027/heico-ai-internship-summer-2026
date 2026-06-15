from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_build_script_help_runs():
    script = Path("scripts/build_trace_net_page_retrieval_large_eval_v2.py")
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "Page Retrieval Large Eval v2" in result.stdout
    assert "--use-query-embedding-cache" in result.stdout


def test_quality_script_help_runs():
    script = Path("scripts/check_trace_net_page_retrieval_large_eval_v2_quality.py")
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "Page Retrieval Large Eval v2" in result.stdout
