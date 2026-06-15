from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_build_script_help_runs():
    result = subprocess.run(
        [sys.executable, "scripts/build_trace_net_ai_trace_pack_v1.py", "--help"],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "AI Trace Pack" in result.stdout or "trace" in result.stdout.lower()


def test_quality_script_help_runs():
    result = subprocess.run(
        [sys.executable, "scripts/check_trace_net_ai_trace_pack_v1_quality.py", "--help"],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "quality" in result.stdout.lower()
