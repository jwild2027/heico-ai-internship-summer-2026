from __future__ import annotations

from tiff.trace_net_artifact_detector_v1_quality import ArtifactDetectorQualityThresholds, evaluate_quality


def test_quality_passes_with_required_counts() -> None:
    report = {
        "schema_version": "trace_net_artifact_detector_v1",
        "summary": {
            "artifact_card_count": 2,
            "page_artifact_card_count": 3,
            "source_page_card_count": 3,
            "unsafe_artifact_card_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
    }
    q = evaluate_quality(report, ArtifactDetectorQualityThresholds(
        min_artifact_cards=2,
        min_page_artifact_cards=3,
        min_source_page_cards=3,
        require_metadata_pages=True,
        require_no_answer_permission=True,
    ))
    assert q["quality_status"] == "PASS"


def test_quality_fails_when_metadata_required_but_missing() -> None:
    report = {
        "schema_version": "trace_net_artifact_detector_v1",
        "summary": {
            "artifact_card_count": 2,
            "page_artifact_card_count": 3,
            "source_page_card_count": 0,
            "unsafe_artifact_card_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
    }
    q = evaluate_quality(report, ArtifactDetectorQualityThresholds(require_metadata_pages=True))
    assert q["quality_status"] == "FAIL"
    assert "metadata_pages_present" in q["quality_fail_reasons"]
