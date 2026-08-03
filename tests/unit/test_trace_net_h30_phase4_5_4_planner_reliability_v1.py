from __future__ import annotations

import json
from typing import Any, Dict, List

from scripts.trace_net_h30_shadow_planner_v1 import call_shadow_planner
from scripts.trace_net_h30_validated_planner_execution_v1 import canonicalize_planner_contract

SAFETY_FALSE = {
    "answer_permission": False,
    "final_answer_allowed": False,
    "can_answer_directly": False,
    "can_prove_claims": False,
    "source_truth_mutation_allowed": False,
}


def graph_seed() -> Dict[str, Any]:
    return {
        "query": "Which assembly contains part 120-41824-003?",
        "candidate_tokens": ["120-41824-003"],
        "deterministic_atoms": {
            "exact_part_numbers": ["120-41824-003"],
            "identifier_mode": "exact",
            "normalized_identifier": "120-41824-003",
            "requested_claims": ["relationship"],
            "graph_requested": True,
        },
        "allowed_routes": ["graph_relationship_reasoning"],
        "allowed_tunnels": ["typed_graph_guidance", "normal_source_resolution", "qdrant_guidance"],
    }


def graph_proposal(tunnels: List[str]) -> Dict[str, Any]:
    return {
        "identifier_mode": "exact",
        "identifier": "120-41824-003",
        "entity_type": "part_number",
        "requested_claims": ["assembly_relationship"],
        "suggested_routes": ["graph_relationship_reasoning"],
        "suggested_tunnels": tunnels,
        "uncertainties": [],
        **SAFETY_FALSE,
    }


def test_invalid_advisory_tunnel_is_dropped_then_revalidated() -> None:
    result = canonicalize_planner_contract(
        graph_proposal(["typed_graph_guidance", "normal_source_resolution", "qdrant_undercut_guidance"]),
        seed=graph_seed(),
    )
    assert result["validation"]["accepted"] is True
    assert result["audit"]["used"] is True
    assert result["audit"]["dropped_advisory_tunnels"] == ["qdrant_undercut_guidance"]
    assert "invalid_advisory_tunnels_dropped" in result["audit"]["changes"]
    assert result["proposal"]["suggested_tunnels"] == ["typed_graph_guidance", "normal_source_resolution"]


def test_unsafe_write_tunnel_still_fails_closed() -> None:
    result = canonicalize_planner_contract(graph_proposal(["qdrant_write"]), seed=graph_seed())
    assert result["validation"] is None
    assert "unsafe_write_or_admin_instruction" in result["audit"]["blocked_reasons"]


class FakeResponse:
    def __init__(self, content: str, status: int = 200) -> None:
        self.status = status
        self._body = json.dumps({"choices": [{"message": {"content": content}}]}).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class SequencedOpener:
    def __init__(self, contents: List[str]) -> None:
        self.contents = list(contents)
        self.calls = 0

    def __call__(self, request: Any, timeout: float) -> FakeResponse:
        del request, timeout
        content = self.contents[self.calls]
        self.calls += 1
        return FakeResponse(content)


def valid_exact_proposal_json() -> str:
    return json.dumps({
        "identifier_mode": "exact",
        "identifier": "VS4956",
        "entity_type": "part_number",
        "requested_claims": ["part_identity"],
        "suggested_routes": ["exact_identifier_lookup"],
        "suggested_tunnels": ["normal_source_truth"],
        "uncertainties": [],
        **SAFETY_FALSE,
    })


def planner_seed() -> Dict[str, Any]:
    return {
        "query": "Find VS4956",
        "candidate_tokens": ["VS4956"],
        "allowed_routes": ["exact_identifier_lookup"],
        "allowed_tunnels": ["normal_source_truth"],
    }


def planner_config() -> Dict[str, Any]:
    return {
        "model": "gemma4:26b",
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key": "ollama",
        "timeout_seconds": 90,
    }


def test_missing_json_object_gets_exactly_one_retry() -> None:
    opener = SequencedOpener(["I will explain the plan first.", valid_exact_proposal_json()])
    result = call_shadow_planner(planner_seed(), planner_config(), opener=opener)
    assert result["call_status"] == "PASS"
    assert result["json_output_retry_used"] is True
    assert result["planner_call_attempt_count"] == 2
    assert "planner_output_did_not_contain_json_object" in result["initial_call_error"]
    assert opener.calls == 2


def test_second_missing_json_object_fails_closed_after_two_attempts() -> None:
    opener = SequencedOpener(["not json", "still not json"])
    result = call_shadow_planner(planner_seed(), planner_config(), opener=opener)
    assert result["call_status"] == "ERROR"
    assert result["http_status"] == 599
    assert result["json_output_retry_used"] is True
    assert result["planner_call_attempt_count"] == 2
    assert result["error"] == "ValueError: planner_output_did_not_contain_json_object"
    assert opener.calls == 2
