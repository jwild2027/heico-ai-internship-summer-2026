from __future__ import annotations

import subprocess
import sys


def test_lineage_guard_scripts_help() -> None:
    for script in (
        "scripts/build_trace_net_opensearch_adapter_lineage_rebuild_v1.py",
        "scripts/check_trace_net_opensearch_adapter_lineage_guard_v1_quality.py",
    ):
        result = subprocess.run([sys.executable, script, "--help"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert result.returncode == 0, result.stderr
        assert "OpenSearch" in result.stdout or "opensearch" in result.stdout
