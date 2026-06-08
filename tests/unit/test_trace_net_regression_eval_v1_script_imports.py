from __future__ import annotations

import runpy
from pathlib import Path


def test_run_script_imports_without_pythonpath() -> None:
    path = Path("scripts/run_trace_net_regression_eval_v1.py")
    namespace = runpy.run_path(str(path))
    assert "main" in namespace


def test_quality_script_imports_without_pythonpath() -> None:
    path = Path("scripts/check_trace_net_regression_eval_v1_quality.py")
    namespace = runpy.run_path(str(path))
    assert "quality_main" in namespace
