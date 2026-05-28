"""Quality-gate checks for the local TIFF backend pipeline.

The quality gate is intentionally command-line first: it prints a compact
terminal report and writes JSON, but HTML is optional/legacy only. The checks
cover the pipeline manifest, minimum table counts, RAG eval results, QA triage,
and source-link audit readiness.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
from typing import Any, Mapping

DEFAULT_MANIFEST_PATH = "local_data/pipeline_runs/latest_backend_pipeline.json"


@dataclass(frozen=True)
class QualityGateThresholds:
    """Thresholds used by the backend quality gate."""

    max_eval_failures: int = 0
    max_manual_review: int = 1
    max_qa_review: int = 250
    max_suspicious_part_ata: int = 10
    max_source_pages_without_links: int = 0
    max_missing_source_tiff_files: int = 0
    max_missing_source_ocr_files: int = 0
    max_missing_source_urls: int = 0
    max_source_sample_queries_without_results: int = 0
    max_missing_ocr_paths: int = 0
    max_missing_ocr_files: int = 0
    max_unreadable_ocr_files: int = 0
    max_empty_ocr_files: int = 0
    max_short_ocr_files: int = 0
    max_org_pages_without_ata: int = 0
    min_org_distinct_parts: int = 1
    min_org_part_mentions: int = 1
    min_org_export_files: int = 5
    require_complete_ocr_text: bool = False
    require_real_rescarta: bool = False
    require_incremental_smoke: bool = False


@dataclass(frozen=True)
class QualityGateCheck:
    """One quality-gate check row."""

    name: str
    status: str
    message: str


@dataclass(frozen=True)
class QualityGateResult:
    """Full quality-gate result."""

    status: str
    manifest_path: str
    summary: dict[str, Any]
    checks: list[QualityGateCheck]


def load_manifest(path: str | Path = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    """Load a pipeline manifest JSON file."""
    manifest_path = Path(path)
    if not manifest_path.exists():
        return {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "ok"}




def _list_count(value: Any) -> int:
    return len(value) if isinstance(value, list) else _as_int(value)


def _add_check(checks: list[QualityGateCheck], name: str, ok: bool, message: str) -> None:
    checks.append(QualityGateCheck(name=name, status="OK" if ok else "FAIL", message=message))


def _count_eval_failures(status_counts: Mapping[str, Any]) -> int:
    total = 0
    for key, value in status_counts.items():
        label = str(key).strip().lower()
        if label in {"fail", "failed", "failure", "error"} or label.startswith("fail"):
            total += _as_int(value)
    return total


def _qa_review_count(qa_summary: Mapping[str, Any]) -> int:
    if "review_queue_rows" in qa_summary:
        return _as_int(qa_summary.get("review_queue_rows"))
    if "needs_review" in qa_summary:
        return _as_int(qa_summary.get("needs_review"))
    by_severity = _as_mapping(qa_summary.get("by_severity"))
    return _as_int(by_severity.get("review"))


def _table_count_check(checks: list[QualityGateCheck], sqlite_counts: Mapping[str, Any], table: str, minimum: int) -> None:
    count = _as_int(sqlite_counts.get(table))
    _add_check(
        checks,
        f"table_count_{table}",
        count >= minimum,
        f"{table} has {count} rows; minimum is {minimum}.",
    )


def check_pipeline_manifest(
    manifest: Mapping[str, Any],
    *,
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    thresholds: QualityGateThresholds | None = None,
) -> QualityGateResult:
    """Check a loaded pipeline manifest against quality gates."""
    limits = thresholds or QualityGateThresholds()
    checks: list[QualityGateCheck] = []

    pipeline_status = str(manifest.get("status") or "missing")
    _add_check(
        checks,
        "pipeline_status",
        pipeline_status == "ok",
        f"Pipeline manifest status is {pipeline_status}.",
    )

    steps = manifest.get("steps") if isinstance(manifest.get("steps"), list) else []
    failed_steps = [
        str(step.get("name") or "unknown")
        for step in steps
        if isinstance(step, Mapping) and _as_int(step.get("returncode"), default=1) != 0
    ]
    _add_check(
        checks,
        "pipeline_steps",
        not failed_steps,
        "All pipeline steps completed successfully." if not failed_steps else "Failed steps: " + ", ".join(failed_steps),
    )

    step_names = {str(step.get("name") or "") for step in steps if isinstance(step, Mapping)}
    _add_check(
        checks,
        "source_link_audit_step",
        "source_link_audit" in step_names,
        "source_link_audit step is present in the pipeline manifest."
        if "source_link_audit" in step_names
        else "source_link_audit step is missing; rerun the pipeline after applying the source-link integration patch.",
    )

    _add_check(
        checks,
        "ocr_coverage_audit_step",
        "ocr_coverage_audit" in step_names,
        "ocr_coverage_audit step is present in the pipeline manifest."
        if "ocr_coverage_audit" in step_names
        else "ocr_coverage_audit step is missing; rerun the pipeline after applying the OCR coverage integration patch.",
    )
    _add_check(
        checks,
        "document_organization_audit_step",
        "document_organization_audit" in step_names,
        "document_organization_audit step is present in the pipeline manifest."
        if "document_organization_audit" in step_names
        else "document_organization_audit step is missing; rerun the pipeline after applying the document organization integration patch.",
    )
    _add_check(
        checks,
        "document_organization_export_step",
        "document_organization_export" in step_names,
        "document_organization_export step is present in the pipeline manifest."
        if "document_organization_export" in step_names
        else "document_organization_export step is missing; rerun the pipeline after applying the document organization export integration patch.",
    )

    sqlite_counts = _as_mapping(manifest.get("sqlite_counts"))
    for table in (
        "manuals",
        "pages",
        "part_mentions",
        "part_catalog_clean",
        "rag_chunks",
        "rag_embeddings",
        "source_links",
    ):
        _table_count_check(checks, sqlite_counts, table, 1)

    eval_summary = _as_mapping(manifest.get("eval_summary"))
    status_counts = _as_mapping(eval_summary.get("status_counts"))
    eval_failures = _count_eval_failures(status_counts)
    eval_manual_review = _as_int(status_counts.get("manual_review"))
    _add_check(
        checks,
        "eval_failures",
        eval_failures <= limits.max_eval_failures,
        f"RAG eval failures: {eval_failures}; max allowed: {limits.max_eval_failures}.",
    )
    _add_check(
        checks,
        "eval_manual_review",
        eval_manual_review <= limits.max_manual_review,
        f"RAG eval manual-review rows: {eval_manual_review}; review threshold: {limits.max_manual_review}.",
    )

    qa_summary = _as_mapping(manifest.get("qa_summary"))
    qa_review_rows = _qa_review_count(qa_summary)
    by_report = _as_mapping(qa_summary.get("by_report"))
    suspicious_part_ata = _as_int(by_report.get("suspicious_part_ata"))
    _add_check(
        checks,
        "qa_review_rows",
        qa_review_rows <= limits.max_qa_review,
        f"QA review rows: {qa_review_rows}; review threshold: {limits.max_qa_review}.",
    )
    _add_check(
        checks,
        "suspicious_part_ata",
        suspicious_part_ata <= limits.max_suspicious_part_ata,
        f"Suspicious part/ATA rows: {suspicious_part_ata}; review threshold: {limits.max_suspicious_part_ata}.",
    )

    source_summary = _as_mapping(manifest.get("source_link_summary"))
    source_summary_present = bool(source_summary)
    source_local_ready = _as_bool(source_summary.get("ready_for_local_source_review"))
    source_real_rescarta_ready = _as_bool(source_summary.get("ready_for_real_rescarta_deeplinks"))
    source_pages_without_links = _as_int(source_summary.get("pages_without_source_links"))
    source_missing_tiff_paths = _as_int(source_summary.get("missing_tiff_path"))
    source_missing_ocr_paths = _as_int(source_summary.get("missing_ocr_path"))
    source_missing_source_urls = _as_int(source_summary.get("missing_source_url"))
    source_missing_tiff_files = _as_int(source_summary.get("missing_tiff_files"))
    source_missing_ocr_files = _as_int(source_summary.get("missing_ocr_files"))
    source_sample_queries_without_results = _as_int(source_summary.get("sample_queries_without_results"))
    source_placeholder_rescarta_urls = _as_int(source_summary.get("local_or_placeholder_rescarta_urls"))

    _add_check(
        checks,
        "source_link_summary",
        source_summary_present,
        "Source-link audit summary is present."
        if source_summary_present
        else "Source-link audit summary is missing; run the pipeline or scripts/audit_source_links.py --write-json.",
    )
    _add_check(
        checks,
        "source_local_review_ready",
        source_local_ready,
        "Local source review is ready."
        if source_local_ready
        else "Local source review is not ready; source links, TIFF paths, OCR paths, or files are missing.",
    )
    _add_check(
        checks,
        "source_pages_without_links",
        source_pages_without_links <= limits.max_source_pages_without_links,
        f"Pages without source links: {source_pages_without_links}; max allowed: {limits.max_source_pages_without_links}.",
    )
    _add_check(
        checks,
        "source_missing_tiff_paths",
        source_missing_tiff_paths <= limits.max_missing_source_tiff_files,
        f"Source rows missing TIFF paths: {source_missing_tiff_paths}; max allowed: {limits.max_missing_source_tiff_files}.",
    )
    _add_check(
        checks,
        "source_missing_ocr_paths",
        source_missing_ocr_paths <= limits.max_missing_source_ocr_files,
        f"Source rows missing OCR paths: {source_missing_ocr_paths}; max allowed: {limits.max_missing_source_ocr_files}.",
    )
    _add_check(
        checks,
        "source_missing_source_urls",
        source_missing_source_urls <= limits.max_missing_source_urls,
        f"Source rows missing source URLs: {source_missing_source_urls}; max allowed: {limits.max_missing_source_urls}.",
    )
    _add_check(
        checks,
        "source_missing_tiff_files",
        source_missing_tiff_files <= limits.max_missing_source_tiff_files,
        f"Missing TIFF files on disk: {source_missing_tiff_files}; max allowed: {limits.max_missing_source_tiff_files}.",
    )
    _add_check(
        checks,
        "source_missing_ocr_files",
        source_missing_ocr_files <= limits.max_missing_source_ocr_files,
        f"Missing OCR files on disk: {source_missing_ocr_files}; max allowed: {limits.max_missing_source_ocr_files}.",
    )
    _add_check(
        checks,
        "source_sample_queries",
        source_sample_queries_without_results <= limits.max_source_sample_queries_without_results,
        f"Source-audit sample queries without results: {source_sample_queries_without_results}; max allowed: {limits.max_source_sample_queries_without_results}.",
    )
    if limits.require_real_rescarta:
        _add_check(
            checks,
            "source_real_rescarta_ready",
            source_real_rescarta_ready,
            "Real ResCarta deep links are ready."
            if source_real_rescarta_ready
            else "Real ResCarta deep links are not ready yet.",
        )
    else:
        _add_check(
            checks,
            "source_real_rescarta_ready",
            True,
            "Real ResCarta deep links are not required yet; placeholder/local URLs are allowed for the local MVP.",
        )


    ocr_summary = _as_mapping(manifest.get("ocr_coverage_summary"))
    ocr_summary_present = bool(ocr_summary)
    ocr_local_ready = _as_bool(ocr_summary.get("local_ocr_paths_ready"))
    ocr_missing_paths = _as_int(ocr_summary.get("missing_ocr_paths"))
    ocr_missing_files = _as_int(ocr_summary.get("missing_ocr_files"))
    ocr_unreadable_files = _as_int(ocr_summary.get("unreadable_ocr_files"))
    ocr_empty_files = _as_int(ocr_summary.get("empty_ocr_files"))
    ocr_short_files = _as_int(ocr_summary.get("short_ocr_files"))
    ocr_nonempty_files = _as_int(ocr_summary.get("nonempty_ocr_files"))

    _add_check(
        checks,
        "ocr_coverage_summary",
        ocr_summary_present,
        "OCR coverage audit summary is present."
        if ocr_summary_present
        else "OCR coverage audit summary is missing; run the pipeline or scripts/audit_ocr_coverage.py --write-json.",
    )
    _add_check(
        checks,
        "ocr_local_paths_ready",
        ocr_local_ready,
        "Local OCR paths/files are ready."
        if ocr_local_ready
        else "Local OCR paths/files are not ready; OCR paths, files, or readability need attention.",
    )
    _add_check(
        checks,
        "ocr_missing_paths",
        ocr_missing_paths <= limits.max_missing_ocr_paths,
        f"Source-linked pages missing OCR paths: {ocr_missing_paths}; max allowed: {limits.max_missing_ocr_paths}.",
    )
    _add_check(
        checks,
        "ocr_missing_files",
        ocr_missing_files <= limits.max_missing_ocr_files,
        f"Source-linked pages missing OCR files: {ocr_missing_files}; max allowed: {limits.max_missing_ocr_files}.",
    )
    _add_check(
        checks,
        "ocr_unreadable_files",
        ocr_unreadable_files <= limits.max_unreadable_ocr_files,
        f"Unreadable OCR files: {ocr_unreadable_files}; max allowed: {limits.max_unreadable_ocr_files}.",
    )
    if limits.require_complete_ocr_text:
        _add_check(
            checks,
            "ocr_empty_files",
            ocr_empty_files <= limits.max_empty_ocr_files,
            f"Empty OCR files: {ocr_empty_files}; max allowed: {limits.max_empty_ocr_files}.",
        )
        _add_check(
            checks,
            "ocr_short_files",
            ocr_short_files <= limits.max_short_ocr_files,
            f"Short non-empty OCR files: {ocr_short_files}; max allowed: {limits.max_short_ocr_files}.",
        )
    else:
        _add_check(
            checks,
            "ocr_empty_or_short_review",
            True,
            f"Empty/short OCR review is allowed for local MVP: empty={ocr_empty_files}, short={ocr_short_files}. Use --require-complete-ocr-text to make this strict.",
        )





    org_summary = _as_mapping(manifest.get("document_organization_summary"))
    org_summary_present = bool(org_summary)
    org_tree_ready = _as_bool(org_summary.get("logical_tree_ready"))
    org_manuals = _as_int(org_summary.get("manuals_total"))
    org_pages = _as_int(org_summary.get("pages_total"))
    org_ata_groups = _as_int(org_summary.get("ata_groups_total"))
    org_pages_without_ata = _as_int(org_summary.get("pages_without_ata"))
    org_distinct_parts = _as_int(org_summary.get("distinct_parts_total"))
    org_part_mentions = _as_int(org_summary.get("part_mentions_total"))
    org_pages_with_parts = _as_int(org_summary.get("pages_with_parts"))
    org_empty_ocr_pages = _as_int(org_summary.get("empty_ocr_pages"))

    _add_check(
        checks,
        "document_organization_summary",
        org_summary_present,
        "Document organization audit summary is present."
        if org_summary_present
        else "Document organization audit summary is missing; run the pipeline or scripts/audit_document_organization.py --write-json.",
    )
    _add_check(
        checks,
        "document_organization_ready",
        org_tree_ready,
        "Logical document organization tree is ready."
        if org_tree_ready
        else "Logical document organization tree is not ready; manual/page/source data is missing.",
    )
    _add_check(
        checks,
        "document_organization_manuals",
        org_manuals >= 1,
        f"Logical organization manuals: {org_manuals}; minimum is 1.",
    )
    _add_check(
        checks,
        "document_organization_ata",
        org_ata_groups >= 1 and org_pages_without_ata <= limits.max_org_pages_without_ata,
        f"ATA groups={org_ata_groups}, pages_without_ata={org_pages_without_ata}; max pages without ATA is {limits.max_org_pages_without_ata}.",
    )
    _add_check(
        checks,
        "document_organization_parts",
        org_distinct_parts >= limits.min_org_distinct_parts and org_part_mentions >= limits.min_org_part_mentions,
        f"Distinct parts={org_distinct_parts}, part mentions={org_part_mentions}; minimums are {limits.min_org_distinct_parts} and {limits.min_org_part_mentions}.",
    )

    org_export_summary = _as_mapping(manifest.get("document_organization_export_summary"))
    org_export_present = bool(org_export_summary)
    org_export_ready = _as_bool(org_export_summary.get("ready"))
    org_export_files = _as_int(org_export_summary.get("files_written"))
    org_export_pages = _as_int(org_export_summary.get("page_count"))
    org_export_parts = _as_int(org_export_summary.get("part_count"))
    org_export_mentions = _as_int(org_export_summary.get("part_mention_count"))

    _add_check(
        checks,
        "document_organization_export_summary",
        org_export_present,
        "Document organization export summary is present."
        if org_export_present
        else "Document organization export summary is missing; run the pipeline or scripts/export_document_organization.py --strict.",
    )
    _add_check(
        checks,
        "document_organization_export_ready",
        org_export_ready,
        "Document organization export artifacts are ready."
        if org_export_ready
        else "Document organization export artifacts are not ready.",
    )
    _add_check(
        checks,
        "document_organization_export_files",
        org_export_files >= limits.min_org_export_files,
        f"Organization export wrote {org_export_files} files; minimum is {limits.min_org_export_files}.",
    )
    _add_check(
        checks,
        "document_organization_export_counts",
        org_export_pages >= 1 and org_export_parts >= limits.min_org_distinct_parts and org_export_mentions >= limits.min_org_part_mentions,
        f"Organization export counts: pages={org_export_pages}, parts={org_export_parts}, mentions={org_export_mentions}.",
    )

    incremental_summary = _as_mapping(manifest.get("incremental_summary"))
    incremental_present = bool(incremental_summary)
    incremental_ok = _as_bool(incremental_summary.get("ok"))
    incremental_dry_run = _as_bool(incremental_summary.get("dry_run"))
    incremental_changed_count = _as_int(incremental_summary.get("changed_list_count"), default=-1)
    incremental_changed_files = _as_int(incremental_summary.get("changed_files"), default=-1)
    incremental_state_committed = _as_bool(incremental_summary.get("state_committed"))
    incremental_backend_planned = _as_bool(incremental_summary.get("backend_command_planned"))
    incremental_changed_page_used = _as_bool(incremental_summary.get("changed_page_command_used"))
    incremental_full_backend_used = _as_bool(incremental_summary.get("full_backend_command_used"))
    incremental_ocr_skipped = _as_bool(incremental_summary.get("ocr_command_skipped"))
    incremental_errors = _list_count(incremental_summary.get("errors"))
    incremental_failed_commands = _list_count(incremental_summary.get("failed_commands"))

    _add_check(
        checks,
        "incremental_smoke_summary",
        incremental_present or not limits.require_incremental_smoke,
        "Incremental smoke summary is present."
        if incremental_present
        else "Incremental smoke summary is not required yet; run scripts/smoke_test_incremental_changed_page.py --write-json to add it.",
    )
    if incremental_present:
        _add_check(
            checks,
            "incremental_smoke_ok",
            incremental_ok,
            "Changed-page incremental smoke test passed." if incremental_ok else "Changed-page incremental smoke test did not pass.",
        )
        _add_check(
            checks,
            "incremental_smoke_changed_count",
            incremental_changed_count == 1 and incremental_changed_files == 1,
            f"Smoke test changed files/list count: changed_files={incremental_changed_files}, changed_list_count={incremental_changed_count}; expected 1 and 1.",
        )
        _add_check(
            checks,
            "incremental_smoke_backend_path",
            incremental_backend_planned and incremental_changed_page_used and not incremental_full_backend_used,
            "Smoke test used changed-page backend and avoided full rebuild."
            if incremental_backend_planned and incremental_changed_page_used and not incremental_full_backend_used
            else "Smoke test did not prove the changed-page backend path cleanly.",
        )
        _add_check(
            checks,
            "incremental_smoke_state_commit",
            (incremental_dry_run and not incremental_state_committed) or ((not incremental_dry_run) and incremental_state_committed),
            "Incremental state commit behavior matched dry-run/real-run expectations."
            if (incremental_dry_run and not incremental_state_committed) or ((not incremental_dry_run) and incremental_state_committed)
            else "Incremental state commit behavior was not safe for the smoke test.",
        )
        _add_check(
            checks,
            "incremental_smoke_ocr_skipped",
            incremental_ocr_skipped,
            "Smoke test skipped OCR as expected." if incremental_ocr_skipped else "Smoke test did not skip OCR.",
        )
        _add_check(
            checks,
            "incremental_smoke_errors",
            incremental_errors == 0 and incremental_failed_commands == 0,
            f"Smoke test errors={incremental_errors}, failed_commands={incremental_failed_commands}; expected 0 and 0.",
        )

    status = "ok" if all(check.status == "OK" for check in checks) else "fail"
    summary = {
        "run_id": manifest.get("run_id", "-"),
        "pipeline_status": pipeline_status,
        "eval_failures": eval_failures,
        "eval_manual_review": eval_manual_review,
        "qa_review_rows": qa_review_rows,
        "suspicious_part_ata": suspicious_part_ata,
        "source_local_review_ready": source_local_ready,
        "source_pages_without_links": source_pages_without_links,
        "source_missing_tiff_paths": source_missing_tiff_paths,
        "source_missing_ocr_paths": source_missing_ocr_paths,
        "source_missing_source_urls": source_missing_source_urls,
        "source_missing_tiff_files": source_missing_tiff_files,
        "source_missing_ocr_files": source_missing_ocr_files,
        "source_sample_queries_without_results": source_sample_queries_without_results,
        "source_real_rescarta_ready": source_real_rescarta_ready,
        "source_placeholder_rescarta_urls": source_placeholder_rescarta_urls,
        "ocr_coverage_present": ocr_summary_present,
        "ocr_local_paths_ready": ocr_local_ready,
        "ocr_nonempty_files": ocr_nonempty_files,
        "ocr_empty_files": ocr_empty_files,
        "ocr_short_files": ocr_short_files,
        "ocr_missing_paths": ocr_missing_paths,
        "ocr_missing_files": ocr_missing_files,
        "ocr_unreadable_files": ocr_unreadable_files,
        "document_organization_present": org_summary_present,
        "document_organization_ready": org_tree_ready,
        "document_organization_manuals": org_manuals,
        "document_organization_pages": org_pages,
        "document_organization_ata_groups": org_ata_groups,
        "document_organization_pages_without_ata": org_pages_without_ata,
        "document_organization_distinct_parts": org_distinct_parts,
        "document_organization_part_mentions": org_part_mentions,
        "document_organization_pages_with_parts": org_pages_with_parts,
        "document_organization_empty_ocr_pages": org_empty_ocr_pages,
        "document_organization_export_present": org_export_present,
        "document_organization_export_ready": org_export_ready,
        "document_organization_export_files": org_export_files,
        "document_organization_export_pages": org_export_pages,
        "document_organization_export_parts": org_export_parts,
        "document_organization_export_mentions": org_export_mentions,
        "incremental_smoke_present": incremental_present,
        "incremental_smoke_ok": incremental_ok if incremental_present else None,
        "incremental_changed_list_count": incremental_changed_count if incremental_present else None,
        "incremental_changed_files": incremental_changed_files if incremental_present else None,
        "incremental_state_committed": incremental_state_committed if incremental_present else None,
        "incremental_changed_page_command_used": incremental_changed_page_used if incremental_present else None,
        "incremental_full_backend_command_used": incremental_full_backend_used if incremental_present else None,
        "incremental_smoke_errors": incremental_errors if incremental_present else None,
    }
    return QualityGateResult(status=status, manifest_path=str(manifest_path), summary=summary, checks=checks)


def check_pipeline_manifest_file(
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    *,
    thresholds: QualityGateThresholds | None = None,
) -> QualityGateResult:
    """Load and check a manifest file."""
    manifest = load_manifest(manifest_path)
    return check_pipeline_manifest(manifest, manifest_path=manifest_path, thresholds=thresholds)


def format_quality_gate_result(result: QualityGateResult) -> str:
    """Format quality-gate results for terminal output."""
    lines = [
        "Pipeline quality gate",
        f"  Status: {result.status.upper()}",
        f"  Manifest: {result.manifest_path}",
        "  Summary:",
    ]
    for key, value in result.summary.items():
        lines.append(f"    {key}: {value}")
    lines.append("  Checks:")
    for check in result.checks:
        lines.append(f"    {check.status} {check.name}: {check.message}")
    return "\n".join(lines)


def quality_gate_result_to_dict(result: QualityGateResult) -> dict[str, Any]:
    """Convert a quality result to a JSON-serializable dictionary."""
    return asdict(result)


def write_quality_gate_json(result: QualityGateResult, path: str | Path) -> Path:
    """Write the quality-gate result as JSON."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(quality_gate_result_to_dict(result), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def write_quality_gate_html(result: QualityGateResult, path: str | Path) -> Path:
    """Write a minimal legacy HTML report only when explicitly requested."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    escaped = format_quality_gate_result(result).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    out.write_text(f"<!doctype html><meta charset='utf-8'><pre>{escaped}</pre>\n", encoding="utf-8")
    return out
