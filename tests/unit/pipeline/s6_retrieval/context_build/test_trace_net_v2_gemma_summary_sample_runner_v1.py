from __future__ import annotations

import json
from pathlib import Path

import pytest

import tiff.trace_net_v2_gemma_summary_sample_runner_v1 as runner


def test_page_id_from_number() -> None:
    assert runner.page_id_from_number(48) == "t_p_120_1176_p000048"


def test_validate_requires_llm_when_enabled() -> None:
    card = {
        "page_id": "t_p_120_1176_p000048",
        "role": "table",
        "subrole": "parts_list",
        "confidence": "medium",
        "short_summary": "Gemma summary.",
        "retrieval_summary": "Gemma retrieval guidance.",
        "answerable_questions": ["What page may be relevant?"],
        "retrieval_cues": ["parts list"],
        "important_entities": [],
        "component_families": [],
        "source_grounding": {"has_ocr": True, "source_url_present": True, "supporting_ocr_phrases": []},
        "not_good_for": ["direct proof"],
        "authority": {
            "trust_scope": "page_context_summary",
            "can_answer_directly": False,
            "canonical_source_truth": False,
            "requires_source_check": True,
            "source_truth_mutation_allowed": False,
        },
        "prompt_version": "page_context_v2_query_guidance_card",
        "generation_provider": "heuristic",
        "generation_model": "heuristic_context_v2",
        "llm_called": False,
    }

    result = runner.validate_card(card, require_llm_called=True)

    assert result["quality_status"] == "FAIL"
    assert "required_gemma_llm_not_called" in result["failure_reasons"]


def test_build_gemma_sample_with_monkeypatched_ollama(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    context_file = tmp_path / "page_contexts.json"
    records = {}
    for n in range(1, 6):
        pid = f"t_p_120_1176_p{n:06d}"
        records[pid] = {
            "page_id": pid,
            "role": "table" if n % 2 == 0 else "figure",
            "summary": f"Sample page {n} for passenger seat parts and figure/table guidance.",
            "text": f"FIGURE {n} PASSENGER SEAT PARTS LIST ARMREST BACKREST 120-36833-00{n}",
            "source_url": f"file:///sample/{n:08d}.tif",
        }
    context_file.write_text(json.dumps(records), encoding="utf-8")

    import tiff.trace_net_page_context_v2 as existing_v2

    def fake_call_ollama(prompt: str, model: str, url: str, timeout: int = 240, temperature: float = 0.0) -> str:
        return json.dumps(
            {
                "role": "figure",
                "subrole": "illustration_or_figure",
                "confidence": "medium",
                "short_summary": "Gemma4 generated a page guidance summary.",
                "retrieval_summary": "Use this page for passenger seat figure/table retrieval guidance.",
                "answerable_questions": ["Which page may discuss passenger seat parts?"],
                "retrieval_cues": ["passenger seat", "parts list", "figure"],
                "important_entities": ["120-36833-001"],
                "component_families": ["passenger seat"],
                "source_grounding": {
                    "has_ocr": True,
                    "source_url_present": True,
                    "supporting_ocr_phrases": ["PASSENGER SEAT PARTS LIST"],
                },
                "not_good_for": ["direct proof without source page"],
                "authority": {
                    "trust_scope": "page_context_summary",
                    "can_answer_directly": False,
                    "canonical_source_truth": False,
                    "requires_source_check": True,
                },
            }
        )

    monkeypatch.setattr(existing_v2, "call_ollama", fake_call_ollama)

    report = runner.build_v2_gemma_summary_sample(
        context_file=context_file,
        output_dir=tmp_path / "out",
        max_pages=5,
        model="gemma4:26b",
        require_gemma=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["sample_record_count"] == 5
    assert report["summary"]["llm_called_count"] == 5
    assert report["summary"]["gemma_success_count"] == 5
    assert all(rec["generation_model"] == "gemma4:26b" for rec in report["records"])
    assert all(rec["llm_called"] is True for rec in report["records"])
    assert all(rec["authority"]["can_answer_directly"] is False for rec in report["records"])


def test_quality_check_passes_for_monkeypatched_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    context_file = tmp_path / "page_contexts.json"
    context_file.write_text(
        json.dumps(
            [
                {
                    "page_id": f"t_p_120_1176_p{n:06d}",
                    "role": "normal_text",
                    "summary": f"Page {n} OCR text.",
                    "ocr_text": f"NOTE PASSENGER SEAT PAGE {n} PART 120-36833-00{n}",
                    "source_url": f"file:///sample/{n:08d}.tif",
                }
                for n in range(1, 6)
            ]
        ),
        encoding="utf-8",
    )

    import tiff.trace_net_page_context_v2 as existing_v2

    def fake_call_ollama(prompt: str, model: str, url: str, timeout: int = 240, temperature: float = 0.0) -> str:
        return json.dumps(
            {
                "short_summary": "Gemma4 generated V2 guidance.",
                "retrieval_summary": "Use this page for passenger seat retrieval.",
                "answerable_questions": ["Which page is relevant?"],
                "retrieval_cues": ["passenger seat"],
                "important_entities": ["120-36833-001"],
                "component_families": ["passenger seat"],
                "source_grounding": {"has_ocr": True, "source_url_present": True, "supporting_ocr_phrases": []},
                "not_good_for": ["direct proof"],
                "authority": {"can_answer_directly": False, "canonical_source_truth": False, "requires_source_check": True},
            }
        )

    monkeypatch.setattr(existing_v2, "call_ollama", fake_call_ollama)

    report = runner.build_v2_gemma_summary_sample(
        context_file=context_file,
        output_dir=tmp_path / "out",
        max_pages=5,
    )
    quality = runner.check_v2_gemma_summary_sample_report(
        report_path=tmp_path / "out" / "trace_net_v2_gemma_summary_sample_runner_v1.json",
        output=tmp_path / "out" / "trace_net_v2_gemma_summary_sample_runner_v1_quality.json",
        min_records=5,
        min_gemma_successes=5,
        require_quality_pass=True,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
    )

    assert report["quality_status"] == "PASS"
    assert quality["quality_status"] == "PASS"
