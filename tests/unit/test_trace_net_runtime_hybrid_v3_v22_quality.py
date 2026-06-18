import json
from pathlib import Path

from tiff.trace_net_runtime_hybrid_v3_v22 import check_main


def test_check_main_writes_quality_json(tmp_path, capsys):
    report_path = tmp_path / "trace_net_runtime_hybrid_v3_v22.json"
    report_path.write_text(json.dumps({
        "schema_version": "trace_net_runtime_hybrid_v3_v22",
        "quality_status": "PASS",
        "summary": {
            "read_only_runtime": True,
            "hybrid_v3_quality_status": "PASS",
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "corrective_action_as_proof_count": 0,
        },
        "checks": {"hybrid_v3_report_present": True, "hybrid_v3_report_quality_pass": True},
        "open_webui": {"base_url": "http://host.docker.internal:8016/v1", "model": "trace-net-final-return-policy-hybrid-v3-v2.2"},
    }), encoding="utf-8")

    rc = check_main(["--report-path", str(report_path), "--require-hybrid-v3-quality-pass", "--write-json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert '"quality_status": "PASS"' in captured.out
    quality_path = report_path.with_name("trace_net_runtime_hybrid_v3_v22_quality.json")
    assert quality_path.exists()
    assert json.loads(quality_path.read_text(encoding="utf-8"))["quality_status"] == "PASS"
