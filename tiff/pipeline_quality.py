"""Quality gates for TIFF backend pipeline manifests.

This module is intentionally lightweight. It reads the JSON manifest written by
``scripts/run_tiff_backend_pipeline.py`` and decides whether the latest backend
run is acceptable for continued processing or review.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import html
import json
from typing import Any, Mapping


DEFAULT_MANIFEST_PATH = "local_data/pipeline_runs/latest_backend_pipeline.json"


@dataclass(frozen=True)
class QualityGateThresholds:
    """Thresholds used when checking a backend pipeline manifest."""

    max_eval_failures: int = 0
    max_manual_review: int = 1
    max_qa_review: int = 250
    max_suspicious_part_ata: int = 10
    min_manuals: int = 1
    min_pages: int = 1
    min_part_mentions: int = 1
    min_part_catalog_clean: int = 1
    min_rag_chunks: int = 1
    min_rag_embeddings: int = 1
    min_source_links: int = 1
    require_all_steps_ok: bool = True


@dataclass(frozen=True)
class QualityGateResult:
    """Result of checking a pipeline manifest."""

    status: str
    manifest_path: str
    checks: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def failed(self) -> bool:
        return self.status == "fail"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_manifest(path: str | Path = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    manifest_path = Path(path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Pipeline manifest not found: {manifest_path}")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Pipeline manifest is not a JSON object: {manifest_path}")
    return data


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _status_from_checks(checks: list[dict[str, Any]]) -> str:
    severities = {str(check.get("status")) for check in checks}
    if "fail" in severities:
        return "fail"
    if "review" in severities:
        return "review"
    return "ok"


def _add_check(checks: list[dict[str, Any]], name: str, status: str, details: str, *, actual: Any = None, expected: Any = None) -> None:
    checks.append(
        {
            "name": name,
            "status": status,
            "details": details,
            "actual": actual,
            "expected": expected,
        }
    )


def check_pipeline_manifest(
    manifest: Mapping[str, Any],
    *,
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    thresholds: QualityGateThresholds | None = None,
) -> QualityGateResult:
    """Check a backend pipeline manifest against quality thresholds."""

    t = thresholds or QualityGateThresholds()
    checks: list[dict[str, Any]] = []

    pipeline_status = str(manifest.get("status") or "missing")
    _add_check(
        checks,
        "pipeline_status",
        "ok" if pipeline_status == "ok" else "fail",
        f"Pipeline manifest status is {pipeline_status}.",
        actual=pipeline_status,
        expected="ok",
    )

    steps = manifest.get("steps") or []
    failed_steps: list[str] = []
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, Mapping):
                continue
            if _int(step.get("returncode")) != 0:
                failed_steps.append(str(step.get("name") or "unknown"))
    if t.require_all_steps_ok:
        _add_check(
            checks,
            "pipeline_steps",
            "ok" if not failed_steps else "fail",
            "All pipeline steps completed successfully." if not failed_steps else f"Failed steps: {', '.join(failed_steps)}",
            actual=failed_steps,
            expected=[],
        )

    counts = manifest.get("sqlite_counts") or {}
    if not isinstance(counts, Mapping):
        counts = {}
    required_counts = {
        "manuals": t.min_manuals,
        "pages": t.min_pages,
        "part_mentions": t.min_part_mentions,
        "part_catalog_clean": t.min_part_catalog_clean,
        "rag_chunks": t.min_rag_chunks,
        "rag_embeddings": t.min_rag_embeddings,
        "source_links": t.min_source_links,
    }
    for table, minimum in required_counts.items():
        actual = _int(counts.get(table), 0)
        _add_check(
            checks,
            f"table_count_{table}",
            "ok" if actual >= minimum else "fail",
            f"{table} has {actual} rows; minimum is {minimum}.",
            actual=actual,
            expected=f">= {minimum}",
        )

    eval_summary = manifest.get("eval_summary") or {}
    if not isinstance(eval_summary, Mapping):
        eval_summary = {}
    status_counts = eval_summary.get("status_counts") or {}
    if not isinstance(status_counts, Mapping):
        status_counts = {}
    eval_failures = _int(status_counts.get("fail"), 0) + _int(status_counts.get("failed"), 0)
    manual_review = _int(status_counts.get("manual_review"), 0) + _int(status_counts.get("review"), 0)
    _add_check(
        checks,
        "eval_failures",
        "ok" if eval_failures <= t.max_eval_failures else "fail",
        f"RAG eval failures: {eval_failures}; max allowed: {t.max_eval_failures}.",
        actual=eval_failures,
        expected=f"<= {t.max_eval_failures}",
    )
    _add_check(
        checks,
        "eval_manual_review",
        "ok" if manual_review <= t.max_manual_review else "review",
        f"RAG eval manual-review rows: {manual_review}; review threshold: {t.max_manual_review}.",
        actual=manual_review,
        expected=f"<= {t.max_manual_review}",
    )

    qa_summary = manifest.get("qa_summary") or {}
    if not isinstance(qa_summary, Mapping):
        qa_summary = {}
    by_severity = qa_summary.get("by_severity") or {}
    by_report = qa_summary.get("by_report") or {}
    if not isinstance(by_severity, Mapping):
        by_severity = {}
    if not isinstance(by_report, Mapping):
        by_report = {}
    qa_review = _int(by_severity.get("review"), 0)
    suspicious_ata = _int(by_report.get("suspicious_part_ata"), 0)
    _add_check(
        checks,
        "qa_review_rows",
        "ok" if qa_review <= t.max_qa_review else "review",
        f"QA review rows: {qa_review}; review threshold: {t.max_qa_review}.",
        actual=qa_review,
        expected=f"<= {t.max_qa_review}",
    )
    _add_check(
        checks,
        "suspicious_part_ata",
        "ok" if suspicious_ata <= t.max_suspicious_part_ata else "review",
        f"Suspicious part/ATA rows: {suspicious_ata}; review threshold: {t.max_suspicious_part_ata}.",
        actual=suspicious_ata,
        expected=f"<= {t.max_suspicious_part_ata}",
    )

    result_status = _status_from_checks(checks)
    summary = {
        "run_id": manifest.get("run_id"),
        "pipeline_status": pipeline_status,
        "eval_failures": eval_failures,
        "eval_manual_review": manual_review,
        "qa_review_rows": qa_review,
        "suspicious_part_ata": suspicious_ata,
        "sqlite_counts": dict(counts),
    }
    return QualityGateResult(status=result_status, manifest_path=str(manifest_path), checks=checks, summary=summary)


def check_pipeline_manifest_file(
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    *,
    thresholds: QualityGateThresholds | None = None,
) -> QualityGateResult:
    manifest = load_manifest(manifest_path)
    return check_pipeline_manifest(manifest, manifest_path=manifest_path, thresholds=thresholds)


def format_quality_gate_result(result: QualityGateResult) -> str:
    lines = ["Pipeline quality gate", f"  Status: {result.status.upper()}", f"  Manifest: {result.manifest_path}"]
    if result.summary:
        lines.append("  Summary:")
        for key in ["run_id", "pipeline_status", "eval_failures", "eval_manual_review", "qa_review_rows", "suspicious_part_ata"]:
            if key in result.summary:
                lines.append(f"    {key}: {result.summary[key]}")
    lines.append("  Checks:")
    for check in result.checks:
        status = str(check.get("status", "unknown")).upper()
        lines.append(f"    {status} {check.get('name')}: {check.get('details')}")
    return "\n".join(lines)


def write_quality_gate_json(result: QualityGateResult, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def write_quality_gate_html(result: QualityGateResult, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for check in result.checks:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(check.get('status')))}</td>"
            f"<td>{html.escape(str(check.get('name')))}</td>"
            f"<td>{html.escape(str(check.get('actual')))}</td>"
            f"<td>{html.escape(str(check.get('expected')))}</td>"
            f"<td>{html.escape(str(check.get('details')))}</td>"
            "</tr>"
        )
    html_doc = f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\">
  <title>TIFF Pipeline Quality Gate</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ccc; padding: 0.35rem 0.5rem; text-align: left; vertical-align: top; }}
    th {{ background: #f3f3f3; }}
    .status {{ font-size: 1.4rem; font-weight: bold; }}
    pre {{ background: #f7f7f7; padding: 1rem; overflow: auto; }}
  </style>
</head>
<body>
  <h1>TIFF Pipeline Quality Gate</h1>
  <p class=\"status\">Status: {html.escape(result.status.upper())}</p>
  <p>Manifest: {html.escape(result.manifest_path)}</p>
  <h2>Summary</h2>
  <pre>{html.escape(json.dumps(result.summary, indent=2, sort_keys=True))}</pre>
  <h2>Checks</h2>
  <table>
    <thead><tr><th>Status</th><th>Check</th><th>Actual</th><th>Expected</th><th>Details</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</body>
</html>
"""
    out.write_text(html_doc, encoding="utf-8")
    return out
