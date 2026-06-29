import json
import subprocess
import sys
from pathlib import Path


def test_build_script_runs_from_repo_root(tmp_path):
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({
        "quality_status": "PASS",
        "records": [{"page_id": "p1", "page_number": 1, "suggested_canonical_route": "blank_candidate", "auto_seeded_gold_route_label": "blank_candidate"}],
    }), encoding="utf-8")
    out = tmp_path / "out"
    proc = subprocess.run([
        sys.executable,
        "scripts/build_trace_net_gold_label_decision_merge_v1.py",
        "--auto-review-seed", str(seed),
        "--output-dir", str(out),
        "--quality",
    ], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    assert (out / "trace_net_gold_label_decision_merge_v1.json").exists()
