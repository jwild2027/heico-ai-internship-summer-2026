from __future__ import annotations

import importlib.util
from pathlib import Path


def test_build_script_imports() -> None:
    script = Path("scripts/build/visual/build_trace_net_table_visual_bbox_localizer_v1.py")
    spec = importlib.util.spec_from_file_location("build_trace_net_table_visual_bbox_localizer_v1", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "main")


def test_quality_script_imports() -> None:
    script = Path("scripts/maintenance/benchmark/check_trace_net_table_visual_bbox_localizer_v1_quality.py")
    spec = importlib.util.spec_from_file_location("check_trace_net_table_visual_bbox_localizer_v1_quality", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "main")
