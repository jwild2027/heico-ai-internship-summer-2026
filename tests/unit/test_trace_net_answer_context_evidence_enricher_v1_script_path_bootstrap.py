from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import subprocess
import sys
from pathlib import Path


def test_scripts_help_from_repo_root():
    root = Path(__file__).resolve().parents[2]
    for script in [
        "scripts/build/ingestion/build_trace_net_answer_context_evidence_enricher_v1.py",
        "scripts/maintenance/benchmark/check_trace_net_answer_context_evidence_enricher_v1_quality.py",
    ]:
        completed = subprocess.run([sys.executable, script, "--help"], cwd=root, text=True, capture_output=True)
        assert completed.returncode == 0, completed.stderr
