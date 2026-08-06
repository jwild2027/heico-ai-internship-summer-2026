from __future__ import annotations

import importlib.util
from pathlib import Path


def test_relationship_final_gate_hardener_v30_scripts_importable():
    for script in (
        "scripts/benchmark/validation/build_trace_net_e2e_relationship_final_gate_hardener_v30.py",
        "scripts/benchmark/validation/check_trace_net_e2e_relationship_final_gate_hardener_v30_quality.py",
    ):
        path = Path(script)
        assert path.exists(), script
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
