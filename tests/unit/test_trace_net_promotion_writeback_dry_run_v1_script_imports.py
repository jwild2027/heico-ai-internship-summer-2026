from __future__ import annotations

import importlib.util
from pathlib import Path


def load_script(path: str):
    spec = importlib.util.spec_from_file_location(Path(path).stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_script_imports() -> None:
    module = load_script("scripts/build_trace_net_promotion_writeback_dry_run_v1.py")
    assert hasattr(module, "main")


def test_check_script_imports() -> None:
    module = load_script("scripts/check_trace_net_promotion_writeback_dry_run_v1_quality.py")
    assert hasattr(module, "main")
