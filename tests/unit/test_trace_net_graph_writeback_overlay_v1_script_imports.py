from __future__ import annotations

import importlib.util
from pathlib import Path


def test_build_script_imports() -> None:
    path = Path("scripts/build/graph/build_trace_net_graph_writeback_overlay_v1.py")
    spec = importlib.util.spec_from_file_location("build_trace_net_graph_writeback_overlay_v1", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "main")


def test_quality_script_imports() -> None:
    path = Path("scripts/maintenance/s3_graph_store/check_trace_net_graph_writeback_overlay_v1_quality.py")
    spec = importlib.util.spec_from_file_location("check_trace_net_graph_writeback_overlay_v1_quality", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "quality_main")
