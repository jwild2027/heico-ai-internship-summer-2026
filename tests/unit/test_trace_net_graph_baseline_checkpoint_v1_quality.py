from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_graph_baseline_checkpoint_v1 import (
    DEFAULT_QUALITY_FILE,
    SCHEMA_VERSION,
    evaluate_checkpoint_quality,
    main_quality,
    write_quality_result,
)


def make_checkpoint() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "checkpoint_name": "unit",
        "generated_at_utc": "2026-06-08T00:00:00Z",
        "checkpoint_sha256": "hash",
        "read_only": True,
        "graph_baseline": {
            "page_count": 509,
            "part_node_count": 442,
            "nomenclature_node_count": 151,
            "has_nomenclature_edge_count": 386,
            "page_context_v2_page_count": 50,
            "has_context_v2_edge_count": 50,
            "required_context_v2_coverage": {"missing_page_numbers": [], "missing_page_count": 0},
        },
        "retrieval_safety_baseline": {
            "rag_candidate_count": 1426,
            "source_citation_count": 1426,
            "unsafe_embedding_candidate_count": 0,
        },
        "artifact_baseline": {
            "graph_explorer_v2_nomenclature_quality": {"status": "PASS"},
        },
    }


def test_write_quality_result_creates_json_payload(tmp_path: Path) -> None:
    quality = evaluate_checkpoint_quality(make_checkpoint(), min_rag_candidates=1426, min_source_citations=1426)
    output_path = tmp_path / DEFAULT_QUALITY_FILE
    write_quality_result(quality, output_path)
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["summary"]["rag_candidate_count"] == 1426
    assert payload["checks"]


def test_main_quality_returns_zero_for_passing_checkpoint(tmp_path: Path, capsys) -> None:
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint_path.write_text(json.dumps(make_checkpoint()), encoding="utf-8")
    code = main_quality(
        [
            "--checkpoint-path",
            str(checkpoint_path),
            "--min-page-count",
            "509",
            "--min-part-nodes",
            "442",
            "--min-nomenclature-nodes",
            "151",
            "--min-has-nomenclature-edges",
            "386",
            "--min-context-v2-pages",
            "50",
            "--min-has-context-v2-edges",
            "50",
            "--min-rag-candidates",
            "1426",
            "--min-source-citations",
            "1426",
            "--require-graph-explorer-quality-pass",
            "--write-json",
        ]
    )
    assert code == 0
    output = capsys.readouterr().out
    assert "Status: PASS" in output
    assert (tmp_path / DEFAULT_QUALITY_FILE).exists()


def test_main_quality_returns_one_for_failed_checkpoint(tmp_path: Path, capsys) -> None:
    checkpoint = make_checkpoint()
    checkpoint["graph_baseline"]["nomenclature_node_count"] = 0
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    code = main_quality(
        [
            "--checkpoint-path",
            str(checkpoint_path),
            "--min-nomenclature-nodes",
            "1",
        ]
    )
    assert code == 1
    output = capsys.readouterr().out
    assert "Status: FAIL" in output
    assert "nomenclature_node_count" in output
