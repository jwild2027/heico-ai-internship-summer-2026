from __future__ import annotations

import importlib.util
from pathlib import Path


def test_build_script_imports() -> None:
    script = Path("scripts/build/ingestion/build_trace_net_page_element_registry_v1.py")
    assert script.exists()
    spec = importlib.util.spec_from_file_location("build_trace_net_page_element_registry_v1", script)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "main")


def test_quality_script_imports() -> None:
    script = Path("scripts/maintenance/ingestion/check_trace_net_page_element_registry_v1_quality.py")
    assert script.exists()
    spec = importlib.util.spec_from_file_location("check_trace_net_page_element_registry_v1_quality", script)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "quality_main")
