import subprocess
import sys
from pathlib import Path


def test_scripts_have_help_from_repo_root():
    root = Path(__file__).resolve().parents[2]
    for script in [
        "scripts/build/graph/build_trace_net_anchor_aware_graph_leiden_expander_v1.py",
        "scripts/maintenance/graph/check_trace_net_anchor_aware_graph_leiden_expander_v1_quality.py",
    ]:
        proc = subprocess.run([sys.executable, script, "--help"], cwd=root, capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, proc.stderr
        assert "usage:" in proc.stdout.lower()
