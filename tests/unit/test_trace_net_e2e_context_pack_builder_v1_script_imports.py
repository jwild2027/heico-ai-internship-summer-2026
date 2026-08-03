from __future__ import annotations

import ast
from pathlib import Path


def test_build_script_imports_module_with_repo_root_patch():
    path = Path("scripts/build/context/build_trace_net_e2e_context_pack_builder_v1.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert any(node.module == "tiff.trace_net_e2e_context_pack_builder_v1" for node in imports)
    text = path.read_text(encoding="utf-8")
    assert "sys.path.insert" in text


def test_quality_script_imports_module_with_repo_root_patch():
    path = Path("scripts/maintenance/benchmark/check_trace_net_e2e_context_pack_builder_v1_quality.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert any(node.module == "tiff.trace_net_e2e_context_pack_builder_v1" for node in imports)
    text = path.read_text(encoding="utf-8")
    assert "sys.path.insert" in text
