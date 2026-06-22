from __future__ import annotations

import importlib.util
from pathlib import Path


def test_build_and_check_scripts_importable():
    for script in [
        "scripts/build_trace_net_e2e_final_answer_gate_v13.py",
        "scripts/check_trace_net_e2e_final_answer_gate_v13_quality.py",
    ]:
        path = Path(script)
        assert path.exists()
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert hasattr(module, "main")
