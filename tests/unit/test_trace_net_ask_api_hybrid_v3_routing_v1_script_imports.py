import subprocess
import sys
from pathlib import Path


def test_scripts_import_and_help_from_repo_root():
    repo_root = Path(__file__).resolve().parents[2]
    scripts = [
        "scripts/build/router/build_trace_net_ask_api_hybrid_v3_routing_v1.py",
        "scripts/maintenance/serving/check_trace_net_ask_api_hybrid_v3_routing_v1_quality.py",
        "scripts/operations/serving/run_trace_net_ask_api_hybrid_v3_routing_v1.py",
    ]
    for script in scripts:
        result = subprocess.run(
            [sys.executable, script, "--help"],
            cwd=repo_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )
        assert result.returncode == 0, result.stderr
        assert "usage:" in result.stdout.lower()
