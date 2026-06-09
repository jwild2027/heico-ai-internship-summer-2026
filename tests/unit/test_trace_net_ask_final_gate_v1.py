from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_ask_final_gate_v1 import (
    check_ask_final_gate_quality,
    run_ask_final_gate,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def final_gate_payload(**overrides):
    payload = {
        "schema_version": "trace_net_final_answer_gate_v1",
        "status": "FINAL_ANSWER_GATE_RAN",
        "quality_status": "PASS",
        "answer_status": "FINAL_ANSWER_GATE_APPROVED",
        "final_answer_allowed": True,
        "query": "Which pages discuss manual revision history?",
        "final_answer_text": "Page 1 and page 13 contain revision-history evidence. [cite:one]\n\nOCR/source note: review the cited source pages for exact wording.",
        "summary": {
            "query": "Which pages discuss manual revision history?",
            "answer_status": "FINAL_ANSWER_GATE_APPROVED",
            "final_answer_allowed": True,
            "quality_status": "PASS",
            "embedding_mode": "ollama",
            "embedding_model_name": "bge-m3:latest",
            "embedding_dim": 1024,
            "composer_mode": "ollama",
            "llm_model_name": "gemma4:26b",
            "llm_assisted_composition_used": False,
            "llm_candidate_answer_allowed_for_final": False,
            "final_claim_count": 2,
            "cited_final_claim_count": 2,
            "uncited_final_claim_count": 0,
            "retrieval_only_final_claim_count": 0,
            "missing_page_id_count": 0,
            "missing_citation_count": 0,
            "missing_authority_count": 0,
            "local_path_leak_count": 0,
            "raw_bytes_repr_count": 0,
            "boilerplate_leak_count": 0,
            "ocr_uncertainty_note_present": True,
            "source_truth_mutation_allowed_count": 0,
            "llm_freeform_answer_allowed_count": 0,
        },
        "final_claims": [
            {
                "final_claim_rank": 1,
                "final_claim_text": "Page 1 has revision evidence.",
                "page_id": "t_p_120_1176_p000001",
                "rag_bucket": "source_text_evidence",
                "authority": "ocr_text_claim_with_citation",
                "citation_ids": ["cite:one"],
            },
            {
                "final_claim_rank": 2,
                "final_claim_text": "Page 13 has revision evidence.",
                "page_id": "t_p_120_1176_p000013",
                "rag_bucket": "source_text_evidence",
                "authority": "ocr_text_claim_with_citation",
                "citation_ids": ["cite:two"],
            },
        ],
    }
    payload.update(overrides)
    return payload


def test_run_ask_final_gate_exposes_only_passed_final_gate(tmp_path: Path) -> None:
    path = tmp_path / "final_gate.json"
    write_json(path, final_gate_payload())

    report = run_ask_final_gate(
        query="Which pages discuss manual revision history?",
        retrieval_mode="hybrid-simulate",
        answer_mode="final-gate",
        final_answer_report_path=path,
        output_dir=tmp_path / "ask_final",
        require_retrieval_mode="hybrid-simulate",
        require_final_answer_gate_pass=True,
        require_final_answer_allowed=True,
        require_embedding_dim=1024,
    )

    assert report["quality_status"] == "PASS"
    assert report["answer_status"] == "FINAL_ANSWER_DELIVERED_BY_GATE"
    assert report["ask_final_answer_allowed"] is True
    assert "Page 1" in report["final_answer_text"]
    assert Path(report["report_path"]).exists()
    assert Path(report["markdown_path"]).exists()


def test_run_ask_final_gate_blocks_wrong_answer_mode(tmp_path: Path) -> None:
    path = tmp_path / "final_gate.json"
    write_json(path, final_gate_payload())

    report = run_ask_final_gate(
        query="Which pages discuss manual revision history?",
        retrieval_mode="hybrid-simulate",
        answer_mode="off",
        final_answer_report_path=path,
        output_dir=tmp_path / "ask_final",
        require_retrieval_mode="hybrid-simulate",
        require_final_answer_gate_pass=True,
        require_final_answer_allowed=True,
        require_embedding_dim=1024,
    )

    assert report["quality_status"] == "FAIL"
    assert report["answer_status"] == "FINAL_ANSWER_BLOCKED_BY_ASK_FLAG"
    assert report["ask_final_answer_allowed"] is False
    assert report["final_answer_text"] == ""


def test_query_mismatch_fails_quality(tmp_path: Path) -> None:
    path = tmp_path / "final_gate.json"
    write_json(path, final_gate_payload())

    report = run_ask_final_gate(
        query="Different question",
        retrieval_mode="hybrid-simulate",
        answer_mode="final-gate",
        final_answer_report_path=path,
        output_dir=tmp_path / "ask_final",
        require_retrieval_mode="hybrid-simulate",
        require_final_answer_gate_pass=True,
        require_final_answer_allowed=True,
        require_embedding_dim=1024,
    )

    assert report["quality_status"] == "FAIL"
    assert report["summary"]["query_match_status"] == "FAIL"


def test_final_answer_path_leak_blocks_exposure(tmp_path: Path) -> None:
    path = tmp_path / "final_gate.json"
    payload = final_gate_payload(final_answer_text="C:\\Users\\juswil\\secret.tif OCR/source note: review cited pages.")
    payload["summary"]["local_path_leak_count"] = 1
    write_json(path, payload)

    report = run_ask_final_gate(
        query="Which pages discuss manual revision history?",
        retrieval_mode="hybrid-simulate",
        answer_mode="final-gate",
        final_answer_report_path=path,
        output_dir=tmp_path / "ask_final",
        require_retrieval_mode="hybrid-simulate",
        require_final_answer_gate_pass=True,
        require_final_answer_allowed=True,
        require_embedding_dim=1024,
    )

    assert report["quality_status"] == "FAIL"
    assert report["summary"]["local_path_leak_count"] == 1


def test_retrieval_only_final_claim_blocks_exposure(tmp_path: Path) -> None:
    path = tmp_path / "final_gate.json"
    payload = final_gate_payload()
    payload["summary"]["retrieval_only_final_claim_count"] = 1
    payload["final_claims"][0]["rag_bucket"] = "context_retrieval_helper"
    write_json(path, payload)

    report = run_ask_final_gate(
        query="Which pages discuss manual revision history?",
        retrieval_mode="hybrid-simulate",
        answer_mode="final-gate",
        final_answer_report_path=path,
        output_dir=tmp_path / "ask_final",
        require_retrieval_mode="hybrid-simulate",
        require_final_answer_gate_pass=True,
        require_final_answer_allowed=True,
        require_embedding_dim=1024,
    )

    assert report["quality_status"] == "FAIL"
    assert report["summary"]["retrieval_only_final_claim_count"] == 1


def test_quality_check_accepts_written_report(tmp_path: Path) -> None:
    path = tmp_path / "final_gate.json"
    write_json(path, final_gate_payload())
    report = run_ask_final_gate(
        query="Which pages discuss manual revision history?",
        retrieval_mode="hybrid-simulate",
        answer_mode="final-gate",
        final_answer_report_path=path,
        output_dir=tmp_path / "ask_final",
        require_retrieval_mode="hybrid-simulate",
        require_final_answer_gate_pass=True,
        require_final_answer_allowed=True,
        require_embedding_dim=1024,
    )

    quality = check_ask_final_gate_quality(
        report_path=Path(report["report_path"]),
        min_final_claims=1,
        require_retrieval_mode="hybrid-simulate",
        require_final_answer_gate_pass=True,
        require_final_answer_allowed=True,
        require_embedding_dim=1024,
    )
    assert quality["status"] == "PASS"
