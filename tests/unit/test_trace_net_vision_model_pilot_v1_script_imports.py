from __future__ import annotations

import importlib.util
from pathlib import Path


def load_script(path: str):
    spec = importlib.util.spec_from_file_location("script_under_test", Path(path))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_script_imports() -> None:
    module = load_script("scripts/build/visual/build_trace_net_vision_model_pilot_v1.py")
    assert hasattr(module, "main")


def test_quality_script_imports() -> None:
    module = load_script("scripts/maintenance/benchmark/check_trace_net_vision_model_pilot_v1_quality.py")
    assert hasattr(module, "quality_main")
