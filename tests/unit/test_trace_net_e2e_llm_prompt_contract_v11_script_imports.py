from __future__ import annotations

import importlib.util
from pathlib import Path


def test_build_and_check_scripts_importable():
    root = Path(__file__).resolve().parents[2]
    for rel in [
        "scripts/build/core/build_trace_net_e2e_llm_prompt_contract_v11.py",
        "scripts/maintenance/benchmark/check_trace_net_e2e_llm_prompt_contract_v11_quality.py",
    ]:
        path = root / rel
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert hasattr(module, "main")
