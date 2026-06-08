from __future__ import annotations

import importlib.util
from pathlib import Path


def load_script(path: str):
    spec = importlib.util.spec_from_file_location("script_under_test", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_run_script_imports():
    module = load_script("scripts/run_trace_net_hybrid_retrieval_sim_v1.py")
    assert hasattr(module, "main")


def test_quality_script_imports():
    module = load_script("scripts/check_trace_net_hybrid_retrieval_sim_v1_quality.py")
    assert hasattr(module, "quality_main")
