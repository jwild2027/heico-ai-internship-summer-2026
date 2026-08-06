import json
from pathlib import Path

from tiff.trace_net_confidence_stage5_control import (
    ConfidenceStage5Options,
    ConfidenceStage5Paths,
    build_confidence_stage5_control,
)


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _record(page, layer, tier, rag, source="source_verified", graph="strong_support", catalog="not_applicable"):
    return {
        "record_id": f"{page}:{layer}",
        "page_id": page,
        "evidence_layer": layer,
        "trust_tier": tier,
        "rag_action": rag,
        "repair_action": "none" if rag.startswith("include") else "review",
        "source_trace": {"status": source, "score": 1.0 if source == "source_verified" else 0.0},
        "graph_support": {"status": graph, "score": 0.9},
        "part_catalog_support": {"status": catalog, "score": 0.9 if catalog == "catalog_verified" else 0.5},
        "hallucination_risk": {"status": "low_risk", "score": 0.05},
        "confidence_scores": {
            "confidence_tier": tier,
            "usable_confidence": 0.8,
            "support_score": 0.85,
            "risk_score": 0.05,
            "hard_gate_blocked": False,
        },
        "properties": {},
    }


def test_stage5_controls_only_low_risk_layers(tmp_path):
    records_path = tmp_path / "consensus.jsonl"
    policy_path = tmp_path / "policy.json"
    output_dir = tmp_path / "out"
    rows = [
        _record("p1", "source_trace", "A", "include_as_source_evidence"),
        _record("p1", "part_catalog", "C", "exclude_from_rag", catalog="catalog_verified"),
        _record("p1", "visual_text", "C", "exclude_from_rag"),
        _record("p2", "table_candidate", "C", "exclude_until_table_tiles_exist"),
    ]
    _write_jsonl(records_path, rows)
    _write_json(policy_path, {"version": "trace_lc_confidence_policy_v1", "layers": {"source_trace": {}, "part_catalog": {}, "visual_text": {}, "table_candidate": {}}})

    result = build_confidence_stage5_control(
        ConfidenceStage5Paths(consensus_records=records_path, confidence_policy=policy_path, output_dir=output_dir),
        ConfidenceStage5Options(controlled_layers=("source_trace", "part_catalog")),
    )

    assert result["status"] == "OK"
    assert result["policy_controlled_records"] == 2
    assert result["rule_controlled_records"] == 2
    assert result["source_trace_policy_A_records"] == 1
    assert result["part_catalog_policy_A_records"] == 1
    assert result["visual_text_controlled_records"] == 0
    assert result["table_candidate_direct_rag_records"] == 0
    assert result["unsafe_stage5_rag_include_records"] == 0
    assert result["routing_mutated"] is False
    rows_out = [json.loads(line) for line in output_dir.joinpath("trace_lc_stage5_policy_control_records.jsonl").read_text().splitlines()]
    by_layer = {row["evidence_layer"]: row for row in rows_out}
    assert by_layer["part_catalog"]["selected_trust_tier"] == "A"
    assert by_layer["visual_text"]["stage5_controlled"] is False
    assert output_dir.joinpath("trace_lc_stage5_policy_control_graph_nodes.json").exists()


def test_stage5_blocks_untraceable_controlled_include(tmp_path):
    records_path = tmp_path / "consensus.jsonl"
    policy_path = tmp_path / "policy.json"
    output_dir = tmp_path / "out"
    rows = [
        _record("p1", "source_trace", "A", "include_as_source_evidence", source="missing_tiff", graph="weak_support"),
    ]
    _write_jsonl(records_path, rows)
    _write_json(policy_path, {"version": "trace_lc_confidence_policy_v1", "layers": {"source_trace": {}}})

    result = build_confidence_stage5_control(
        ConfidenceStage5Paths(consensus_records=records_path, confidence_policy=policy_path, output_dir=output_dir),
        ConfidenceStage5Options(controlled_layers=("source_trace",)),
    )

    assert result["status"] == "OK"
    assert result["source_trace_policy_A_records"] == 0
    assert result["selected_trust_tier_counts"] == {"D": 1}
    assert result["selected_rag_action_counts"] == {"exclude_from_rag": 1}
    assert result["unsafe_stage5_rag_include_records"] == 0
