import subprocess
import sys
from pathlib import Path


def test_runtime_scripts_help_from_repo_root():
    repo_root = Path(__file__).resolve().parents[2]
    for script in [
        "scripts/build_trace_net_runtime_hybrid_v3_v22.py",
        "scripts/check_trace_net_runtime_hybrid_v3_v22_quality.py",
        "scripts/run_trace_net_runtime_hybrid_v3_v22.py",
    ]:
        result = subprocess.run(
            [sys.executable, script, "--help"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=20,
        )
        assert result.returncode == 0, result.stderr
        assert "usage:" in result.stdout.lower()
