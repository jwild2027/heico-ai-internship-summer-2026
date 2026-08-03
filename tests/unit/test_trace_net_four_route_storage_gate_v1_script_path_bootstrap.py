import json
import subprocess
import sys
from pathlib import Path


def test_build_script_runs_from_repo_root(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps(
            {
                "quality_status": "PASS",
                "records": [
                    {
                        "page_id": "p1",
                        "page_number": 1,
                        "final_validated_operational_route": "plain_text",
                        "final_do_not_embed": False,
                        "qdrant_embedding_allowed": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build/ingestion/build_trace_net_four_route_storage_gate_v1.py",
            "--route-unresolved-retry-probe",
            str(source),
            "--output-dir",
            str(output_dir),
            "--quality",
        ],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert (output_dir / "trace_net_four_route_storage_gate_v1.json").exists()
