from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_script(path: str):
    script_path = REPO_ROOT / path
    spec = importlib.util.spec_from_file_location(script_path.stem, script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_script_imports_main() -> None:
    module = load_script("scripts/build_trace_net_evidence_snippet_cleaner_v1.py")
    assert callable(module.main)


def test_quality_script_imports_quality_main() -> None:
    module = load_script("scripts/check_trace_net_evidence_snippet_cleaner_v1_quality.py")
    assert callable(module.quality_main)
