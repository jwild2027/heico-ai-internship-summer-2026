from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff import trace_net_citation_answer_draft_v1 as mod


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def support_record(page_id: str = "t_p_120_1176_p000001", bucket: str = "source_text_evidence", citation_id: str = "cite:source_text:t_p_120_1176_p000001:abc") -> dict:
    return {
        "context_record_id": f"ctx_{page_id}_{bucket}",
        "context_pack_role": "answer_support_candidate",
        "rag_bucket": bucket,
        "authority": "ocr_text_claim_with_citation" if bucket == "source_text_evidence" else "part_page_relationship",
        "page_id": page_id,
        "page_number": 1,
        "document_id": "t_p_120_1176",
        "ata_code": "25-21-00",
        "citation_id": citation_id,
        "source_url": "https://example.test/source",
        "source_candidate_id": f"rag_candidate:{bucket}:{page_id}",
        "embedding_candidate_id": f"embcand_{page_id}_{bucket}",
        "text_preview": "Revision history and technical publication evidence.",
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "canonical_source_truth": False,
        "embedding_answer_authority_allowed": False,
    }


def retrieval_only_record() -> dict:
    return {
        "context_record_id": "ctx_route_only",
        "context_pack_role": "retrieval_only",
        "rag_bucket": "context_retrieval_helper",
        "authority": "retrieval_helper_only",
        "page_id": "t_p_120_1176_p000001",
        "citation_id": "cite:helper:not-proof",
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "embedding_answer_authority_allowed": False,
    }


def context_pack_payload() -> dict:
    s1 = support_record()
    s2 = support_record("t_p_120_1176_p000001", "verified_part_evidence", "cite:verified_part:t_p_120_1176_p000001:def")
    route = retrieval_only_record()
    return {
        "schema_version": "trace_net_answer_context_pack_v1",
        "status": "CONTEXT_PACK_BUILT",
        "quality_status": "PASS",
        "query": "Which pages discuss manual revision history?",
        "answer_status": "CONTEXT_PACK_ONLY",
        "answer_composition_allowed": False,
        "llm_answer_allowed": False,
        "summary": {
            "query": "Which pages discuss manual revision history?",
            "answer_status": "CONTEXT_PACK_ONLY",
            "embedding_mode": "ollama",
            "embedding_model_name": "bge-m3:latest",
            "embedding_dim": 1024,
            "context_pack_group_count": 1,
            "context_record_count": 3,
            "answer_support_record_count": 2,
            "retrieval_only_record_count": 1,
        },
        "quality": {"status": "PASS", "checks": []},
        "groups": [
            {
                "rank": 1,
                "page_id": "t_p_120_1176_p000001",
                "hybrid_score": 1.2,
                "answer_support_records": [s1, s2],
                "retrieval_only_records": [route],
                "all_records": [s1, s2, route],
            }
        ],
        "records": [s1, s2, route],
    }


def test_build_claim_from_support_record_is_cited_and_not_final() -> None:
    group = {"rank": 1, "page_id": "t_p_120_1176_p000001", "hybrid_score": 1.0}
    claim = mod.build_claim_from_record(record=support_record(), group=group, query="manual revision history", claim_rank=1)
    assert claim["claim_allowed_for_draft"] is True
    assert claim["citation_ids"] == ["cite:source_text:t_p_120_1176_p000001:abc"]
    assert claim["final_answer_allowed"] is False
    assert claim["llm_freeform_answer_allowed"] is False
    assert claim["can_answer_directly"] is False
    assert claim["retrieval_only_source_used_as_claim"] is False


def test_retrieval_only_record_becomes_note_not_claim() -> None:
    group = {"rank": 1, "page_id": "t_p_120_1176_p000001"}
    note = mod.build_retrieval_only_note(record=retrieval_only_record(), group=group, query="manual revision history")
    assert note["use_status"] == "retrieval_only_excluded_from_claims"
    assert note["can_support_draft_claim"] is False
    assert note["final_answer_allowed"] is False


def test_build_claims_from_context_pack_excludes_retrieval_only() -> None:
    claims, blocked, notes = mod.build_claims_from_context_pack(context_pack_payload(), max_claims=10)
    assert len(claims) == 2
    assert not blocked
    assert len(notes) == 1
    assert {claim["rag_bucket"] for claim in claims} == {"source_text_evidence", "verified_part_evidence"}


def test_build_trace_net_citation_answer_draft_writes_outputs(tmp_path: Path) -> None:
    context_path = tmp_path / "context.json"
    write_json(context_path, context_pack_payload())

    report = mod.build_trace_net_citation_answer_draft(
        context_pack_path=context_path,
        output_dir=tmp_path / "draft",
        min_claims=1,
        require_context_pack_quality_pass=True,
        require_embedding_dim=1024,
        write_quality=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["answer_status"] == "CITATION_DRAFT_ONLY"
    assert report["final_answer_allowed"] is False
    assert report["summary"]["claim_count"] == 2
    assert report["summary"]["uncited_claim_count"] == 0
    assert report["summary"]["retrieval_only_claim_count"] == 0
    assert Path(report["report_path"]).exists()
    assert Path(report["claims_path"]).exists()
    assert Path(report["quality_path"]).exists()


def test_quality_fails_for_uncited_claim() -> None:
    summary = {
        "answer_status": "CITATION_DRAFT_ONLY",
        "final_answer_allowed": False,
        "llm_freeform_answer_allowed": False,
        "context_pack_quality_status": "PASS",
        "context_pack_answer_status": "CONTEXT_PACK_ONLY",
        "embedding_dim": 1024,
        "claim_count": 1,
        "cited_claim_count": 0,
        "uncited_claim_count": 1,
        "retrieval_only_claim_count": 0,
        "page_profile_claim_count": 0,
        "context_helper_claim_count": 0,
        "source_evidence_claim_count": 0,
        "claim_without_authority_count": 0,
        "claim_without_page_id_count": 0,
        "claim_without_citation_count": 1,
        "direct_answer_allowed_claim_count": 0,
        "claim_proof_direct_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "final_answer_allowed_count": 0,
        "llm_freeform_answer_allowed_count": 0,
        "missing_source_resolution_count": 0,
        "missing_authority_gate_count": 0,
        "missing_citation_requirement_count": 0,
    }
    quality = mod.evaluate_draft_quality(summary, min_claims=1)
    assert quality.status == "FAIL"


def test_quality_check_reads_report_and_writes_json(tmp_path: Path) -> None:
    context_path = tmp_path / "context.json"
    write_json(context_path, context_pack_payload())
    report = mod.build_trace_net_citation_answer_draft(
        context_pack_path=context_path,
        output_dir=tmp_path / "draft",
        write_quality=True,
    )
    quality = mod.check_trace_net_citation_answer_draft_quality(
        report_path=Path(report["report_path"]),
        min_claims=1,
        require_context_pack_quality_pass=True,
        require_embedding_dim=1024,
        write_json_result=True,
    )
    assert quality["status"] == "PASS"
    assert Path(quality["quality_path"]).exists()
