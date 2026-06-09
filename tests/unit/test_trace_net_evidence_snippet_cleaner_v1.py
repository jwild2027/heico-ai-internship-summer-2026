from __future__ import annotations

import json
from pathlib import Path

from tiff import trace_net_evidence_snippet_cleaner_v1 as mod


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def context_pack_payload() -> dict:
    return {
        "schema_version": "trace_net_answer_context_pack_v1",
        "quality_status": "PASS",
        "answer_status": "CONTEXT_PACK_ONLY",
        "summary": {"answer_status": "CONTEXT_PACK_ONLY", "embedding_dim": 1024},
        "quality": {"status": "PASS", "checks": []},
    }


def snippet_claims_payload(ocr_path: str | None = None, *, include_verified_low_content: bool = False) -> dict:
    source_claim = {
        "snippet_claim_id": "snippet_1",
        "snippet_claim_rank": 1,
        "query": "Which pages discuss manual revision history?",
        "answer_status": "SNIPPET_CLAIMS_ONLY",
        "final_answer_allowed": False,
        "llm_freeform_answer_allowed": False,
        "page_id": "t_p_120_1176_p000001",
        "page_number": 1,
        "rag_bucket": "source_text_evidence",
        "authority": "ocr_text_claim_with_citation",
        "citation_ids": ["cite:source_text:p1:abc"],
        "citation_id": "cite:source_text:p1:abc",
        "source_snippet": (
            "Source text evidence for page t_p_120_1176_p000001. "
            "This chunk is source-backed OCR/page-context text. Document: t_p_120_1176. "
            "Source URL: http://localhost:8080/rescarta/t_p_120_1176/000001. "
            "TIFF path: local_data\\rescarta_exports\\p1.tif. "
            "OCR path: local_data\\rescarta_exports\\p1.txt. "
            "OCR text: [b'REVISION HISTORY Revision 4 supersedes Revision 3 for T.P. 120/1176.']"
        ),
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
    }
    if ocr_path:
        source_claim["ocr_path"] = ocr_path
    claims = [source_claim]
    if include_verified_low_content:
        claims.append(
            {
                "snippet_claim_id": "snippet_part_low",
                "snippet_claim_rank": 2,
                "query": "Which pages discuss manual revision history?",
                "page_id": "t_p_120_1176_p000001",
                "page_number": 1,
                "rag_bucket": "verified_part_evidence",
                "authority": "part_page_relationship",
                "citation_ids": ["cite:verified_part:p1:abc"],
                "citation_id": "cite:verified_part:p1:abc",
                "source_snippet": (
                    "Verified part evidence for page t_p_120_1176_p000001. "
                    "This record comes from the verified part evidence pool and is source-traceable. "
                    "Verified part evidence is present for this page, but no page-index part list was available in this candidate build. "
                    "Source URL: http://localhost:8080/rescarta/t_p_120_1176/000001."
                ),
                "requires_source_resolution": True,
                "requires_citation": True,
                "requires_authority_gate": True,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "can_mutate_source_truth": False,
            }
        )
    return {
        "schema_version": "trace_net_evidence_snippet_claims_v1",
        "quality_status": "PASS",
        "answer_status": "SNIPPET_CLAIMS_ONLY",
        "final_answer_allowed": False,
        "quality": {"status": "PASS", "checks": []},
        "summary": {
            "query": "Which pages discuss manual revision history?",
            "answer_status": "SNIPPET_CLAIMS_ONLY",
            "embedding_mode": "ollama",
            "embedding_model_name": "bge-m3:latest",
            "embedding_dim": 1024,
            "snippet_claim_count": len(claims),
        },
        "snippet_claims": claims,
    }


def test_clean_manual_text_removes_boilerplate_paths_and_bytes() -> None:
    raw = (
        "Source text evidence for page t_p_120_1176_p000001. "
        "TIFF path: local_data\\rescarta_exports\\p1.tif. "
        "OCR text: [b'REVISION HISTORY Revision 4 supersedes Revision 3.']"
    )
    cleaned = mod.clean_manual_text(raw, max_chars=200)
    assert "REVISION HISTORY" in cleaned
    assert "local_data" not in cleaned
    assert "OCR text:" not in cleaned
    assert "b'" not in cleaned
    assert "Source text evidence" not in cleaned


def test_build_cleaner_reads_local_ocr_file_and_blocks_low_content_part(tmp_path: Path) -> None:
    ocr_path = tmp_path / "ocr" / "000001.txt"
    ocr_path.parent.mkdir(parents=True)
    ocr_path.write_text("REVISION HISTORY\nRevision 4 supersedes Revision 3 for T.P. 120/1176.\n", encoding="utf-8")
    snippet_path = tmp_path / "snippet.json"
    context_path = tmp_path / "context.json"
    write_json(snippet_path, snippet_claims_payload(str(ocr_path), include_verified_low_content=True))
    write_json(context_path, context_pack_payload())

    report = mod.build_evidence_snippet_cleaner_report(
        snippet_claims_path=snippet_path,
        context_pack_path=context_path,
        embedding_candidates_path=None,
        output_dir=tmp_path / "out",
        min_clean_snippets=1,
        require_snippet_claims_quality_pass=True,
        require_context_pack_quality_pass=True,
        require_snippet_claims_answer_status="SNIPPET_CLAIMS_ONLY",
        require_context_pack_answer_status="CONTEXT_PACK_ONLY",
        require_embedding_dim=1024,
        write_quality=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["clean_snippet_claim_count"] == 1
    assert report["summary"]["blocked_clean_snippet_count"] == 1
    clean = report["clean_snippet_claims"][0]
    assert clean["raw_source_path_read"] is True
    assert "REVISION HISTORY" in clean["clean_source_snippet"]
    assert "local_data" not in clean["clean_source_snippet"]
    assert clean["final_answer_allowed"] is False
    assert "verified_part_evidence_low_content" in report["blocked_records"][0]["block_reasons"]


def test_retrieval_only_bucket_is_blocked(tmp_path: Path) -> None:
    payload = snippet_claims_payload()
    payload["snippet_claims"][0]["rag_bucket"] = "context_retrieval_helper"
    snippet_path = tmp_path / "snippet.json"
    write_json(snippet_path, payload)

    clean, blocked = mod.build_clean_snippets_from_artifacts(
        snippet_claims_payload=payload,
        max_claims=5,
        repo_root=tmp_path,
        allow_local_ocr_read=False,
    )
    assert clean == []
    assert blocked
    assert any("retrieval_or_banned_bucket:context_retrieval_helper" in reason for reason in blocked[0]["block_reasons"])


def test_quality_report_from_path(tmp_path: Path) -> None:
    report = {
        "summary": {
            "answer_status": "CLEAN_SNIPPETS_ONLY",
            "final_answer_allowed": False,
            "llm_freeform_answer_allowed": False,
            "snippet_claims_quality_status": "PASS",
            "context_pack_quality_status": "PASS",
            "snippet_claims_answer_status": "SNIPPET_CLAIMS_ONLY",
            "context_pack_answer_status": "CONTEXT_PACK_ONLY",
            "embedding_dim": 1024,
            "clean_snippet_claim_count": 1,
            "cited_clean_snippet_count": 1,
            "uncited_clean_snippet_count": 0,
            "missing_page_id_count": 0,
            "missing_citation_count": 0,
            "missing_clean_snippet_count": 0,
            "boilerplate_snippet_count": 0,
            "local_path_leak_count": 0,
            "raw_bytes_repr_count": 0,
            "forbidden_marker_count": 0,
            "retrieval_only_clean_claim_count": 0,
            "page_profile_clean_claim_count": 0,
            "context_helper_clean_claim_count": 0,
            "source_evidence_clean_claim_count": 0,
            "derived_context_clean_claim_count": 0,
            "claim_without_authority_count": 0,
            "direct_answer_allowed_claim_count": 0,
            "claim_proof_direct_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "final_answer_allowed_count": 0,
            "llm_freeform_answer_allowed_count": 0,
            "missing_source_resolution_count": 0,
            "missing_authority_gate_count": 0,
            "missing_citation_requirement_count": 0,
        }
    }
    path = tmp_path / "report.json"
    write_json(path, report)
    quality = mod.quality_report_from_path(report_path=path, min_clean_snippets=1, require_embedding_dim=1024)
    assert quality["status"] == "PASS"
