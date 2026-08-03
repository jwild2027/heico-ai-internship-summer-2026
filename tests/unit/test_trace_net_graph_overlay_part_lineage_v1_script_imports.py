from __future__ import annotations

import importlib.util
from pathlib import Path


def test_scripts_import_without_repo_pythonpath() -> None:
    for rel in [
        "scripts/build/graph/build_trace_net_graph_overlay_part_lineage_v1.py",
        "scripts/maintenance/benchmark/check_trace_net_graph_overlay_part_lineage_v1_quality.py",
    ]:
        path = Path(rel)
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec is not None
