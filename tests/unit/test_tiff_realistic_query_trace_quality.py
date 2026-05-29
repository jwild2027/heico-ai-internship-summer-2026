from __future__ import annotations

import json
from pathlib import Path

from tiff.document_graph_quality import GraphQualityThresholds, build_graph_quality_result
from tiff.pipeline_quality import QualityGateThresholds, check_pipeline_manifest


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_minimal_graph(graph_dir: Path) -> None:
    nodes = [
        {"id": "document:doc", "type": "document", "label": "Doc"},
        {"id": "ata_section:doc_25_21_00", "type": "ata_section", "label": "ATA 25-21-00"},
        {"id": "page:t_p_120_1176_p000083", "type": "page", "label": "Page 1056", "properties": {"page_id": "t_p_120_1176_p000083"}},
        {"id": "page:t_p_120_1176_p000495", "type": "page", "label": "Page 621", "properties": {"page_id": "t_p_120_1176_p000495"}},
        {"id": "source_link:t_p_120_1176_p000083", "type": "source_link", "label": "source 83"},
        {"id": "source_link:t_p_120_1176_p000495", "type": "source_link", "label": "source 495"},
        {"id": "part:120_37313_001", "type": "part", "label": "120-37313-001", "properties": {"part_number": "120-37313-001"}},
        {"id": "nomenclature:holder_magazine", "type": "nomenclature", "label": "HOLDER, MAGAZINE"},
        {"id": "page_context:t_p_120_1176_p000083", "type": "page_context", "label": "context 83", "properties": {"score": 0.9}},
        {"id": "page_context:t_p_120_1176_p000495", "type": "page_context", "label": "context 495", "properties": {"score": 0.9}},
    ]
    edges = [
        {"source": "document:doc", "target": "page:t_p_120_1176_p000083", "type": "HAS_PAGE"},
        {"source": "document:doc", "target": "page:t_p_120_1176_p000495", "type": "HAS_PAGE"},
        {"source": "page:t_p_120_1176_p000083", "target": "document:doc", "type": "BELONGS_TO_DOCUMENT"},
        {"source": "page:t_p_120_1176_p000495", "target": "document:doc", "type": "BELONGS_TO_DOCUMENT"},
        {"source": "page:t_p_120_1176_p000083", "target": "ata_section:doc_25_21_00", "type": "BELONGS_TO_ATA"},
        {"source": "page:t_p_120_1176_p000495", "target": "ata_section:doc_25_21_00", "type": "BELONGS_TO_ATA"},
        {"source": "page:t_p_120_1176_p000083", "target": "source_link:t_p_120_1176_p000083", "type": "HAS_SOURCE_LINK"},
        {"source": "page:t_p_120_1176_p000495", "target": "source_link:t_p_120_1176_p000495", "type": "HAS_SOURCE_LINK"},
        {"source": "part:120_37313_001", "target": "page:t_p_120_1176_p000083", "type": "APPEARS_ON"},
        {"source": "part:120_37313_001", "target": "nomenclature:holder_magazine", "type": "HAS_NOMENCLATURE"},
        {"source": "page:t_p_120_1176_p000083", "target": "part:120_37313_001", "type": "MENTIONS_PART"},
        {"source": "page:t_p_120_1176_p000083", "target": "page_context:t_p_120_1176_p000083", "type": "HAS_CONTEXT"},
        {"source": "page:t_p_120_1176_p000495", "target": "page_context:t_p_120_1176_p000495", "type": "HAS_CONTEXT"},
    ]
    write_json(graph_dir / "graph_nodes.json", nodes)
    write_json(graph_dir / "graph_edges.json", edges)


def realistic_results_payload(fail: int = 0, include_slow: bool = True):
    results = [
        {"id": "part_prompt_120_37313_001_to_graph", "category": "part_prompt_to_graph", "status": "pass", "checks": [{"status": "pass"}]},
        {"id": "vector_payload_page_000495_to_graph_context", "category": "vector_to_graph", "status": "pass", "checks": [{"status": "pass"}]},
    ]
    if include_slow:
        results.append({"id": "slow_rag_summary_passenger_seat_back_to_graph", "category": "rag_vector_to_graph_slow", "status": "pass", "checks": [{"status": "pass"}]})
    if fail:
        results.append({"id": "bad_case", "category": "part_prompt_to_graph", "status": "fail", "checks": [{"status": "fail"}]})
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "pass")
    check_total = sum(len(r["checks"]) for r in results)
    check_pass = sum(1 for r in results for c in r["checks"] if c["status"] == "pass")
    return {
        "summary": {
            "total": total,
            "pass": passed,
            "fail": total - passed,
            "check_total": check_total,
            "check_pass": check_pass,
            "check_fail": check_total - check_pass,
            "status_counts": {"pass": passed, "fail": total - passed},
        },
        "results": results,
    }


def test_graph_quality_requires_realistic_trace_results(tmp_path: Path) -> None:
    graph_dir = tmp_path / "graph"
    context_file = tmp_path / "contexts.json"
    user_results = tmp_path / "user_query.json"
    realistic_results = tmp_path / "realistic.json"
    write_minimal_graph(graph_dir)
    write_json(context_file, {"contexts": [
        {"page_id": "t_p_120_1176_p000083", "role": "parts_list", "confidence": "high"},
        {"page_id": "t_p_120_1176_p000495", "role": "procedure", "confidence": "high"},
    ]})
    write_json(user_results, {"results": [{"status": "pass"}]})
    write_json(realistic_results, realistic_results_payload())

    result = build_graph_quality_result(
        graph_dir=graph_dir,
        context_file=context_file,
        user_query_results=user_results,
        realistic_query_results=realistic_results,
        thresholds=GraphQualityThresholds(
            require_user_query_tests=True,
            require_realistic_query_trace_tests=True,
            require_slow_realistic_query_trace=True,
        ),
    )
    assert result.status == "ok"
    assert result.summary["realistic_query_total"] == 3
    assert result.summary["realistic_query_fail"] == 0
    assert result.summary["realistic_query_slow_cases"] == 1


def test_graph_quality_fails_failed_realistic_trace_results(tmp_path: Path) -> None:
    graph_dir = tmp_path / "graph"
    context_file = tmp_path / "contexts.json"
    realistic_results = tmp_path / "realistic.json"
    write_minimal_graph(graph_dir)
    write_json(context_file, {"contexts": [
        {"page_id": "t_p_120_1176_p000083", "role": "parts_list", "confidence": "high"},
        {"page_id": "t_p_120_1176_p000495", "role": "procedure", "confidence": "high"},
    ]})
    write_json(realistic_results, realistic_results_payload(fail=1))

    result = build_graph_quality_result(
        graph_dir=graph_dir,
        context_file=context_file,
        realistic_query_results=realistic_results,
        thresholds=GraphQualityThresholds(require_realistic_query_trace_tests=True),
    )
    assert result.status == "fail"
    failing = {check.name for check in result.checks if check.status == "FAIL"}
    assert "realistic_query_trace_results" in failing


def test_pipeline_quality_reads_realistic_graph_summary() -> None:
    manifest = {
        "status": "ok",
        "steps": [
            {"name": "source_link_audit", "returncode": 0},
            {"name": "ocr_coverage_audit", "returncode": 0},
            {"name": "document_organization_audit", "returncode": 0},
            {"name": "document_organization_export", "returncode": 0},
        ],
        "sqlite_counts": {
            "manuals": 1,
            "pages": 1,
            "part_mentions": 1,
            "part_catalog_clean": 1,
            "rag_chunks": 1,
            "rag_embeddings": 1,
            "source_links": 1,
        },
        "eval_summary": {"status_counts": {"pass": 1}},
        "qa_summary": {"review_queue_rows": 0, "by_report": {"suspicious_part_ata": 0}},
        "source_link_summary": {
            "ready_for_local_source_review": True,
            "pages_without_source_links": 0,
            "missing_tiff_path": 0,
            "missing_ocr_path": 0,
            "missing_source_url": 0,
            "missing_tiff_files": 0,
            "missing_ocr_files": 0,
            "sample_queries_without_results": 0,
        },
        "ocr_coverage_summary": {
            "local_ocr_paths_ready": True,
            "missing_ocr_paths": 0,
            "missing_ocr_files": 0,
            "unreadable_ocr_files": 0,
            "empty_ocr_files": 0,
            "short_ocr_files": 0,
            "nonempty_ocr_files": 1,
        },
        "document_organization_summary": {
            "logical_tree_ready": True,
            "manuals_total": 1,
            "pages_total": 1,
            "ata_groups_total": 1,
            "pages_without_ata": 0,
            "distinct_parts_total": 1,
            "part_mentions_total": 1,
        },
        "document_organization_export_summary": {
            "ready": True,
            "files_written": 5,
            "page_count": 1,
            "part_count": 1,
            "part_mention_count": 1,
        },
    }
    # Do not require live graph files for this manifest-only unit test.
    result = check_pipeline_manifest(
        manifest,
        thresholds=QualityGateThresholds(require_graph_quality=False, require_realistic_query_trace=True),
    )
    # Graph is optional here, so the realistic query requirement is not evaluated from missing graph files.
    assert result.status == "ok"
