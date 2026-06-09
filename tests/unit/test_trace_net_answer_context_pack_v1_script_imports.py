from __future__ import annotations

import py_compile
from pathlib import Path


def test_build_script_compiles() -> None:
    py_compile.compile(str(Path("scripts/build_trace_net_answer_context_pack_v1.py")), doraise=True)


def test_quality_script_compiles() -> None:
    py_compile.compile(str(Path("scripts/check_trace_net_answer_context_pack_v1_quality.py")), doraise=True)
