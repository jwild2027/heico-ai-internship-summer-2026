import json
from pathlib import Path

from tiff.trace_net_opensearch_missing_lineage_inspector_v1 import (
    build_missing_lineage_inspection,
    check_existing_report,
)


def _write_adapter(tmp_path: Path) -> Path:
    path = tmp_path / "adapter.json"
    path.write_text(
        json.dumps(
            {
                "quality_status": "FAIL",
                "documents": [
                    {"opensearch_document_id": "good", "document_type": "page_retrieval_profile", "page_id": "p1", "source_trace_present": True, "safe_for_opensearch": True},
                    {"opensearch_document_id": "bad", "document_type": "part_candidate_lineage", "rag_bucket": "part_candidate_lineage", "safe_for_opensearch": True},
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_build_quality_passes_with_expected_missing_lineage_budget(tmp_path):
    adapter = _write_adapter(tmp_path)
    report = build_missing_lineage_inspection(
        adapter_path=adapter,
        output_dir=tmp_path / "out",
        min_documents=2,
        max_missing_lineage_docs=1,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["missing_lineage_doc_count"] == 1
    assert (tmp_path / "out" / "trace_net_opensearch_missing_lineage_inspector_v1.json").exists()
    assert (tmp_path / "out" / "trace_net_opensearch_missing_lineage_inspector_v1_quality.json").exists()


def test_quality_fails_when_missing_lineage_budget_is_zero(tmp_path):
    adapter = _write_adapter(tmp_path)
    report = build_missing_lineage_inspection(
        adapter_path=adapter,
        output_dir=tmp_path / "out",
        min_documents=2,
        max_missing_lineage_docs=1,
    )
    report_path = Path(report["paths"]["report_path"])
    checked = check_existing_report(
        report_path=report_path,
        min_documents=2,
        max_missing_lineage_docs=0,
    )
    assert checked["quality_status"] == "FAIL"
    failed = [c["name"] for c in checked["quality"]["checks"] if not c["passed"]]
    assert "missing_lineage_doc_count_max" in failed
