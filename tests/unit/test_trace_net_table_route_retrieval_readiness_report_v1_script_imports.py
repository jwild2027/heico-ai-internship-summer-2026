from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_build_script_imports() -> None:
    path = ROOT / "scripts" / "build_trace_net_table_route_retrieval_readiness_report_v1.py"
    spec = importlib.util.spec_from_file_location("build_table_route_readiness_report", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "main")


def test_check_script_imports() -> None:
    path = ROOT / "scripts" / "check_trace_net_table_route_retrieval_readiness_report_v1_quality.py"
    spec = importlib.util.spec_from_file_location("check_table_route_readiness_report", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "main")
