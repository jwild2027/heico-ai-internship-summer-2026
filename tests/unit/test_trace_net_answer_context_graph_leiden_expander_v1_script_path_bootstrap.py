import subprocess
import sys
from pathlib import Path


def test_build_script_help_from_repo_root():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "build_trace_net_answer_context_graph_leiden_expander_v1.py"), "--help"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0
    assert "--evidence-enricher" in result.stdout
