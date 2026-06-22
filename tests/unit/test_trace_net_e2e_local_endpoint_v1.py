from __future__ import annotations

import json
from pathlib import Path
import tempfile

from tiff.trace_net_e2e_local_endpoint_v1 import (
    clean_response_content,
    _coerce_api_responses,
    build_endpoint_manifest,
    extract_query_from_payload,
    make_openai_chat_completion,
    make_trace_net_ask_response,
    normalize_query,
    score_response_for_query,
)


def fake_source_report():
    return {
        "quality_status": "PASS",
        "summary": {
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "opensearch_upload_attempt_count": 0,
        },
        "api_responses": [
            {
                "query_id": "q1",
                "query_intent": "covered_part_number",
                "user_query": "Find part number 120-36833-001",
                "message": {"role": "assistant", "content": "Found part number 120-36833-001 on the source page."},
                "citations": [
                    {
                        "citation_id": "c1",
                        "page_id": "t_p_120_1176_p000003",
                        "field_name": "covered_part_number",
                        "normalized_value": "120-36833-001",
                        "citation_ready": True,
                        "source_trace_ready": True,
                    }
                ],
                "page_ids": ["t_p_120_1176_p000003"],
            },
            {
                "query_id": "q2",
                "query_intent": "manual_page_reference",
                "user_query": "Where is manual reference 25-21-00 used?",
                "message": {"role": "assistant", "content": "Found manual reference 25-21-00."},
                "citations": [
                    {
                        "citation_id": "c2",
                        "page_id": "t_p_120_1176_p000005",
                        "field_name": "manual_page_reference",
                        "normalized_value": "25-21-00",
                    }
                ],
                "page_ids": ["t_p_120_1176_p000005"],
            },
        ],
    }


def test_normalize_query_preserves_part_number_shape():
    assert normalize_query(" Find part number 120-36833-001! ") == "find part number 120-36833-001"


def test_coerce_api_responses_sets_safety_flags():
    responses = _coerce_api_responses(fake_source_report())
    assert len(responses) == 2
    assert responses[0]["answer_permission"] is False
    assert responses[0]["can_answer_directly"] is False
    assert responses[0]["citation_count"] == 1


def test_score_prefers_exact_query_match():
    responses = _coerce_api_responses(fake_source_report())
    exact = score_response_for_query("Find part number 120-36833-001", responses[0])
    weak = score_response_for_query("Find part number 120-36833-001", responses[1])
    assert exact > weak


def test_make_trace_net_ask_response_matches_known_query():
    responses = _coerce_api_responses(fake_source_report())
    response = make_trace_net_ask_response("Find part number 120-36833-001", responses)
    assert response["matched_artifact_response"] is True
    assert response["citations"][0]["page_id"] == "t_p_120_1176_p000003"
    assert response["safety"]["can_prove_claims"] is False


def test_make_trace_net_ask_response_audit_only_for_unknown_query():
    responses = _coerce_api_responses(fake_source_report())
    response = make_trace_net_ask_response("totally unrelated query", responses, min_match_score=999)
    assert response["matched_artifact_response"] is False
    assert response["response"]["api_response_status"] == "AUDIT_ONLY_NO_MATCHING_E2E_DEMO_RESPONSE"


def test_openai_chat_completion_shape():
    responses = _coerce_api_responses(fake_source_report())
    ask = make_trace_net_ask_response("Find part number 120-36833-001", responses)
    chat = make_openai_chat_completion("Find part number 120-36833-001", ask)
    assert chat["object"] == "chat.completion"
    assert chat["choices"][0]["message"]["role"] == "assistant"
    assert "Citations:" in chat["choices"][0]["message"]["content"]


def test_extract_query_from_payload_supports_ask_and_chat():
    assert extract_query_from_payload({"query": "hello"}) == "hello"
    assert extract_query_from_payload({"messages": [{"role": "user", "content": "hi"}]}) == "hi"


def test_build_endpoint_manifest_quality_passes():
    with tempfile.TemporaryDirectory() as td:
        source = Path(td) / "source.json"
        source.write_text(json.dumps(fake_source_report()), encoding="utf-8")
        report = build_endpoint_manifest(
            e2e_api_wrapper_smoke_path=source,
            output_dir=Path(td) / "out",
            min_api_responses=2,
            min_citation_backed_responses=2,
            min_total_citations=2,
        )
        assert report["quality_status"] == "PASS"
        assert report["summary"]["api_response_count"] == 2
        assert Path(report["paths"]["inspect_md_path"]).exists()


def test_coerce_api_responses_fills_blank_citation_values_from_draft_text():
    source = fake_source_report()
    source["api_responses"][0]["message"]["content"] = (
        "Final-gate smoke draft: covered_part_number=120-36833-001 ont_p_120_1176_p000003; "
        "covered_part_number=120-36833-003 on t_p_120_1176_p000003."
    )
    source["api_responses"][0]["citations"] = [
        {
            "citation_id": "c1",
            "page_id": "t_p_120_1176_p000003",
            "field_name": "covered_part_number",
            "normalized_value": "",
            "citation_ready": True,
            "source_trace_ready": True,
        },
        {
            "citation_id": "c2",
            "page_id": "t_p_120_1176_p000003",
            "field_name": "covered_part_number",
            "normalized_value": "",
            "citation_ready": True,
            "source_trace_ready": True,
        },
    ]
    responses = _coerce_api_responses(source)
    assert responses[0]["message"]["content"].count("on t_p_120_1176_p000003") == 2
    assert responses[0]["citations"][0]["normalized_value"] == "120-36833-001"
    assert responses[0]["citations"][1]["normalized_value"] == "120-36833-003"


def test_openai_chat_completion_renders_inferred_citation_values():
    source = fake_source_report()
    source["api_responses"][0]["message"]["content"] = (
        "Final-gate smoke draft: covered_part_number=120-36833-001 on t_p_120_1176_p000003."
    )
    source["api_responses"][0]["citations"][0]["normalized_value"] = ""
    responses = _coerce_api_responses(source)
    ask = make_trace_net_ask_response("Find part number 120-36833-001", responses)
    chat = make_openai_chat_completion("Find part number 120-36833-001", ask)
    content = chat["choices"][0]["message"]["content"]
    assert "value=120-36833-001" in content
    assert "ont_p_" not in content


def test_clean_response_content_repairs_concatenated_on_page_id():
    dirty = "covered_part_number=120-36833-001 ont_p_120_1176_p000003"
    assert "120-36833-001 on t_p_120_1176_p000003" in clean_response_content(dirty)


def test_openai_chat_completion_cleans_final_message_content_spacing():
    ask = {
        "matched_artifact_response": True,
        "match_score": 1000.0,
        "message": {
            "role": "assistant",
            "content": "covered_part_number=120-36833-001 ont_p_120_1176_p000003",
        },
        "citations": [
            {
                "page_id": "t_p_120_1176_p000003",
                "field_name": "covered_part_number",
                "normalized_value": "120-36833-001",
            }
        ],
        "safety": {"answer_permission": False},
    }
    chat = make_openai_chat_completion("Find part number 120-36833-001", ask)
    content = chat["choices"][0]["message"]["content"]
    assert "120-36833-001 on t_p_120_1176_p000003" in content
    assert "ont_p_" not in content
    assert "value=120-36833-001" in content
