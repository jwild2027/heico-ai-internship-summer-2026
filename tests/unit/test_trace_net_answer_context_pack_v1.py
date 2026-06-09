from __future__ import annotations

import json
from pathlib import Path

from tiff import trace_net_answer_context_pack_v1 as mod


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def candidate_record(**updates):
    record = {
        "schema_version": "trace_net_embedding_candidates_v1",
        "embedding_candidate_id": "embcand__1",
        "source_candidate_id": "rag_candidate:source_text_evidence:test",
        "page_id": "t_p_120_1176_p000001",
        "page_number": 1,
        "document_id": "t_p_120_1176",
        "ata_code": "25-21-00",
        "rag_bucket": "source_text_evidence",
        "authority": "source_text_support_only",
        "trust_tier": "B",
        "citation_id": "cite_1",
        "source_url": "https://example.test/source/page1",
        "tiff_path": "page001.tif",
        "ocr_path": "page001.txt",
        "can_answer_directly": False,
        "can_prove_claims": False,
        "canonical_source_truth": False,
        "can_mutate_source_truth": False,
        "embedding_answer_authority_allowed": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "embedding_text": "Source-backed revision history text for page one.",
    }
    record.update(updates)
    return record


def page_profile_record(**updates):
    record = {
        "schema_version": "trace_net_page_retrieval_profiles_v1",
        "profile_id": "page_profile__1",
        "page_id": "t_p_120_1176_p000001",
        "page_number": 1,
        "document_id": "t_p_120_1176",
        "ata_code": "25-21-00",
        "rag_bucket": "page_retrieval_profile",
        "authority": "page_route_only",
        "context_v2_present": True,
        "source_trace_present": True,
        "known_parts": ["120-11111-001"],
        "known_nomenclature": ["PLACARD"],
        "retrieval_cues": ["manual revision history"],
        "query_tunnel_terms": ["Revision 4"],
        "can_answer_directly": False,
        "can_prove_claims": False,
        "canonical_source_truth": False,
        "can_mutate_source_truth": False,
        "embedding_answer_authority_allowed": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "embedding_text": "Page-level route profile for manual revision history.",
    }
    record.update(updates)
    return record


def ask_report(**updates):
    report = {
        "schema_version": "trace_net_ask_hybrid_flag_v1",
        "status": "ASK_RAN",
        "quality_status": "PASS",
        "query": "Which pages discuss manual revision history?",
        "summary": {
            "retrieval_mode": "hybrid-simulate",
            "answer_status": "NOT_COMPOSED_SIMULATION_ONLY",
            "regression_quality_status": "PASS",
            "hybrid_quality_status": "PASS",
            "embedding_mode": "ollama",
            "embedding_model_name": "bge-m3:latest",
            "embedding_dim": 1024,
        },
    }
    report.update(updates)
    return report


def hybrid_report():
    candidate_hit = {
        "collection_role": "candidate",
        "rank": 1,
        "score": 0.91,
        "page_id": "t_p_120_1176_p000001",
        "rag_bucket": "source_text_evidence",
        "embedding_candidate_id": "embcand__1",
        "source_candidate_id": "rag_candidate:source_text_evidence:test",
        "citation_id": "cite_1",
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "unsafe_reasons": [],
    }
    page_hit = {
        "collection_role": "page_profile",
        "rank": 1,
        "score": 0.88,
        "page_id": "t_p_120_1176_p000001",
        "rag_bucket": "page_retrieval_profile",
        "profile_id": "page_profile__1",
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "unsafe_reasons": [],
    }
    group = {
        "rank": 1,
        "page_id": "t_p_120_1176_p000001",
        "page_number": 1,
        "document_id": "t_p_120_1176",
        "ata_code": "25-21-00",
        "hybrid_score": 1.79,
        "safety_status": "retrieval_safe",
        "answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "page_profile_hits": [page_hit],
        "candidate_hits": [candidate_hit],
        "unsafe_reasons": [],
    }
    return {
        "schema_version": "trace_net_hybrid_retrieval_sim_v1",
        "status": "SIM_RAN",
        "quality": {"status": "PASS", "checks": []},
        "summary": {
            "hybrid_quality_status": "PASS",
            "embedding_mode": "ollama",
            "embedding_model_name": "bge-m3:latest",
            "embedding_dim": 1024,
            "candidate_collection_count": 1476,
            "page_profile_collection_count": 509,
        },
        "query_results": [
            {
                "query_id": "inline_001",
                "query": "Which pages discuss manual revision history?",
                "ranked_groups": [group],
            }
        ],
    }


def artifact_payload(records):
    return {"schema_version": "artifact", "quality_status": "PASS", "record_count": len(records), "records": records}


def write_fixture_files(tmp_path: Path):
    ask_path = tmp_path / "ask.json"
    hybrid_path = tmp_path / "hybrid.json"
    candidates_path = tmp_path / "candidates.json"
    profiles_path = tmp_path / "profiles.json"
    write_json(ask_path, ask_report(hybrid_report_path=str(hybrid_path)))
    write_json(hybrid_path, hybrid_report())
    write_json(candidates_path, artifact_payload([candidate_record()]))
    write_json(profiles_path, artifact_payload([page_profile_record()]))
    return ask_path, hybrid_path, candidates_path, profiles_path


def test_build_context_pack_separates_answer_support_and_retrieval_only(tmp_path: Path) -> None:
    ask_path, hybrid_path, candidates_path, profiles_path = write_fixture_files(tmp_path)
    report = mod.build_trace_net_answer_context_pack(
        ask_report_path=ask_path,
        hybrid_report_path=hybrid_path,
        embedding_candidates_path=candidates_path,
        page_profiles_path=profiles_path,
        output_dir=tmp_path / "out",
        write_quality=True,
    )
    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["context_pack_group_count"] == 1
    assert summary["answer_support_record_count"] == 1
    assert summary["retrieval_only_record_count"] == 1
    assert summary["unsafe_record_count"] == 0
    group = report["groups"][0]
    assert group["answer_composition_allowed"] is False
    assert group["answer_support_records"][0]["rag_bucket"] == "source_text_evidence"
    assert group["retrieval_only_records"][0]["rag_bucket"] == "page_retrieval_profile"
    assert Path(report["report_path"]).exists()
    assert Path(report["records_jsonl_path"]).exists()


def test_answer_support_missing_citation_fails_quality(tmp_path: Path) -> None:
    ask_path, hybrid_path, candidates_path, profiles_path = write_fixture_files(tmp_path)
    write_json(candidates_path, artifact_payload([candidate_record(citation_id="", source_url="", tiff_path="")]))
    payload = hybrid_report()
    hit = payload["query_results"][0]["ranked_groups"][0]["candidate_hits"][0]
    hit["citation_id"] = ""
    hit["source_url"] = ""
    write_json(hybrid_path, payload)
    report = mod.build_trace_net_answer_context_pack(
        ask_report_path=ask_path,
        hybrid_report_path=hybrid_path,
        embedding_candidates_path=candidates_path,
        page_profiles_path=profiles_path,
        output_dir=tmp_path / "out",
        write_quality=True,
    )
    assert report["quality_status"] == "FAIL"
    assert report["summary"]["answer_support_record_count"] == 0
    assert report["summary"]["unsafe_record_count"] >= 1


def test_context_helper_stays_retrieval_only(tmp_path: Path) -> None:
    ask_path, hybrid_path, candidates_path, profiles_path = write_fixture_files(tmp_path)
    context_record = candidate_record(
        embedding_candidate_id="ctx_1",
        source_candidate_id="ctx_source_1",
        rag_bucket="context_retrieval_helper",
        authority="retrieval_helper_only",
        citation_id="cite_ctx",
    )
    payload = hybrid_report()
    hit = payload["query_results"][0]["ranked_groups"][0]["candidate_hits"][0]
    hit["embedding_candidate_id"] = "ctx_1"
    hit["source_candidate_id"] = "ctx_source_1"
    hit["rag_bucket"] = "context_retrieval_helper"
    write_json(hybrid_path, payload)
    write_json(candidates_path, artifact_payload([context_record]))
    report = mod.build_trace_net_answer_context_pack(
        ask_report_path=ask_path,
        hybrid_report_path=hybrid_path,
        embedding_candidates_path=candidates_path,
        page_profiles_path=profiles_path,
        output_dir=tmp_path / "out",
        min_answer_support_records=0,
    )
    assert report["summary"]["context_helper_record_count"] == 1
    assert report["summary"]["context_helper_answer_allowed_count"] == 0
    assert report["groups"][0]["retrieval_only_record_count"] == 2


def test_same_page_answer_support_expansion_adds_safe_support_when_hits_are_route_only(tmp_path: Path) -> None:
    ask_path, hybrid_path, candidates_path, profiles_path = write_fixture_files(tmp_path)
    source_locator = candidate_record(
        embedding_candidate_id="source_locator_1",
        source_candidate_id="rag_candidate:source_evidence:test",
        rag_bucket="source_evidence",
        authority="source_exists_only",
        citation_id="cite_source",
        embedding_text="Page source locator, not answer proof.",
    )
    source_text = candidate_record(
        embedding_candidate_id="source_text_1",
        source_candidate_id="rag_candidate:source_text_evidence:test-expanded",
        rag_bucket="source_text_evidence",
        authority="source_text_support_only",
        citation_id="cite_text",
        source_url="https://example.test/source/page1#text",
        embedding_text="Source-backed page text that can support a future citation-gated answer.",
    )
    payload = hybrid_report()
    hit = payload["query_results"][0]["ranked_groups"][0]["candidate_hits"][0]
    hit["embedding_candidate_id"] = "source_locator_1"
    hit["source_candidate_id"] = "rag_candidate:source_evidence:test"
    hit["rag_bucket"] = "source_evidence"
    hit["authority"] = "source_exists_only"
    write_json(hybrid_path, payload)
    write_json(candidates_path, artifact_payload([source_locator, source_text]))

    report = mod.build_trace_net_answer_context_pack(
        ask_report_path=ask_path,
        hybrid_report_path=hybrid_path,
        embedding_candidates_path=candidates_path,
        page_profiles_path=profiles_path,
        output_dir=tmp_path / "out",
        write_quality=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["answer_support_record_count"] == 1
    assert report["summary"]["source_evidence_answer_allowed_count"] == 0
    assert report["summary"]["answer_support_expansion_record_count"] == 1
    group = report["groups"][0]
    assert group["answer_support_expansion_record_count"] == 1
    support = group["answer_support_records"][0]
    assert support["rag_bucket"] == "source_text_evidence"
    assert support["context_pack_expansion_source"] == mod.ANSWER_SUPPORT_EXPANSION_SOURCE
    assert support["llm_context_allowed"] is True
    assert support["can_answer_directly"] is False


def test_same_page_answer_support_expansion_skips_unsafe_support_candidates(tmp_path: Path) -> None:
    ask_path, hybrid_path, candidates_path, profiles_path = write_fixture_files(tmp_path)
    source_locator = candidate_record(
        embedding_candidate_id="source_locator_1",
        source_candidate_id="rag_candidate:source_evidence:test",
        rag_bucket="source_evidence",
        authority="source_exists_only",
        citation_id="cite_source",
    )
    unsafe_source_text = candidate_record(
        embedding_candidate_id="unsafe_source_text_1",
        source_candidate_id="rag_candidate:source_text_evidence:unsafe",
        rag_bucket="source_text_evidence",
        citation_id="",
        source_url="",
        tiff_path="",
    )
    payload = hybrid_report()
    hit = payload["query_results"][0]["ranked_groups"][0]["candidate_hits"][0]
    hit["embedding_candidate_id"] = "source_locator_1"
    hit["source_candidate_id"] = "rag_candidate:source_evidence:test"
    hit["rag_bucket"] = "source_evidence"
    write_json(hybrid_path, payload)
    write_json(candidates_path, artifact_payload([source_locator, unsafe_source_text]))

    report = mod.build_trace_net_answer_context_pack(
        ask_report_path=ask_path,
        hybrid_report_path=hybrid_path,
        embedding_candidates_path=candidates_path,
        page_profiles_path=profiles_path,
        output_dir=tmp_path / "out",
        min_answer_support_records=0,
        write_quality=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["answer_support_record_count"] == 0
    assert report["summary"]["answer_support_expansion_record_count"] == 0
    assert report["summary"]["source_evidence_answer_allowed_count"] == 0


def test_check_quality_reads_written_report(tmp_path: Path) -> None:
    ask_path, hybrid_path, candidates_path, profiles_path = write_fixture_files(tmp_path)
    report = mod.build_trace_net_answer_context_pack(
        ask_report_path=ask_path,
        hybrid_report_path=hybrid_path,
        embedding_candidates_path=candidates_path,
        page_profiles_path=profiles_path,
        output_dir=tmp_path / "out",
        write_quality=True,
    )
    quality = mod.check_trace_net_answer_context_pack_quality(report_path=Path(report["report_path"]), write_json_report=True)
    assert quality["status"] == "PASS"
    assert Path(quality["quality_path"]).exists()


def test_quality_fails_when_retrieval_only_can_answer() -> None:
    summary = {
        "context_pack_group_count": 1,
        "context_record_count": 1,
        "answer_support_record_count": 1,
        "retrieval_only_record_count": 1,
        "ask_quality_status": "PASS",
        "hybrid_quality_status": "PASS",
        "regression_quality_status": "PASS",
        "embedding_dim": 1024,
        "missing_page_id_count": 0,
        "missing_source_candidate_id_count": 0,
        "missing_citation_required_count": 0,
        "retrieval_only_answer_allowed_count": 1,
        "page_profile_answer_allowed_count": 0,
        "context_helper_answer_allowed_count": 0,
        "source_evidence_answer_allowed_count": 0,
        "direct_answer_allowed_record_count": 0,
        "claim_proof_without_authority_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "answer_composition_allowed_count": 0,
        "llm_answer_allowed_count": 0,
        "unsafe_group_count": 0,
        "unsafe_record_count": 0,
    }
    assert mod.evaluate_context_pack_quality(summary).status == "FAIL"
