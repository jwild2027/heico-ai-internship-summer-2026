from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_context_retrieval_helper_v1 import (
    DEFAULT_HELPERS_FILE,
    DEFAULT_QUALITY_FILE,
    build_helper_bundle,
    build_helper_records,
    evaluate_helper_quality,
    main_quality,
    write_helper_outputs,
    write_quality_result,
)


def make_row(page: int) -> dict:
    return {
        "context_id": f"ctx-{page}",
        "page_id": f"t_p_120_1176_p{page:06d}",
        "summary": f"Page {page} safe context summary.",
        "retrieval_cues": [f"cue {page}", "part lookup"],
        "answerable_questions": [f"What does page {page} help locate?"],
        "important_entities": [f"ENTITY-{page:03d}"],
        "component_families": ["manual page"],
        "source_grounding_phrases": [f"page {page}"],
    }


def make_baseline(tmp_path: Path, status: str = "PASS") -> Path:
    checkpoint = {
        "checkpoint_name": "trace_net_graph_ui_context_v2_nomenclature_baseline_v1",
        "checkpoint_sha256": "abc123",
        "graph_baseline": {
            "page_count": 509,
            "page_context_v2_page_count": 50,
            "has_context_v2_edge_count": 50,
            "nomenclature_node_count": 151,
            "has_nomenclature_edge_count": 386,
        },
        "retrieval_safety_baseline": {"rag_candidate_count": 1426, "source_citation_count": 1426},
    }
    checkpoint_path = tmp_path / "trace_net_graph_baseline_checkpoint_v1.json"
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    quality_path = tmp_path / "trace_net_graph_baseline_checkpoint_v1_quality.json"
    quality_path.write_text(json.dumps({"status": status}), encoding="utf-8")
    return checkpoint_path


def test_evaluate_quality_passes_for_50_safe_records(tmp_path: Path) -> None:
    records = build_helper_records([make_row(i) for i in range(1, 51)])
    baseline_path = make_baseline(tmp_path, "PASS")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    quality = evaluate_helper_quality(
        records,
        baseline_checkpoint=baseline,
        baseline_checkpoint_path=baseline_path,
        require_pages=list(range(1, 51)),
        require_baseline_quality_pass=True,
    )
    assert quality.status == "PASS"
    assert quality.summary["helper_count"] == 50
    assert quality.summary["unsafe_helper_count"] == 0
    assert quality.summary["required_page_missing_count"] == 0
    assert quality.summary["baseline_quality_status"] == "PASS"


def test_evaluate_quality_fails_when_context_can_answer() -> None:
    records = build_helper_records([make_row(i) for i in range(1, 51)])
    records[0]["can_answer_directly"] = True
    quality = evaluate_helper_quality(records, require_pages=list(range(1, 51)))
    assert quality.status == "FAIL"
    assert quality.summary["can_answer_directly_true_count"] == 1
    assert quality.summary["unsafe_helper_count"] >= 1


def test_evaluate_quality_fails_when_required_page_missing() -> None:
    records = build_helper_records([make_row(i) for i in range(1, 50)])
    quality = evaluate_helper_quality(records, require_pages=list(range(1, 51)), min_helper_records=49, min_pages_with_helpers=49)
    assert quality.status == "FAIL"
    assert quality.summary["required_page_missing_count"] == 1
    assert quality.summary["required_page_coverage"]["missing_page_numbers"] == [50]


def test_write_quality_result_creates_json(tmp_path: Path) -> None:
    records = build_helper_records([make_row(i) for i in range(1, 51)])
    quality = evaluate_helper_quality(records, require_pages=list(range(1, 51)))
    output_path = tmp_path / DEFAULT_QUALITY_FILE
    write_quality_result(quality, output_path)
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["summary"]["helper_count"] == 50
    assert payload["checks"]


def test_main_quality_passes_and_writes_json(tmp_path: Path, capsys) -> None:
    bundle = build_helper_bundle([make_row(i) for i in range(1, 51)], require_pages=list(range(1, 51)))
    write_helper_outputs(bundle, tmp_path)
    baseline_path = make_baseline(tmp_path, "PASS")
    code = main_quality(
        [
            "--helpers-path",
            str(tmp_path / DEFAULT_HELPERS_FILE),
            "--baseline-checkpoint",
            str(baseline_path),
            "--require-baseline-quality-pass",
            "--require-first-pages",
            "1-50",
            "--write-json",
        ]
    )
    assert code == 0
    output = capsys.readouterr().out
    assert "Status: PASS" in output
    assert (tmp_path / DEFAULT_QUALITY_FILE).exists()


def test_main_quality_fails_for_unsafe_record(tmp_path: Path, capsys) -> None:
    records = build_helper_records([make_row(i) for i in range(1, 51)])
    records[0]["can_prove_claims"] = True
    payload = {"records": records}
    helpers_path = tmp_path / DEFAULT_HELPERS_FILE
    helpers_path.write_text(json.dumps(payload), encoding="utf-8")
    code = main_quality(["--helpers-path", str(helpers_path), "--require-first-pages", "1-50"])
    assert code == 1
    output = capsys.readouterr().out
    assert "Status: FAIL" in output
    assert "unsafe_helper_count" in output
