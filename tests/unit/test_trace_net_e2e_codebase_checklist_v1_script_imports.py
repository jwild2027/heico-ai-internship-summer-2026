from __future__ import annotations

import importlib.util
from pathlib import Path


def test_script_imports() -> None:
    path = Path("scripts/operations/validation/run_trace_net_e2e_codebase_checklist_v1.py")
    spec = importlib.util.spec_from_file_location("run_trace_net_e2e_codebase_checklist_v1", path)
    assert spec is not None
