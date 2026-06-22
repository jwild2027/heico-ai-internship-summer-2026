from __future__ import annotations

import importlib.util
from pathlib import Path


def test_v10_build_and_check_scripts_importable():
    for script in [
        Path("scripts/build_trace_net_e2e_crag_retrieval_corrector_v10.py"),
        Path("scripts/check_trace_net_e2e_crag_retrieval_corrector_v10_quality.py"),
    ]:
        assert script.exists(), script
        spec = importlib.util.spec_from_file_location(script.stem, script)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        assert hasattr(module, "main")
