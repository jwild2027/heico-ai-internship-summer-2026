from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_build_script_imports_from_repo_root() -> None:
    script = Path("scripts/build/ocr/build_trace_net_fishnet_retry_refinement_v1.py")
    assert script.exists()
    result = subprocess.run([sys.executable, str(script), "--help"], text=True, capture_output=True)
    assert result.returncode == 0
    assert "fishnet retry refinement" in result.stdout.lower()


def test_quality_script_imports_from_repo_root() -> None:
    script = Path("scripts/maintenance/benchmark/check_trace_net_fishnet_retry_refinement_v1_quality.py")
    assert script.exists()
    result = subprocess.run([sys.executable, str(script), "--help"], text=True, capture_output=True)
    assert result.returncode == 0
    assert "fishnet retry refinement" in result.stdout.lower()
