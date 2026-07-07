import json
from pathlib import Path

from tiff.trace_net_ocr_v2_v3_embedding_candidates_v1 import (
    build_candidate_bundle,
    check_candidate_manifest,
    write_bundle,
)


def test_builds_ocr_v2_v3_candidates(tmp_path: Path):
    fishnet = {"records": [
        {
            "page_id": "source_p000001",
            "page_number": 1,
            "source_path": "00000001.tif",
            "page_ocr_status": "ok",
            "ocr_engine_status": "ok",
            "recommended_route_candidate": "normal_text",
            "page_ocr_features": {
                "ocr_char_count": 55,
                "ocr_word_count": 8,
                "sample_text": "PASSENGER SEATS COMPONENT MAINTENANCE MANUAL",
            },
        },
        {
            "page_id": "source_p000002",
            "page_number": 2,
            "source_path": "00000002.tif",
            "page_ocr_status": "empty",
            "ocr_engine_status": "empty",
            "recommended_route_candidate": "blank_candidate",
            "page_ocr_features": {"sample_text": ""},
        },
    ]}
    v2 = [
        {
            "page_id": "t_p_120_1176_p000001",
            "context_id": "page_context_v2:t_p_120_1176_p000001",
            "role": "front_matter",
            "subrole": "title_page",
            "generation_model": "gemma4:26b",
            "retrieval_summary": "Title page retrieval summary.",
            "important_entities": ["Embraer"],
        }
    ]
    v3 = {"records": [
        {
            "page_id": "t_p_120_1176_p000001",
            "page_number": 1,
            "id": "v3_page_intelligence::t_p_120_1176_p000001",
            "v3_id": "v3_page_intelligence::t_p_120_1176_p000001",
            "v2_context_status": "available",
            "v2_context_available": True,
            "route": {"recommended_route_candidate": "normal_text"},
            "ocr": {"status": "ok", "char_count": 55, "sample_text": "manual"},
            "retrieval_profile": {"text": "V3 intelligence for page 1."},
        },
        {
            "page_id": "t_p_120_1176_p000002",
            "page_number": 2,
            "id": "v3_page_intelligence::t_p_120_1176_p000002",
            "v3_id": "v3_page_intelligence::t_p_120_1176_p000002",
            "v2_context_status": "missing_deferred",
            "v2_context_available": False,
            "route": {"recommended_route_candidate": "blank_candidate"},
            "ocr": {"status": "empty", "char_count": 0, "sample_text": ""},
            "retrieval_profile": {"text": "V3 intelligence for page 2."},
        },
    ]}

    fishnet_path = tmp_path / "fishnet.json"
    v2_path = tmp_path / "v2.json"
    v3_path = tmp_path / "v3.json"
    fishnet_path.write_text(json.dumps(fishnet), encoding="utf-8")
    v2_path.write_text(json.dumps(v2), encoding="utf-8")
    v3_path.write_text(json.dumps(v3), encoding="utf-8")

    bundle = build_candidate_bundle(
        fishnet_report=fishnet_path,
        page_context_v2=v2_path,
        v3_cards=v3_path,
        min_records=5,
        expected_records=5,
        min_pages_with_candidates=2,
    )

    assert bundle["quality_status"] == "PASS"
    assert bundle["summary"]["embedding_candidate_count"] == 5
    assert bundle["summary"]["ocr_page_text_candidate_count"] == 2
    assert bundle["summary"]["page_context_v2_candidate_count"] == 1
    assert bundle["summary"]["v3_page_intelligence_candidate_count"] == 2
    assert bundle["summary"]["page_count"] == 2
    assert bundle["summary"]["unsafe_embedding_candidate_count"] == 0
    assert all(r["can_answer_directly"] is False for r in bundle["records"])
    assert all(r["canonical_source_truth"] is False for r in bundle["records"])
    assert all(r["traceability"] for r in bundle["records"])
    assert all(r["requires_source_resolution"] is True for r in bundle["records"])
    assert all(r["must_pass_authority_gate"] is True for r in bundle["records"])
    assert all(r["must_use_source_citation"] is True for r in bundle["records"])
    assert bundle["summary"]["missing_traceability_count"] == 0


def test_quality_check_round_trip(tmp_path: Path):
    fishnet = {"records": [{
        "page_id": "source_p000001",
        "page_number": 1,
        "page_ocr_status": "ok",
        "ocr_engine_status": "ok",
        "recommended_route_candidate": "normal_text",
        "page_ocr_features": {"sample_text": "manual"},
    }]}
    v2 = [{
        "page_id": "t_p_120_1176_p000001",
        "context_id": "page_context_v2:t_p_120_1176_p000001",
        "retrieval_summary": "summary",
    }]
    v3 = {"records": [{
        "page_id": "t_p_120_1176_p000001",
        "page_number": 1,
        "id": "v3_page_intelligence::t_p_120_1176_p000001",
        "retrieval_profile": {"text": "v3 text"},
    }]}
    fishnet_path = tmp_path / "fishnet.json"
    v2_path = tmp_path / "v2.json"
    v3_path = tmp_path / "v3.json"
    fishnet_path.write_text(json.dumps(fishnet), encoding="utf-8")
    v2_path.write_text(json.dumps(v2), encoding="utf-8")
    v3_path.write_text(json.dumps(v3), encoding="utf-8")

    bundle = build_candidate_bundle(
        fishnet_report=fishnet_path,
        page_context_v2=v2_path,
        v3_cards=v3_path,
        min_records=3,
        expected_records=3,
        min_pages_with_candidates=1,
    )
    paths = write_bundle(bundle, tmp_path / "out")
    assert paths["legacy_quality"].name == "trace_net_embedding_candidates_v1_quality.json"
    assert paths["legacy_manifest"].name == "trace_net_embedding_candidates_v1_manifest.json"
    result = check_candidate_manifest(
        paths["manifest"],
        min_records=3,
        expected_records=3,
        min_pages_with_candidates=1,
        require_quality_pass=True,
        max_unsafe=0,
    )
    assert result["quality_status"] == "PASS"
