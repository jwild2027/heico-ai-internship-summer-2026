import subprocess
import sys
from pathlib import Path


def test_build_script_help_imports():
    result = subprocess.run(
        [sys.executable, "scripts/build_trace_net_llm_graph_path_compliance_judge_v1.py", "--help"],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode == 0
    assert "--page-retrieval-large-eval-v2" in result.stdout


def test_check_script_help_imports():
    result = subprocess.run(
        [sys.executable, "scripts/check_trace_net_llm_graph_path_compliance_judge_v1_quality.py", "--help"],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode == 0
    assert "--report-path" in result.stdout
