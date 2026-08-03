from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_build_script_help_runs() -> None:
    script = Path("scripts/build/tables/build_trace_net_table_image_resolver_v1.py")
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "table-line-geometry" in result.stdout


def test_quality_script_help_runs() -> None:
    script = Path("scripts/maintenance/benchmark/check_trace_net_table_image_resolver_v1_quality.py")
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "report-path" in result.stdout
