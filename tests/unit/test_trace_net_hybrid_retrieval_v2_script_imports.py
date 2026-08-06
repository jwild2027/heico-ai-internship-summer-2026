from __future__ import annotations

import importlib.util
from pathlib import Path


def test_scripts_import_without_running():
    for script in [
        "scripts/benchmark/s6_retrieval/build_trace_net_hybrid_retrieval_v2.py",
        "scripts/benchmark/s6_retrieval/check_trace_net_hybrid_retrieval_v2_quality.py",
    ]:
        path = Path(script)
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec is not None
