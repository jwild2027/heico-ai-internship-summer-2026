from __future__ import annotations

import importlib.util
from pathlib import Path


def test_script_imports() -> None:
    scripts = [
        Path("scripts/build/graph/build_trace_net_category_aware_leiden_overlay_v1.py"),
        Path("scripts/maintenance/graph/check_trace_net_category_aware_leiden_overlay_v1_quality.py"),
    ]
    for script in scripts:
        spec = importlib.util.spec_from_file_location(script.stem, script)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
