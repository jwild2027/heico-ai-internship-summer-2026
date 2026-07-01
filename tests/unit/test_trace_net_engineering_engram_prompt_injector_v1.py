from pathlib import Path
import json

from tiff.trace_net_engineering_llm_answer_smoke_v1 import (
    build_engram_prompt_block,
    build_llm_prompt,
    select_engram_atoms,
    _build_reasoning_trace,
    _load_engram_core,
)


def _engram_core():
    return {
        "quality_status": "PASS",
        "records": [
            {
                "engram_id": "policy_no_interchangeability_without_authority_v1",
                "memory_type": "policy_trait",
                "priority": "hard_boundary",
                "trait": "source_trace_caution",
                "triggers": ["interchangeability", "replacement approval", "shared nomenclature"],
                "trigger_text": "interchangeability | replacement approval | shared nomenclature",
                "rule": "Shared nomenclature is not proof of interchangeability.",
                "good_behavior": "Say not proven, then list what TRACE-Net can prove.",
                "bad_behavior": "Treating shared names as compatibility approval.",
                "status": "active",
            },
            {
                "engram_id": "route_visual_link_vs_ocr_nomenclature_v1",
                "memory_type": "route_behavior",
                "priority": "high",
                "trait": "route_awareness",
                "triggers": ["visual route", "OCR nomenclature", "nomenclature missing"],
                "rule": "visual_figure_link establishes identity; ocr_nomenclature provides line-text proof.",
                "good_behavior": "Explain both routes separately.",
                "status": "active",
            },
        ],
    }


def _context_pack():
    return {
        "records": [
            {
                "proof_context": [
                    {
                        "context_type": "visual_figure_link",
                        "citation_label": "V6",
                        "figure": "69",
                        "part_number": "120-50645-005",
                        "nomenclature": "DOUBLE PASSENGER SEAT ASSY",
                        "source_trace_ready": True,
                    },
                    {
                        "context_type": "ocr_nomenclature",
                        "citation_label": "O1",
                        "figure": "69",
                        "part_number": "120-50645-005",
                        "nomenclature": "DOUBLE PASSENGER SEAT ASSY",
                        "source_trace_ready": True,
                    },
                ],
                "guidance_context": [],
                "answer_constraints": {"summary_guidance_policy": "guidance only"},
            }
        ]
    }


def _runner():
    return {
        "quality_status": "PASS",
        "answer_text": "Figure 69 is linked to part number 120-50645-005 [V6] [O1].",
        "summary": {"task_type": "exact_part_lookup", "required_routes": ["image_or_diagram"]},
    }


def test_select_engram_atoms_prioritizes_interchangeability_policy():
    selected = select_engram_atoms(
        engram_core=_engram_core(),
        question="Is 120-50645-005 interchangeable with 120-50645-011?",
        category="interchangeability",
        task_type="exact_part_lookup",
        max_engram_atoms=2,
    )
    assert selected
    assert selected[0]["engram_id"] == "policy_no_interchangeability_without_authority_v1"


def test_build_engram_prompt_block_marks_memory_as_not_proof():
    block = build_engram_prompt_block(_engram_core()["records"][:1])
    assert "behavior guidance only" in block
    assert "NOT source proof" in block
    assert "policy_no_interchangeability_without_authority_v1" in block


def test_build_llm_prompt_injects_engram_without_replacing_proof_context():
    prompt = build_llm_prompt(
        question="Is 120-50645-005 interchangeable with 120-50645-011?",
        category="interchangeability",
        runner_manifest=_runner(),
        context_pack=_context_pack(),
        engram_core=_engram_core(),
        max_engram_atoms=2,
    )
    assert "TRACE_NET_ENGINEERING_ENGRAM_MEMORY" in prompt
    assert "Engram memory may guide behavior" in prompt
    assert "policy_no_interchangeability_without_authority_v1" in prompt
    assert "PROOF_CONTEXT:" in prompt
    assert "[V6]" in prompt and "[O1]" in prompt


def test_safe_reasoning_trace_records_selected_engram_ids(tmp_path):
    selected = select_engram_atoms(
        engram_core=_engram_core(),
        question="Why was nomenclature missing from the visual route evidence?",
        category="troubleshooting",
        task_type="troubleshooting_question",
        max_engram_atoms=2,
    )
    trace = _build_reasoning_trace(
        question_id="q16",
        category="troubleshooting",
        question="Why was nomenclature missing from the visual route evidence?",
        runner_manifest=_runner(),
        context_pack=_context_pack(),
        prompt_path=tmp_path / "prompt.txt",
        answer_path=tmp_path / "answer.txt",
        prompt="TRACE_NET_ENGINEERING_ENGRAM_MEMORY\nSTRUCTURED_TRACE_NET_SCAFFOLD\nINTENT_RULE: test",
        answer_text="Answer [V6] [O1]",
        eval_result={"grade": "GOOD", "llm_answered": True},
        llm_error="",
        selected_engram_atoms=selected,
    )
    assert trace["trace_type"] == "safe_reasoning_trace_not_hidden_chain_of_thought"
    assert trace["engram_atom_count"] == len(selected)
    assert trace["engram_ids"]
    assert "not source proof" in trace["engram_note"]


def test_load_engram_core_rejects_failed_manifest(tmp_path):
    p = tmp_path / "bad_engram.json"
    p.write_text(json.dumps({"quality_status": "FAIL", "records": []}), encoding="utf-8")
    try:
        _load_engram_core(p)
    except ValueError as exc:
        assert "quality_status is not PASS" in str(exc)
    else:
        raise AssertionError("expected ValueError")
