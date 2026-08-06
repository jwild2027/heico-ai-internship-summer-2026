"""Server-access checklist and runbook helpers for TIFF production intake.

This module is intentionally read-only/planning focused. It does not touch the
real server, OCR, indexes, or local database. It produces a checklist and a
safe first-run command plan for when server access becomes available.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DEFAULT_JSON_OUTPUT = Path("local_data/batch_audit/server_access_checklist.json")
DEFAULT_MARKDOWN_OUTPUT = Path("local_data/batch_audit/server_access_runbook.md")


@dataclass(frozen=True)
class ChecklistItem:
    """One question/requirement to resolve before production intake."""

    id: str
    section: str
    prompt: str
    why_it_matters: str
    expected_answer_type: str = "text"
    required_before_processing: bool = True


@dataclass(frozen=True)
class RunbookStep:
    """One safe operational step for the first server access pass."""

    number: int
    name: str
    goal: str
    command: str
    expected_output: str
    stop_if: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_checklist_items() -> list[ChecklistItem]:
    """Return the server-access checklist grouped by topic."""

    return [
        ChecklistItem(
            "access.server_root",
            "Access and permissions",
            "What is the exact read-only root path for the TIFF/ResCarta archive?",
            "All inventory and intake tools need a stable root path. We should not guess or crawl unrelated shares.",
        ),
        ChecklistItem(
            "access.approved_host",
            "Access and permissions",
            "Which machine is approved to run read-only inventory and pilot scripts?",
            "The processing host determines path syntax, available disk, network speed, and whether OCR tools can be installed.",
        ),
        ChecklistItem(
            "access.write_location",
            "Access and permissions",
            "Where are we allowed to write derived outputs such as OCR text, manifests, logs, and indexes?",
            "The source archive should stay read-only; derived data needs a separate approved location.",
        ),
        ChecklistItem(
            "access.data_policy",
            "Access and permissions",
            "Are there export, retention, or access-control rules for technical manuals and derived OCR text?",
            "OCR text, vectors, and summaries are derived from controlled source material and may need the same access restrictions.",
        ),
        ChecklistItem(
            "layout.folder_shape",
            "Archive layout",
            "What is the folder layout: one document per folder, ResCarta object folders, pages/ocr subfolders, ZIPs, or mixed?",
            "The scanner must group pages into documents without relying only on filenames.",
        ),
        ChecklistItem(
            "layout.metadata_files",
            "Archive layout",
            "Where are metadata files such as metadata.xml, JSON, MARC, or ResCarta descriptors stored?",
            "Metadata gives document IDs, titles, page order, and source-link information.",
        ),
        ChecklistItem(
            "layout.naming",
            "Archive layout",
            "Are TIFF filenames globally unique, document-local, or only page-number based?",
            "Our sample has duplicate stems across pages/OCR folders; production matching should use full path plus metadata.",
        ),
        ChecklistItem(
            "ocr.coverage",
            "OCR availability",
            "Does the server contain full-page OCR, header-only OCR, or no OCR? Where is it stored?",
            "OpenSearch, Qdrant, graph extraction, and RAG require body OCR, not just headers.",
        ),
        ChecklistItem(
            "ocr.format",
            "OCR availability",
            "If OCR exists, what format is it in: plain text, ALTO XML, hOCR, PDF text layer, database field, or ResCarta export?",
            "Different formats need different importers and quality checks.",
        ),
        ChecklistItem(
            "ocr.quality",
            "OCR availability",
            "Do we have OCR confidence data or sample pages to compare against the TIFF images?",
            "OCR quality determines whether part extraction and RAG are reliable.",
            required_before_processing=False,
        ),
        ChecklistItem(
            "rescarta.deep_links",
            "ResCarta/source links",
            "What is the real ResCarta deep-link URL format for a document/page?",
            "The local MVP uses placeholder links. Production needs links users can open.",
        ),
        ChecklistItem(
            "rescarta.auth",
            "ResCarta/source links",
            "Does ResCarta require authentication, VPN, cookies, or role-based access?",
            "The UI must show source links only to users with the right access.",
        ),
        ChecklistItem(
            "scale.file_count",
            "Scale and batching",
            "Roughly how many TIFF files and total bytes are in scope?",
            "The cost depends on page count, not only terabytes.",
        ),
        ChecklistItem(
            "scale.change_feed",
            "Scale and batching",
            "Is there a change feed, modified-time policy, or manifest that identifies new/changed pages?",
            "After baseline, incremental processing should avoid rescanning the full archive.",
            required_before_processing=False,
        ),
        ChecklistItem(
            "scale.pilot_scope",
            "Scale and batching",
            "Can we copy or process a small pilot set, for example 500 to 5,000 pages, before baseline?",
            "A pilot proves OCR/extraction/index quality before large-scale processing.",
        ),
        ChecklistItem(
            "storage.postgres",
            "Production storage",
            "Where will PostgreSQL live, and who manages backups, access, and schema migrations?",
            "PostgreSQL will hold graph/catalog/source/feedback records.",
            required_before_processing=False,
        ),
        ChecklistItem(
            "storage.opensearch",
            "Production storage",
            "Where will OpenSearch live, and what index/retention limits should we assume?",
            "OpenSearch will hold searchable OCR/page/chunk text, which can be large.",
            required_before_processing=False,
        ),
        ChecklistItem(
            "storage.qdrant",
            "Production storage",
            "Where will Qdrant live, and what vector dimension/model/collection policy should we use?",
            "Qdrant stores embeddings and page/chunk pointers, not TIFF bytes.",
            required_before_processing=False,
        ),
        ChecklistItem(
            "security.permissions",
            "Security and audit",
            "What user/group permissions should be carried from source files into search results and graph records?",
            "Search and RAG must not reveal sources users cannot access.",
        ),
        ChecklistItem(
            "security.audit_log",
            "Security and audit",
            "Do we need an audit log for source opens, questions, answers, feedback, and exports?",
            "Technical data systems often need traceable usage history.",
            required_before_processing=False,
        ),
    ]


def build_runbook_steps(
    *,
    server_root: str = "<SERVER_ROOT>",
    target_total_tb: float = 5.0,
    max_files: int = 100_000,
    pilot_pages: int = 500,
) -> list[RunbookStep]:
    """Return safe first-run commands for real server access."""

    inventory = (
        "python scripts/maintenance/serving/audit_real_server_inventory.py "
        f"--root {server_root} --target-total-tb {target_total_tb:g} "
        f"--max-files {max_files} --write-json"
    )
    ocr_depth = (
        "python scripts/maintenance/s2_ocr/audit_ocr_depth.py "
        f"--root {server_root} --max-files {max_files} --write-json "
        "--json-output local_data/ocr/real_server_ocr_depth_sample.json"
    )
    batch_audit = (
        "python scripts/maintenance/ingestion/audit_document_batch.py "
        f"--root {server_root} --max-files {max_files} --write-json"
    )
    pilot = (
        "python scripts/operations/s2_ocr/run_ocr_pilot.py "
        f"--root {server_root} --limit {pilot_pages} --engine auto --write-json"
    )

    return [
        RunbookStep(
            1,
            "Confirm read-only access",
            "Verify the approved root path and confirm scripts will only read from it.",
            f"dir {server_root}  # Windows, or ls {server_root} on Git Bash/Linux",
            "You can list the top-level source folders without permission errors.",
            "Access denied, path unknown, or path points to a broader share than intended.",
        ),
        RunbookStep(
            2,
            "Read-only inventory sample",
            "Count files, measure sizes, and estimate scale without OCR/indexing.",
            inventory,
            "A JSON inventory report with TIFF count, bytes, OCR count, and rough scale estimates.",
            "The scan sees unrelated files, too many permission errors, or unexpected file layout.",
        ),
        RunbookStep(
            3,
            "OCR-depth sample",
            "Determine whether OCR is missing, header-only, empty, or full-page.",
            ocr_depth,
            "An OCR-depth report showing missing/header-only/full-page OCR counts.",
            "Most OCR is missing/header-only and no OCR-generation path is approved yet.",
        ),
        RunbookStep(
            4,
            "Document batch shape audit",
            "Check folder shape, duplicate names, empty files, TIFF/OCR pairing, and metadata presence.",
            batch_audit,
            "A batch audit report that confirms document organization and risky files.",
            "Duplicate matching is ambiguous, metadata is missing, or empty TIFF/metadata files appear.",
        ),
        RunbookStep(
            5,
            "Small OCR pilot only after approval",
            "Run OCR on a small pilot set to validate OCR quality before baseline processing.",
            pilot,
            "Pilot OCR files and an OCR pilot report under local_data/ocr/pilot/.",
            "No OCR engine is approved/available, or pilot OCR is not good enough for extraction.",
        ),
        RunbookStep(
            6,
            "Pilot quality gate",
            "Run source/OCR/graph/query quality checks against the pilot before scaling.",
            "python scripts/maintenance/benchmark/check_full_system_quality.py --require-api-adapter-quality --require-api-contract-tests --require-user-query-tests --require-realistic-query-trace --require-source-package-traceability",
            "Quality gate is OK for the pilot/local sample.",
            "Any source, OCR, graph, API, or user-query check fails.",
        ),
    ]


def build_server_access_runbook(
    *,
    server_root: str = "<SERVER_ROOT>",
    target_total_tb: float = 5.0,
    max_files: int = 100_000,
    pilot_pages: int = 500,
) -> dict[str, Any]:
    """Build a JSON-serializable server-access checklist/runbook."""

    checklist = build_checklist_items()
    steps = build_runbook_steps(
        server_root=server_root,
        target_total_tb=target_total_tb,
        max_files=max_files,
        pilot_pages=pilot_pages,
    )
    required_open_questions = sum(1 for item in checklist if item.required_before_processing)

    return {
        "status": "OK",
        "created_at": _now_iso(),
        "purpose": "Prepare for read-only real-server inventory, OCR-depth audit, pilot OCR, and safe batched intake.",
        "server_root": server_root,
        "target_total_tb": target_total_tb,
        "max_inventory_files": max_files,
        "pilot_pages": pilot_pages,
        "required_open_questions": required_open_questions,
        "checklist": [asdict(item) for item in checklist],
        "runbook_steps": [asdict(step) for step in steps],
        "guardrails": [
            "Do not run OCR, embeddings, or page-context generation across the full server on first access.",
            "Start with read-only inventory and OCR-depth audit using --max-files.",
            "Treat source TIFF locations as read-only; write derived outputs elsewhere.",
            "Do not store TIFF bytes in PostgreSQL, OpenSearch, or Qdrant.",
            "Require explicit approval before any large baseline processing run.",
            "Use pilot batches and quality gates before scaling.",
        ],
        "decision_points": [
            "If OCR is full-page and usable, import/clean it before OCR generation.",
            "If OCR is missing or header-only, run a controlled full-page OCR pilot.",
            "If TIFF count is extremely high, use selective/on-demand AI page context instead of all-page context.",
            "If ResCarta deep links are unknown, keep local source review links but mark real ResCarta not ready.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render the runbook report as Markdown."""

    lines: list[str] = []
    lines.append("# TIFF Real-Server Access Checklist and Runbook")
    lines.append("")
    lines.append(f"Generated: `{report.get('created_at', '-')}`")
    lines.append(f"Server root placeholder: `{report.get('server_root', '<SERVER_ROOT>')}`")
    lines.append(f"Target total TiB: `{report.get('target_total_tb')}`")
    lines.append(f"Max inventory files: `{report.get('max_inventory_files')}`")
    lines.append(f"Pilot pages: `{report.get('pilot_pages')}`")
    lines.append("")
    lines.append("## Purpose")
    lines.append("")
    lines.append(str(report.get("purpose", "")))
    lines.append("")
    lines.append("## Guardrails")
    lines.append("")
    for item in report.get("guardrails", []):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Checklist")
    lines.append("")
    current_section = None
    for item in report.get("checklist", []):
        section = item.get("section", "Other")
        if section != current_section:
            lines.append(f"### {section}")
            lines.append("")
            current_section = section
        required = "required" if item.get("required_before_processing") else "optional/planning"
        lines.append(f"- **{item.get('id')}** ({required}): {item.get('prompt')}")
        lines.append(f"  - Why: {item.get('why_it_matters')}")
    lines.append("")
    lines.append("## First-access runbook")
    lines.append("")
    for step in report.get("runbook_steps", []):
        lines.append(f"### {step.get('number')}. {step.get('name')}")
        lines.append("")
        lines.append(f"Goal: {step.get('goal')}")
        lines.append("")
        lines.append("```bash")
        lines.append(str(step.get("command", "")))
        lines.append("```")
        lines.append("")
        lines.append(f"Expected output: {step.get('expected_output')}")
        lines.append("")
        lines.append(f"Stop if: {step.get('stop_if')}")
        lines.append("")
    lines.append("## Decision points")
    lines.append("")
    for item in report.get("decision_points", []):
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def write_runbook_files(
    report: dict[str, Any], *, json_output: Path = DEFAULT_JSON_OUTPUT, markdown_output: Path = DEFAULT_MARKDOWN_OUTPUT
) -> None:
    """Write JSON and Markdown runbook files."""

    import json

    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.write_text(render_markdown(report), encoding="utf-8")
