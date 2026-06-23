from __future__ import annotations

import importlib.util
from pathlib import Path


def test_build_script_imports():
    path = Path("scripts/build_trace_net_e2e_reasoned_response_draft_v12.py")
    spec = importlib.util.spec_from_file_location("build_trace_net_e2e_reasoned_response_draft_v12", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)


def test_check_script_imports():
    path = Path("scripts/check_trace_net_e2e_reasoned_response_draft_v12_quality.py")
    spec = importlib.util.spec_from_file_location("check_trace_net_e2e_reasoned_response_draft_v12_quality", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
