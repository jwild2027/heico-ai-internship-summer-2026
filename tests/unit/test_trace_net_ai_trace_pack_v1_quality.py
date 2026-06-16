from __future__ import annotations

from tiff.trace_net_ai_trace_pack_v1 import check_trace_pack_quality, TracePackThresholds


def test_quality_fails_when_trace_pack_count_too_low():
    report = {
        "quality_status": "PASS",
        "summary": {
            "trace_pack_count": 0,
            "trace_pack_with_graph_context_count": 0,
            "trace_pack_with_dublin_core_identity_count": 0,
            "community_as_proof_count": 0,
            "category_as_proof_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "source_quality_statuses": {},
        },
    }
    quality = check_trace_pack_quality(report, TracePackThresholds(min_trace_packs=1))
    assert quality["quality_status"] == "FAIL"
    assert quality["failures"]


def test_quality_fails_when_community_as_proof_leaks():
    report = {
        "quality_status": "PASS",
        "summary": {
            "trace_pack_count": 1,
            "trace_pack_with_graph_context_count": 1,
            "trace_pack_with_dublin_core_identity_count": 1,
            "community_as_proof_count": 1,
            "category_as_proof_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "source_quality_statuses": {},
        },
    }
    quality = check_trace_pack_quality(report, TracePackThresholds(max_community_as_proof=0))
    assert quality["quality_status"] == "FAIL"
    assert "community_as_proof_count" in quality["failures"][0]
