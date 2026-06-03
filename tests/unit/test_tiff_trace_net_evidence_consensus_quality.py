from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_evidence_consensus_quality import (
    EvidenceConsensusQualityPaths,
    build_evidence_consensus_quality,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def test_evidence_consensus_quality_passes_safe_report(tmp_path: Path) -> None:
    consensus_dir = tmp_path / "consensus"
    _write_json(
        consensus_dir / "evidence_consensus_summary.json",
        {
            "status": "OK",
            "records": 3,
            "pages_loaded": 2,
            "source_trace_records": 2,
            "visual_text_records": 1,
            "unsafe_rag_include_records": 0,
            "graph_nodes": 10,
            "graph_edges": 9,
            "layer_counts": {"source_trace": 2, "visual_text": 1},
            "trust_tier_counts": {"A": 2, "C": 1},
            "rag_action_counts": {"include_as_source_truth": 2, "exclude_from_rag": 1},
            "repair_action_counts": {"none": 2, "ocr_graph_validation_or_human_review": 1},
            "confidence_score_records": 3,
            "confidence_tier_counts": {"A": 2, "C": 1},
            "confidence_avg_usable": 0.8,
            "confidence_tier_disagreement_records": 0,
        },
    )
    _write_jsonl(
        consensus_dir / "evidence_consensus_records.jsonl",
        [
            {"page_id": "p1", "evidence_layer": "source_trace", "trust_tier": "A", "rag_action": "include_as_source_truth", "confidence_scores": {"usable_confidence": 0.95, "confidence_tier": "A"}},
            {"page_id": "p2", "evidence_layer": "source_trace", "trust_tier": "A", "rag_action": "include_as_source_truth", "confidence_scores": {"usable_confidence": 0.95, "confidence_tier": "A"}},
            {"page_id": "p1", "evidence_layer": "visual_text", "trust_tier": "C", "rag_action": "exclude_from_rag", "confidence_scores": {"usable_confidence": 0.50, "confidence_tier": "C"}},
        ],
    )
    _write_json(consensus_dir / "evidence_consensus_graph_nodes.json", [{} for _ in range(10)])
    _write_json(consensus_dir / "evidence_consensus_graph_edges.json", [{} for _ in range(9)])
    report = build_evidence_consensus_quality(
        EvidenceConsensusQualityPaths(
            records_path=consensus_dir / "evidence_consensus_records.jsonl",
            summary_path=consensus_dir / "evidence_consensus_summary.json",
            graph_nodes_path=consensus_dir / "evidence_consensus_graph_nodes.json",
            graph_edges_path=consensus_dir / "evidence_consensus_graph_edges.json",
            quality_path=consensus_dir / "evidence_consensus_quality.json",
        ),
        min_pages=2,
        min_records=3,
        require_source_trace=True,
        require_rag_safety=True,
        require_confidence_scores=True,
    )
    assert report["status"] == "OK"


def test_evidence_consensus_quality_fails_unsafe_rag_include(tmp_path: Path) -> None:
    consensus_dir = tmp_path / "consensus"
    _write_json(consensus_dir / "evidence_consensus_summary.json", {"status": "OK", "records": 1, "pages_loaded": 1, "source_trace_records": 1, "unsafe_rag_include_records": 1})
    _write_jsonl(consensus_dir / "evidence_consensus_records.jsonl", [{"page_id": "p1", "evidence_layer": "visual_text", "trust_tier": "D", "rag_action": "include_as_derived_context"}])
    _write_json(consensus_dir / "evidence_consensus_graph_nodes.json", [{}])
    _write_json(consensus_dir / "evidence_consensus_graph_edges.json", [{}])
    report = build_evidence_consensus_quality(
        EvidenceConsensusQualityPaths(
            records_path=consensus_dir / "evidence_consensus_records.jsonl",
            summary_path=consensus_dir / "evidence_consensus_summary.json",
            graph_nodes_path=consensus_dir / "evidence_consensus_graph_nodes.json",
            graph_edges_path=consensus_dir / "evidence_consensus_graph_edges.json",
        ),
        min_pages=1,
        min_records=1,
        require_rag_safety=True,
    )
    assert report["status"] == "FAIL"
    assert any(c["name"] == "evidence_consensus_no_unsafe_rag" and not c["ok"] for c in report["checks"])


def test_evidence_consensus_quality_can_require_refined_table_text(tmp_path: Path) -> None:
    consensus_dir = tmp_path / "consensus"
    _write_json(
        consensus_dir / "evidence_consensus_summary.json",
        {
            "status": "OK",
            "records": 2,
            "pages_loaded": 1,
            "source_trace_records": 1,
            "table_tile_text_refined_records": 1,
            "unsafe_rag_include_records": 0,
            "graph_nodes": 3,
            "graph_edges": 2,
            "layer_counts": {"source_trace": 1, "table_tile_text_refined": 1},
            "trust_tier_counts": {"A": 1, "B": 1},
            "rag_action_counts": {"include_as_source_evidence": 1, "include_as_derived_context": 1},
            "repair_action_counts": {"none": 2},
        },
    )
    _write_jsonl(
        consensus_dir / "evidence_consensus_records.jsonl",
        [
            {"page_id": "p1", "evidence_layer": "source_trace", "trust_tier": "A", "rag_action": "include_as_source_evidence", "source_trace": {"status": "source_verified"}},
            {"page_id": "p1", "evidence_layer": "table_tile_text_refined", "trust_tier": "B", "rag_action": "include_as_derived_context", "source_trace": {"status": "source_verified"}},
        ],
    )
    _write_json(consensus_dir / "evidence_consensus_graph_nodes.json", [{} for _ in range(3)])
    _write_json(consensus_dir / "evidence_consensus_graph_edges.json", [{} for _ in range(2)])
    report = build_evidence_consensus_quality(
        EvidenceConsensusQualityPaths(
            records_path=consensus_dir / "evidence_consensus_records.jsonl",
            summary_path=consensus_dir / "evidence_consensus_summary.json",
            graph_nodes_path=consensus_dir / "evidence_consensus_graph_nodes.json",
            graph_edges_path=consensus_dir / "evidence_consensus_graph_edges.json",
        ),
        min_pages=1,
        min_records=2,
        min_table_tile_text_refined_records=1,
    )
    assert report["status"] == "OK"


def test_evidence_consensus_quality_can_require_confidence_scores(tmp_path: Path) -> None:
    consensus_dir = tmp_path / "consensus"
    _write_json(
        consensus_dir / "evidence_consensus_summary.json",
        {
            "status": "OK",
            "records": 1,
            "pages_loaded": 1,
            "source_trace_records": 1,
            "unsafe_rag_include_records": 0,
            "graph_nodes": 1,
            "graph_edges": 1,
            "layer_counts": {"source_trace": 1},
            "trust_tier_counts": {"A": 1},
            "rag_action_counts": {"include_as_source_evidence": 1},
            "repair_action_counts": {"none": 1},
            "confidence_score_records": 1,
            "confidence_tier_counts": {"A": 1},
            "confidence_avg_usable": 0.95,
            "confidence_tier_disagreement_records": 0,
        },
    )
    _write_jsonl(
        consensus_dir / "evidence_consensus_records.jsonl",
        [{"page_id": "p1", "evidence_layer": "source_trace", "trust_tier": "A", "rag_action": "include_as_source_evidence", "confidence_scores": {"usable_confidence": 0.95, "confidence_tier": "A"}}],
    )
    _write_json(consensus_dir / "evidence_consensus_graph_nodes.json", [{}])
    _write_json(consensus_dir / "evidence_consensus_graph_edges.json", [{}])
    report = build_evidence_consensus_quality(
        EvidenceConsensusQualityPaths(
            records_path=consensus_dir / "evidence_consensus_records.jsonl",
            summary_path=consensus_dir / "evidence_consensus_summary.json",
            graph_nodes_path=consensus_dir / "evidence_consensus_graph_nodes.json",
            graph_edges_path=consensus_dir / "evidence_consensus_graph_edges.json",
        ),
        min_pages=1,
        min_records=1,
        require_confidence_scores=True,
    )
    assert report["status"] == "OK"
    assert report["summary"]["evidence_consensus_confidence_score_records"] == 1
