import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(
    "src/trace_net/writing/trace_net_h30_evidence_aware_answer_modes_v1.py"
)
WRITER_PATH = Path(
    "scripts/operations/serving/serve_trace_net_full_gemma_cognitive_v1.py"
)
LAUNCHER_PATH = Path(
    "scripts/operations/launch_trace_net_cognitive_openwebui_v1.sh"
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


# --- Evidence synthesis (Phase 4) -------------------------------------------


def _install_on_fake(module, sample):
    class FakeRuntime:
        _sample = sample

        def process(self, payload):
            return dict(self._sample)

        def health(self):
            return {"quality_status": "PASS"}

    module_dict = {"Runtime": FakeRuntime}
    module.install_evidence_aware_answer_modes(module_dict)
    return FakeRuntime


def test_ensure_mode_disclaimer_inserts_into_body_before_followups():
    module = load_module()
    content = (
        "Found two candidates.\n\n"
        "Helpful follow-up questions:\n- What comes before the fragment?"
    )
    out = module._ensure_mode_disclaimer(content, module.MODE_CANDIDATE)
    # Disclaimer lands in the body, above the follow-up marker (which the
    # final rollout strips and re-adds), and contains the critic's phrase.
    body = out.split(module.FOLLOWUP_MARKER, 1)[0]
    assert "not a final identification" in body.lower()
    assert out.index("not a final identification") < out.index(module.FOLLOWUP_MARKER)


def test_synthesis_answer_is_kept_not_overwritten(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_EVIDENCE_AWARE_ANSWER_MODES_ENABLED", "1")
    module = load_module()
    gemma_answer = (
        "TRACE-Net found candidate identifiers near the hinge figure; the "
        "strongest is 120-41824-003."
    )
    sample = result(
        "guided_part_discovery",
        [record("candidate_evidence", candidate="120-41824-003")],
    )
    sample["content"] = gemma_answer
    sample["gemma_status"] = "LLM_CALL_SUCCEEDED_AND_VALIDATED"
    sample["evidence_synthesis"] = {
        "enabled": True,
        "attempted": True,
        "written": True,
    }
    runtime = _install_on_fake(module, sample)()
    out = runtime.process({})

    # Gemma's synthesis is preserved (not replaced by the deterministic template)
    # and the safety disclaimer is present; the writer status is not downgraded.
    assert "120-41824-003" in out["content"]
    assert "candidate identifiers near the hinge figure" in out["content"]
    assert "not a final identification" in out["content"].lower()
    assert out["gemma_status"] == "LLM_CALL_SUCCEEDED_AND_VALIDATED"
    assert out["writer_mode"] == "evidence_aware_synthesis_candidate_discovery"
    assert out["answer_permission"] is False


def test_without_synthesis_marker_still_renders_deterministically(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_EVIDENCE_AWARE_ANSWER_MODES_ENABLED", "1")
    module = load_module()
    sample = result(
        "guided_part_discovery",
        [record("candidate_evidence", candidate="120-41824-003")],
    )
    sample["content"] = "some raw model text that must not survive"
    sample["gemma_status"] = "SKIPPED_NO_DIRECT_EVIDENCE"
    # No evidence_synthesis marker -> deterministic behavior unchanged.
    runtime = _install_on_fake(module, sample)()
    out = runtime.process({})

    assert out["gemma_status"] == "SKIPPED_BY_TYPED_EVIDENCE_MODE"
    assert out["writer_mode"] == "evidence_aware_candidate_discovery"
    assert "not a final identification" in out["content"].lower()
    assert "must not survive" not in out["content"]


def test_validate_answer_extra_allowed_permits_candidate_identifiers():
    spec = importlib.util.spec_from_file_location(
        "trace_net_full_gemma_writer_test", WRITER_PATH
    )
    writer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = writer
    assert spec and spec.loader
    spec.loader.exec_module(writer)

    result_obj = {
        "route": "guided_part_discovery",
        "evidence_envelope": {
            "candidate_evidence": [
                {"candidate_value": "120-41824-003", "page_id": "t_p_120_1176_p000351"}
            ],
        },
    }
    answer = "The strongest candidate is 120-41824-003, but this is not confirmed."

    # Without extra_allowed the candidate identifier is unsupported (proof-only).
    strict = writer.validate_answer(answer, "The P/N contains 41824", result_obj)
    assert not strict["accepted"]
    assert any(f.startswith("unsupported_part_number") for f in strict["failures"])

    # With synthesis extra_allowed the candidate id AND its source page may be
    # mentioned as leads (q06: candidate page ids must be allowed too).
    extra = writer.synthesis_allowed_identifiers("The P/N contains 41824", result_obj)
    assert "T_P_120_1176_P000351" in extra["pages"]
    lenient = writer.validate_answer(
        "Candidate 120-41824-003 appears on page t_p_120_1176_p000351 (not confirmed).",
        "The P/N contains 41824",
        result_obj,
        extra_allowed=extra,
    )
    assert lenient["accepted"]

    # But a dangerous claim without authority is still blocked in synthesis mode.
    unsafe = writer.validate_answer(
        "120-41824-003 is an approved replacement.",
        "The P/N contains 41824",
        result_obj,
        extra_allowed=extra,
    )
    assert not unsafe["accepted"]
    assert "dangerous_claim_without_explicit_authority" in unsafe["failures"]


def _load_writer():
    spec = importlib.util.spec_from_file_location(
        "trace_net_full_gemma_writer_test", WRITER_PATH
    )
    writer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = writer
    assert spec and spec.loader
    spec.loader.exec_module(writer)
    return writer


def test_citation_registry_allows_guidance_only_citations():
    writer = _load_writer()
    # Guidance-only result (no direct evidence) — the q02/q12 scenario.
    result_obj = {
        "route": "guided_part_discovery",
        "evidence_envelope": {
            "direct_evidence": [],
            "candidate_evidence": [
                {"candidate_value": "120-41824-003", "page_id": "t_p_demo_p1"}
            ],
        },
    }
    registry = writer.citation_registry(result_obj)
    assert len(registry) == 1
    assert registry[0]["authority"] == "guidance"
    assert registry[0]["class"] == "candidate"

    extra = writer.synthesis_allowed_identifiers("The P/N contains 41824", result_obj)
    # Citing the guidance record [1] must be accepted (previously rejected as
    # unknown_citation_id because only direct evidence was citable).
    ok = writer.validate_answer(
        "TRACE-Net found a candidate [1]; this is a candidate, not confirmed.",
        "The P/N contains 41824",
        result_obj,
        extra_allowed=extra,
    )
    assert "unknown_citation_id" not in ok["failures"]

    # A citation beyond the registry is still rejected.
    bad = writer.validate_answer("See [2].", "q", result_obj)
    assert "unknown_citation_id" in bad["failures"]


def _q06_result():
    return {
        "route": "guided_part_discovery",
        "evidence_envelope": {
            "direct_evidence": [
                {
                    "page_id": "t_p_120_1176_p000003",
                    "field_name": "covered_part_number",
                    "value": "120-36833-005",
                }
            ],
            "candidate_evidence": [
                {"candidate_value": "120-29067-005", "page_id": "t_p_120_1176_p000351"},
                {"candidate_value": "120-29068-005", "page_id": "t_p_120_1176_p000398"},
            ],
        },
    }


def test_mixed_direct_candidate_answer_validates_with_per_class_citations():
    # q06: one direct exact hit plus several suffix candidates. Gemma cites the
    # direct hit with its proof id and each candidate with its own guidance id;
    # the answer must validate with no unsupported / uncited failures.
    writer = _load_writer()
    result_obj = _q06_result()
    registry = writer.citation_registry(result_obj)
    assert registry[0]["can_prove_claims"] is True
    assert registry[0]["class"] == "direct_source"
    assert all(entry["guidance_only"] for entry in registry[1:])
    assert writer.citation_registry_digest(registry)

    extra = writer.synthesis_allowed_identifiers("ends with 005", result_obj)
    answer = (
        "## Directly supported\n"
        "Part 120-36833-005 appears on page t_p_120_1176_p000003 [1].\n"
        "## Possible candidates\n"
        "Candidate 120-29067-005 is listed on page t_p_120_1176_p000351 [2].\n"
        "Candidate 120-29068-005 is listed on page t_p_120_1176_p000398 [3]."
    )
    v = writer.validate_answer(
        answer, "ends with 005", result_obj, extra_allowed=extra, registry=registry
    )
    assert v["accepted"], v["failures"]
    assert "uncited_factual_line" not in v["failures"]
    assert not any(f.startswith("unsupported_") for f in v["failures"])


def test_candidate_factual_line_without_citation_is_rejected():
    # Negative: a candidate factual line with no citation must still fail
    # uncited_factual_line (the guard is not weakened).
    writer = _load_writer()
    result_obj = _q06_result()
    registry = writer.citation_registry(result_obj)
    extra = writer.synthesis_allowed_identifiers("ends with 005", result_obj)
    answer = (
        "Part 120-36833-005 appears on page t_p_120_1176_p000003 [1].\n"
        "Candidate 120-29067-005 is listed on page t_p_120_1176_p000351."
    )
    v = writer.validate_answer(
        answer, "ends with 005", result_obj, extra_allowed=extra, registry=registry
    )
    assert not v["accepted"]
    assert "uncited_factual_line" in v["failures"]


def test_citation_registry_direct_first_preserves_proof_numbering():
    writer = _load_writer()
    result_obj = {
        "route": "exact_identifier_lookup",
        "evidence_envelope": {
            "direct_evidence": [
                {"page_id": "t_p_demo_p1", "field_name": "part_number", "value": "120-41824-003"}
            ],
            "candidate_evidence": [
                {"candidate_value": "120-99999-001", "page_id": "t_p_demo_p9"}
            ],
        },
    }
    registry = writer.citation_registry(result_obj)
    # Direct evidence is [1] (proof); guidance follows.
    assert registry[0]["authority"] == "proof"
    assert registry[0]["class"] == "direct_source"
    assert registry[1]["authority"] == "guidance"
