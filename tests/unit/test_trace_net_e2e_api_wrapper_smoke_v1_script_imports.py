from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_build_script_imports():
    path = Path("scripts/benchmark/build_trace_net_e2e_api_wrapper_smoke_v1.py")
    spec = importlib.util.spec_from_file_location("build_trace_net_e2e_api_wrapper_smoke_v1", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "main")


def test_check_script_imports():
    path = Path("scripts/benchmark/check_trace_net_e2e_api_wrapper_smoke_v1_quality.py")
    spec = importlib.util.spec_from_file_location("check_trace_net_e2e_api_wrapper_smoke_v1_quality", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "main")
