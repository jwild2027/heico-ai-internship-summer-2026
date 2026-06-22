from __future__ import annotations

import ast
from pathlib import Path


def test_scripts_add_repo_root_before_importing_tiff():
    for rel in [
        "scripts/build_trace_net_e2e_hybrid_retrieval_runtime_v1.py",
        "scripts/check_trace_net_e2e_hybrid_retrieval_runtime_v1_quality.py",
    ]:
        text = Path(rel).read_text(encoding="utf-8")
        assert "sys.path.insert(0, str(REPO_ROOT))" in text
        assert "from tiff.trace_net_e2e_hybrid_retrieval_runtime_v1" in text


def test_script_modules_parse():
    for rel in [
        "scripts/build_trace_net_e2e_hybrid_retrieval_runtime_v1.py",
        "scripts/check_trace_net_e2e_hybrid_retrieval_runtime_v1_quality.py",
    ]:
        ast.parse(Path(rel).read_text(encoding="utf-8"))
