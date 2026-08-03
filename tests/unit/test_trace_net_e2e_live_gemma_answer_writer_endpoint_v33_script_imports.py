from __future__ import annotations

import importlib.util
from pathlib import Path


def test_v33_scripts_importable():
    for script in (
        "scripts/build/writing/build_trace_net_e2e_live_gemma_answer_writer_endpoint_v33.py",
        "scripts/maintenance/writing/check_trace_net_e2e_live_gemma_answer_writer_endpoint_v33_quality.py",
        "scripts/operations/writing/serve_trace_net_e2e_live_gemma_answer_writer_endpoint_v33.py",
    ):
        path = Path(script)
        assert path.exists(), script
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
