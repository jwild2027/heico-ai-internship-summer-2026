from __future__ import annotations

import json
from pathlib import Path

from tiff.pipeline_manifest import refresh_manifest_eval_summary, summarize_eval_json
from tiff.pipeline_runner import PipelineConfig, build_pipeline_steps


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_summarize_eval_json_counts_expanded_results() -> None:
    rows = [
        {"status": "pass", "llm_used": False, "embeddings_used": False},
        {"status": "pass", "llm_used": False, "embeddings_used": True},
        {"status": "manual_review", "llm_used": True, "embeddings_used": True},
    ]
    summary = summarize_eval_json(rows)
    assert summary["questions"] == 3
    assert summary["status_counts"] == {"manual_review": 1, "pass": 2}
    assert summary["llm_used"] == 1
    assert summary["embeddings_used"] == 2


def test_refresh_manifest_eval_summary_updates_latest_and_timestamped(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "pipeline_runs"
    latest = manifest_dir / "latest_backend_pipeline.json"
    timestamped = manifest_dir / "tiff_backend_pipeline_TEST-RUN.json"
    manifest = {
        "run_id": "TEST-RUN",
        "pipeline": "tiff_backend_pipeline",
        "status": "ok",
        "eval_summary": {"questions": 4, "status_counts": {"pass": 3, "manual_review": 1}},
        "qa_summary": {"review_queue_rows": 149},
        "artifacts": {"eval_html": "old.html", "eval_json": "old.json"},
    }
    _write_json(latest, manifest)
    _write_json(timestamped, manifest)

    eval_json = tmp_path / "evals" / "rag_eval_results.json"
    eval_csv = tmp_path / "evals" / "rag_eval_results.csv"
    rows = [
        {"status": "pass", "llm_used": False, "embeddings_used": False},
        {"status": "pass", "llm_used": False, "embeddings_used": True},
        {"status": "manual_review", "llm_used": True, "embeddings_used": True},
    ]
    _write_json(eval_json, rows)
    eval_csv.parent.mkdir(parents=True, exist_ok=True)
    eval_csv.write_text("id,status\n", encoding="utf-8")

    written = refresh_manifest_eval_summary(
        eval_csv=eval_csv,
        eval_json=eval_json,
        manifest_path=latest,
    )

    assert written == [latest, timestamped]
    refreshed = json.loads(latest.read_text(encoding="utf-8"))
    assert refreshed["eval_summary"]["questions"] == 3
    assert refreshed["eval_summary"]["status_counts"] == {"manual_review": 1, "pass": 2}
    assert refreshed["eval_summary"]["llm_used"] == 1
    assert refreshed["eval_summary"]["embeddings_used"] == 2
    assert refreshed["qa_summary"] == {"review_queue_rows": 149}
    assert refreshed["artifacts"]["eval_csv"] == str(eval_csv)
    assert refreshed["artifacts"]["eval_json"] == str(eval_json)
    assert "eval_html" not in refreshed["artifacts"]
    assert json.loads(timestamped.read_text(encoding="utf-8"))["eval_summary"]["questions"] == 3


def test_pipeline_eval_step_disables_mid_run_manifest_refresh() -> None:
    config = PipelineConfig(
        python_executable="python",
        skip_search_index=True,
        skip_part_catalog=True,
        skip_rag_chunks=True,
        skip_embeddings=True,
        skip_qa=True,
        questions_path="local_data/evals/rag_eval_questions.json",
    )
    steps = build_pipeline_steps(config)
    eval_steps = [step for step in steps if step.name == "rag_eval"]
    assert len(eval_steps) == 1
    assert "--no-refresh-manifest" in eval_steps[0].command
