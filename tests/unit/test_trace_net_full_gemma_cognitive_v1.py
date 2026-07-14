from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path("scripts/serve_trace_net_full_gemma_cognitive_v1.py")


def load():
    spec = importlib.util.spec_from_file_location("gemma_cognitive_v1", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["gemma_cognitive_v1"] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def base_result():
    return {
        "route": "exact_identifier_lookup",
        "evidence_envelope": {
            "direct_evidence": [{
                "page_id": "t_p_120_1176_p000202",
                "field_name": "part_number",
                "normalized_value": "120-41824-003",
            }],
            "authority_evidence": [],
            "candidate_evidence": [],
            "semantic_guidance": [],
            "visual_guidance": [],
            "contradictions": [],
        },
    }


def test_valid_supported_answer_is_accepted():
    mod = load()
    result = base_result()
    check = mod.validate_answer(
        "Part 120-41824-003 appears in the cited source field [1].",
        "Find part 120-41824-003",
        result,
    )
    assert check["accepted"] is True


def test_unknown_part_number_is_rejected():
    mod = load()
    result = base_result()
    check = mod.validate_answer(
        "Part 120-99999-001 is the answer [1].",
        "Find part 120-41824-003",
        result,
    )
    assert check["accepted"] is False
    assert any(item.startswith("unsupported_part_number") for item in check["failures"])


def test_missing_citation_is_rejected():
    mod = load()
    result = base_result()
    check = mod.validate_answer(
        "Part 120-41824-003 appears in the source.",
        "Find part 120-41824-003",
        result,
    )
    assert check["accepted"] is False
    assert "direct_answer_missing_citation" in check["failures"]


def test_approval_claim_without_authority_is_rejected():
    mod = load()
    result = base_result()
    check = mod.validate_answer(
        "Part 120-41824-003 is an approved replacement [1].",
        "Is part 120-41824-003 an approved replacement?",
        result,
    )
    assert check["accepted"] is False
    assert "dangerous_claim_without_explicit_authority" in check["failures"]


def test_uncited_factual_line_is_rejected_even_when_another_line_has_a_citation():
    mod = load()
    result = base_result()
    check = mod.validate_answer(
        "Part 120-41824-003 appears in the source [1].\nThe manual lists it as a locking ring.",
        "Find part 120-41824-003",
        result,
    )
    assert check["accepted"] is False
    assert "uncited_factual_line" in check["failures"]
