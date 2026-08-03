
import subprocess
import sys
from pathlib import Path


def test_scripts_help_execute_from_repo_root():
    root = Path(__file__).resolve().parents[2]
    scripts = [
        "scripts/build/serving/build_trace_net_engineering_webui_answer_server_v1_3.py",
        "scripts/maintenance/serving/check_trace_net_engineering_webui_answer_server_v1_3_quality.py",
        "scripts/operations/serving/run_trace_net_engineering_webui_answer_server_v1_3.py",
    ]
    for script in scripts:
        completed = subprocess.run([sys.executable, script, "--help"], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert completed.returncode == 0, completed.stderr
