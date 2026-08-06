import json
from pathlib import Path

from tiff.trace_net_ask_api_v1 import (
    AskApiConfig,
    build_api_report,
    build_trace_net_ask_response,
    extract_markdown_answer,
    openai_chat_completion_response,
    sanitize_for_user,
)


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def minimal_final_report(query: str = "Which pages discuss manual revision history?") -> dict:
    return {
        "schema_version": "trace_net_final_answer_gate_v1",
        "quality_status": "PASS",
        "final_answer_allowed": True,
        "query": query,
        "summary": {"query": query, "final_answer_allowed": True},
        "final_answer_text": "Page 13 discusses revision history. [cite:x]",
    }


def minimal_community_report(query: str = "Which pages discuss manual revision history?") -> dict:
    return {
        "schema_version": "trace_net_community_aware_retrieval_sim_v1",
        "quality_status": "PASS",
        "query_results": [
            {
                "query_id": "manual_revision_history",
                "query": query,
                "ranked_groups": [
                    {"page_id": "t_p_120_1176_p000013", "community_aware_rank": 1, "community_aware_score": 1.23, "community_ids": ["c1"]},
                    {"page_id": "t_p_120_1176_p000001", "community_aware_rank": 2, "community_aware_score": 1.0, "community_ids": ["c2"]},
                ],
            }
        ],
    }


def test_extract_markdown_answer_final_section() -> None:
    text = "# Title\n\n## Final gated answer\n\nThis is the answer.\n\n## Other\nNo"
    assert extract_markdown_answer(text) == "This is the answer."


def test_sanitize_for_user_redacts_local_path() -> None:
    out, counts = sanitize_for_user("See local_data/foo and C:/Users/name/file")
    assert "[redacted-local-path]" in out
    assert counts["local_path_leak_count"] >= 1


def test_build_final_gate_answer_when_query_matches(tmp_path: Path) -> None:
    final = write_json(tmp_path / "final.json", minimal_final_report())
    community = write_json(tmp_path / "community.json", minimal_community_report())
    config = AskApiConfig(final_answer_report=final, community_aware_retrieval=community)
    response = build_trace_net_ask_response("Which pages discuss manual revision history?", config)
    assert response["quality_status"] == "PASS"
    assert response["summary"]["final_answer_used"] is True
    assert response["summary"]["can_answer_directly"] is True
    assert "Page 13" in response["answer_text"]
    assert len(response["retrieval_groups"]) == 2


def test_query_mismatch_blocks_final_answer(tmp_path: Path) -> None:
    final = write_json(tmp_path / "final.json", minimal_final_report("old query"))
    config = AskApiConfig(final_answer_report=final)
    response = build_trace_net_ask_response("new query", config)
    assert response["summary"]["final_answer_used"] is False
    assert response["summary"]["final_answer_allowed"] is False
    assert response["summary"]["answer_status"] == "QUERY_MISMATCH_RETRIEVAL_ONLY"


def test_retrieval_only_mode_never_answers(tmp_path: Path) -> None:
    community = write_json(tmp_path / "community.json", minimal_community_report())
    config = AskApiConfig(community_aware_retrieval=community)
    response = build_trace_net_ask_response("Which pages discuss manual revision history?", config, answer_mode="retrieval-only")
    assert response["summary"]["answer_status"] == "RETRIEVAL_ONLY"
    assert response["summary"]["can_answer_directly"] is False
    assert len(response["retrieval_groups"]) == 2


def test_build_api_report_is_read_only(tmp_path: Path) -> None:
    final = write_json(tmp_path / "final.json", minimal_final_report())
    config = AskApiConfig(final_answer_report=final)
    report = build_api_report(config)
    assert report["quality_status"] == "PASS"
    assert report["summary"]["read_only_api"] is True
    assert report["summary"]["source_truth_mutation_allowed_count"] == 0


def test_openai_chat_completion_shape(tmp_path: Path) -> None:
    response = {
        "answer_markdown": "hello",
        "summary": {"answer_status": "RETRIEVAL_ONLY"},
        "retrieval_groups": [{"rank": 1, "page_id": "p1", "score": 0.9, "community_ids": []}],
    }
    chat = openai_chat_completion_response("q", response, "trace-net")
    assert chat["object"] == "chat.completion"
    assert chat["choices"][0]["message"]["role"] == "assistant"
    assert "p1" in chat["choices"][0]["message"]["content"]
