from __future__ import annotations

import importlib.util
from pathlib import Path


def test_v23_scripts_importable():
    for script in (
        "scripts/benchmark/ingestion/build_trace_net_e2e_live_llm_final_gate_v23.py",
        "scripts/benchmark/check_trace_net_e2e_live_llm_final_gate_v23_quality.py",
    ):
        path = Path(script)
        assert path.exists(), script
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
