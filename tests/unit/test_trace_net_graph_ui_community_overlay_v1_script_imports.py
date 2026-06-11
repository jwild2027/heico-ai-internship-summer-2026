from __future__ import annotations

import importlib.util
from pathlib import Path


def test_scripts_importable() -> None:
    for rel in [
        "scripts/build_trace_net_graph_ui_community_overlay_v1.py",
        "scripts/check_trace_net_graph_ui_community_overlay_v1_quality.py",
    ]:
        path = Path(rel)
        assert path.exists()
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec is not None
        assert spec.loader is not None
