
import subprocess, sys
from pathlib import Path

def test_scripts_help_execute_from_repo_root():
    root = Path(__file__).resolve().parents[2]
    scripts = ['scripts/build_trace_net_engineering_webui_answer_server_v1.py','scripts/check_trace_net_engineering_webui_answer_server_v1_quality.py','scripts/run_trace_net_engineering_webui_answer_server_v1.py']
    for script in scripts:
        completed = subprocess.run([sys.executable, script, '--help'], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert completed.returncode == 0, completed.stderr
    help_run = subprocess.run([sys.executable, 'scripts/run_trace_net_engineering_webui_answer_server_v1.py', '--help'], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert '--disable-empty-response-retry' in help_run.stdout
