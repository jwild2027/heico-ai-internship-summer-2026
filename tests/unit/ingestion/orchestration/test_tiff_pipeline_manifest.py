from pathlib import Path
import json
import sqlite3

from tiff.pipeline_manifest import (
    build_pipeline_manifest,
    format_manifest_summary,
    summarize_eval_json,
    summarize_qa_json,
    write_pipeline_manifest,
)
from tiff.pipeline_runner import PipelineConfig, PipelineRunResult, PipelineStep


def _make_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE manuals (manual_id TEXT);
            CREATE TABLE pages (page_id TEXT);
            CREATE TABLE part_mentions (part_number_display TEXT);
            CREATE TABLE part_catalog_clean (part_number_display TEXT);
            CREATE TABLE rag_chunks (chunk_id TEXT);
            CREATE TABLE rag_embeddings (chunk_id TEXT);
            INSERT INTO manuals VALUES ('m1');
            INSERT INTO pages VALUES ('p1');
            INSERT INTO pages VALUES ('p2');
            INSERT INTO part_mentions VALUES ('120-1');
            INSERT INTO part_catalog_clean VALUES ('120-1');
            INSERT INTO rag_chunks VALUES ('c1');
            INSERT INTO rag_embeddings VALUES ('c1');
            """
        )


def test_summarize_eval_json_accepts_list_rows():
    data = [
        {"status": "pass", "llm_used": False, "embeddings_used": False},
        {"status": "manual_review", "llm_used": True, "embeddings_used": True},
    ]

    summary = summarize_eval_json(data)

    assert summary["questions"] == 2
    assert summary["status_counts"] == {"manual_review": 1, "pass": 1}
    assert summary["llm_used"] == 1
    assert summary["embeddings_used"] == 1


def test_summarize_qa_json_counts_report_and_severity():
    data = [
        {"report": "part_nomenclature_conflicts", "severity": "review"},
        {"report": "suspicious_part_ata", "severity": "review"},
        {"report": "nomenclature_groups", "severity": "info"},
    ]

    summary = summarize_qa_json(data)

    assert summary["rows"] == 3
    assert summary["by_report"]["suspicious_part_ata"] == 1
    assert summary["by_severity"] == {"info": 1, "review": 2}


def test_write_pipeline_manifest_creates_timestamped_and_latest(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "search.db"
    _make_db(db_path)

    eval_dir = tmp_path / "local_data" / "evals"
    qa_dir = tmp_path / "local_data" / "qa"
    eval_dir.mkdir(parents=True)
    qa_dir.mkdir(parents=True)
    (eval_dir / "rag_eval_results.json").write_text(
        json.dumps([{"status": "pass", "llm_used": False, "embeddings_used": True}]),
        encoding="utf-8",
    )
    (qa_dir / "part_catalog_qa_all.json").write_text(
        json.dumps([{"report": "suspicious_part_ata", "severity": "review"}]),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    config = PipelineConfig(db_path=str(db_path), config_path="local_config.yaml")
    result = PipelineRunResult(
        step=PipelineStep("rag_eval", ("python", "scripts/benchmark/evaluate_rag_questions.py")),
        returncode=0,
        elapsed_seconds=1.25,
    )

    manifest = build_pipeline_manifest(
        config=config,
        results=[result],
        started_at="2026-01-01T00:00:00+00:00",
        ended_at="2026-01-01T00:00:02+00:00",
    )
    timestamped, latest = write_pipeline_manifest(manifest, tmp_path / "runs")

    assert timestamped.exists()
    assert latest.exists()
    payload = json.loads(latest.read_text(encoding="utf-8"))
    assert payload["status"] == "ok"
    assert payload["sqlite_counts"]["pages"] == 2
    assert payload["eval_summary"]["questions"] == 1
    assert payload["qa_summary"]["rows"] == 1
    assert payload["steps"][0]["elapsed_seconds"] == 1.25
    assert "Pipeline manifest" in format_manifest_summary(payload)
