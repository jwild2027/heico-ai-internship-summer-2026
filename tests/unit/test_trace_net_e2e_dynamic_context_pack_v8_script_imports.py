from __future__ import annotations

import importlib.util
from pathlib import Path


def test_build_script_imports():
    path = Path("scripts/build/context/build_trace_net_e2e_dynamic_context_pack_v8.py")
    spec = importlib.util.spec_from_file_location("build_trace_net_e2e_dynamic_context_pack_v8", path)
    assert spec and spec.loader


def test_check_script_imports():
    path = Path("scripts/maintenance/s6_retrieval/check_trace_net_e2e_dynamic_context_pack_v8_quality.py")
    spec = importlib.util.spec_from_file_location("check_trace_net_e2e_dynamic_context_pack_v8_quality", path)
    assert spec and spec.loader
