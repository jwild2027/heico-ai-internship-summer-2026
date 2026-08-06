from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_build_script_help_runs() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build/ingestion/build_trace_net_fast_answer_composer_v1.py", "--help"],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "--context-pack" in result.stdout


def test_check_script_help_runs() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/maintenance/writing/check_trace_net_fast_answer_composer_v1_quality.py", "--help"],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "--report-path" in result.stdout
