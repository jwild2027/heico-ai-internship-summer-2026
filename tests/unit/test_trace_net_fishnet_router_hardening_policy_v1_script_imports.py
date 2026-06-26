from __future__ import annotations

import importlib.util
from pathlib import Path


def test_build_script_imports() -> None:
    path = Path("scripts/build_trace_net_fishnet_router_hardening_policy_v1.py")
    spec = importlib.util.spec_from_file_location("build_trace_net_fishnet_router_hardening_policy_v1", path)
    assert spec is not None
    assert spec.loader is not None


def test_check_script_imports() -> None:
    path = Path("scripts/check_trace_net_fishnet_router_hardening_policy_v1_quality.py")
    spec = importlib.util.spec_from_file_location("check_trace_net_fishnet_router_hardening_policy_v1_quality", path)
    assert spec is not None
    assert spec.loader is not None


def test_module_imports() -> None:
    mod = __import__("tiff.trace_net_fishnet_router_hardening_policy_v1", fromlist=["MODULE_VERSION"])
    assert mod.MODULE_VERSION == "trace_net_fishnet_router_hardening_policy_v1"
