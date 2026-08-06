from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_build_script_help_runs_when_invoked_as_path() -> None:
    repo = _repo_root()
    result = subprocess.run(
        [sys.executable, "scripts/build/ocr/build_trace_net_fishnet_route_manifest_overlay_v1.py", "--help"],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode == 0, result.stderr
    assert "--policy" in result.stdout
    assert "--current-route-manifest" in result.stdout


def test_quality_script_help_runs_when_invoked_as_path() -> None:
    repo = _repo_root()
    result = subprocess.run(
        [sys.executable, "scripts/maintenance/s2_ocr/check_trace_net_fishnet_route_manifest_overlay_v1_quality.py", "--help"],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode == 0, result.stderr
    assert "--report-path" in result.stdout
    assert "--write-json" in result.stdout
