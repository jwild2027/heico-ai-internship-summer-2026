import json
from pathlib import Path

from tiff.trace_net_corrective_retrieval_planner_v1 import (
    Thresholds,
    build_corrective_retrieval_plan,
    get_quality_status,
)


def write(path: Path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_qdrant_quality_normalizes_summary_only_pass_shape(tmp_path):
    qdrant = {
        "status": "QDRANT_PAGE_PROFILE_COLLECTION_LOADED",
        "summary": {
            "profile_quality_status": "PASS",
            "loaded_point_count": 509,
            "qdrant_count": 509,
            "page_count": 509,
            "source_trace_point_count": 509,
            "context_v2_point_count": 200,
            "rejected_count": 0,
            "unsafe_point_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
        },
    }

    assert get_quality_status(qdrant, artifact_name="qdrant_page_profile_quality") == "PASS"

    payload = build_corrective_retrieval_plan(
        output_dir=tmp_path / "out",
        qdrant_page_profile_quality=write(tmp_path / "qdrant_quality.json", qdrant),
        thresholds=Thresholds(
            min_correction_records=1,
            min_safe_action_records=1,
            require_qdrant_quality_pass=True,
            require_no_answer_permission=True,
        ),
    )

    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["source_quality_statuses"]["qdrant_page_profile_quality"] == "PASS"
    assert payload["corrective_retrieval_records"][0]["issue_type"] == "semantic_search_channel_available"
    assert payload["corrective_retrieval_records"][0]["can_answer_directly"] is False
    assert payload["corrective_retrieval_records"][0]["can_prove_claims"] is False


def test_qdrant_quality_count_fallback_passes_manifest_shape(tmp_path):
    qdrant = {
        "status": "QDRANT_MANIFEST_READY",
        "loaded_point_count": 509,
        "qdrant_count": 509,
        "page_count": 509,
        "source_trace_point_count": 509,
        "context_v2_point_count": 200,
        "rejected_count": 0,
        "unsafe_point_count": 0,
        "source_truth_mutation_allowed_count": 0,
    }

    payload = build_corrective_retrieval_plan(
        output_dir=tmp_path / "out",
        qdrant_page_profile_quality=write(tmp_path / "qdrant_manifest.json", qdrant),
        thresholds=Thresholds(min_correction_records=1, require_qdrant_quality_pass=True),
    )

    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["source_quality_statuses"]["qdrant_page_profile_quality"] == "PASS"


def test_qdrant_quality_fails_on_nonzero_unsafe_counter(tmp_path):
    qdrant = {
        "summary": {
            "profile_quality_status": "PASS",
            "loaded_point_count": 509,
            "qdrant_count": 509,
            "source_trace_point_count": 509,
            "context_v2_point_count": 200,
            "unsafe_point_count": 1,
        }
    }

    payload = build_corrective_retrieval_plan(
        output_dir=tmp_path / "out",
        qdrant_page_profile_quality=write(tmp_path / "qdrant_bad.json", qdrant),
        thresholds=Thresholds(require_qdrant_quality_pass=True),
    )

    assert payload["quality_status"] == "FAIL"
    assert payload["summary"]["source_quality_statuses"]["qdrant_page_profile_quality"] == "FAIL"
