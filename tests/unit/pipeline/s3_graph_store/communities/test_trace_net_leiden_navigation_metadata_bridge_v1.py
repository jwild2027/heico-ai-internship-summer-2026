import json
from pathlib import Path

from tiff.trace_net_leiden_navigation_metadata_bridge_v1 import (
    BridgeThresholds,
    build_navigation_metadata_bridge,
)


def _sample_label_tightening(path: Path) -> Path:
    payload = {
        "schema_version": "trace_net_leiden_representative_label_tightening_v1",
        "status": "LEIDEN_REPRESENTATIVE_LABELS_REFINED",
        "quality_status": "PASS",
        "summary": {
            "source_quality_statuses": {"dublin_core_refined": "PASS"},
            "community_profile_record_count": 3,
            "community_as_proof_count": 0,
        },
        "community_profile_records": [
            {
                "community_id": "tracenet_community_00011",
                "source_label": "Part family community 120-46137",
                "refined_label": "Part family community 120-46137",
                "page_count": 9,
                "representative_page_ids": ["t_p_120_1176_p000208", "t_p_120_1176_p000339"],
                "representative_part_family": "120-46137",
                "representative_part_numbers": ["120-46137-001", "120-46137-501"],
                "dominant_evidence_category": "table_evidence",
                "dominant_evidence_ratio": 0.49,
                "navigation_intent": "part_family_navigation",
                "navigation_confidence": "MODERATE_NAVIGATION_CONFIDENCE",
                "macro_category_counts": {"table_evidence": 10, "visual_evidence": 5},
                "risk_flags": [],
                "review_reasons": [],
            },
            {
                "community_id": "tracenet_community_00134",
                "source_label": "Visual evidence community (1 page(s))",
                "refined_label": "Visual evidence community (1 page(s))",
                "page_count": 1,
                "representative_page_ids": ["t_p_120_1176_p000017"],
                "representative_part_numbers": [],
                "dominant_evidence_category": "visual_evidence",
                "dominant_evidence_ratio": 0.65,
                "navigation_intent": "visual_evidence_navigation",
                "navigation_confidence": "HIGH_NAVIGATION_CONFIDENCE",
                "risk_flags": [],
                "review_reasons": [],
            },
            {
                "community_id": "tracenet_community_00229",
                "source_label": "TRACE-Net graph community",
                "refined_label": "TRACE-Net graph community",
                "page_count": 0,
                "representative_page_ids": [],
                "representative_part_numbers": [],
                "dominant_evidence_category": None,
                "navigation_intent": "mixed_evidence_navigation",
                "navigation_confidence": "REVIEW_ONLY",
                "risk_flags": ["missing_page_membership", "missing_category_summary"],
                "review_reasons": ["community_has_no_page_membership_signal"],
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_navigation_metadata_bridge_creates_routing_only_records(tmp_path):
    source = _sample_label_tightening(tmp_path / "label.json")
    report = build_navigation_metadata_bridge(
        label_tightening_path=source,
        output_dir=tmp_path / "out",
        thresholds=BridgeThresholds(
            min_community_records=3,
            min_retrieval_hints=2,
            min_page_navigation_hints=3,
            max_review_only_communities=1,
            max_missing_page_membership=1,
            require_label_tightening_quality_pass=True,
            require_no_answer_permission=True,
        ),
    )

    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["community_navigation_record_count"] == 3
    assert summary["retrieval_navigation_hint_count"] == 2
    assert summary["page_navigation_hint_count"] == 3
    assert summary["review_only_community_count"] == 1
    assert summary["community_as_proof_count"] == 0
    assert summary["can_answer_directly_count"] == 0

    for record in report["community_navigation_records"]:
        assert record["routing_only"] is True
        assert record["retrieval_only"] is True
        assert record["can_answer_directly"] is False
        assert record["can_prove_claims"] is False
        assert record["answer_permission"] is False


def test_build_navigation_metadata_bridge_writes_files(tmp_path):
    source = _sample_label_tightening(tmp_path / "label.json")
    out_dir = tmp_path / "bridge"
    report = build_navigation_metadata_bridge(
        label_tightening_path=source,
        output_dir=out_dir,
        thresholds=BridgeThresholds(min_community_records=3, min_retrieval_hints=2, min_page_navigation_hints=3),
    )
    assert Path(report["report_path"]).exists()
    assert Path(report["quality_path"]).exists()
    assert Path(report["records_path"]).exists()
    assert Path(report["page_hints_path"]).exists()
    assert Path(report["markdown_path"]).exists()


def test_bridge_quality_fails_when_too_few_hints(tmp_path):
    source = _sample_label_tightening(tmp_path / "label.json")
    report = build_navigation_metadata_bridge(
        label_tightening_path=source,
        output_dir=None,
        thresholds=BridgeThresholds(min_community_records=3, min_retrieval_hints=99, min_page_navigation_hints=1),
        write_files=False,
    )
    assert report["quality_status"] == "FAIL"
    assert "retrieval_navigation_hint_count_below_minimum" in report["summary"]["quality_issues"]
