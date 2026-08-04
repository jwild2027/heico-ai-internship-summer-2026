import importlib.util
import sys
from pathlib import Path

import pytest


MODE_PATH = Path(
    "src/trace_net/writing/trace_net_h30_evidence_aware_answer_modes_v1.py"
)
CONTRACT_PATH = Path(
    "src/trace_net/writing/trace_net_h30_public_answer_contract_v1.py"
)


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def sample(route: str):
    return {
        "route": route,
        "writer_mode": "deterministic_fail_closed",
        "query_atoms": {},
        "evidence_envelope": {"typed_evidence": []},
        "follow_up_questions": [],
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }


@pytest.mark.parametrize(
    "route",
    [
        "visual_figure_callout_lookup",
        "contradiction_resolution",
        "ocr_scan_recovery",
        "high_degree_entity_aggregation",
        "multi_question_research",
    ],
)
def test_no_evidence_technical_modes_satisfy_public_contract(route):
    modes = load(MODE_PATH, f"trace_net_modes_{route}")
    contract = load(CONTRACT_PATH, f"trace_net_contract_{route}")

    result = sample(route)
    decision = modes.classify_answer_mode(result)
    assert decision["mode"] == modes.MODE_NO_EVIDENCE

    text = modes.render_deterministic_mode(result, decision)
    check = contract.validate_public_answer_contract(text, route=route)

    assert "## Answer" in text
    assert "## Evidence" in text
    assert "## Limits" in text
    assert check["accepted"] is True
    assert check["failures"] == []
    assert "[1]" not in text


def test_visual_no_evidence_wording_is_specific_and_fail_closed():
    modes = load(MODE_PATH, "trace_net_modes_visual_specific")
    contract = load(CONTRACT_PATH, "trace_net_contract_visual_specific")

    result = sample("visual_figure_callout_lookup")
    decision = modes.classify_answer_mode(result)
    text = modes.render_deterministic_mode(result, decision)

    assert "No source-supported visual match was resolved" in text
    assert "No typed visual record" in text
    assert "cannot be confirmed" in text
    assert contract.validate_public_answer_contract(
        text,
        route="visual_figure_callout_lookup",
    )["accepted"] is True


def test_candidate_guidance_is_structured_without_promotion():
    modes = load(MODE_PATH, "trace_net_modes_candidate_contract")
    contract = load(CONTRACT_PATH, "trace_net_contract_candidate_contract")

    result = {
        **sample("guided_part_discovery"),
        "query_atoms": {
            "identifier_mode": "contains",
            "normalized_identifier": "41824",
        },
        "evidence_envelope": {
            "typed_evidence": [
                {
                    "source_bucket": "candidate_evidence",
                    "modality": "candidate",
                    "claim_support_allowed": False,
                    "guidance_only": True,
                    "conflicted": False,
                    "identity": {
                        "candidate": "120-41824-003",
                        "part_numbers": ["120-41824-003"],
                    },
                    "source_trace": {},
                    "excerpt": "candidate",
                }
            ]
        },
    }
    decision = modes.classify_answer_mode(result)
    text = modes.render_deterministic_mode(result, decision)

    assert decision["mode"] == modes.MODE_CANDIDATE
    assert "not a final identification" in text
    assert contract.validate_public_answer_contract(
        text,
        route="guided_part_discovery",
    )["accepted"] is True
