from __future__ import annotations

import importlib.util
from pathlib import Path


def test_llm_assisted_query_planner_v17_scripts_importable():
    for script in (
        "scripts/build/ingestion/build_trace_net_e2e_llm_assisted_query_planner_v17.py",
        "scripts/maintenance/validation/check_trace_net_e2e_llm_assisted_query_planner_v17_quality.py",
    ):
        path = Path(script)
        assert path.exists(), script
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
