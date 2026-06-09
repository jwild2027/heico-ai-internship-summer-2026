from __future__ import annotations

import json
from pathlib import Path

import pytest

from tiff import trace_net_evidence_snippet_claims_v1 as mod


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def context_pack_payload() -> dict:
    return {
        "schema_version": "trace_net_answer_context_pack_v1",
        "quality_status": "PASS",
        "answer_status": "CONTEXT_PACK_ONLY",
        "summary": {
            "query": "Which pages discuss manual revision history?",
            "answer_status": "CONTEXT_PACK_ONLY",
            "embedding_mode": "ollama",
            "embedding_model_name": "bge-m3:latest",
            "embedding_dim": 1024,
            "context_pack_group_count": 1,
            "context_record_count": 2,
        },
        "quality": {"status": "PASS", "checks": []},
        "groups": [
            {
                "context_group_id": "ctx_group_1",
                "rank": 1,
                "page_id": "t_p_120_1176_p000001",
                "all_records": [
                    {
                        "context_record_id": "ctx_rec_1",
                        "context_pack_role": "answer_support_candidate",
                        "resolved_to_artifact": True,
                        "rag_bucket": "source_text_evidence",
                        "authority": "ocr_text_claim_with_citation",
                        "page_id": "t_p_120_1176_p000001",
                        "page_number": 1,
                        "citation_id": "cite:source_text:p1:abc",
                        "source_candidate_id": "rag_candidate:source_text:p1",
                        "embedding_candidate_id": "emb_1",
                        "text_preview": "REVISION HISTORY Revision 4 supersedes Revision 3 for T.P. 120/1176.",
                        "requires_source_resolution": True,
                        "requires_citation": True,
                        "requires_authority_gate": True,
                        "can_answer_directly": False,
                        "can_prove_claims": False,
                        "can_mutate_source_truth": False,
                    },
                    {
                        "context_record_id": "ctx_route_1",
                        "context_pack_role": "retrieval_only",
                        "resolved_to_artifact": True,
                        "rag_bucket": "page_retrieval_profile",
                        "authority": "page_route_only",
                        "page_id": "t_p_120_1176_p000001",
                        "text_preview": "route-only profile",
                    },
                ],
            }
        ],
    }


def draft_payload() -> dict:
    return {
        "schema_version": "trace_net_citation_answer_draft_v1",
        "quality_status": "PASS",
        "answer_status": "CITATION_DRAFT_ONLY",
        "final_answer_allowed": False,
        "quality": {"status": "PASS", "checks": []},
        "summary": {
            "query": "Which pages discuss manual revision history?",
            "answer_status": "CITATION_DRAFT_ONLY",
            "embedding_mode": "ollama",
            "embedding_model_name": "bge-m3:latest",
            "embedding_dim": 1024,
            "claim_count": 1,
        },
        "claims": [
            {
                "claim_id": "draft_claim_1",
                "claim_rank": 1,
                "query": "Which pages discuss manual revision history?",
                "claim_text": "page 1 has citation-backed source-text evidence relevant to the query.",
                "page_id": "t_p_120_1176_p000001",
                "page_number": 1,
                "rag_bucket": "source_text_evidence",
                "authority": "ocr_text_claim_with_citation",
                "citation_ids": ["cite:source_text:p1:abc"],
                "citation_id": "cite:source_text:p1:abc",
                "source_context_record_id": "ctx_rec_1",
                "source_candidate_id": "rag_candidate:source_text:p1",
                "embedding_candidate_id": "emb_1",
                "requires_source_resolution": True,
                "requires_citation": True,
                "requires_authority_gate": True,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "can_mutate_source_truth": False,
                "final_answer_allowed": False,
                "llm_freeform_answer_allowed": False,
            }
        ],
    }


def test_build_snippet_claims_passes(tmp_path: Path) -> None:
    context_path = tmp_path / "context.json"
    draft_path = tmp_path / "draft.json"
    write_json(context_path, context_pack_payload())
    write_json(draft_path, draft_payload())

    report = mod.build_trace_net_evidence_snippet_claims(
        citation_draft_path=draft_path,
        context_pack_path=context_path,
        output_dir=tmp_path / "out",
        min_snippet_claims=1,
        write_quality=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["answer_status"] == "SNIPPET_CLAIMS_ONLY"
    assert report["final_answer_allowed"] is False
    assert report["summary"]["snippet_claim_count"] == 1
    assert report["summary"]["cited_snippet_claim_count"] == 1
    assert report["summary"]["missing_source_snippet_count"] == 0
    claim = report["snippet_claims"][0]
    assert claim["source_snippet"] == "REVISION HISTORY Revision 4 supersedes Revision 3 for T.P. 120/1176."
    assert "REVISION HISTORY" in claim["materialized_claim_text"]
    assert claim["citation_ids"] == ["cite:source_text:p1:abc"]
    assert claim["requires_final_answer_gate"] is True
    assert claim["final_answer_allowed"] is False
    assert Path(report["report_path"]).exists()
    assert Path(report["claims_path"]).exists()
    assert Path(report["quality_path"]).exists()


def test_retrieval_only_draft_claim_is_blocked(tmp_path: Path) -> None:
    context = context_pack_payload()
    context["groups"][0]["all_records"].append(
        {
            "context_record_id": "ctx_route_2",
            "context_pack_role": "retrieval_only",
            "resolved_to_artifact": True,
            "rag_bucket": "context_retrieval_helper",
            "authority": "retrieval_helper_only",
            "page_id": "t_p_120_1176_p000001",
            "citation_id": "cite:helper:p1",
            "text_preview": "route only helper text",
        }
    )
    draft = draft_payload()
    draft["claims"][0].update(
        {
            "claim_id": "bad_claim",
            "rag_bucket": "context_retrieval_helper",
            "authority": "retrieval_helper_only",
            "citation_id": "cite:helper:p1",
            "citation_ids": ["cite:helper:p1"],
            "source_context_record_id": "ctx_route_2",
        }
    )
    context_path = tmp_path / "context.json"
    draft_path = tmp_path / "draft.json"
    write_json(context_path, context)
    write_json(draft_path, draft)

    report = mod.build_trace_net_evidence_snippet_claims(
        citation_draft_path=draft_path,
        context_pack_path=context_path,
        output_dir=tmp_path / "out",
        min_snippet_claims=1,
    )

    assert report["quality_status"] == "FAIL"
    assert report["summary"]["snippet_claim_count"] == 0
    assert report["blocked_records"]
    assert "banned_bucket_for_snippet_claim" in report["blocked_records"][0]["block_reasons"]


def test_missing_source_snippet_is_blocked(tmp_path: Path) -> None:
    context = context_pack_payload()
    context["groups"][0]["all_records"][0]["text_preview"] = ""
    draft = draft_payload()
    draft["claims"][0]["evidence_preview"] = ""
    draft["claims"][0]["claim_text"] = ""
    context_path = tmp_path / "context.json"
    draft_path = tmp_path / "draft.json"
    write_json(context_path, context)
    write_json(draft_path, draft)

    report = mod.build_trace_net_evidence_snippet_claims(
        citation_draft_path=draft_path,
        context_pack_path=context_path,
        output_dir=tmp_path / "out",
        min_snippet_claims=1,
    )

    assert report["quality_status"] == "FAIL"
    assert report["summary"]["snippet_claim_count"] == 0
    assert "missing_source_snippet" in report["blocked_records"][0]["block_reasons"]


def test_quality_checker_reads_written_report(tmp_path: Path) -> None:
    context_path = tmp_path / "context.json"
    draft_path = tmp_path / "draft.json"
    write_json(context_path, context_pack_payload())
    write_json(draft_path, draft_payload())
    report = mod.build_trace_net_evidence_snippet_claims(
        citation_draft_path=draft_path,
        context_pack_path=context_path,
        output_dir=tmp_path / "out",
        write_quality=True,
    )

    result = mod.check_trace_net_evidence_snippet_claims_quality(
        report_path=Path(report["report_path"]),
        min_snippet_claims=1,
        write_json_result=True,
    )

    assert result["status"] == "PASS"
    assert result["summary"]["snippet_claim_count"] == 1
    assert Path(result["quality_path"]).exists()


def test_requires_context_record_match(tmp_path: Path) -> None:
    context = context_pack_payload()
    draft = draft_payload()
    draft["claims"][0]["source_context_record_id"] = "missing_context"
    draft["claims"][0]["citation_id"] = "missing_citation"
    draft["claims"][0]["citation_ids"] = ["missing_citation"]
    draft["claims"][0]["source_candidate_id"] = "missing_source_candidate"
    draft["claims"][0]["embedding_candidate_id"] = "missing_embedding_candidate"
    context_path = tmp_path / "context.json"
    draft_path = tmp_path / "draft.json"
    write_json(context_path, context)
    write_json(draft_path, draft)

    report = mod.build_trace_net_evidence_snippet_claims(
        citation_draft_path=draft_path,
        context_pack_path=context_path,
        output_dir=tmp_path / "out",
    )

    assert report["quality_status"] == "FAIL"
    assert report["summary"]["snippet_claim_count"] == 0
    assert "missing_context_pack_source_record" in report["blocked_records"][0]["block_reasons"]
