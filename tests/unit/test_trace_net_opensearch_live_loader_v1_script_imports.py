from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_script_imports() -> None:
    root = Path(__file__).resolve().parents[2]
    scripts = [
        root / "scripts/build/retrieval/build_trace_net_opensearch_live_loader_v1.py",
        root / "scripts/maintenance/benchmark/check_trace_net_opensearch_live_loader_v1_quality.py",
        root / "scripts/operations/retrieval/run_trace_net_opensearch_live_loader_v1.py",
    ]
    for script in scripts:
        result = subprocess.run([sys.executable, str(script), "--help"], cwd=root, text=True, capture_output=True)
        assert result.returncode == 0, result.stderr
        assert "OpenSearch" in result.stdout or "quality" in result.stdout
