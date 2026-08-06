import json
import zipfile
from pathlib import Path

from tiff.trace_net_page_retrieval_large_eval_v1 import (
    QualityThresholds,
    build_large_eval,
    build_query_from_profile,
    normalize_page_id,
    page_number_from_page_id,
)


def test_page_number_round_trip():
    assert normalize_page_id(12) == "t_p_120_1176_p000012"
    assert page_number_from_page_id("t_p_120_1176_p000167") == 167


def test_blank_query_generation_from_profile_and_zip():
    page_id = "t_p_120_1176_p000002"
    profile = {
        "page_id": page_id,
        "has_context_v2": True,
        "context_v2": {"role": "blank", "subrole": "empty_or_blank_page"},
        "embedding_text": "blank empty page",
    }
    zip_record = {"blank_by_zip_size": True, "zip_entry_size_bytes": 3000, "blank_by_image_heuristic": True}
    record = build_query_from_profile(page_id, profile, zip_record)
    assert record["blank_expected"] is True
    assert "blank" in record["llm_question"].lower()
    assert record["expected_answer_behavior"] == "LLM_SHOULD_STATE_PAGE_IS_BLANK_OR_EMPTY"
    assert record["can_answer_directly"] is False
    assert record["can_prove_claims"] is False


def test_build_large_eval_without_qdrant(tmp_path: Path):
    metadata_zip = tmp_path / "metadata.zip"
    with zipfile.ZipFile(metadata_zip, "w") as zf:
        zf.writestr("00000001.tif", b"not-a-real-tiff-but-size-is-enough" * 200)
        zf.writestr("00000002.tif", b"tiny")
    profiles = {
        "quality_status": "PASS",
        "page_profiles": [
            {
                "page_id": "t_p_120_1176_p000001",
                "has_context_v2": True,
                "context_v2": {"role": "front_matter", "subrole": "revision_history"},
                "retrieval_summary": "Revision history and title block.",
            },
            {
                "page_id": "t_p_120_1176_p000002",
                "has_context_v2": True,
                "context_v2": {"role": "blank", "subrole": "empty_or_blank_page"},
            },
        ],
    }
    profiles_path = tmp_path / "profiles.json"
    profiles_path.write_text(json.dumps(profiles), encoding="utf-8")
    payload = build_large_eval(
        metadata_zip=metadata_zip,
        profiles_path=profiles_path,
        output_dir=tmp_path / "out",
        first_pages=2,
        run_qdrant=False,
        qdrant_url="http://localhost:6333",
        collection="test_collection",
        ollama_url="http://localhost:11434",
        ollama_model="bge-m3:latest",
        top_k=10,
        batch_size=2,
        ollama_timeout=10,
        progress=False,
        thresholds=QualityThresholds(min_query_records=2, min_blank_queries=1, min_context_v2_queries=2),
    )
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["query_record_count"] == 2
    assert payload["summary"]["blank_expected_count"] == 1
    assert Path(payload["report_path"]).exists()
