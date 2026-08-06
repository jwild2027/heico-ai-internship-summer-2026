import importlib
import subprocess
import sys
from pathlib import Path


def test_hybrid_retrieval_v3_script_imports():
    assert importlib.import_module("scripts.benchmark.s6_retrieval.build_trace_net_hybrid_retrieval_v3")
    assert importlib.import_module("scripts.benchmark.s6_retrieval.check_trace_net_hybrid_retrieval_v3_quality")


def test_hybrid_retrieval_v3_scripts_run_help_from_repo_root():
    repo_root = Path(__file__).resolve().parents[2]
    scripts = [
        repo_root / "scripts/benchmark/s6_retrieval/build_trace_net_hybrid_retrieval_v3.py",
        repo_root / "scripts/benchmark/s6_retrieval/check_trace_net_hybrid_retrieval_v3_quality.py",
    ]

    for script_path in scripts:
        result = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            cwd=repo_root,
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr
        assert "usage:" in result.stdout.lower()
