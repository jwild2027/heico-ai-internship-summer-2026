from __future__ import annotations

import ast
from pathlib import Path


def test_build_script_imports_main() -> None:
    path = Path("scripts/build_trace_net_table_cell_normalizer_v1.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert any(n.module == "tiff.trace_net_table_cell_normalizer_v1" for n in imports)


def test_quality_script_imports_quality_main() -> None:
    path = Path("scripts/check_trace_net_table_cell_normalizer_v1_quality.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert any(n.module == "tiff.trace_net_table_cell_normalizer_v1" for n in imports)
