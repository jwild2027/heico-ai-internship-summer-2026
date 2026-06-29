import json
from pathlib import Path

from tiff.trace_net_engineering_webui_answer_server_v1_3_bridge_v1 import check_manifest_bridge_v1


def _write_report(path: Path, **summary_overrides):
    summary = {
        "page_record_count": 509,
        "gated_draft_count": 1,
        "server_llm_model": "gemma4:26b",
        "self_rag_crag_bridge_enabled": True,
        "sample_bridge_used": True,
        "self_rag_used": True,
        "crag_retry_status": "skipped_not_needed",
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }
    summary.update(summary_overrides)
    payload = {"quality_status": "PASS", "summary": summary}
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_check_manifest_bridge_quality_passes(tmp_path):
    report = tmp_path / "report.json"
    _write_report(report)

    result = check_manifest_bridge_v1(
        report_path=report,
        min_page_records=509,
        min_gated_drafts=1,
        require_llm_model="gemma4:26b",
        require_bridge_preflight=True,
        require_self_rag_used=True,
        require_crag_evaluated=True,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )

    assert result["quality_status"] == "PASS"
    assert result["failures"] == []


def test_check_manifest_fails_when_self_rag_missing(tmp_path):
    report = tmp_path / "report.json"
    _write_report(report, self_rag_used=False)

    result = check_manifest_bridge_v1(report_path=report, require_self_rag_used=True)

    assert result["quality_status"] == "FAIL"
    assert any("Self-RAG" in failure for failure in result["failures"])


def test_check_manifest_fails_when_crag_not_evaluated(tmp_path):
    report = tmp_path / "report.json"
    _write_report(report, crag_retry_status="not_called")

    result = check_manifest_bridge_v1(report_path=report, require_crag_evaluated=True)

    assert result["quality_status"] == "FAIL"
    assert any("CRAG" in failure for failure in result["failures"])


def test_check_manifest_fails_on_write_attempt(tmp_path):
    report = tmp_path / "report.json"
    _write_report(report, qdrant_write_attempt_count=1)

    result = check_manifest_bridge_v1(report_path=report, require_no_write_attempts=True)

    assert result["quality_status"] == "FAIL"
    assert any("qdrant_write_attempt_count" in failure for failure in result["failures"])
