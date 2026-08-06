from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_script_imports() -> None:
    module = _load_script(Path("scripts/build/ocr/build_trace_net_fishnet_ocr_grid_v1.py"))
    assert hasattr(module, "main_build")


def test_quality_script_imports() -> None:
    module = _load_script(Path("scripts/maintenance/s2_ocr/check_trace_net_fishnet_ocr_grid_v1_quality.py"))
    assert hasattr(module, "main_check")
