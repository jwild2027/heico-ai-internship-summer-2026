from __future__ import annotations

import importlib.util
from pathlib import Path


def test_build_script_imports():
    path = Path("scripts/build_trace_net_retrieval_critic_v1.py")
    spec = importlib.util.spec_from_file_location("build_trace_net_retrieval_critic_v1", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "main")


def test_check_script_imports():
    path = Path("scripts/check_trace_net_retrieval_critic_v1_quality.py")
    spec = importlib.util.spec_from_file_location("check_trace_net_retrieval_critic_v1_quality", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "main")
