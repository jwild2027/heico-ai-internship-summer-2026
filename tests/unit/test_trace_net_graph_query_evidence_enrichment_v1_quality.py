from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_graph_query_evidence_enrichment_v1 import Thresholds, check_enrichment_quality


def test_quality_fails_when_answer_permission_present(tmp_path: Path):
    report = {
        "quality_status": "PENDING",
        "status": "GRAPH_QUERY_EVIDENCE_ENRICHMENT_BUILT",
        "summary": {
            "source_graph_query_helper_quality_status": "PASS",
            "query_record_count": 1,
            "enriched_page_record_count": 1,
            "source_resolved_page_count": 1,
            "exact_evidence_page_count": 1,
            "hybrid_evidence_page_count": 0,
            "leiden_navigation_page_count": 0,
            "claim_trace_page_count": 0,
            "community_as_proof_count": 0,
            "category_as_proof_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "can_answer_directly_count": 1,
            "can_prove_claims_count": 0,
        },
    }
    p = tmp_path / "report.json"
    p.write_text(json.dumps(report), encoding="utf-8")
    quality = check_enrichment_quality(
        report_path=p,
        thresholds=Thresholds(min_query_records=1, min_enriched_page_records=1, min_source_resolved_pages=1, require_no_answer_permission=True),
    )
    assert quality["quality_status"] == "FAIL"
    assert any("can_answer_directly" in x for x in quality["failures"])


def test_quality_passes_with_safe_counts(tmp_path: Path):
    report = {
        "quality_status": "PENDING",
        "status": "GRAPH_QUERY_EVIDENCE_ENRICHMENT_BUILT",
        "summary": {
            "source_graph_query_helper_quality_status": "PASS",
            "query_record_count": 3,
            "enriched_page_record_count": 4,
            "source_resolved_page_count": 4,
            "exact_evidence_page_count": 1,
            "hybrid_evidence_page_count": 1,
            "leiden_navigation_page_count": 1,
            "claim_trace_page_count": 0,
            "community_as_proof_count": 0,
            "category_as_proof_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
        },
    }
    p = tmp_path / "report.json"
    p.write_text(json.dumps(report), encoding="utf-8")
    quality = check_enrichment_quality(
        report_path=p,
        thresholds=Thresholds(
            min_query_records=3,
            min_enriched_page_records=4,
            min_source_resolved_pages=4,
            min_exact_evidence_pages=1,
            min_hybrid_evidence_pages=1,
            min_leiden_navigation_pages=1,
            require_helper_quality_pass=True,
            require_no_answer_permission=True,
        ),
    )
    assert quality["quality_status"] == "PASS"
