from __future__ import annotations

import json
from pathlib import Path

import pytest

from tiff import trace_net_final_answer_gate_v1 as mod


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def clean_claim(rank: int = 1, *, bucket: str = "source_text_evidence", citation: str = "cite:source_text:p000001:abc", page_id: str = "t_p_120_1176_p000001", snippet: str = "Revision 4 dated 10 April 2006 appears in the technical publication title and revision block.") -> dict:
    return {
        "clean_snippet_claim_id": f"clean_{rank}",
        "schema_version": "trace_net_evidence_snippet_cleaner_v1",
        "answer_status": "CLEAN_SNIPPETS_ONLY",
        "query": "Which pages discuss manual revision history?",
        "clean_snippet_rank": rank,
        "page_id": page_id,
        "page_number": int(page_id.rsplit("p", 1)[-1]) if page_id.rsplit("p", 1)[-1].isdigit() else rank,
        "document_id": "t_p_120_1176",
        "ata_code": "25-21-00",
        "rag_bucket": bucket,
        "authority": "ocr_text_claim_with_citation" if bucket == "source_text_evidence" else "part_page_relationship",
        "trust_tier": "B",
        "citation_ids": [citation] if citation else [],
        "citation_id": citation,
        "clean_source_snippet": snippet,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
        "llm_freeform_answer_allowed": False,
        "retrieval_only_source_used_as_claim": False,
        "final_answer_allowed": False,
    }


def cleaner_payload(claims: list[dict] | None = None) -> dict:
    claims = claims or [
        clean_claim(1),
        clean_claim(
            2,
            bucket="verified_part_evidence",
            citation="cite:verified_part:p000001:def",
            snippet="Part 120-12345-001 is associated with page-level verified part/page evidence.",
        ),
    ]
    return {
        "schema_version": "trace_net_evidence_snippet_cleaner_v1",
        "status": "CLEAN_SNIPPETS_BUILT",
        "quality_status": "PASS",
        "answer_status": "CLEAN_SNIPPETS_ONLY",
        "summary": {
            "query": "Which pages discuss manual revision history?",
            "answer_status": "CLEAN_SNIPPETS_ONLY",
            "clean_snippet_claim_count": len(claims),
            "quality_status": "PASS",
            "embedding_mode": "ollama",
            "embedding_model_name": "bge-m3:latest",
            "embedding_dim": 1024,
            "local_path_leak_count": 0,
            "raw_bytes_repr_count": 0,
        },
        "quality": {"status": "PASS", "checks": []},
        "clean_snippet_claims": claims,
    }


def test_build_final_answer_gate_passes_for_clean_cited_claims(tmp_path: Path) -> None:
    payload = cleaner_payload()
    report = mod.build_final_answer_gate_report(
        clean_snippet_payload=payload,
        min_final_claims=1,
        require_clean_snippet_quality_pass=True,
        require_clean_snippet_answer_status="CLEAN_SNIPPETS_ONLY",
        require_embedding_dim=1024,
        require_final_answer_allowed=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["answer_status"] == "FINAL_ANSWER_GATE_APPROVED"
    assert report["final_answer_allowed"] is True
    assert report["summary"]["final_claim_count"] == 2
    assert report["summary"]["uncited_final_claim_count"] == 0
    assert report["summary"]["retrieval_only_final_claim_count"] == 0
    assert report["summary"]["ocr_uncertainty_note_present"] is True
    assert "cite:source_text:p000001:abc" in report["final_answer_text"]


def test_retrieval_only_claim_is_blocked(tmp_path: Path) -> None:
    payload = cleaner_payload([
        clean_claim(bucket="context_retrieval_helper", citation="cite:ctx:x", snippet="routing-only helper text"),
    ])
    report = mod.build_final_answer_gate_report(clean_snippet_payload=payload, min_final_claims=1)

    assert report["quality_status"] == "FAIL"
    assert report["final_answer_allowed"] is False
    assert report["summary"]["final_claim_count"] == 0
    assert report["blocked_final_claims"]
    assert "bucket_not_allowed_for_final_answer" in report["blocked_final_claims"][0]["block_reasons"]


def test_uncited_claim_is_blocked() -> None:
    payload = cleaner_payload([clean_claim(citation="")])
    report = mod.build_final_answer_gate_report(clean_snippet_payload=payload)

    assert report["quality_status"] == "FAIL"
    assert report["summary"]["final_claim_count"] == 0
    assert any("missing_citation" in item["block_reasons"] for item in report["blocked_final_claims"])


def test_local_path_leak_blocks_final_claim() -> None:
    payload = cleaner_payload([
        clean_claim(snippet="Manual evidence C:\\Users\\juswil\\Documents\\heico-local-data\\file.tif should not leak."),
    ])
    report = mod.build_final_answer_gate_report(clean_snippet_payload=payload)

    assert report["quality_status"] == "FAIL"
    assert report["summary"]["final_claim_count"] == 0
    assert any("clean_source_snippet_contains_forbidden_text" in item["block_reasons"] for item in report["blocked_final_claims"])


def test_run_final_answer_gate_writes_outputs(tmp_path: Path) -> None:
    clean_path = tmp_path / "clean.json"
    out_dir = tmp_path / "out"
    write_json(clean_path, cleaner_payload())

    report = mod.run_final_answer_gate(
        clean_snippets_path=clean_path,
        output_dir=out_dir,
        min_final_claims=1,
        require_clean_snippet_quality_pass=True,
        require_clean_snippet_answer_status="CLEAN_SNIPPETS_ONLY",
        require_embedding_dim=1024,
        require_final_answer_allowed=True,
    )

    assert report["quality_status"] == "PASS"
    assert Path(report["report_path"]).exists()
    assert Path(report["markdown_path"]).exists()
    assert Path(report["html_path"]).exists()
    loaded = json.loads(Path(report["report_path"]).read_text(encoding="utf-8"))
    assert loaded["summary"]["final_claim_count"] == 2


def test_ollama_mode_stores_advisory_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_call(**kwargs):
        return (
            "Page 1 has revision evidence [cite:source_text:p000001:abc]. OCR may contain noise; review cited pages.",
            {"response": "ok"},
        )

    monkeypatch.setattr(mod, "call_ollama_generate", fake_call)
    report = mod.build_final_answer_gate_report(
        clean_snippet_payload=cleaner_payload([clean_claim()]),
        composer_mode="ollama",
        llm_model="gemma4:26b",
        allow_llm_final_text=False,
        min_final_claims=1,
        require_final_answer_allowed=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["llm_assisted_composition_used"] is True
    assert report["summary"]["llm_model_name"] == "gemma4:26b"
    assert report["llm_candidate_answer"]
    # Conservative default: Gemma draft is advisory; gated template remains final.
    assert report["summary"]["llm_candidate_answer_allowed_for_final"] is False
    assert report["final_answer_text"] == report["template_final_answer_text"]


def test_llm_final_text_can_be_used_when_explicitly_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    text = "Page 1 has revision evidence [cite:source_text:p000001:abc]. OCR may contain noise; review cited pages."
    monkeypatch.setattr(mod, "call_ollama_generate", lambda **kwargs: (text, {"response": text}))
    report = mod.build_final_answer_gate_report(
        clean_snippet_payload=cleaner_payload([clean_claim()]),
        composer_mode="ollama",
        llm_model="gemma4:26b",
        allow_llm_final_text=True,
        min_final_claims=1,
        require_final_answer_allowed=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["llm_candidate_answer_allowed_for_final"] is True
    assert report["final_answer_text"] == text
