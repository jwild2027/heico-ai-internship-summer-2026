import json
from pathlib import Path

from tiff.trace_net_runtime_hybrid_v3_v22 import (
    RuntimeConfig,
    RuntimePaths,
    build_report,
    docker_start_services,
    evaluate_quality,
    final_policy_api_command,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_report_passes_with_hybrid_v3_quality(tmp_path):
    hybrid = tmp_path / "hybrid.json"
    final_return = tmp_path / "final_return.json"
    final_answer = tmp_path / "final_answer.json"
    final_md = tmp_path / "answer.md"

    write_json(hybrid, {
        "quality_status": "PASS",
        "summary": {
            "hybrid_v3_group_count": 40,
            "corrective_group_count": 13,
            "review_routed_group_count": 13,
            "unsafe_group_count": 0,
        },
    })
    write_json(final_return, {"quality_status": "PASS", "summary": {}})
    write_json(final_answer, {"quality_status": "PASS", "summary": {}})
    final_md.write_text("answer", encoding="utf-8")

    paths = RuntimePaths(hybrid, final_return, final_answer, final_md, tmp_path / "out")
    config = RuntimeConfig(
        model_name="trace-net-final-return-policy-hybrid-v3-v2.2",
        host="0.0.0.0",
        port=8016,
        max_groups=8,
        open_webui_base_url="http://host.docker.internal:8016/v1",
        docker_services=("trace-net-postgres", "trace-net-qdrant", "open-webui"),
    )
    report = build_report(paths, config, require_hybrid_v3_quality_pass=True)
    quality = evaluate_quality(report)

    assert report["quality_status"] == "PASS"
    assert quality["quality_status"] == "PASS"
    assert report["summary"]["hybrid_v3_group_count"] == 40
    assert report["summary"]["postgres_write_attempt_count"] == 0
    assert report["summary"]["qdrant_write_attempt_count"] == 0
    assert report["summary"]["opensearch_write_attempt_count"] == 0
    assert report["summary"]["source_truth_mutation_allowed_count"] == 0
    assert report["summary"]["answer_permission_count"] == 0
    assert report["open_webui"]["model"] == "trace-net-final-return-policy-hybrid-v3-v2.2"


def test_build_report_fails_when_required_hybrid_quality_is_not_pass(tmp_path):
    hybrid = tmp_path / "hybrid.json"
    write_json(hybrid, {"quality_status": "FAIL", "summary": {}})

    paths = RuntimePaths(hybrid, tmp_path / "missing-final-return.json", tmp_path / "missing-final-answer.json", tmp_path / "missing.md", tmp_path / "out")
    config = RuntimeConfig("m", "0.0.0.0", 8016, 8, "http://host.docker.internal:8016/v1", ())
    report = build_report(paths, config, require_hybrid_v3_quality_pass=True)

    assert report["quality_status"] == "FAIL"
    assert "hybrid_v3_quality_not_pass" in report["summary"]["quality_fail_reasons"]


def test_docker_start_services_dry_run_does_not_execute():
    results = docker_start_services(["trace-net-postgres", "trace-net-qdrant"], dry_run=True)
    assert [r["status"] for r in results] == ["DRY_RUN", "DRY_RUN"]
    assert results[0]["command"] == ["docker", "start", "trace-net-postgres"]


def test_final_policy_api_command_uses_expected_script_and_defaults(tmp_path):
    class Args:
        host = "0.0.0.0"
        port = 8016
        hybrid_v3_report = tmp_path / "hybrid.json"
        final_answer_report = tmp_path / "final.json"
        final_answer_markdown = tmp_path / "final.md"
        final_return_output_dir = tmp_path / "out"
        model_name = "trace-net-final-return-policy-hybrid-v3-v2.2"
        max_groups = 8

    command = final_policy_api_command(Args())
    assert "scripts/operations/serving/run_trace_net_ask_api_final_return_policy_hybrid_v3_v22.py" in command[1]
    assert "--port" in command
    assert "8016" in command
    assert "trace-net-final-return-policy-hybrid-v3-v2.2" in command
