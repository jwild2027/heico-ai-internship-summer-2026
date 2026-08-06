from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_confidence_stage2 import ConfidenceStage2Paths, evaluate_confidence_stage2


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")


def test_stage2_confusion_and_layer_metrics(tmp_path: Path) -> None:
    records = [
        {
            "record_id": "r1",
            "page_id": "p1",
            "evidence_layer": "source_trace",
            "trust_tier": "A",
            "rag_action": "include_as_source_evidence",
            "confidence_scores": {"confidence_tier": "B", "usable_confidence": 0.81, "support_score": 0.85, "risk_score": 0.05},
        },
        {
            "record_id": "r2",
            "page_id": "p1",
            "evidence_layer": "table_tile_text_refined",
            "trust_tier": "B",
            "rag_action": "include_as_derived_context",
            "confidence_scores": {"confidence_tier": "B", "usable_confidence": 0.77, "support_score": 0.8, "risk_score": 0.04},
        },
        {
            "record_id": "r3",
            "page_id": "p2",
            "evidence_layer": "visual_text",
            "trust_tier": "C",
            "rag_action": "exclude_from_rag",
            "confidence_scores": {"confidence_tier": "B", "usable_confidence": 0.71, "support_score": 0.75, "risk_score": 0.05},
        },
    ]
    records_path = tmp_path / "records.jsonl"
    summary_path = tmp_path / "summary.json"
    _write_jsonl(records_path, records)
    summary_path.write_text(json.dumps({"status": "OK", "pages_loaded": 2}), encoding="utf-8")

    paths = ConfidenceStage2Paths(consensus_records=records_path, consensus_summary=summary_path, output_dir=tmp_path / "out")
    report = evaluate_confidence_stage2(paths, max_samples=10)

    assert report["status"] == "OK"
    assert report["records"] == 3
    assert report["scored_records"] == 3
    assert report["disagreement_records"] == 2
    assert report["exact_match_records"] == 1
    assert report["confusion_matrix"]["A"]["B"] == 1
    assert report["confusion_matrix"]["C"]["B"] == 1
    assert report["per_layer"]["source_trace"]["source_trace" if False else "records"] == 1
    assert report["source_trace_confidence_below_A_records"] == 1
    assert report["rule_excludes_confidence_high_records"] == 1
    assert paths.eval_json.exists()
    assert paths.report_md.exists()
    assert paths.report_html.exists()


def test_stage2_handles_missing_confidence(tmp_path: Path) -> None:
    records = [
        {"record_id": "r1", "page_id": "p1", "evidence_layer": "source_trace", "trust_tier": "A"},
        {
            "record_id": "r2",
            "page_id": "p2",
            "evidence_layer": "part_catalog",
            "trust_tier": "A",
            "rag_action": "include_as_verified_part_evidence",
            "confidence_scores": {"confidence_tier": "B", "usable_confidence": 0.8, "support_score": 0.84, "risk_score": 0.05},
        },
    ]
    records_path = tmp_path / "records.jsonl"
    summary_path = tmp_path / "summary.json"
    _write_jsonl(records_path, records)
    summary_path.write_text(json.dumps({"status": "OK"}), encoding="utf-8")

    paths = ConfidenceStage2Paths(consensus_records=records_path, consensus_summary=summary_path, output_dir=tmp_path / "out")
    report = evaluate_confidence_stage2(paths)

    assert report["records"] == 2
    assert report["scored_records"] == 1
    assert report["missing_confidence_records"] == 1
