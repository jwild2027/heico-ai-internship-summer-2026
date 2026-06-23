from __future__ import annotations

import importlib.util
from pathlib import Path


def test_build_script_importable() -> None:
    path = Path("scripts/build_trace_net_e2e_rag_demo_report_v1.py")
    spec = importlib.util.spec_from_file_location("build_trace_net_e2e_rag_demo_report_v1", path)
    assert spec is not None


def test_check_script_importable() -> None:
    path = Path("scripts/check_trace_net_e2e_rag_demo_report_v1_quality.py")
    spec = importlib.util.spec_from_file_location("check_trace_net_e2e_rag_demo_report_v1_quality", path)
    assert spec is not None
