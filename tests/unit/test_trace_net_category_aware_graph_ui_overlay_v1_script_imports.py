from __future__ import annotations

import importlib.util
from pathlib import Path


def test_scripts_importable() -> None:
    for rel in [
        "scripts/build/graph/build_trace_net_category_aware_graph_ui_overlay_v1.py",
        "scripts/maintenance/serving/check_trace_net_category_aware_graph_ui_overlay_v1_quality.py",
    ]:
        path = Path(rel)
        assert path.exists()
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
