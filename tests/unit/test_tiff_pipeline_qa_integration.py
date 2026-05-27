from __future__ import annotations

from tiff.pipeline_manifest import summarize_qa_json
from tiff.pipeline_runner import PipelineConfig, build_pipeline_steps


def test_pipeline_runs_qa_triage_after_raw_qa() -> None:
    config = PipelineConfig(
        python_executable="python",
        skip_search_index=True,
        skip_part_catalog=True,
        skip_rag_chunks=True,
        skip_embeddings=True,
        skip_eval=True,
    )
    steps = build_pipeline_steps(config)
    names = [step.name for step in steps]
    assert names == ["part_catalog_qa", "part_catalog_qa_triage"]
    assert "scripts/triage_part_catalog_qa.py" in steps[1].command
    assert "--replace-all-report" in steps[1].command


def test_pipeline_can_skip_qa_triage() -> None:
    config = PipelineConfig(
        skip_search_index=True,
        skip_part_catalog=True,
        skip_rag_chunks=True,
        skip_embeddings=True,
        skip_eval=True,
        skip_qa_triage=True,
    )
    names = [step.name for step in build_pipeline_steps(config)]
    assert names == ["part_catalog_qa"]


def test_qa_summary_uses_triaged_severity_and_categories() -> None:
    payload = {
        "summary": {
            "review_queue_rows": 1,
            "suppressed_from_review_queue": 1,
        },
        "rows": [
            {
                "report": "part_nomenclature_conflicts",
                "severity": "review",
                "original_severity": "review",
                "triage_category": "real_part_nomenclature_conflict",
                "triage_action": "manual_review",
                "needs_review": "true",
            },
            {
                "report": "parts_missing_nomenclature",
                "severity": "info",
                "original_severity": "review",
                "triage_category": "compound_part_reference",
                "triage_action": "keep_as_info",
                "needs_review": "false",
            },
        ],
    }
    summary = summarize_qa_json(payload)
    assert summary["rows"] == 2
    assert summary["by_severity"] == {"info": 1, "review": 1}
    assert summary["by_original_severity"] == {"review": 2}
    assert summary["by_triage_category"] == {
        "compound_part_reference": 1,
        "real_part_nomenclature_conflict": 1,
    }
    assert summary["review_queue_rows"] == 1
    assert summary["suppressed_from_review_queue"] == 1
    assert summary["needs_review"] == 1
