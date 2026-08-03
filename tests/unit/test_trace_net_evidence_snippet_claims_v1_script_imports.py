from __future__ import annotations

import importlib.util
from pathlib import Path


def load_script(path: str):
    spec = importlib.util.spec_from_file_location(Path(path).stem, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_script_imports_main() -> None:
    module = load_script("scripts/build/ingestion/build_trace_net_evidence_snippet_claims_v1.py")
    assert callable(module.main)


def test_quality_script_imports_quality_main() -> None:
    module = load_script("scripts/maintenance/benchmark/check_trace_net_evidence_snippet_claims_v1_quality.py")
    assert callable(module.quality_main)
