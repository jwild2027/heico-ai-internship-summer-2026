from __future__ import annotations

import importlib.util
from pathlib import Path


def test_build_script_imports() -> None:
    path = Path("scripts/build/ocr/build_trace_net_fishnet_retry_engine_v1.py")
    if not path.exists():
        path = Path(__file__).resolve().parents[2] / "scripts/build/ocr/build_trace_net_fishnet_retry_engine_v1.py"
    spec = importlib.util.spec_from_file_location("build_trace_net_fishnet_retry_engine_v1", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "main")


def test_quality_script_imports() -> None:
    path = Path("scripts/maintenance/s2_ocr/check_trace_net_fishnet_retry_engine_v1_quality.py")
    if not path.exists():
        path = Path(__file__).resolve().parents[2] / "scripts/maintenance/s2_ocr/check_trace_net_fishnet_retry_engine_v1_quality.py"
    spec = importlib.util.spec_from_file_location("check_trace_net_fishnet_retry_engine_v1_quality", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "quality_main")
