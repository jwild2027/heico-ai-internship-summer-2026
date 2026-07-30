from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.trace_net_nha_phase7_8_runtime_v1 import (
    NHAIntegrationAdapter,
    build_gate_bank,
    classify_nha_intent,
    evaluate_gate_bank,
    extract_user_query,
    public_contract_valid,
    render_gated_answer,
    validate_gate_results,
)


class FakeEngine:
    def execute_question(self, question):
        category = question["category"]
        query = question["query"]
        part_match = re.search(r"\b\d{3}-\d{5}-\d{3}\b", query)
        part = part_match.group(0) if part_match else "120-00000-001"
        base = {
            "behavior": "no_relationship",
            "child": part,
            "parent": part,
            "direct_nha": "",
            "parent_candidates": [],
            "chain": [],
            "direct_children": [],
            "descendants": [],
            "pages": ["t_p_120_1176_p000343"],
            "limits": [],
        }
        if category == "direct_nha":
            base.update(behavior="direct_answer", direct_nha="120-99999-001")
        elif category == "ancestor_chain":
            base.update(
                behavior="ordered_chain_answer",
                direct_nha="120-99999-001",
                chain=[part, "120-99999-001", "120-99999-002"],
            )
        elif category == "direct_children":
            base.update(
                behavior="direct_children_answer",
                parent=part,
                direct_children=["120-11111-001", "120-11111-002"],
            )
        elif category == "direct_vs_descendant":
            base.update(
                behavior="tree_answer",
                parent=part,
                direct_children=["120-11111-001"],
                descendants=["120-22222-001"],
            )
        elif category == "relationship_evidence_page":
            base.update(behavior="page_and_trait_answer")
        return base


def test_extract_user_query_from_openai_messages():
    payload = {
        "messages": [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "What is the direct NHA of 120-29073-001?"},
        ]
    }
    assert extract_user_query(payload) == "What is the direct NHA of 120-29073-001?"


def test_classifier_recognizes_core_intents():
    cases = {
        "What is the direct NHA of 120-29073-001?": "direct_nha",
        "Show the complete assembly chain above 120-29073-001.": "ancestor_chain",
        "List the direct children of assembly 120-29067-001.": "direct_children",
        "Show direct versus lower descendants below assembly 120-29067-001.": "direct_vs_descendant",
        "Which page proves the NHA relationship for 120-29073-001?": "relationship_evidence_page",
        "What is the direct NHA of 42952-10?": "direct_nha",
    }
    for query, expected in cases.items():
        result = classify_nha_intent(query)
        assert result["recognized"] is True
        assert result["intent"] == expected
        assert result["route_id"] == "assembly_relationship_reasoning"


def test_classifier_blocks_synthetic_identifier():
    result = classify_nha_intent("What is the direct NHA of synthetic part 990-91001-001?")
    assert result["recognized"] is False
    assert result["synthetic_part_detected"] is True
    assert result["reason"] == "synthetic_identifier_blocked"


def test_non_nha_query_is_passthrough():
    adapter = NHAIntegrationAdapter(FakeEngine(), mode="gated")
    decision = adapter.evaluate("Find part 120-29067-003 and cite its strongest page.")
    assert decision["action"] == "passthrough"
    assert decision["override"] is False


def test_shadow_mode_never_overrides():
    adapter = NHAIntegrationAdapter(FakeEngine(), mode="shadow")
    decision = adapter.evaluate("What is the direct NHA of 120-29073-001?")
    assert decision["action"] == "shadow_candidate"
    assert decision["shadow_candidate"] is True
    assert decision["override"] is False
    assert decision["public_answer"] == ""


def test_gated_mode_returns_public_contract():
    adapter = NHAIntegrationAdapter(FakeEngine(), mode="gated")
    decision = adapter.evaluate("What is the direct NHA of 120-29073-001?")
    assert decision["action"] == "override"
    assert decision["override"] is True
    valid, failures = public_contract_valid(decision["public_answer"], decision["pages"])
    assert valid, failures
    assert "120-99999-001" in decision["public_answer"]


def test_render_conflict_is_limited_not_positive():
    answer = render_gated_answer({
        "behavior": "conflict_limited",
        "child": "120-29073-001",
        "parent_candidates": ["120-29067-001", "120-29067-003"],
        "pages": ["t_p_120_1176_p000343", "t_p_120_1176_p000349"],
    })
    assert "No single direct NHA can be confirmed" in answer
    assert "## Answer" in answer and "## Evidence" in answer and "## Limits" in answer
    assert "[1]" in answer and "[2]" in answer


def test_telemetry_hashes_query_by_default(tmp_path: Path):
    path = tmp_path / "telemetry.jsonl"
    adapter = NHAIntegrationAdapter(FakeEngine(), mode="shadow", telemetry_path=path)
    query = "What is the direct NHA of 120-29073-001?"
    adapter.evaluate(query)
    payload = json.loads(path.read_text(encoding="utf-8").strip())
    assert "query" not in payload
    assert payload["query_sha256"]


def _real_cases():
    return [
        {
            "case_id": f"real-{index}",
            "child_part": f"120-{30000 + index:05d}-001",
            "expected_behavior": "direct_answer",
        }
        for index in range(20)
    ]


def _relationships():
    rows = []
    for index in range(10):
        parent = f"120-{40000 + index:05d}-001"
        child = f"120-{41000 + index:05d}-001"
        rows.append({
            "relationship_status": "source_supported",
            "child_part": child,
            "direct_nha": parent,
            "hierarchy_depth": 1,
        })
        rows.append({
            "relationship_status": "source_supported",
            "child_part": f"120-{42000 + index:05d}-001",
            "direct_nha": child,
            "hierarchy_depth": 2,
        })
    return rows


def test_gate_bank_has_40_cases_and_controls():
    bank = build_gate_bank(_real_cases(), _relationships(), total=40)
    assert len(bank) == 40
    assert sum(row["kind"] == "non_nha_control" for row in bank) == 3
    assert sum(row["kind"] == "synthetic_block_control" for row in bank) == 3
    assert sum(bool(row["expected_real_route"]) for row in bank) == 34


def test_shadow_and_gated_gate_validation_passes():
    bank = build_gate_bank(_real_cases(), _relationships(), total=40)
    shadow = evaluate_gate_bank(bank, NHAIntegrationAdapter(FakeEngine(), mode="shadow"))
    gated = evaluate_gate_bank(bank, NHAIntegrationAdapter(FakeEngine(), mode="gated"))
    quality = validate_gate_results(shadow, gated, expected_count=40)
    assert quality["quality_status"] == "PASS", quality["failures"]
    assert quality["counts"]["shadow_override_count"] == 0
    assert quality["counts"]["gated_override_count"] == 34
    assert quality["counts"]["synthetic_access_count"] == 0
