from __future__ import annotations

import py_compile
from pathlib import Path


def test_scripts_compile() -> None:
    for script in [
        Path("scripts/benchmark/build_trace_net_table_route_retrieval_demo_query_pack_v1.py"),
        Path("scripts/benchmark/check_trace_net_table_route_retrieval_demo_query_pack_v1_quality.py"),
    ]:
        py_compile.compile(str(script), doraise=True)


def test_module_compile() -> None:
    py_compile.compile("tiff/trace_net_table_route_retrieval_demo_query_pack_v1.py", doraise=True)
