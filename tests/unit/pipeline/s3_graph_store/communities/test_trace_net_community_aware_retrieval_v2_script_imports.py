from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_module_imports() -> None:
    import tiff.trace_net_community_aware_retrieval_v2 as module

    assert module.SCHEMA_VERSION == "trace_net_community_aware_retrieval_v2"


def test_build_script_help_runs() -> None:
    root = Path(__file__).resolve().parents[5]
    result = subprocess.run(
        [sys.executable, str(root / "scripts/benchmark/s3_graph_store/build_trace_net_community_aware_retrieval_v2.py"), "--help"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Community-Aware Retrieval v2" in result.stdout


def test_quality_script_help_runs() -> None:
    root = Path(__file__).resolve().parents[5]
    result = subprocess.run(
        [sys.executable, str(root / "scripts/benchmark/s3_graph_store/check_trace_net_community_aware_retrieval_v2_quality.py"), "--help"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Community-Aware Retrieval v2" in result.stdout
