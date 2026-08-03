from __future__ import annotations

import importlib.util
from pathlib import Path


def test_scripts_import_module() -> None:
    root = Path(__file__).resolve().parents[2]
    for rel in [
        "scripts/build/ingestion/build_trace_net_incremental_state_commit_gate_v1.py",
        "scripts/maintenance/benchmark/check_trace_net_incremental_state_commit_gate_v1_quality.py",
    ]:
        spec = importlib.util.spec_from_file_location("script_under_test", root / rel)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert hasattr(module, "main")
