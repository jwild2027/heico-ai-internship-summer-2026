from __future__ import annotations

import ast
from pathlib import Path


def test_build_script_imports_main() -> None:
    path = Path("scripts/build/ingestion/build_trace_net_figure_chart_understanding_v1.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert any(node.module == "tiff.trace_net_figure_chart_understanding_v1" for node in imports)


def test_quality_script_imports_quality_main() -> None:
    path = Path("scripts/maintenance/benchmark/check_trace_net_figure_chart_understanding_v1_quality.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert any(node.module == "tiff.trace_net_figure_chart_understanding_v1" for node in imports)
