from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_scripts_help_from_repo_root():
    repo = Path(__file__).resolve().parents[2]
    scripts = [
        "scripts/build/serving/build_trace_net_ask_api_final_return_policy_hybrid_v3_v22.py",
        "scripts/maintenance/benchmark/check_trace_net_ask_api_final_return_policy_hybrid_v3_v22_quality.py",
        "scripts/operations/serving/run_trace_net_ask_api_final_return_policy_hybrid_v3_v22.py",
    ]
    for script in scripts:
        result = subprocess.run(
            [sys.executable, script, "--help"],
            cwd=repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
