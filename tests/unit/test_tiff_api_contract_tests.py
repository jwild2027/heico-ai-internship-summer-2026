from __future__ import annotations

from pathlib import Path

from tiff.api_contract_tests import DEFAULT_OUTPUT, default_contract_cases, run_api_contract_tests, write_contract_report


def test_default_output_exported() -> None:
    assert str(DEFAULT_OUTPUT).replace('\\', '/').endswith('local_data/api/api_contract_results.json')


def test_case_ids_include_required_contracts() -> None:
    ids = {case.case_id for case in default_contract_cases()}
    assert 'status_endpoint' in ids
    assert 'trace_vector_payload_000495' in ids
    assert 'feedback_round_trip' in ids


def test_write_contract_report(tmp_path: Path) -> None:
    report = {'status': 'ok', 'total': 1, 'pass': 1, 'fail': 0, 'cases': []}
    out = write_contract_report(report, tmp_path / 'api_contract_results.json')
    assert out.exists()
    assert 'status' in out.read_text(encoding='utf-8')
