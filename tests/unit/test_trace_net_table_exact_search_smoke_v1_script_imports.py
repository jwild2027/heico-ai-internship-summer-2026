from __future__ import annotations

import ast
from pathlib import Path


def test_build_script_injects_repo_root_before_tiff_import():
    path = Path("scripts/build_trace_net_table_exact_search_smoke_v1.py")
    text = path.read_text(encoding="utf-8")
    assert "REPO_ROOT = Path(__file__).resolve().parents[1]" in text
    assert "sys.path.insert(0, str(REPO_ROOT))" in text
    assert "from tiff.trace_net_table_exact_search_smoke_v1 import main" in text
    ast.parse(text)


def test_quality_script_injects_repo_root_before_tiff_import():
    path = Path("scripts/check_trace_net_table_exact_search_smoke_v1_quality.py")
    text = path.read_text(encoding="utf-8")
    assert "REPO_ROOT = Path(__file__).resolve().parents[1]" in text
    assert "sys.path.insert(0, str(REPO_ROOT))" in text
    assert "from tiff.trace_net_table_exact_search_smoke_v1 import quality_main" in text
    ast.parse(text)
