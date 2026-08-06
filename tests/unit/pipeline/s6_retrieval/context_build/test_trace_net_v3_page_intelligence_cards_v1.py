import json
from pathlib import Path

from tiff.trace_net_v3_page_intelligence_cards_v1 import build_v3_bundle, check_manifest_quality, write_bundle


def test_v3_builds_all_fishnet_pages_with_deferred_v2(tmp_path: Path):
    fishnet = {
        "records": [
            {
                "page_id": "source_p000001",
                "page_number": 1,
                "source_path": "00000001.tif",
                "file_name": "00000001.tif",
                "page_ocr_status": "ok",
                "ocr_engine_status": "ok",
                "page_ocr_features": {"ocr_char_count": 100, "ocr_word_count": 20, "sample_text": "Title page"},
                "page_ink_features": {"ink_ratio": 0.1},
                "recommended_route_candidate": "normal_text",
                "best_route_candidate_before_review": "normal_text",
                "route_confidence": 0.7,
                "review_required": False,
                "route_scores": {"normal_text": 0.7},
                "reason_counts": {},
            },
            {
                "page_id": "source_p000002",
                "page_number": 2,
                "source_path": "00000002.tif",
                "file_name": "00000002.tif",
                "page_ocr_status": "empty",
                "ocr_engine_status": "empty",
                "page_ocr_features": {"ocr_char_count": 0, "ocr_word_count": 0, "sample_text": ""},
                "page_ink_features": {"ink_ratio": 0.0},
                "recommended_route_candidate": "blank_candidate",
                "best_route_candidate_before_review": "blank_candidate",
                "route_confidence": 0.9,
                "review_required": False,
                "route_scores": {"blank_candidate": 0.9},
                "reason_counts": {},
            },
            {
                "page_id": "source_p000003",
                "page_number": 3,
                "source_path": "00000003.tif",
                "file_name": "00000003.tif",
                "page_ocr_status": "ok",
                "ocr_engine_status": "ok",
                "page_ocr_features": {"ocr_char_count": 80, "ocr_word_count": 18, "sample_text": "Parts list"},
                "page_ink_features": {"ink_ratio": 0.2},
                "recommended_route_candidate": "table",
                "best_route_candidate_before_review": "table",
                "route_confidence": 0.6,
                "review_required": True,
                "route_scores": {"table": 0.6},
                "reason_counts": {},
            },
        ]
    }
    v2 = [
        {
            "page_id": "t_p_120_1176_p000001",
            "context_id": "page_context_v2:t_p_120_1176_p000001",
            "generation_model": "gemma4:26b",
            "role": "front_matter",
            "subrole": "title_page",
            "confidence": "high",
            "retrieval_summary": "Title page summary",
            "important_entities": ["Embraer"],
            "guidance_only": True,
            "canonical_source_truth": False,
            "can_answer_directly": False,
            "source_truth_mutation_allowed": False,
        },
        {
            "page_id": "t_p_120_1176_p000003",
            "context_id": "page_context_v2:t_p_120_1176_p000003",
            "generation_model": "gemma4:26b",
            "role": "parts_list",
            "subrole": "ipl",
            "confidence": "high",
            "retrieval_summary": "Parts list summary",
            "important_parts": ["120-1"],
            "guidance_only": True,
            "canonical_source_truth": False,
            "can_answer_directly": False,
            "source_truth_mutation_allowed": False,
        },
    ]
    fishnet_path = tmp_path / "fishnet.json"
    v2_path = tmp_path / "v2.json"
    deferred_path = tmp_path / "deferred.json"
    fishnet_path.write_text(json.dumps(fishnet), encoding="utf-8")
    v2_path.write_text(json.dumps(v2), encoding="utf-8")
    deferred_path.write_text(json.dumps({"deferred_page_ids": ["t_p_120_1176_p000002"]}), encoding="utf-8")

    bundle = build_v3_bundle(
        fishnet_path=fishnet_path,
        page_context_v2_path=v2_path,
        deferred_page_ids_path=deferred_path,
        min_records=3,
        expected_records=3,
        max_missing_v2=1,
    )

    assert bundle["quality_status"] == "PASS"
    assert bundle["summary"]["record_count"] == 3
    assert bundle["summary"]["v2_context_available_count"] == 2
    assert bundle["summary"]["v2_context_missing_count"] == 1
    assert bundle["summary"]["has_v3_page_intelligence_edge_count"] == 3
    missing = [r for r in bundle["records"] if not r["v2_context_available"]]
    assert missing[0]["v2_context_status"] == "missing_deferred"
    assert missing[0]["deferred_reason"] == "Gemma V2 invalid JSON"


def test_v3_quality_checker_enforces_graph_contract(tmp_path: Path):
    fishnet_path = tmp_path / "fishnet.json"
    v2_path = tmp_path / "v2.json"
    deferred_path = tmp_path / "deferred.json"
    fishnet_path.write_text(json.dumps({"records": [{
        "page_id": "source_p000001",
        "page_number": 1,
        "page_ocr_status": "ok",
        "ocr_engine_status": "ok",
        "page_ocr_features": {"sample_text": "x"},
        "page_ink_features": {},
        "recommended_route_candidate": "normal_text",
    }]}), encoding="utf-8")
    v2_path.write_text(json.dumps([{
        "page_id": "t_p_120_1176_p000001",
        "context_id": "page_context_v2:t_p_120_1176_p000001",
        "role": "front_matter",
        "guidance_only": True,
        "canonical_source_truth": False,
        "can_answer_directly": False,
        "source_truth_mutation_allowed": False,
    }]), encoding="utf-8")
    deferred_path.write_text(json.dumps({"deferred_page_ids": []}), encoding="utf-8")

    bundle = build_v3_bundle(
        fishnet_path=fishnet_path,
        page_context_v2_path=v2_path,
        deferred_page_ids_path=deferred_path,
        min_records=1,
        expected_records=1,
        max_missing_v2=0,
    )
    out = tmp_path / "out"
    paths = write_bundle(bundle, out)

    result = check_manifest_quality(
        paths["manifest"],
        min_records=1,
        expected_records=1,
        max_missing_v2=0,
        require_quality_pass=True,
        require_v3_graph_contract=True,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        max_unsafe=0,
    )
    assert result["quality_status"] == "PASS"
