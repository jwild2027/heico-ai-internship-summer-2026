from __future__ import annotations

from pathlib import Path


def test_build_script_imports() -> None:
    path = Path("scripts/build/serving/build_trace_net_it_operations_console_v1.py")
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "from tiff.trace_net_it_operations_console_v1 import main" in text


def test_check_script_imports() -> None:
    path = Path("scripts/maintenance/serving/check_trace_net_it_operations_console_v1_quality.py")
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "check_it_operations_console_quality" in text
