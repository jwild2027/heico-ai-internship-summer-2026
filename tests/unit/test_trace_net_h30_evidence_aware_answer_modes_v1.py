import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(
    "scripts/trace_net_h30_evidence_aware_answer_modes_v1.py"
)
WRITER_PATH = Path(
    "scripts/serve_trace_net_full_gemma_cognitive_v1.py"
)
LAUNCHER_PATH = Path(
    "scripts/launch_trace_net_cognitive_openwebui_v1.sh"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "trace_net_phase5_answer_modes_test",
        MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def record(
    bucket,
    *,
    modality="textual_source",
    support=False,
    conflict=False,
    candidate="",
    page="",
    claims=None,
):
    return {
        "source_bucket": bucket,
        "modality": modality,
        "claim_support_allowed": support,
        "guidance_only": not support,
        "conflicted": conflict,
        "claim_types": list(claims or []),
        "identity": {
            "candidate": candidate,
            "part_numbers": [candidate] if candidate else [],
            "figure_refs": ["2"] if modality == "visual" else [],
        },
        "source_trace": {
            "page_id": page,
            "ready": support,
        },
        "excerpt": "example evidence",
    }


def result(route, records):
    return {
        "route": route,
        "writer_mode": "deterministic_fail_closed",
        "query_atoms": {
            "identifier_mode": "contains",
            "normalized_identifier": "41824",
        },
        "evidence_envelope": {
            "typed_evidence": records,
        },
        "follow_up_questions": [
            "What additional characters do you remember?"
        ],
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }


def test_disabled_by_default():
    module = load_module()
    assert module.load_answer_mode_config({})["enabled"] is False


def test_confirmed_requires_claim_supporting_direct_record():
    module = load_module()
    sample = result(
        "exact_identifier_lookup",
        [
            record(
                "direct_evidence",
                support=True,
                candidate="120-41824-003",
                page="t_p_demo_p1",
                claims=["part_identity"],
            )
        ],
    )
    decision = module.classify_answer_mode(sample)
    assert decision["mode"] == module.MODE_CONFIRMED_DIRECT
    assert decision["gemma_writing_allowed"] is True


def test_direct_without_claim_support_is_not_confirmed():
    module = load_module()
    sample = result(
        "exact_identifier_lookup",
        [record("direct_evidence", support=False)],
    )
    decision = module.classify_answer_mode(sample)
    assert decision["mode"] == module.MODE_NO_EVIDENCE


def test_candidate_mode_is_deterministic():
    module = load_module()
    sample = result(
        "guided_part_discovery",
        [
            record(
                "candidate_evidence",
                candidate="120-41824-003",
            )
        ],
    )
    decision = module.classify_answer_mode(sample)
    text = module.render_deterministic_mode(
        sample,
        decision,
    )
    assert decision["mode"] == module.MODE_CANDIDATE
    assert decision["gemma_writing_allowed"] is False
    assert "not a final identification" in text
    assert "120-41824-003" in text


def test_visual_mode_is_guidance_only():
    module = load_module()
    sample = result(
        "visual_figure_callout_lookup",
        [
            record(
                "visual_guidance",
                modality="visual",
                page="t_p_demo_p2",
            )
        ],
    )
    decision = module.classify_answer_mode(sample)
    text = module.render_deterministic_mode(
        sample,
        decision,
    )
    assert decision["mode"] == module.MODE_VISUAL
    assert "no citation-ready direct source proof" in text


def test_semantic_graph_summary_mode_is_guidance_only():
    module = load_module()
    sample = result(
        "semantic_discovery",
        [
            record(
                "semantic_guidance",
                modality="graph",
                page="t_p_demo_p3",
            )
        ],
    )
    decision = module.classify_answer_mode(sample)
    assert decision["mode"] == module.MODE_SEMANTIC
    assert decision["deterministic_rendering_required"] is True


def test_conflict_precedes_candidate_without_direct_support():
    module = load_module()
    sample = result(
        "guided_part_discovery",
        [
            record(
                "candidate_evidence",
                candidate="120-41824-003",
            ),
            record(
                "contradictions",
                modality="conflict",
                conflict=True,
            ),
        ],
    )
    decision = module.classify_answer_mode(sample)
    assert decision["mode"] == module.MODE_CONFLICT


def test_authority_route_without_authority_support_fails_closed():
    module = load_module()
    sample = result(
        "authority_eligibility_verification",
        [
            record(
                "candidate_evidence",
                candidate="120-41824-003",
            )
        ],
    )
    decision = module.classify_answer_mode(sample)
    text = module.render_deterministic_mode(
        sample,
        decision,
    )
    assert decision["mode"] == module.MODE_AUTHORITY_MISSING
    assert "did not find direct authority evidence" in text


def test_no_evidence_mode_is_deterministic():
    module = load_module()
    sample = result("clarification_no_evidence", [])
    decision = module.classify_answer_mode(sample)
    assert decision["mode"] == module.MODE_NO_EVIDENCE
    assert decision["gemma_writing_allowed"] is False


def test_general_chat_is_passthrough():
    module = load_module()
    sample = result("safe_general_chat", [])
    decision = module.classify_answer_mode(sample)
    assert decision["mode"] == module.MODE_GENERAL_CHAT
    assert decision["deterministic_rendering_required"] is False


def test_validation_rejects_confirmed_without_support():
    module = load_module()
    sample = result("exact_identifier_lookup", [])
    decision = module.classify_answer_mode(sample)
    decision["mode"] = module.MODE_CONFIRMED_DIRECT
    check = module.validate_mode_result(sample, decision)
    assert check["quality_status"] == "FAIL"
    assert (
        "confirmed_mode_without_claim_supporting_direct_evidence"
        in check["failures"]
    )


def test_safety_contract_is_read_only():
    module = load_module()
    health = module.answer_modes_health(
        {
            "TRACE_NET_H30_EVIDENCE_AWARE_ANSWER_MODES_ENABLED": "1"
        }
    )
    assert health["quality_status"] == "PASS"
    assert health["answer_permission"] is False
    assert health["source_truth_mutation_allowed"] is False
    assert health["write_attempt_count"] == 0


def test_runtime_files_are_wired():
    writer = WRITER_PATH.read_text(encoding="utf-8")
    launcher = LAUNCHER_PATH.read_text(encoding="utf-8")
    assert "install_evidence_aware_answer_modes" in writer
    assert (
        "TRACE_NET_H30_EVIDENCE_AWARE_ANSWER_MODES_ENABLED"
        in launcher
    )
    assert (
        "test_trace_net_h30_evidence_aware_answer_modes_v1.py"
        in launcher
    )
