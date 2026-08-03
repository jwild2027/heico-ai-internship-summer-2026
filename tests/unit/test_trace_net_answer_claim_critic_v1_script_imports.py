from __future__ import annotations

import importlib.util
from pathlib import Path


def test_build_script_imports() -> None:
    path = Path("scripts/build/validation/build_trace_net_answer_claim_critic_v1.py")
    spec = importlib.util.spec_from_file_location("build_trace_net_answer_claim_critic_v1", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)


def test_check_script_imports() -> None:
    path = Path("scripts/maintenance/benchmark/check_trace_net_answer_claim_critic_v1_quality.py")
    spec = importlib.util.spec_from_file_location("check_trace_net_answer_claim_critic_v1_quality", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
