"""Run manifest and health-summary helpers for the TIFF backend pipeline."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
from typing import Any, Iterable, Mapping

DEFAULT_MANIFEST_DIR = "local_data/pipeline_runs"
DEFAULT_EVAL_JSON = "local_data/evals/rag_eval_results.json"
DEFAULT_QA_JSON = "local_data/qa/part_catalog_qa_all.json"
DEFAULT_SOURCE_LINK_AUDIT_JSON = "local_data/source_links/source_link_audit.json"

COUNT_TABLES = (
    "manuals",
    "pages",
    "part_mentions",
    "part_catalog",
    "part_catalog_clean",
    "ocr_clean_pages",
    "rag_chunks",
    "rag_embeddings",
    "source_links",
)


def utc_now_iso() -> str:
    """Return a filesystem-safe UTC timestamp string."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def read_json_file(path: str | Path) -> Any:
    """Read JSON, returning None if the file is missing or invalid."""
    json_path = Path(path)
    if not json_path.exists():
        return None
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def collect_sqlite_counts(db_path: str | Path, tables: Iterable[str] = COUNT_TABLES) -> dict[str, int]:
    """Collect row counts for known SQLite tables if they exist."""
    path = Path(db_path)
    if not path.exists():
        return {}
    counts: dict[str, int] = {}
    try:
        with sqlite3.connect(path) as conn:
            for table in tables:
                if _table_exists(conn, table):
                    row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                    counts[table] = int(row[0] if row else 0)
    except sqlite3.Error:
        return counts
    return counts


def summarize_eval_json(data: Any) -> dict[str, Any]:
    """Summarize evaluation JSON from evaluate_rag_questions.py."""
    if data is None:
        return {}
    if isinstance(data, dict):
        rows = data.get("results") or data.get("rows") or data.get("questions") or []
        direct = {k: v for k, v in data.items() if k not in {"results", "rows", "questions"}}
    elif isinstance(data, list):
        rows = data
        direct = {}
    else:
        return {}

    if not isinstance(rows, list):
        rows = []
    statuses: Counter[str] = Counter()
    llm_used = 0
    embeddings_used = 0
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        status = str(row.get("status") or row.get("result") or "unknown")
        statuses[status] += 1
        if bool(row.get("llm_used")):
            llm_used += 1
        if bool(row.get("embeddings_used")):
            embeddings_used += 1

    summary: dict[str, Any] = {
        "questions": len(rows),
        "status_counts": dict(sorted(statuses.items())),
        "llm_used": llm_used,
        "embeddings_used": embeddings_used,
    }
    summary.update(direct)
    return summary


def _rows_from_report_payload(data: Any) -> tuple[list[Any], dict[str, Any]]:
    if isinstance(data, dict):
        rows = data.get("rows") or data.get("results") or data.get("reports") or []
        direct = {k: v for k, v in data.items() if k not in {"rows", "results", "reports"}}
    elif isinstance(data, list):
        rows = data
        direct = {}
    else:
        return [], {}
    return (rows if isinstance(rows, list) else []), direct


def summarize_qa_json(data: Any) -> dict[str, Any]:
    """Summarize part-catalog QA JSON rows.

    Triaged QA reports include fields such as `triage_category`,
    `triage_action`, and `needs_review`. The manifest summary now preserves
    those counters so the quality gate/status output reflects the cleaned
    command-line QA report instead of only the old raw severity buckets.
    """
    if data is None:
        return {}

    rows, direct = _rows_from_report_payload(data)
    by_report: Counter[str] = Counter()
    by_severity: Counter[str] = Counter()
    by_original_severity: Counter[str] = Counter()
    by_triage_category: Counter[str] = Counter()
    by_triage_action: Counter[str] = Counter()
    needs_review_count = 0

    for row in rows:
        if not isinstance(row, Mapping):
            continue
        by_report[str(row.get("report") or row.get("type") or row.get("check") or "unknown")] += 1
        by_severity[str(row.get("severity") or row.get("triage_severity") or "unknown")] += 1
        original = row.get("original_severity")
        if original:
            by_original_severity[str(original)] += 1
        category = row.get("triage_category")
        if category:
            by_triage_category[str(category)] += 1
        action = row.get("triage_action")
        if action:
            by_triage_action[str(action)] += 1
        needs_review = str(row.get("needs_review") or "").strip().lower()
        if needs_review in {"1", "true", "yes", "y"}:
            needs_review_count += 1

    summary: dict[str, Any] = {
        "rows": len(rows),
        "by_report": dict(sorted(by_report.items())),
        "by_severity": dict(sorted(by_severity.items())),
    }
    if by_original_severity:
        summary["by_original_severity"] = dict(sorted(by_original_severity.items()))
    if by_triage_category:
        summary["by_triage_category"] = dict(sorted(by_triage_category.items()))
    if by_triage_action:
        summary["by_triage_action"] = dict(sorted(by_triage_action.items()))
    if needs_review_count:
        summary["needs_review"] = needs_review_count

    embedded_summary = direct.get("summary")
    if isinstance(embedded_summary, Mapping):
        review_queue = embedded_summary.get("review_queue_rows")
        suppressed = embedded_summary.get("suppressed_from_review_queue")
        if review_queue is not None:
            summary["review_queue_rows"] = review_queue
        if suppressed is not None:
            summary["suppressed_from_review_queue"] = suppressed

    for key, value in direct.items():
        if key == "summary":
            continue
        summary[key] = value
    return summary



def summarize_source_link_audit_json(data: Any) -> dict[str, Any]:
    """Summarize command-line source-link audit JSON for pipeline status."""
    if not isinstance(data, Mapping):
        return {}

    keys = (
        "total_links",
        "distinct_manuals",
        "pages_total",
        "pages_without_source_links",
        "missing_tiff_path",
        "missing_ocr_path",
        "missing_source_url",
        "missing_rescarta_url",
        "local_or_placeholder_rescarta_urls",
        "rescarta_urls_with_template_braces",
        "source_url_file_fallbacks",
        "missing_tiff_files",
        "missing_ocr_files",
        "sample_queries_checked",
        "sample_queries_without_results",
        "ready_for_local_source_review",
        "ready_for_real_rescarta_deeplinks",
    )
    summary = {key: data.get(key) for key in keys if key in data}
    warnings = data.get("warnings")
    if isinstance(warnings, list):
        summary["warnings"] = len(warnings)
    return summary


def _result_to_dict(result: Any) -> dict[str, Any]:
    step = getattr(result, "step", None)
    command = tuple(getattr(step, "command", ()) or ())
    return {
        "name": getattr(step, "name", "unknown"),
        "description": getattr(step, "description", ""),
        "command": list(command),
        "returncode": int(getattr(result, "returncode", 0)),
        "skipped": bool(getattr(result, "skipped", False)),
        "elapsed_seconds": float(getattr(result, "elapsed_seconds", 0.0) or 0.0),
    }


def build_pipeline_manifest(
    *,
    config: Any,
    results: Iterable[Any],
    started_at: str | None = None,
    ended_at: str | None = None,
    dry_run: bool = False,
    status: str | None = None,
) -> dict[str, Any]:
    """Build a JSON-serializable manifest for a backend pipeline run."""
    result_rows = [_result_to_dict(item) for item in results]
    ok = all(row["returncode"] == 0 for row in result_rows)
    run_status = status or ("ok" if ok else "failed")
    db_path = str(getattr(config, "db_path", "local_data/db/tiff_search.db"))
    eval_json = DEFAULT_EVAL_JSON
    qa_json = DEFAULT_QA_JSON
    source_link_audit_json = DEFAULT_SOURCE_LINK_AUDIT_JSON
    return {
        "manifest_version": 1,
        "run_id": utc_now_iso(),
        "pipeline": "tiff_backend_pipeline",
        "status": run_status,
        "dry_run": bool(dry_run),
        "started_at": started_at,
        "ended_at": ended_at,
        "config": {
            "db_path": db_path,
            "rescarta_export_dir": str(getattr(config, "rescarta_export_dir", "local_data/rescarta_exports")),
            "embed_model": str(getattr(config, "embed_model", "bge-m3:latest")),
            "config_path": str(getattr(config, "config_path", "local_config.yaml")),
            "questions_path": str(getattr(config, "questions_path", "local_data/evals/rag_eval_questions.json")),
        },
        "steps": result_rows,
        "sqlite_counts": collect_sqlite_counts(db_path),
        "artifacts": {
            "eval_csv": "local_data/evals/rag_eval_results.csv",
            "eval_json": eval_json,
            "qa_csv": "local_data/qa/part_catalog_qa_all.csv",
            "qa_json": qa_json,
            "source_links_csv": "local_data/source_links/rescarta_mapping_report.csv",
            "source_links_json": "local_data/source_links/rescarta_mapping_report.json",
            "source_link_audit_json": source_link_audit_json,
        },
        "eval_summary": summarize_eval_json(read_json_file(eval_json)),
        "qa_summary": summarize_qa_json(read_json_file(qa_json)),
        "source_link_summary": summarize_source_link_audit_json(read_json_file(source_link_audit_json)),
    }


def write_pipeline_manifest(
    manifest: Mapping[str, Any],
    manifest_dir: str | Path = DEFAULT_MANIFEST_DIR,
) -> tuple[Path, Path]:
    """Write timestamped and latest pipeline manifest files."""
    out_dir = Path(manifest_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(manifest.get("run_id") or utc_now_iso())
    timestamped = out_dir / f"tiff_backend_pipeline_{run_id}.json"
    latest = out_dir / "latest_backend_pipeline.json"
    payload = json.dumps(manifest, indent=2, sort_keys=True)
    timestamped.write_text(payload + "\n", encoding="utf-8")
    latest.write_text(payload + "\n", encoding="utf-8")
    return timestamped, latest


def refresh_manifest_eval_summary(
    *,
    eval_csv: str | Path = "local_data/evals/rag_eval_results.csv",
    eval_json: str | Path = DEFAULT_EVAL_JSON,
    manifest_path: str | Path = f"{DEFAULT_MANIFEST_DIR}/latest_backend_pipeline.json",
) -> list[Path]:
    """Refresh eval-summary fields inside the latest pipeline manifest.

    Standalone eval runs update ``local_data/evals/rag_eval_results.json``.
    The pipeline manifest is a snapshot from the last pipeline run, so without
    this helper status/quality commands can still show an older question count.
    This refresh updates only eval-related manifest fields and preserves the
    original run id, step results, DB counts, and QA summary.
    """
    manifest_file = Path(manifest_path)
    if not manifest_file.exists():
        return []

    manifest_payload = read_json_file(manifest_file)
    if not isinstance(manifest_payload, dict):
        return []

    eval_json_path = Path(eval_json)
    eval_payload = read_json_file(eval_json_path)
    manifest_payload["eval_summary"] = summarize_eval_json(eval_payload)

    artifacts = manifest_payload.get("artifacts")
    if not isinstance(artifacts, dict):
        artifacts = {}
    artifacts["eval_csv"] = str(Path(eval_csv))
    artifacts["eval_json"] = str(eval_json_path)
    # HTML is optional/legacy for evals; keep the default command-line path clean.
    artifacts.pop("eval_html", None)
    manifest_payload["artifacts"] = artifacts

    written: list[Path] = []
    payload = json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n"
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.write_text(payload, encoding="utf-8")
    written.append(manifest_file)

    run_id = str(manifest_payload.get("run_id") or "").strip()
    if run_id:
        timestamped = manifest_file.parent / f"tiff_backend_pipeline_{run_id}.json"
        if timestamped != manifest_file:
            timestamped.write_text(payload, encoding="utf-8")
            written.append(timestamped)
    return written


def format_manifest_summary(manifest: Mapping[str, Any]) -> str:
    """Return a concise human-readable manifest summary."""
    lines = [
        "Pipeline manifest",
        f"  Run ID: {manifest.get('run_id', '-')}",
        f"  Status: {manifest.get('status', '-')}",
        f"  Pipeline: {manifest.get('pipeline', '-')}",
    ]

    sqlite_counts = manifest.get("sqlite_counts") or {}
    if isinstance(sqlite_counts, Mapping) and sqlite_counts:
        lines.append("  SQLite counts:")
        for key in sorted(sqlite_counts):
            lines.append(f"    {key}: {sqlite_counts[key]}")

    eval_summary = manifest.get("eval_summary") or {}
    if isinstance(eval_summary, Mapping) and eval_summary:
        lines.append("  Eval summary:")
        lines.append(f"    Questions: {eval_summary.get('questions', '-')}")
        lines.append(f"    Status counts: {eval_summary.get('status_counts', {})}")
        lines.append(f"    LLM used: {eval_summary.get('llm_used', '-')}")
        lines.append(f"    Embeddings used: {eval_summary.get('embeddings_used', '-')}")

    qa_summary = manifest.get("qa_summary") or {}
    if isinstance(qa_summary, Mapping) and qa_summary:
        lines.append("  QA summary:")
        lines.append(f"    Rows: {qa_summary.get('rows', '-')}")
        if "review_queue_rows" in qa_summary:
            lines.append(f"    Review queue rows: {qa_summary.get('review_queue_rows')}")
        if "suppressed_from_review_queue" in qa_summary:
            lines.append(f"    Suppressed from review queue: {qa_summary.get('suppressed_from_review_queue')}")
        lines.append(f"    By report: {qa_summary.get('by_report', {})}")
        lines.append(f"    By severity: {qa_summary.get('by_severity', {})}")
        if qa_summary.get("by_triage_category"):
            lines.append(f"    By triage category: {qa_summary.get('by_triage_category', {})}")

    source_link_summary = manifest.get("source_link_summary") or {}
    if isinstance(source_link_summary, Mapping) and source_link_summary:
        lines.append("  Source-link summary:")
        lines.append(f"    Total links: {source_link_summary.get('total_links', '-')}")
        lines.append(f"    Indexed pages: {source_link_summary.get('pages_total', '-')}")
        lines.append(f"    Pages without source links: {source_link_summary.get('pages_without_source_links', '-')}")
        lines.append(f"    Missing TIFF files: {source_link_summary.get('missing_tiff_files', '-')}")
        lines.append(f"    Missing OCR files: {source_link_summary.get('missing_ocr_files', '-')}")
        lines.append(f"    Local source review ready: {source_link_summary.get('ready_for_local_source_review', '-')}")
        lines.append(f"    Real ResCarta deep-link ready: {source_link_summary.get('ready_for_real_rescarta_deeplinks', '-')}")
        placeholder_count = source_link_summary.get("local_or_placeholder_rescarta_urls")
        if placeholder_count is not None:
            lines.append(f"    Local/placeholder ResCarta URLs: {placeholder_count}")

    steps = manifest.get("steps") or []
    if isinstance(steps, list):
        lines.append("  Steps:")
        for step in steps:
            if not isinstance(step, Mapping):
                continue
            status = "OK" if step.get("returncode") == 0 else f"FAILED ({step.get('returncode')})"
            lines.append(f"    {step.get('name', 'unknown')}: {status}")
    return "\n".join(lines)
