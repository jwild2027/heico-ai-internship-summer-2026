from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path


def test_script_modules_import() -> None:
    build_mod = importlib.import_module("scripts.build_trace_net_opensearch_loader_smoke_v1")
    check_mod = importlib.import_module("scripts.check_trace_net_opensearch_loader_smoke_v1_quality")

    assert hasattr(build_mod, "main")
    assert hasattr(check_mod, "main")


def test_build_script_runs_help_when_called_directly() -> None:
    """Regression: direct script execution must find the repo-local tiff package."""
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "build_trace_net_opensearch_loader_smoke_v1.py"

    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--opensearch-adapter" in result.stdout
