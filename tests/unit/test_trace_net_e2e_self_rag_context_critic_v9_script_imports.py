from __future__ import annotations

import importlib.util
from pathlib import Path


def test_build_script_imports():
    path = Path("scripts/build/validation/build_trace_net_e2e_self_rag_context_critic_v9.py")
    spec = importlib.util.spec_from_file_location("build_trace_net_e2e_self_rag_context_critic_v9", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "main")


def test_quality_script_imports():
    path = Path("scripts/maintenance/validation/check_trace_net_e2e_self_rag_context_critic_v9_quality.py")
    spec = importlib.util.spec_from_file_location("check_trace_net_e2e_self_rag_context_critic_v9_quality", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "main")
