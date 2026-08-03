from __future__ import annotations

import importlib.util
from pathlib import Path


def test_run_script_imports() -> None:
    path = Path("scripts/operations/ingestion/run_trace_net_ask_hybrid_flag_v1.py")
    assert path.exists()
    spec = importlib.util.spec_from_file_location("run_trace_net_ask_hybrid_flag_v1", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "run_main")


def test_quality_script_imports() -> None:
    path = Path("scripts/maintenance/benchmark/check_trace_net_ask_hybrid_flag_v1_quality.py")
    assert path.exists()
    spec = importlib.util.spec_from_file_location("check_trace_net_ask_hybrid_flag_v1_quality", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "quality_main")
