"""Inspect visual-text extraction outputs.

This module is read-only. It loads the visual text extraction JSONL/summary
artifacts produced by scripts/operations/visual/run_visual_text_extraction.py and renders them as
terminal summaries, markdown, or a local HTML review page.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_VISUAL_TEXT_DIR = Path("local_data/organization/visual_text")
DEFAULT_RECORDS_PATH = DEFAULT_VISUAL_TEXT_DIR / "visual_text_extraction.jsonl"
DEFAULT_SUMMARY_PATH = DEFAULT_VISUAL_TEXT_DIR / "visual_text_extraction_summary.json"
DEFAULT_REVIEW_MD_PATH = DEFAULT_VISUAL_TEXT_DIR / "visual_text_review.md"
DEFAULT_REVIEW_HTML_PATH = DEFAULT_VISUAL_TEXT_DIR / "visual_text_review.html"

SECTION_TITLES = (
    "Page type",
    "Visible title/header",
    "Transcribed visible text",
    "Visual summary",
    "OCR/context assist notes",
    "Tables",
    "Figures/diagrams",
    "Charts/graphs",
    "Labels/callouts/part numbers",
    "Warnings/notes",
    "Uncertain/unreadable",
    "Model caution",
)


@dataclass(frozen=True)
class VisualTextOutputPaths:
    records_path: Path = DEFAULT_RECORDS_PATH
    summary_path: Path = DEFAULT_SUMMARY_PATH


@dataclass(frozen=True)
class VisualTextOutputReport:
    summary: dict[str, Any]
    records: list[dict[str, Any]]
    section_counts: dict[str, int]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def load_visual_text_records(path: Path = DEFAULT_RECORDS_PATH) -> list[dict[str, Any]]:
    """Load visual-text JSONL records."""

    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return sorted(records, key=lambda record: _text(record.get("page_id")))


def parse_markdown_sections(markdown: str) -> dict[str, str]:
    """Parse the expected ## sections from one visual-text markdown blob."""

    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in str(markdown or "").splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            title = line[3:].strip()
            current = title
            sections.setdefault(current, [])
            continue
        if line.startswith("# "):
            current = None
            continue
        if current is not None:
            sections.setdefault(current, []).append(line)
    return {title: "\n".join(lines).strip() for title, lines in sections.items()}


def record_sections(record: Mapping[str, Any]) -> dict[str, str]:
    return parse_markdown_sections(_text(record.get("visual_text_markdown")))


def _snippet(text: Any, max_chars: int = 220) -> str:
    value = " ".join(_text(text).split())
    if len(value) <= max_chars:
        return value
    return value[: max(0, max_chars - 1)].rstrip() + "…"


def _record_search_text(record: Mapping[str, Any]) -> str:
    pieces: list[str] = []
    for key in (
        "page_id",
        "status",
        "provider",
        "model",
        "page_role",
        "image_classification",
        "visual_text_plain",
        "visual_text_markdown",
    ):
        pieces.append(_text(record.get(key)))
    parents = _as_dict(record.get("parents"))
    pieces.extend(_text(parents.get(key)) for key in ("document_label", "ata_code"))
    source = _as_dict(record.get("source"))
    pieces.extend(_text(source.get(key)) for key in ("source_url", "tiff_path", "ocr_path"))
    return "\n".join(pieces).lower()


def _record_ata(record: Mapping[str, Any]) -> str:
    return _text(_as_dict(record.get("parents")).get("ata_code")) or "unknown"


def _record_source(record: Mapping[str, Any]) -> dict[str, str]:
    source = _as_dict(record.get("source"))
    return {
        "source_url": _text(source.get("source_url")),
        "tiff_path": _text(source.get("tiff_path")),
        "ocr_path": _text(source.get("ocr_path")),
    }


def filter_records(
    records: Sequence[Mapping[str, Any]],
    page_ids: Sequence[str] = (),
    statuses: Sequence[str] = (),
    search: str = "",
    limit: int | None = None,
) -> list[dict[str, Any]]:
    wanted_pages = {_text(pid) for pid in page_ids if _text(pid)}
    wanted_statuses = {_text(status).lower() for status in statuses if _text(status)}
    needle = _text(search).lower()
    out: list[dict[str, Any]] = []
    for raw in records:
        record = dict(raw)
        if wanted_pages and _text(record.get("page_id")) not in wanted_pages:
            continue
        if wanted_statuses and _text(record.get("status")).lower() not in wanted_statuses:
            continue
        if needle and needle not in _record_search_text(record):
            continue
        out.append(record)
        if limit is not None and limit >= 0 and len(out) >= limit:
            break
    return out


def build_visual_text_output_report(paths: VisualTextOutputPaths = VisualTextOutputPaths()) -> VisualTextOutputReport:
    summary = _as_dict(_load_json(paths.summary_path, {}))
    records = load_visual_text_records(paths.records_path)
    section_counts: dict[str, int] = {title: 0 for title in SECTION_TITLES}
    for record in records:
        sections = record_sections(record)
        for title in SECTION_TITLES:
            if _text(sections.get(title)):
                section_counts[title] += 1
    if not summary:
        status_counts: dict[str, int] = {}
        for record in records:
            status = _text(record.get("status")) or "unknown"
            status_counts[status] = status_counts.get(status, 0) + 1
        summary = {
            "status": "OK" if records and status_counts.get("error", 0) == 0 else "UNKNOWN",
            "records": len(records),
            "ok_records": status_counts.get("ok", 0),
            "planned_records": status_counts.get("planned", 0),
            "error_records": status_counts.get("error", 0),
            "visual_text_char_total": sum(int(record.get("char_count") or 0) for record in records),
        }
    return VisualTextOutputReport(summary=summary, records=records, section_counts=section_counts)


def format_terminal_report(
    report: VisualTextOutputReport,
    records: Sequence[Mapping[str, Any]] | None = None,
    show_full: bool = False,
    max_records: int = 25,
) -> str:
    selected = list(records if records is not None else report.records)
    if max_records is not None and max_records >= 0 and not show_full:
        selected = selected[:max_records]

    summary = report.summary
    lines: list[str] = []
    lines.append("Visual text extraction outputs")
    lines.append(f"  Status: {_text(summary.get('status')) or _text(summary.get('Status')) or 'unknown'}")
    lines.append("  Summary:")
    for key in (
        "provider",
        "model",
        "selected_pages",
        "records",
        "ok_records",
        "planned_records",
        "error_records",
        "pages_with_visual_text",
        "visual_text_char_total",
        "visual_text_avg_chars",
        "prompt_version",
        "ocr_assist_enabled",
        "visual_text_v2_records",
        "visual_text_required_sections_records",
        "visual_text_transcribed_records",
        "visual_text_table_row_records",
        "visual_text_label_callout_records",
        "visual_text_part_number_records",
        "visual_text_ocr_context_note_records",
        "visual_text_metadata_leakage_records",
        "visual_text_summary_heavy_records",
        "visual_text_hallucination_risk_records",
        "graph_overlay_nodes",
        "graph_overlay_edges",
    ):
        if key in summary:
            lines.append(f"    {key}: {summary.get(key)}")
    lines.append("  Section coverage:")
    for title, count in report.section_counts.items():
        lines.append(f"    {title}: {count}")
    lines.append("")
    lines.append(f"Records shown: {len(selected)} / {len(report.records)}")

    for index, record in enumerate(selected, start=1):
        page_id = _text(record.get("page_id"))
        sections = record_sections(record)
        source = _record_source(record)
        lines.append("")
        lines.append(
            f"[{index}] {page_id} | status={_text(record.get('status')) or 'unknown'} "
            f"| ATA={_record_ata(record)} | role={_text(record.get('page_role')) or 'unknown'} "
            f"| image={_text(record.get('image_classification')) or 'unknown'} "
            f"| chars={record.get('char_count') or 0}"
        )
        if record.get("elapsed_seconds") not in (None, ""):
            lines.append(f"    elapsed_seconds: {record.get('elapsed_seconds')}")
        if source.get("source_url"):
            lines.append(f"    source_url: {source['source_url']}")
        if source.get("tiff_path"):
            lines.append(f"    tiff_path: {source['tiff_path']}")
        if _text(record.get("error")):
            lines.append(f"    error: {_text(record.get('error'))}")
        scores = _as_dict(record.get("visual_text_scores"))
        if scores:
            score_bits = []
            for key in ("required_sections_present", "has_table_rows", "has_figure_description", "has_labels_or_callouts", "has_part_numbers", "has_ocr_context_notes", "metadata_leakage_risk", "too_summary_heavy", "refusal_like", "hallucination_risk"):
                if key in scores:
                    score_bits.append(f"{key}={scores.get(key)}")
            lines.append(f"    scores: {'; '.join(score_bits)}")
        for title in SECTION_TITLES:
            value = sections.get(title)
            if _text(value):
                lines.append(f"    {title}: {_snippet(value, 260)}")
        if show_full:
            lines.append("    --- full visual_text_markdown ---")
            for raw_line in _text(record.get("visual_text_markdown")).splitlines():
                lines.append(f"    {raw_line}")
    return "\n".join(lines).rstrip() + "\n"


def build_markdown_review(report: VisualTextOutputReport, records: Sequence[Mapping[str, Any]] | None = None) -> str:
    selected = list(records if records is not None else report.records)
    summary = report.summary
    lines: list[str] = []
    lines.append("# Visual Text Extraction Review")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    for key in (
        "status",
        "provider",
        "model",
        "selected_pages",
        "records",
        "ok_records",
        "planned_records",
        "error_records",
        "pages_with_visual_text",
        "visual_text_char_total",
        "visual_text_avg_chars",
        "prompt_version",
        "ocr_assist_enabled",
        "visual_text_v2_records",
        "visual_text_required_sections_records",
        "visual_text_transcribed_records",
        "visual_text_table_row_records",
        "visual_text_label_callout_records",
        "visual_text_part_number_records",
        "visual_text_ocr_context_note_records",
        "visual_text_metadata_leakage_records",
        "visual_text_summary_heavy_records",
        "visual_text_hallucination_risk_records",
        "graph_overlay_nodes",
        "graph_overlay_edges",
    ):
        if key in summary:
            lines.append(f"- **{key}:** {summary.get(key)}")
    lines.append("")
    lines.append("## Section coverage")
    lines.append("")
    for title, count in report.section_counts.items():
        lines.append(f"- **{title}:** {count}")
    lines.append("")
    lines.append("## Records")
    lines.append("")
    for record in selected:
        page_id = _text(record.get("page_id"))
        lines.append(f"### {page_id}")
        lines.append("")
        lines.append(f"- status: {_text(record.get('status'))}")
        lines.append(f"- ATA: {_record_ata(record)}")
        lines.append(f"- role: {_text(record.get('page_role'))}")
        lines.append(f"- image_classification: {_text(record.get('image_classification'))}")
        lines.append(f"- chars: {record.get('char_count') or 0}")
        source = _record_source(record)
        if source.get("source_url"):
            lines.append(f"- source_url: {source['source_url']}")
        if source.get("tiff_path"):
            lines.append(f"- tiff_path: `{source['tiff_path']}`")
        if _text(record.get("error")):
            lines.append(f"- error: {_text(record.get('error'))}")
        lines.append("")
        lines.append(_text(record.get("visual_text_markdown")) or "_No visual text._")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _html_attr(value: Any) -> str:
    return html.escape(_text(value), quote=True)


def _html_text(value: Any) -> str:
    return html.escape(_text(value))


def build_html_review(report: VisualTextOutputReport, records: Sequence[Mapping[str, Any]] | None = None) -> str:
    selected = list(records if records is not None else report.records)
    summary = report.summary
    cards: list[str] = []
    for record in selected:
        page_id = _text(record.get("page_id"))
        sections = record_sections(record)
        source = _record_source(record)
        search = _record_search_text(record)
        section_blocks: list[str] = []
        for title in SECTION_TITLES:
            value = sections.get(title)
            if _text(value):
                section_blocks.append(
                    f"<section><h3>{_html_text(title)}</h3><pre>{_html_text(value)}</pre></section>"
                )
        if not section_blocks:
            section_blocks.append("<section><h3>No parsed sections</h3><pre>No visual-text sections were parsed for this record.</pre></section>")
        source_rows = "".join(
            f"<tr><th>{_html_text(key)}</th><td>{_html_text(value)}</td></tr>"
            for key, value in source.items()
            if value
        )
        error_block = ""
        if _text(record.get("error")):
            error_block = f"<div class='error'>Error: {_html_text(record.get('error'))}</div>"
        scores = _as_dict(record.get("visual_text_scores"))
        score_block = ""
        if scores:
            score_rows = "".join(
                f"<tr><th>{_html_text(key)}</th><td>{_html_text(value)}</td></tr>"
                for key, value in scores.items()
                if key in {
                    "required_sections_present",
                    "section_count",
                    "has_transcribed_visible_text",
                    "has_table_rows",
                    "has_figure_description",
                    "has_labels_or_callouts",
                    "has_part_numbers",
                    "visible_part_number_count",
                    "has_ocr_context_notes",
                    "metadata_leakage_risk",
                    "metadata_leakage_markers",
                    "metadata_leakage_marker_count",
                    "too_summary_heavy",
                    "refusal_like",
                    "hallucination_risk",
                }
            )
            score_block = f"<section><h3>Extraction scores</h3><table class='record-meta'>{score_rows}</table></section>"
        ocr_block = ""
        if _text(record.get("ocr_assist_preview")):
            ocr_block = f"<section><h3>OCR assist preview</h3><pre>{_html_text(record.get('ocr_assist_preview'))}</pre></section>"
        cards.append(
            "\n".join(
                [
                    f"<article class='card status-{_html_attr(record.get('status'))}' data-search='{_html_attr(search)}'>",
                    "<details>",
                    "<summary>",
                    f"<span class='page'>{_html_text(page_id)}</span>",
                    f"<span class='pill'>{_html_text(record.get('status'))}</span>",
                    f"<span class='meta'>ATA {_html_text(_record_ata(record))}</span>",
                    f"<span class='meta'>{_html_text(record.get('page_role'))}</span>",
                    f"<span class='meta'>{_html_text(record.get('image_classification'))}</span>",
                    f"<span class='meta'>{_html_text(record.get('char_count') or 0)} chars</span>",
                    "</summary>",
                    error_block,
                    "<table class='record-meta'>",
                    f"<tr><th>page_id</th><td>{_html_text(page_id)}</td></tr>",
                    f"<tr><th>provider</th><td>{_html_text(record.get('provider'))}</td></tr>",
                    f"<tr><th>model</th><td>{_html_text(record.get('model'))}</td></tr>",
                    f"<tr><th>elapsed_seconds</th><td>{_html_text(record.get('elapsed_seconds'))}</td></tr>",
                    source_rows,
                    "</table>",
                    score_block,
                    ocr_block,
                    "".join(section_blocks),
                    "<section><h3>Full markdown</h3>",
                    f"<pre>{_html_text(record.get('visual_text_markdown'))}</pre></section>",
                    "</details>",
                    "</article>",
                ]
            )
        )

    section_rows = "".join(
        f"<tr><th>{_html_text(title)}</th><td>{count}</td></tr>" for title, count in report.section_counts.items()
    )
    summary_rows = "".join(
        f"<tr><th>{_html_text(key)}</th><td>{_html_text(value)}</td></tr>"
        for key, value in summary.items()
        if key in {
            "status",
            "provider",
            "model",
            "selected_pages",
            "records",
            "ok_records",
            "planned_records",
            "error_records",
            "pages_with_visual_text",
            "visual_text_char_total",
            "visual_text_avg_chars",
            "prompt_version",
            "ocr_assist_enabled",
            "visual_text_v2_records",
            "visual_text_required_sections_records",
            "visual_text_transcribed_records",
            "visual_text_table_row_records",
            "visual_text_label_callout_records",
            "visual_text_part_number_records",
            "visual_text_ocr_context_note_records",
        "visual_text_metadata_leakage_records",
        "visual_text_summary_heavy_records",
            "visual_text_hallucination_risk_records",
            "graph_overlay_nodes",
            "graph_overlay_edges",
        }
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HEICO Visual Text Output Review</title>
<style>
:root {{ --bg:#0f172a; --panel:#111827; --card:#1f2937; --muted:#94a3b8; --text:#e5e7eb; --accent:#38bdf8; --ok:#22c55e; --err:#ef4444; --warn:#f59e0b; }}
body {{ margin:0; font-family:Segoe UI, Arial, sans-serif; background:var(--bg); color:var(--text); }}
header {{ position:sticky; top:0; z-index:2; background:rgba(15,23,42,.96); border-bottom:1px solid #334155; padding:18px 24px; }}
h1 {{ margin:0 0 8px; font-size:24px; }}
.controls {{ display:flex; gap:12px; flex-wrap:wrap; align-items:center; }}
input, select {{ background:#020617; color:var(--text); border:1px solid #475569; border-radius:8px; padding:9px 10px; }}
main {{ display:grid; grid-template-columns:340px 1fr; gap:18px; padding:18px 24px; }}
.panel {{ background:var(--panel); border:1px solid #334155; border-radius:14px; padding:14px; align-self:start; position:sticky; top:105px; }}
table {{ border-collapse:collapse; width:100%; }}
th,td {{ border-bottom:1px solid #334155; padding:7px 6px; text-align:left; vertical-align:top; }}
th {{ color:#bae6fd; width:160px; }}
.card {{ background:var(--card); border:1px solid #334155; border-radius:14px; margin:0 0 12px; overflow:hidden; }}
.card[hidden] {{ display:none; }}
summary {{ cursor:pointer; padding:13px 15px; display:flex; gap:10px; align-items:center; flex-wrap:wrap; }}
summary:hover {{ background:#273449; }}
.page {{ color:#f8fafc; font-weight:700; font-family:Consolas, monospace; }}
.pill {{ border-radius:999px; padding:3px 9px; background:#334155; color:#e2e8f0; font-size:12px; text-transform:uppercase; }}
.status-ok .pill {{ background:rgba(34,197,94,.18); color:#bbf7d0; }}
.status-error .pill {{ background:rgba(239,68,68,.18); color:#fecaca; }}
.status-planned .pill {{ background:rgba(245,158,11,.18); color:#fde68a; }}
.meta {{ color:var(--muted); font-size:13px; }}
.record-meta {{ margin:4px 15px 12px; width:calc(100% - 30px); }}
section {{ margin:14px 15px; border-top:1px solid #334155; padding-top:12px; }}
h3 {{ margin:0 0 8px; color:#7dd3fc; }}
pre {{ white-space:pre-wrap; word-wrap:break-word; background:#020617; border:1px solid #334155; border-radius:10px; padding:12px; line-height:1.45; color:#e2e8f0; }}
.error {{ margin:12px 15px; padding:10px; border-radius:10px; background:rgba(239,68,68,.15); color:#fecaca; }}
.count {{ color:var(--accent); font-weight:700; }}
@media (max-width: 900px) {{ main {{ grid-template-columns:1fr; }} .panel {{ position:static; }} }}
</style>
</head>
<body>
<header>
  <h1>HEICO Visual Text Output Review</h1>
  <div class="controls">
    <input id="search" placeholder="Search page, part, ATA, label, text..." size="42">
    <select id="status"><option value="">All statuses</option><option value="ok">ok</option><option value="error">error</option><option value="planned">planned</option></select>
    <button id="expand">Expand all</button>
    <button id="collapse">Collapse all</button>
    <span id="visibleCount" class="count"></span>
  </div>
</header>
<main>
  <aside class="panel">
    <h2>Run summary</h2>
    <table>{summary_rows}</table>
    <h2>Section coverage</h2>
    <table>{section_rows}</table>
  </aside>
  <section id="cards">
    {''.join(cards)}
  </section>
</main>
<script>
const searchInput = document.getElementById('search');
const statusInput = document.getElementById('status');
const count = document.getElementById('visibleCount');
const cards = Array.from(document.querySelectorAll('.card'));
function applyFilter() {{
  const needle = searchInput.value.trim().toLowerCase();
  const wantedStatus = statusInput.value.trim().toLowerCase();
  let shown = 0;
  for (const card of cards) {{
    const haystack = card.getAttribute('data-search') || '';
    const statusOk = !wantedStatus || card.classList.contains('status-' + wantedStatus);
    const textOk = !needle || haystack.includes(needle);
    const visible = statusOk && textOk;
    card.hidden = !visible;
    if (visible) shown += 1;
  }}
  count.textContent = shown + ' / ' + cards.length + ' records visible';
}}
searchInput.addEventListener('input', applyFilter);
statusInput.addEventListener('change', applyFilter);
document.getElementById('expand').addEventListener('click', () => cards.forEach(c => {{ if (!c.hidden) c.querySelector('details').open = true; }}));
document.getElementById('collapse').addEventListener('click', () => cards.forEach(c => c.querySelector('details').open = false));
applyFilter();
</script>
</body>
</html>
"""


def _open_in_browser(path: Path) -> None:
    path = path.resolve()
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        print(f"Open manually: {path}")


def _split_csv(values: Sequence[str] | None) -> list[str]:
    out: list[str] = []
    for value in values or []:
        out.extend(piece.strip() for piece in str(value).split(",") if piece.strip())
    return out


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Print or render visual-text extraction outputs.")
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS_PATH, help="Path to visual_text_extraction.jsonl.")
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH, help="Path to visual_text_extraction_summary.json.")
    parser.add_argument("--page-id", action="append", default=[], help="Page ID to show. Can be repeated or comma-separated.")
    parser.add_argument("--status", action="append", default=[], help="Status to show, such as ok/error/planned. Can be repeated or comma-separated.")
    parser.add_argument("--search", default="", help="Search text across page metadata and extracted visual text.")
    parser.add_argument("--limit", type=int, default=25, help="Maximum terminal records to show unless --full is used. Use -1 for all.")
    parser.add_argument("--full", action="store_true", help="Print full visual_text_markdown for shown records.")
    parser.add_argument("--write-md", nargs="?", const=str(DEFAULT_REVIEW_MD_PATH), default=None, help="Write markdown review. Optional path.")
    parser.add_argument("--write-html", nargs="?", const=str(DEFAULT_REVIEW_HTML_PATH), default=None, help="Write HTML review. Optional path.")
    parser.add_argument("--open", action="store_true", help="Open the HTML review after writing it.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    paths = VisualTextOutputPaths(records_path=args.records, summary_path=args.summary)
    report = build_visual_text_output_report(paths)
    page_ids = _split_csv(args.page_id)
    statuses = _split_csv(args.status)
    limit = args.limit if args.limit is not None and args.limit >= 0 else None
    selected = filter_records(report.records, page_ids=page_ids, statuses=statuses, search=args.search, limit=None)
    print(format_terminal_report(report, records=selected, show_full=args.full, max_records=(-1 if limit is None else limit)))

    if args.write_md:
        md_path = Path(args.write_md)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(build_markdown_review(report, selected), encoding="utf-8")
        print(f"Markdown review: {md_path}")

    html_path: Path | None = None
    if args.write_html:
        html_path = Path(args.write_html)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(build_html_review(report, selected), encoding="utf-8")
        print(f"HTML review: {html_path}")

    if args.open:
        if html_path is None:
            html_path = DEFAULT_REVIEW_HTML_PATH
            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text(build_html_review(report, selected), encoding="utf-8")
            print(f"HTML review: {html_path}")
        _open_in_browser(html_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
