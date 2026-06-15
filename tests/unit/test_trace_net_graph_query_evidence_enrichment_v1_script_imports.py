from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_module_imports():
    import tiff.trace_net_graph_query_evidence_enrichment_v1 as module

    assert module.SCHEMA_VERSION == "trace_net_graph_query_evidence_enrichment_v1"


def test_build_script_help_runs():
    script = Path("scripts/build_trace_net_graph_query_evidence_enrichment_v1.py")
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "graph-query-helper" in result.stdout


def test_quality_script_help_runs():
    script = Path("scripts/check_trace_net_graph_query_evidence_enrichment_v1_quality.py")
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "report-path" in result.stdout
