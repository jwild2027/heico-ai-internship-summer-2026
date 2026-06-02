from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_evidence_consensus import (
    EvidenceConsensusOptions,
    EvidenceConsensusPaths,
    build_and_write_evidence_consensus,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def test_evidence_consensus_builds_layer_records_and_graph(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    visual_dir = tmp_path / "visual"
    trust_dir = tmp_path / "trust"
    table_dir = tmp_path / "table"
    output_dir = tmp_path / "consensus"

    image = tmp_path / "page001.tif"
    image.write_bytes(b"fake")
    ocr = tmp_path / "page001.txt"
    ocr.write_text("120-12345-001 SEAT BACKREST", encoding="utf-8")

    _write_json(
        export_dir / "page_index.json",
        {
            "page-001": {
                "page_id": "page-001",
                "document_id": "doc-1",
                "ata_code": "25-21-00",
                "source_url": "http://localhost/page-001",
                "tiff_path": str(image),
                "ocr_path": str(ocr),
                "page_role": "table",
                "image_classification": "likely_table_or_grid",
                "part_numbers": ["120-12345-001"],
            },
            "page-002": {
                "page_id": "page-002",
                "document_id": "doc-1",
                "ata_code": "25-21-00",
                "source_url": "http://localhost/page-002",
                "tiff_path": str(image),
                "ocr_path": str(ocr),
                "page_role": "figure",
                "image_classification": "likely_figure_or_diagram",
            },
        },
    )
    _write_json(export_dir / "part_tree.json", {"parts": []})
    _write_jsonl(
        visual_dir / "visual_text_extraction_clean.jsonl",
        [
            {
                "page_id": "page-001",
                "status": "ok",
                "trust_tier": "C",
                "tiff_path": str(image),
                "ocr_path": str(ocr),
                "visual_text_scores": {"hallucination_risk": True},
                "part_numbers": ["120-12345-001"],
            }
        ],
    )
    _write_jsonl(
        trust_dir / "trust_trait_assertions.jsonl",
        [
            {
                "page_id": "page-001",
                "entity_id": "visual_text:page-001",
                "trait_type": "review",
                "trait_key": "visual_text",
                "trait_value": "hallucination_risk",
            }
        ],
    )
    _write_jsonl(
        table_dir / "all_page_scan" / "table_candidate_plan.jsonl",
        [
            {
                "page_id": "page-001",
                "status": "ok",
                "primary_repair_route": "table_crop_tile_repair_route_high",
                "tiff_path": str(image),
            }
        ],
    )
    _write_jsonl(
        table_dir / "table_tile_plan.jsonl",
        [
            {
                "page_id": "page-001",
                "status": "ok",
                "repair_route": "table_crop_tile_repair_route_high",
                "tiff_path": str(image),
                "tile_count": 6,
            }
        ],
    )

    result = build_and_write_evidence_consensus(
        EvidenceConsensusPaths(
            export_dir=export_dir,
            visual_text_dir=visual_dir,
            trust_trait_dir=trust_dir,
            table_dir=table_dir,
            output_dir=output_dir,
        ),
        EvidenceConsensusOptions(expected_pages=2),
    )

    summary = result["summary"]
    assert result["status"] == "OK"
    assert summary["pages_loaded"] == 2
    assert summary["source_trace_records"] == 2
    assert summary["visual_text_records"] == 1
    assert summary["table_candidate_records"] == 1
    assert summary["table_tile_records"] == 1
    assert summary["unsafe_rag_include_records"] == 0
    assert summary["confidence_score_records"] == summary["records"]
    assert "confidence_tier_counts" in summary
    assert (output_dir / "evidence_consensus_records.jsonl").exists()
    assert (output_dir / "evidence_consensus_review.html").exists()


def test_visual_text_consensus_excludes_c_tier_from_rag(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    visual_dir = tmp_path / "visual"
    output_dir = tmp_path / "consensus"
    image = tmp_path / "page.tif"
    image.write_bytes(b"fake")
    _write_json(
        export_dir / "page_index.json",
        {"p1": {"page_id": "p1", "source_url": "x", "tiff_path": str(image), "document_id": "doc"}},
    )
    _write_json(export_dir / "part_tree.json", {"parts": []})
    _write_jsonl(visual_dir / "visual_text_extraction_clean.jsonl", [{"page_id": "p1", "trust_tier": "C", "status": "ok", "tiff_path": str(image)}])

    result = build_and_write_evidence_consensus(
        EvidenceConsensusPaths(export_dir=export_dir, visual_text_dir=visual_dir, output_dir=output_dir),
        EvidenceConsensusOptions(),
    )
    visual = [r for r in result["records"] if r["evidence_layer"] == "visual_text"][0]
    assert visual["trust_tier"] == "C"
    assert visual["rag_action"] == "exclude_from_rag"
    assert visual["confidence_scores"]["version"] == "trace_lc_v1"
    assert 0.0 <= visual["confidence_scores"]["usable_confidence"] <= 1.0


def test_refined_table_tile_text_becomes_consensus_layer(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    table_dir = tmp_path / "table"
    output_dir = tmp_path / "consensus"
    image = tmp_path / "page.tif"
    image.write_bytes(b"fake")
    ocr = tmp_path / "page.txt"
    ocr.write_text("120-12345-001 25-NUMERICAL", encoding="utf-8")

    _write_json(
        export_dir / "page_index.json",
        {
            "p1": {
                "page_id": "p1",
                "source_url": "http://localhost/p1",
                "tiff_path": str(image),
                "ocr_path": str(ocr),
                "page_role": "table",
                "part_numbers": ["120-12345-001"],
            }
        },
    )
    _write_json(export_dir / "part_tree.json", {"parts": []})
    _write_jsonl(
        table_dir / "table_tile_text_refined" / "table_tile_text_refined_records.jsonl",
        [
            {
                "page_id": "p1",
                "tile_id": "tile_001",
                "status": "ok",
                "trust_tier": "B",
                "tile_text": "120-12345-001 25-NUMERICAL",
                "catalog_supported_part_numbers": ["120-12345-001"],
                "index_labels": ["25-NUMERICAL"],
            }
        ],
    )

    result = build_and_write_evidence_consensus(
        EvidenceConsensusPaths(export_dir=export_dir, table_dir=table_dir, output_dir=output_dir),
        EvidenceConsensusOptions(include_visual_text=False, include_table_candidates=False, include_table_tiles=False),
    )
    refined = [r for r in result["records"] if r["evidence_layer"] == "table_tile_text_refined"]
    assert len(refined) == 1
    assert result["summary"]["table_tile_text_refined_records"] == 1
    assert refined[0]["trust_tier"] == "B"
    assert refined[0]["rag_action"] == "include_as_derived_context"
    assert refined[0]["confidence_scores"]["source_trace_score"] == 1.0
    assert refined[0]["confidence_scores"]["support_score"] > 0


def test_confidence_scores_are_advisory_not_routing_overrides(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    visual_dir = tmp_path / "visual"
    output_dir = tmp_path / "consensus"
    image = tmp_path / "page.tif"
    image.write_bytes(b"fake")
    _write_json(
        export_dir / "page_index.json",
        {"p1": {"page_id": "p1", "source_url": "x", "tiff_path": str(image), "page_role": "figure"}},
    )
    _write_json(export_dir / "part_tree.json", {"parts": []})
    _write_jsonl(
        visual_dir / "visual_text_extraction_clean.jsonl",
        [{"page_id": "p1", "trust_tier": "C", "status": "ok", "visual_text": "derived figure text"}],
    )
    result = build_and_write_evidence_consensus(
        EvidenceConsensusPaths(export_dir=export_dir, visual_text_dir=visual_dir, output_dir=output_dir),
        EvidenceConsensusOptions(include_table_candidates=False, include_table_tiles=False, include_table_tile_text_refined=False),
    )
    visual = [r for r in result["records"] if r["evidence_layer"] == "visual_text"][0]
    assert visual["trust_tier"] == "C"
    assert visual["confidence_scores"]["confidence_tier"] in {"A", "B", "C", "D"}
    assert result["summary"]["confidence_tier_disagreement_records"] >= 0



def test_trace_lc_confidence_scores_are_written_and_advisory(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    table_dir = tmp_path / "table"
    output_dir = tmp_path / "consensus"
    image = tmp_path / "page.tif"
    image.write_bytes(b"fake")
    ocr = tmp_path / "page.txt"
    ocr.write_text("120-12345-001", encoding="utf-8")

    _write_json(
        export_dir / "page_index.json",
        {
            "p1": {
                "page_id": "p1",
                "source_url": "http://localhost/p1",
                "tiff_path": str(image),
                "ocr_path": str(ocr),
                "page_role": "table",
                "part_numbers": ["120-12345-001"],
            }
        },
    )
    _write_json(export_dir / "part_tree.json", {"parts": []})
    _write_jsonl(
        table_dir / "table_tile_text_refined" / "table_tile_text_refined_records.jsonl",
        [
            {
                "page_id": "p1",
                "tile_id": "tile_001",
                "status": "ok",
                "trust_tier": "B",
                "tile_text": "120-12345-001",
                "catalog_supported_part_numbers": ["120-12345-001"],
            }
        ],
    )

    result = build_and_write_evidence_consensus(
        EvidenceConsensusPaths(export_dir=export_dir, table_dir=table_dir, output_dir=output_dir),
        EvidenceConsensusOptions(include_visual_text=False, include_table_candidates=False, include_table_tiles=False),
    )
    summary = result["summary"]
    assert summary["consensus_version"] == "trace_net_evidence_consensus_v1_2"
    assert summary["confidence_score_records"] == summary["records"]
    assert "confidence_avg_usable" in summary
    refined = [r for r in result["records"] if r["evidence_layer"] == "table_tile_text_refined"][0]
    scores = refined["confidence_scores"]
    assert scores["version"] == "trace_lc_v1"
    assert scores["usable_confidence"] > 0
    assert scores["confidence_tier"] in {"A", "B", "C", "D"}
    # Stage 1 is advisory: the existing trust tier/routing still wins.
    assert refined["trust_tier"] == "B"
    assert refined["rag_action"] == "include_as_derived_context"
