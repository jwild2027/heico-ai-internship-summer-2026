from __future__ import annotations

import importlib.util
from pathlib import Path


def test_v34_scripts_import_without_running() -> None:
    root = Path(__file__).resolve().parents[2]
    for rel in [
        "scripts/build/visual/build_trace_net_e2e_image_visual_observer_route_v34.py",
        "scripts/maintenance/serving/check_trace_net_e2e_image_visual_observer_route_v34_quality.py",
        "scripts/operations/serving/serve_trace_net_e2e_image_visual_observer_route_v34.py",
    ]:
        path = root / rel
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "main")
