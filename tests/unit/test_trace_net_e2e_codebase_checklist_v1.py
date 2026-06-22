from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_e2e_codebase_checklist_v1 import build_checklist, render_terminal_checklist, write_report_files


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_build_checklist_reports_missing_items(tmp_path: Path) -> None:
    report = build_checklist(tmp_path)
    assert report["overall_status"] == "FAIL"
    assert report["blocking_count"] > 0
    rendered = render_terminal_checklist(report)
    assert "TRACE-Net E2E Codebase Checklist v1" in rendered
    assert "Hybrid search assessment" in rendered


def test_build_checklist_accepts_passing_minimal_artifact(tmp_path: Path) -> None:
    # Create a source file and one representative artifact to exercise PASS checks.
    (tmp_path / "tiff").mkdir()
    (tmp_path / "tiff" / "trace_net_e2e_query_input_v1.py").write_text("# ok\n", encoding="utf-8")
    _write_json(
        tmp_path / "local_data/organization/trace_net/e2e_query_input/trace_net_e2e_query_input_v1.json",
        {
            "quality_status": "PASS",
            "e2e_query_input_status": "E2E_QUERY_INPUT_READY_FOR_RETRIEVAL_RUNTIME",
            "summary": {
                "e2e_query_input_record_count": 5,
                "answer_permission_count": 0,
                "can_answer_directly_count": 0,
                "can_prove_claims_count": 0,
                "source_truth_mutation_allowed_count": 0,
            },
        },
    )
    report = build_checklist(tmp_path)
    names = {item["name"]: item for item in report["items"]}
    assert names["E2E query input harness"]["status"] == "PASS"
    assert names["E2E query input"]["status"] == "PASS"
    assert names["E2E query input status"]["status"] == "PASS"


def test_write_report_files(tmp_path: Path) -> None:
    report = build_checklist(tmp_path)
    paths = write_report_files(report, tmp_path / "out")
    assert Path(paths["json_path"]).exists()
    assert Path(paths["md_path"]).exists()
    assert "TRACE-Net E2E Codebase Checklist" in Path(paths["md_path"]).read_text(encoding="utf-8")
