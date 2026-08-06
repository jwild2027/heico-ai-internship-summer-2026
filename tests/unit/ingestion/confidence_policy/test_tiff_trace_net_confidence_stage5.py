import json
from pathlib import Path

from tiff.trace_net_confidence_stage5_control import (
    ConfidenceStage5Options,
    ConfidenceStage5Paths,
    build_confidence_stage5_control,
)


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _policy():
    return {
        "status": "OK",
        "version": "trace_lc_confidence_policy_v1",
        "layers": {
            "source_trace": {
                "max_auto_trust_tier": "A",
                "thresholds": {"A": 0.75, "B": 0.6, "C": 0.4},
                "hard_blocks": ["missing_page", "missing_tiff", "missing_source_url", "source_untraceable"],
                "default_rag_action": "include_as_source_evidence",
            },
            "part_catalog": {
                "max_auto_trust_tier": "A",
                "thresholds": {"A": 0.82, "B": 0.66, "C": 0.42},
                "hard_blocks": ["catalog_conflict", "invalid_part_pattern", "source_untraceable"],
                "default_rag_action": "include_as_verified_part_evidence",
            },
            "table_candidate": {
                "max_auto_trust_tier": "B",
                "thresholds": {"A": 0.9, "B": 0.66, "C": 0.4},
                "default_rag_action": "exclude_until_table_tiles_exist",
            },
        },
    }


def test_stage5_controls_only_source_trace_and_part_catalog(tmp_path):
    records_path = tmp_path / "consensus.jsonl"
    policy_path = tmp_path / "policy.json"
    out_dir = tmp_path / "out"
    rows = [
        {
            "record_id": "p1:source_trace",
            "page_id": "p1",
            "evidence_layer": "source_trace",
            "trust_tier": "B",
            "rag_action": "exclude_from_rag",
            "repair_action": "human_review",
            "source_trace": {"status": "source_verified"},
            "graph_support": {"status": "strong_support"},
            "part_catalog_support": {"status": "not_applicable"},
            "hallucination_risk": {"status": "low_risk"},
            "confidence_scores": {"usable_confidence": 0.60},
        },
        {
            "record_id": "p1:part_catalog",
            "page_id": "p1",
            "evidence_layer": "part_catalog",
            "trust_tier": "C",
            "rag_action": "exclude_from_rag",
            "repair_action": "human_review",
            "source_trace": {"status": "source_verified"},
            "graph_support": {"status": "strong_support"},
            "part_catalog_support": {"status": "catalog_verified"},
            "hallucination_risk": {"status": "low_risk"},
            "confidence_scores": {"usable_confidence": 0.70},
        },
        {
            "record_id": "p1:table_candidate",
            "page_id": "p1",
            "evidence_layer": "table_candidate",
            "trust_tier": "C",
            "rag_action": "exclude_until_table_tiles_exist",
            "repair_action": "run_table_crop_tile",
            "source_trace": {"status": "source_verified"},
            "graph_support": {"status": "strong_support"},
            "confidence_scores": {"usable_confidence": 0.80},
        },
    ]
    _write_jsonl(records_path, rows)
    policy_path.write_text(json.dumps(_policy()), encoding="utf-8")
    result = build_confidence_stage5_control(
        ConfidenceStage5Paths(consensus_records=records_path, confidence_policy=policy_path, output_dir=out_dir),
        ConfidenceStage5Options(controlled_layers=("source_trace", "part_catalog")),
    )
    assert result["status"] == "OK"
    assert result["policy_controlled_records"] == 2
    assert result["source_trace_policy_A_records"] == 1
    assert result["part_catalog_policy_A_records"] == 1
    assert result["table_candidate_direct_rag_records"] == 0
    out_rows = [json.loads(line) for line in (out_dir / "trace_lc_stage5_policy_control_records.jsonl").read_text().splitlines()]
    assert out_rows[0]["selected_trust_tier"] == "A"
    assert out_rows[0]["selected_rag_action"] == "include_as_source_evidence"
    assert out_rows[1]["selected_trust_tier"] == "A"
    assert out_rows[1]["selected_rag_action"] == "include_as_verified_part_evidence"
    assert out_rows[2]["selected_trust_tier"] == "C"  # unchanged because not controlled.
    assert out_rows[2]["stage5_controlled"] is False


def test_stage5_blocks_untraceable_controlled_records(tmp_path):
    records_path = tmp_path / "consensus.jsonl"
    policy_path = tmp_path / "policy.json"
    out_dir = tmp_path / "out"
    rows = [
        {
            "record_id": "p1:part_catalog",
            "page_id": "p1",
            "evidence_layer": "part_catalog",
            "trust_tier": "A",
            "rag_action": "include_as_verified_part_evidence",
            "repair_action": "none",
            "source_trace": {"status": "missing_tiff"},
            "graph_support": {"status": "strong_support"},
            "part_catalog_support": {"status": "catalog_verified"},
            "confidence_scores": {"usable_confidence": 0.99},
        }
    ]
    _write_jsonl(records_path, rows)
    policy_path.write_text(json.dumps(_policy()), encoding="utf-8")
    result = build_confidence_stage5_control(
        ConfidenceStage5Paths(consensus_records=records_path, confidence_policy=policy_path, output_dir=out_dir),
        ConfidenceStage5Options(controlled_layers=("part_catalog",)),
    )
    out_rows = [json.loads(line) for line in (out_dir / "trace_lc_stage5_policy_control_records.jsonl").read_text().splitlines()]
    assert out_rows[0]["selected_trust_tier"] == "D"
    assert out_rows[0]["selected_rag_action"] == "exclude_from_rag"
    assert result["unsafe_stage5_rag_include_records"] == 0


def test_stage5b_controls_refined_table_tile_text(tmp_path):
    records_path = tmp_path / "consensus.jsonl"
    policy_path = tmp_path / "policy.json"
    out_dir = tmp_path / "out"
    rows = [
        {
            "record_id": "p1:table_tile_text_refined",
            "page_id": "p1",
            "evidence_layer": "table_tile_text_refined",
            "trust_tier": "C",
            "rag_action": "exclude_from_rag",
            "repair_action": "run_table_tile_ocr_or_human_review",
            "source_trace": {"status": "source_verified"},
            "graph_support": {"status": "strong_support"},
            "part_catalog_support": {"status": "catalog_verified"},
            "hallucination_risk": {"status": "low_risk"},
            "confidence_scores": {"usable_confidence": 0.84},
        },
        {
            "record_id": "p2:visual_text",
            "page_id": "p2",
            "evidence_layer": "visual_text",
            "trust_tier": "C",
            "rag_action": "exclude_from_rag",
            "repair_action": "human_review",
            "source_trace": {"status": "source_verified"},
            "graph_support": {"status": "strong_support"},
            "confidence_scores": {"usable_confidence": 0.95},
        },
    ]
    _write_jsonl(records_path, rows)
    policy = _policy()
    policy["layers"]["table_tile_text_refined"] = {
        "max_auto_trust_tier": "A",
        "thresholds": {"A": 0.82, "B": 0.64, "C": 0.4},
        "default_rag_action": "include_as_derived_context",
    }
    policy["layers"]["visual_text"] = {
        "max_auto_trust_tier": "B",
        "thresholds": {"A": 0.92, "B": 0.74, "C": 0.45},
        "default_rag_action": "include_as_derived_context",
    }
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    result = build_confidence_stage5_control(
        ConfidenceStage5Paths(consensus_records=records_path, confidence_policy=policy_path, output_dir=out_dir),
        ConfidenceStage5Options(),
    )
    assert result["status"] == "OK"
    assert result["table_tile_text_refined_controlled_records"] == 1
    assert result["table_tile_text_refined_derived_context_records"] == 1
    assert result["table_tile_text_refined_direct_verified_records"] == 0
    assert result["visual_text_controlled_records"] == 0
    out_rows = [json.loads(line) for line in (out_dir / "trace_lc_stage5_policy_control_records.jsonl").read_text().splitlines()]
    table_row = next(row for row in out_rows if row["evidence_layer"] == "table_tile_text_refined")
    visual_row = next(row for row in out_rows if row["evidence_layer"] == "visual_text")
    assert table_row["stage5_controlled"] is True
    assert table_row["selected_rag_action"] == "include_as_derived_context"
    assert visual_row["stage5_controlled"] is False
    assert visual_row["selected_rag_action"] == "exclude_from_rag"
