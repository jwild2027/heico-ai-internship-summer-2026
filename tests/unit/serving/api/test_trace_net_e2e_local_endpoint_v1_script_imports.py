from __future__ import annotations

import importlib.util
from pathlib import Path


def test_module_imports():
    import tiff.trace_net_e2e_local_endpoint_v1 as module

    assert module.DEFAULT_MODEL_ID == "trace-net-e2e-local-endpoint-v1"


def test_scripts_import_without_running():
    for rel in [
        "scripts/build/serving/build_trace_net_e2e_local_endpoint_v1.py",
        "scripts/maintenance/benchmark/check_trace_net_e2e_local_endpoint_v1_quality.py",
        "scripts/operations/serving/serve_trace_net_e2e_local_endpoint_v1.py",
    ]:
        path = Path(rel)
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
