from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_build_script_imports_without_pythonpath() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build/writing/build_trace_net_citation_answer_draft_v1.py", "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "TRACE-Net Citation/Authority Answer" in result.stdout


def test_quality_script_imports_without_pythonpath() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/maintenance/writing/check_trace_net_citation_answer_draft_v1_quality.py", "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "TRACE-Net Citation/Authority Answer" in result.stdout
