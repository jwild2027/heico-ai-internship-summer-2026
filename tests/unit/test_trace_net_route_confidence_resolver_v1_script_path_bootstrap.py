import subprocess
import sys
import json
from pathlib import Path


def test_build_script_runs_from_repo_root(tmp_path):
    scan = tmp_path / "scan.json"
    scan.write_text(json.dumps({"quality_status": "PASS", "records": [
        {"page_id": "p", "canonical_page_number": 1, "accepted_route": "blank_candidate", "ocr_sample_text": "", "ocr_text_word_count": 0, "part_number_tokens": []}
    ]}), encoding="utf-8")
    out = tmp_path / "out"
    result = subprocess.run([
        sys.executable,
        "scripts/build_trace_net_route_confidence_resolver_v1.py",
        "--scan-pack", str(scan),
        "--output-dir", str(out),
        "--quality",
    ], capture_output=True, text=True, check=True)
    assert "TRACE_NET_ROUTE_CONFIDENCE_RESOLVER_BUILT" in result.stdout
