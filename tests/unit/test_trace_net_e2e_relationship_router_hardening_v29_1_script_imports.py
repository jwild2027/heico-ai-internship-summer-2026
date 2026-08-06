from __future__ import annotations

import importlib.util
from pathlib import Path


def test_relationship_router_hardening_v29_1_scripts_importable():
    for script in (
        "scripts/build/graph/build_trace_net_e2e_relationship_router_hardening_v29_1.py",
        "scripts/maintenance/s6_retrieval/check_trace_net_e2e_relationship_router_hardening_v29_1_quality.py",
        "scripts/operations/s6_retrieval/serve_trace_net_e2e_relationship_router_hardening_v29_1.py",
    ):
        path = Path(script)
        assert path.exists(), script
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
