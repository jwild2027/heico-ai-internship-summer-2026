from __future__ import annotations

import importlib.util
from pathlib import Path


def test_scripts_import_without_running() -> None:
    script_paths = [
        Path("scripts/record_trace_net_human_review_decision_v1.py"),
        Path("scripts/build_trace_net_human_review_decisions_v1.py"),
        Path("scripts/check_trace_net_human_review_decisions_v1_quality.py"),
    ]
    for script_path in script_paths:
        spec = importlib.util.spec_from_file_location(script_path.stem, script_path)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
