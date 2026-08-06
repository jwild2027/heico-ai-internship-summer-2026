from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_confidence_stage4_simulation import ConfidenceStage4Paths, simulate_confidence_policy


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")


def _check(status: str, score: float = 1.0) -> dict:
    return {"status": status, "score": score, "reasons": []}


def _scores(tier: str, usable: float) -> dict:
    return {
        "confidence_tier": tier,
        "usable_confidence": usable,
        "support_score": usable,
        "risk_score": 0.0,
    }


def _policy() -> dict:
    return {
        "status": "OK",
        "version": "trace_lc_confidence_policy_v1",
        "layers": {
            "source_trace": {
                "max_auto_trust_tier": "A",
                "min_rag_tier": "A",
                "default_rag_action": "include_as_source_evidence",
                "hard_blocks": ["missing_tiff", "missing_source_url", "source_untraceable"],
                "thresholds": {"A": 0.75, "B": 0.6, "C": 0.4},
            },
            "table_candidate": {
                "purpose": "routing_signal",
                "max_auto_trust_tier": "B",
                "min_rag_tier": None,
                "default_rag_action": "exclude_until_table_tiles_exist",
                "hard_blocks": ["graph_gate_blocked", "layout_gate_blocked"],
                "thresholds": {"A": 0.9, "B": 0.66, "C": 0.4},
            },
            "visual_text": {
                "max_auto_trust_tier": "B",
                "min_rag_tier": "B",
                "default_rag_action": "include_as_derived_context",
                "hard_blocks": ["metadata_leakage", "prompt_template_leakage", "refusal_like"],
                "thresholds": {"A": 0.92, "B": 0.74, "C": 0.45},
            },
            "table_tile_text_refined": {
                "max_auto_trust_tier": "A",
                "min_rag_tier": "B",
                "default_rag_action": "include_as_derived_context",
                "hard_blocks": ["index_label_as_part", "source_untraceable"],
                "thresholds": {"A": 0.82, "B": 0.64, "C": 0.4},
            },
        },
    }


def test_stage4_simulation_keeps_source_trace_as_A_and_blocks_table_candidate_rag(tmp_path: Path) -> None:
    records = [
        {
            "page_id": "p1",
            "evidence_layer": "source_trace",
            "trust_tier": "A",
            "rag_action": "include_as_source_evidence",
            "repair_action": "none",
            "source_trace": _check("source_verified"),
            "graph_support": _check("strong_support"),
            "ocr_support": _check("ocr_available"),
            "part_catalog_support": _check("not_applicable"),
            "hallucination_risk": _check("low_risk"),
            "confidence_scores": _scores("C", 0.68),
        },
        {
            "page_id": "p1",
            "evidence_layer": "table_candidate",
            "trust_tier": "C",
            "rag_action": "exclude_until_table_tiles_exist",
            "repair_action": "run_table_crop_tile",
            "source_trace": _check("source_verified"),
            "graph_support": _check("strong_support"),
            "ocr_support": _check("not_evaluated"),
            "part_catalog_support": _check("not_applicable"),
            "hallucination_risk": _check("low_risk"),
            "confidence_scores": _scores("B", 0.8),
        },
        {
            "page_id": "p1",
            "evidence_layer": "visual_text",
            "trust_tier": "C",
            "rag_action": "exclude_from_rag",
            "repair_action": "human_review",
            "source_trace": _check("source_verified"),
            "graph_support": _check("strong_support"),
            "ocr_support": _check("not_found"),
            "part_catalog_support": _check("not_applicable"),
            "hallucination_risk": _check("low_risk"),
            "confidence_scores": _scores("A", 0.95),
        },
    ]
    records_path = tmp_path / "records.jsonl"
    policy_path = tmp_path / "policy.json"
    _write_jsonl(records_path, records)
    _write_json(policy_path, _policy())

    result = simulate_confidence_policy(ConfidenceStage4Paths(records_path, policy_path, tmp_path / "out"))

    assert result["status"] == "OK"
    assert result["source_trace_policy_A_records"] == 1
    assert result["table_candidate_direct_rag_records"] == 0
    assert result["visual_text_above_B_records"] == 0
    assert result["unsafe_policy_rag_include_records"] == 0
    assert result["policy_trust_tier_counts"]["A"] == 1
    assert result["policy_trust_tier_counts"]["B"] == 2


def test_stage4_simulation_marks_untraceable_include_as_unsafe(tmp_path: Path) -> None:
    records = [
        {
            "page_id": "p2",
            "evidence_layer": "table_tile_text_refined",
            "trust_tier": "A",
            "rag_action": "include_as_derived_context",
            "repair_action": "none",
            "source_trace": _check("missing_tiff"),
            "graph_support": _check("strong_support"),
            "ocr_support": _check("ocr_available"),
            "part_catalog_support": _check("catalog_supported_part_numbers_found"),
            "hallucination_risk": _check("low_risk"),
            "confidence_scores": _scores("A", 0.95),
        }
    ]
    records_path = tmp_path / "records.jsonl"
    policy_path = tmp_path / "policy.json"
    _write_jsonl(records_path, records)
    _write_json(policy_path, _policy())

    result = simulate_confidence_policy(ConfidenceStage4Paths(records_path, policy_path, tmp_path / "out"))

    assert result["policy_trust_tier_counts"] == {"D": 1}
    assert result["policy_rag_action_counts"] == {"exclude_from_rag": 1}
    assert result["unsafe_policy_rag_include_records"] == 0
