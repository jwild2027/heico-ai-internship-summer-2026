from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_opensearch_loader_smoke_v1 import (
    LoaderSmokeThresholds,
    build_loader_smoke_report,
    check_loader_smoke_quality,
)


def _thresholds(min_documents: int = 1) -> LoaderSmokeThresholds:
    return LoaderSmokeThresholds(
        min_documents=min_documents,
        min_page_scoped_documents=min_documents,
        min_query_plans=3,
        require_mapping=True,
        require_adapter_quality_pass=True,
    )


def test_quality_check_fails_missing_page_lineage(tmp_path: Path) -> None:
    adapter = tmp_path / "adapter.json"
    adapter.write_text(
        json.dumps(
            {
                "quality_status": "PASS",
                "mapping": {"properties": {"search_text": {"type": "text"}}},
                "documents": [
                    {
                        "opensearch_document_id": "bad-doc",
                        "document_type": "source_text_evidence",
                        "search_text": "manual revision history sample text",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    report = build_loader_smoke_report(
        opensearch_adapter_path=adapter,
        output_dir=tmp_path / "out",
        thresholds=_thresholds(),
    )

    assert report["quality_status"] == "FAIL"
    assert any("missing_page_id_count" in e for e in report["quality_errors"])
    assert any("missing_source_trace_count" in e for e in report["quality_errors"])


def test_check_loader_smoke_quality_can_rewrite_quality_json(tmp_path: Path) -> None:
    adapter = tmp_path / "adapter.json"
    adapter.write_text(
        json.dumps(
            {
                "quality_status": "PASS",
                "mapping": {"properties": {"search_text": {"type": "text"}}},
                "documents": [
                    {
                        "opensearch_document_id": "doc-1",
                        "document_type": "table_cell",
                        "rag_bucket": "table_cell",
                        "page_id": "p1",
                        "source_trace": {"page_id": "p1"},
                        "search_text": "Part 120-46137-001 table cell sample text",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"
    report = build_loader_smoke_report(
        opensearch_adapter_path=adapter,
        output_dir=output_dir,
        thresholds=_thresholds(),
    )
    report_path = output_dir / "trace_net_opensearch_loader_smoke_v1.json"

    checked = check_loader_smoke_quality(
        report_path=report_path,
        thresholds=_thresholds(),
        write_json_report=True,
    )

    assert report["quality_status"] == "PASS"
    assert checked["quality_status"] == "PASS"
    assert (output_dir / "trace_net_opensearch_loader_smoke_v1_quality.json").exists()


def test_quality_check_detects_missing_mapping(tmp_path: Path) -> None:
    adapter = tmp_path / "adapter.json"
    adapter.write_text(
        json.dumps(
            {
                "quality_status": "PASS",
                "documents": [
                    {
                        "opensearch_document_id": "doc-1",
                        "page_id": "p1",
                        "source_trace": {"page_id": "p1"},
                        "search_text": "Part 120-46137-001 manual revision history sample text",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    report = build_loader_smoke_report(
        opensearch_adapter_path=adapter,
        output_dir=tmp_path / "out",
        thresholds=_thresholds(),
    )

    assert report["quality_status"] == "FAIL"
    assert any("mapping is required" in e for e in report["quality_errors"])
