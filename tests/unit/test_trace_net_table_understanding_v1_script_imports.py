from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_build_script_help() -> None:
    script = Path("scripts/build_trace_net_table_understanding_v1.py")
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "TRACE-Net table understanding" in result.stdout or "table understanding" in result.stdout


def test_quality_script_help() -> None:
    script = Path("scripts/check_trace_net_table_understanding_v1_quality.py")
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "quality" in result.stdout.lower()
