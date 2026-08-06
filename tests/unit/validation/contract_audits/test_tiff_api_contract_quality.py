import json
from pathlib import Path

from tiff.api_contract_quality import evaluate_api_contract_quality, write_api_contract_quality


def test_api_contract_quality_accepts_in_process_case_results(tmp_path: Path) -> None:
    results = {
        "status": "ok",
        "mode": "in_process",
        "base_url": "http://127.0.0.1:8000",
        "total": 11,
        "status_counts": {"pass": 11, "fail": 0},
        "cases": [
            {"id": "status_endpoint", "status": "pass"},
            {"id": "organization_summary_endpoint", "status": "pass"},
            {"id": "part_lookup_120_37313_001", "status": "pass"},
            {"id": "page_lookup_000083", "status": "pass"},
            {"id": "ata_lookup_25_21_00", "status": "pass"},
            {"id": "trace_part_120_37313_001", "status": "pass"},
            {"id": "trace_page_000083", "status": "pass"},
            {"id": "trace_vector_payload_000495", "status": "pass"},
            {"id": "ask_exact_part_120_37313_001", "status": "pass"},
            {"id": "feedback_round_trip", "status": "pass"},
            {"id": "feedback_summary_endpoint", "status": "pass"},
        ],
    }
    path = tmp_path / "api_contract_results.json"
    path.write_text(json.dumps(results), encoding="utf-8")
    report = evaluate_api_contract_quality(path)
    assert report.status == "ok"
    assert report.summary["api_contract_status_endpoint_ok"] is True
    assert report.summary["api_contract_part_lookup_ok"] is True
    assert report.summary["api_contract_page_lookup_ok"] is True
    assert report.summary["api_contract_trace_vector_ok"] is True
    assert report.summary["api_contract_ask_ok"] is True
    assert report.summary["api_contract_feedback_round_trip_ok"] is True
    assert report.summary["api_contract_feedback_summary_ok"] is True


def test_write_quality_report(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"
    report = evaluate_api_contract_quality(path)
    out = write_api_contract_quality(report, tmp_path / "quality.json")
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["status"] == "fail"
