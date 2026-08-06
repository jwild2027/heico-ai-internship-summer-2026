from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_graph_query_evidence_enrichment_v1 import (
    Thresholds,
    build_enrichment_report,
    build_from_paths,
    check_enrichment_quality,
)


def _helper():
    return {
        "quality_status": "PASS",
        "status": "GRAPH_QUERY_HELPER_BUILT",
        "summary": {"graph_node_count": 10, "graph_edge_count": 20},
        "query_records": [
            {
                "plan_id": "part_source_check_v1",
                "query_type": "part_lookup",
                "input": {"part_number": "120-46137-001"},
                "result_count": 1,
                "pages": [
                    {
                        "page_id": "t_p_120_1176_p000340",
                        "source_resolved": True,
                        "source_links": [{"source_uri": "http://example/340"}],
                        "dublin_core_source_identity": {"page_id": "t_p_120_1176_p000340"},
                        "retrieval_only": True,
                        "can_answer_directly": False,
                        "can_prove_claims": False,
                    }
                ],
            },
            {
                "plan_id": "page_source_context_v1",
                "query_type": "page_lookup",
                "input": {"page_id_or_label": "t_p_120_1176_p000003"},
                "pages": [{"page_id": "t_p_120_1176_p000003", "source_links": [{"source_uri": "http://example/3"}]}],
            },
            {
                "plan_id": "ata_pages_browse_v1",
                "query_type": "ata_browse",
                "input": {"ata_code": "25-21-00"},
                "pages": [{"page_id": "t_p_120_1176_p000001", "source_links": [{"source_uri": "http://example/1"}]}],
            },
        ],
    }


def _opensearch():
    return {
        "quality_status": "PASS",
        "documents": [
            {
                "opensearch_document_id": "os1",
                "document_type": "table_cell_normalized",
                "page_id": "t_p_120_1176_p000003",
                "source_trace": {"page_id": "t_p_120_1176_p000003"},
                "search_text": "120-46137-001 exact table cell",
            },
            {
                "opensearch_document_id": "os2",
                "document_type": "verified_part_evidence",
                "page_id": "t_p_120_1176_p000339",
                "source_trace": {"page_id": "t_p_120_1176_p000339"},
                "search_text": "Verified part 120-46137-001 on page 339 ATA 25-21-00",
            },
        ],
    }


def _hybrid():
    return {
        "quality_status": "PASS",
        "query_results": [
            {
                "query_id": "part_120_46137_001",
                "query": "120-46137-001",
                "ranked_groups": [
                    {"page_id": "t_p_120_1176_p000340", "hybrid_v2_rank": 1, "hybrid_v2_score": 0.5, "part_numbers": ["120-46137-001"], "exact_hit_count": 4},
                    {"page_id": "t_p_120_1176_p000341", "hybrid_v2_rank": 2, "hybrid_v2_score": 0.4, "part_numbers": ["120-46137-001"], "exact_hit_count": 3},
                ],
            },
            {
                "query_id": "ata_25_21_00",
                "query": "ATA 25-21-00",
                "ranked_groups": [{"page_id": "t_p_120_1176_p000050", "hybrid_v2_rank": 1, "semantic_group_count": 1}],
            },
        ],
    }


def _leiden():
    return {
        "quality_status": "PASS",
        "retrieval_navigation_hints": [
            {
                "community_id": "tracenet_community_00011",
                "refined_label": "Part family community 120-46137",
                "navigation_intent": "part_family_navigation",
                "navigation_confidence": "MODERATE_NAVIGATION_CONFIDENCE",
                "representative_page_ids": ["t_p_120_1176_p000208", "t_p_120_1176_p000339"],
                "representative_part_numbers": ["120-46137-001", "120-46137-501"],
            }
        ],
        "page_navigation_hints": [
            {
                "community_id": "tracenet_community_00011",
                "page_id": "t_p_120_1176_p000339",
                "refined_label": "Part family community 120-46137",
                "navigation_confidence": "MODERATE_NAVIGATION_CONFIDENCE",
                "navigation_intent": "part_family_navigation",
            }
        ],
    }


def _dublin():
    return {
        "quality_status": "PASS",
        "page_records": [
            {"page_id": f"t_p_120_1176_p{i:06d}", "dc": {"dc:title": f"page {i}"}, "source_package": {"entry": i}}
            for i in [1, 3, 50, 208, 339, 340, 341]
        ],
    }


def _claims():
    return {
        "quality_status": "PASS",
        "entailment_records": [
            {
                "query_id": "part_120_46137_001",
                "claim_id": "claim_1",
                "claim_text": "Page 339 matches part number 120-46137-001.",
                "page_ids": ["t_p_120_1176_p000339"],
                "best_evidence_span": {"page_ids": ["t_p_120_1176_p000003"], "evidence_kind": "table_cell_normalized", "citation_ids": ["cite:x"]},
                "entailment_status": "PARTIALLY_SUPPORTED_NEEDS_REVIEW",
                "entailment_score": 0.35,
            }
        ],
    }


def test_build_report_enriches_part_lookup_with_v2_evidence():
    report = build_enrichment_report(
        graph_query_helper=_helper(),
        opensearch_adapter=_opensearch(),
        hybrid_v2_report=_hybrid(),
        leiden_navigation_metadata_bridge=_leiden(),
        dublin_core_source_package_extension=_dublin(),
        claim_evidence_entailment=_claims(),
    )
    summary = report["summary"]
    assert summary["query_record_count"] == 3
    assert summary["exact_evidence_page_count"] >= 1
    assert summary["hybrid_evidence_page_count"] >= 1
    assert summary["leiden_navigation_page_count"] >= 1
    assert summary["part_evidence_expansion_count"] >= 1
    assert summary["can_answer_directly_count"] == 0
    part_record = next(r for r in report["query_records"] if r["query_type"] == "part_lookup")
    page_ids = {p["page_id"] for p in part_record["pages"]}
    assert "t_p_120_1176_p000340" in page_ids
    assert "t_p_120_1176_p000339" in page_ids
    assert "t_p_120_1176_p000341" in page_ids


def test_build_from_paths_and_quality(tmp_path: Path):
    paths = {}
    for name, payload in {
        "helper": _helper(),
        "opensearch": _opensearch(),
        "hybrid": _hybrid(),
        "leiden": _leiden(),
        "dublin": _dublin(),
        "claims": _claims(),
    }.items():
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        paths[name] = str(p)
    out = tmp_path / "out"
    thresholds = Thresholds(
        min_query_records=3,
        min_enriched_page_records=3,
        min_source_resolved_pages=3,
        min_exact_evidence_pages=1,
        min_hybrid_evidence_pages=1,
        min_leiden_navigation_pages=1,
        require_helper_quality_pass=True,
        require_no_answer_permission=True,
    )
    report = build_from_paths(
        graph_query_helper_path=paths["helper"],
        opensearch_adapter_path=paths["opensearch"],
        hybrid_v2_report_path=paths["hybrid"],
        leiden_navigation_metadata_bridge_path=paths["leiden"],
        dublin_core_source_package_extension_path=paths["dublin"],
        claim_evidence_entailment_path=paths["claims"],
        output_dir=out,
        thresholds=thresholds,
        quality=True,
    )
    assert report["quality_status"] == "PASS"
    quality = check_enrichment_quality(
        report_path=out / "trace_net_graph_query_evidence_enrichment_v1.json",
        thresholds=thresholds,
        write_json_report=True,
    )
    assert quality["quality_status"] == "PASS"
