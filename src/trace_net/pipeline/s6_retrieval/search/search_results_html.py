"""Clickable HTML export for local TIFF search results.

The HTML page is intentionally static and local-only. It does not require a web
server and does not upload source paths or document contents anywhere.
"""

from __future__ import annotations

import html
import os
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from tiff.search_index import SearchResult, collapse_ws


DEFAULT_TITLE = "TIFF Search Results"


def _has_uri_scheme(value: str) -> bool:
    parsed = urlparse(value)
    return bool(parsed.scheme and len(parsed.scheme) > 1)


def path_to_file_uri(path_value: str | None, base_dir: Path | None = None) -> str | None:
    """Convert a local path to a clickable file URI.

    Relative paths are resolved from base_dir, which should usually be the
    project repository root. Existing file://, http://, and https:// links are
    returned unchanged.
    """

    if not path_value:
        return None

    value = str(path_value).strip()
    if not value:
        return None
    if _has_uri_scheme(value):
        return value

    # Previous search results may contain Windows backslashes. On POSIX systems
    # used by tests, convert them so Path can still resolve the intended parts.
    if os.name != "nt":
        value = value.replace("\\", "/")

    path = Path(value)
    if not path.is_absolute():
        path = (base_dir or Path.cwd()) / path

    try:
        return path.resolve().as_uri()
    except ValueError:
        # Some unusual Windows/network paths can fail as_uri if not absolute.
        return str(path.resolve())


def _text(value: object | None) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _link(label: str, href: str | None, css_class: str = "button") -> str:
    if not href:
        return f'<span class="button disabled">{_text(label)} unavailable</span>'
    return f'<a class="{css_class}" href="{_text(href)}" target="_blank" rel="noopener">{_text(label)}</a>'


def _result_title(result: SearchResult, number: int) -> str:
    parts: list[str] = [f"Result {number}"]
    if result.publication_number:
        parts.append(result.publication_number)
    if result.ata_code:
        parts.append(f"ATA {result.ata_code}")
    if result.page_sequence is not None:
        parts.append(f"Seq {result.page_sequence}")
    if result.page_label:
        parts.append(f"Page {result.page_label}")
    return " - ".join(parts)


def render_search_results_html(
    query: str,
    results: Iterable[SearchResult],
    *,
    db_path: Path | str | None = None,
    base_dir: Path | None = None,
    title: str = DEFAULT_TITLE,
    generated_at: datetime | None = None,
) -> str:
    """Render a static HTML page for clickable local search results."""

    generated_at = generated_at or datetime.now()
    result_list = list(results)
    base_dir = base_dir or Path.cwd()

    nav_items = []
    for idx, result in enumerate(result_list, start=1):
        label_bits = [str(idx)]
        if result.page_sequence is not None:
            label_bits.append(f"seq {result.page_sequence}")
        if result.page_label:
            label_bits.append(f"pg {result.page_label}")
        nav_items.append(
            f'<a class="jump" href="#result-{idx}">{_text(" / ".join(label_bits))}</a>'
        )

    cards: list[str] = []
    for idx, result in enumerate(result_list, start=1):
        tiff_uri = path_to_file_uri(result.tiff_path, base_dir=base_dir)
        ocr_uri = path_to_file_uri(result.ocr_text_path, base_dir=base_dir)
        thumb_uri = path_to_file_uri(result.thumbnail_path, base_dir=base_dir)
        source_title = _result_title(result, idx)

        metadata_rows = [
            ("Match", result.match_source),
            ("Matched part", result.matched_part_number),
            ("Nomenclature", result.part_nomenclature),
            ("Item", result.part_item_number),
            ("Quantity", result.part_quantity),
            ("Figure", result.part_figure_number),
            ("Nomenclature confidence", result.part_confidence),
            ("Manual ID", result.manual_id),
            ("Publication", result.publication_number),
            ("ATA", result.ata_code),
            ("Page sequence", result.page_sequence),
            ("Page label", result.page_label),
            ("Page type", result.page_type),
            ("Title", result.title),
            ("ResCarta object/page", f"{result.rescarta_object_id or ''} / {result.rescarta_page_id or ''}".strip(" /")),
            ("TIFF path", result.tiff_path),
            ("OCR path", result.ocr_text_path),
        ]
        rows_html = "\n".join(
            f"<tr><th>{_text(label)}</th><td>{_text(value)}</td></tr>"
            for label, value in metadata_rows
            if value not in (None, "")
        )

        snippet = collapse_ws(result.snippet or "")
        part_evidence = collapse_ws(result.part_evidence_text or "")
        evidence_html = ""
        if part_evidence and part_evidence != snippet:
            evidence_html = f'<h3>Nomenclature evidence</h3><p class="snippet evidence">{_text(part_evidence)}</p>'
        thumbnail_html = ""
        if thumb_uri:
            thumbnail_html = f'<a href="{_text(tiff_uri or thumb_uri)}" target="_blank" rel="noopener"><img src="{_text(thumb_uri)}" alt="thumbnail for result {idx}" /></a>'

        cards.append(
            f"""
            <section id="result-{idx}" class="card">
              <div class="card-header">
                <h2>{_text(source_title)}</h2>
                <a class="top-link" href="#top">Back to top</a>
              </div>
              <div class="actions">
                {_link("Open TIFF", tiff_uri)}
                {_link("Open OCR text", ocr_uri)}
              </div>
              {thumbnail_html}
              <table>{rows_html}</table>
              {evidence_html}
              <h3>Matched text</h3>
              <p class="snippet">{_text(snippet) if snippet else "No snippet available."}</p>
            </section>
            """
        )

    empty_html = ""
    if not cards:
        empty_html = "<p class=\"empty\">No results found.</p>"

    db_label = str(db_path) if db_path else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_text(title)} - {_text(query)}</title>
  <style>
    :root {{
      --bg: #f6f7f9;
      --card: #ffffff;
      --text: #1f2933;
      --muted: #5b6773;
      --border: #d9dee5;
      --accent: #1f5fbf;
      --accent-dark: #16498f;
      --disabled: #9aa5b1;
    }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.45;
    }}
    header {{
      position: sticky;
      top: 0;
      z-index: 10;
      background: #ffffff;
      border-bottom: 1px solid var(--border);
      padding: 18px 24px;
      box-shadow: 0 1px 6px rgba(0,0,0,0.05);
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 24px;
    }}
    h1 {{
      margin: 0 0 8px 0;
      font-size: 24px;
    }}
    h2 {{
      margin: 0;
      font-size: 20px;
    }}
    h3 {{
      margin-bottom: 6px;
      color: var(--muted);
      font-size: 15px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .meta {{
      color: var(--muted);
      font-size: 14px;
    }}
    .jump-list {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 12px;
    }}
    .jump, .button {{
      display: inline-block;
      padding: 8px 11px;
      border-radius: 8px;
      text-decoration: none;
      border: 1px solid var(--accent);
      color: var(--accent);
      background: #ffffff;
      font-weight: 600;
      font-size: 14px;
    }}
    .button {{
      background: var(--accent);
      color: #ffffff;
      margin-right: 8px;
    }}
    .button:hover {{ background: var(--accent-dark); }}
    .jump:hover {{ background: #eef4ff; }}
    .disabled {{
      border-color: var(--disabled);
      color: var(--disabled);
      background: #f1f3f5;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      margin: 0 0 22px 0;
      padding: 20px;
      box-shadow: 0 1px 8px rgba(0,0,0,0.04);
    }}
    .card-header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
      margin-bottom: 12px;
    }}
    .top-link {{ color: var(--muted); font-size: 14px; }}
    .actions {{ margin: 12px 0 16px 0; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 12px;
      font-size: 14px;
    }}
    th, td {{
      border-top: 1px solid var(--border);
      padding: 8px;
      text-align: left;
      vertical-align: top;
      word-break: break-word;
    }}
    th {{
      width: 180px;
      color: var(--muted);
      font-weight: 700;
    }}
    .snippet {{
      background: #f2f5f8;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
      white-space: pre-wrap;
    }}
    img {{
      max-width: 220px;
      border: 1px solid var(--border);
      border-radius: 8px;
      margin: 8px 0;
    }}
    .empty {{
      background: #ffffff;
      border: 1px solid var(--border);
      padding: 18px;
      border-radius: 12px;
    }}
    code {{ background: #eef1f4; padding: 2px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
  <header id="top">
    <h1>{_text(title)}</h1>
    <div class="meta">
      Query: <code>{_text(query)}</code> &nbsp;|&nbsp;
      Results: {len(result_list)} &nbsp;|&nbsp;
      Generated: {_text(generated_at.strftime('%Y-%m-%d %H:%M:%S'))}
      {f' &nbsp;|&nbsp; DB: <code>{_text(db_label)}</code>' if db_label else ''}
    </div>
    <nav class="jump-list">{''.join(nav_items)}</nav>
  </header>
  <main>
    {empty_html}
    {''.join(cards)}
  </main>
</body>
</html>
"""


def write_search_results_html(
    query: str,
    results: Iterable[SearchResult],
    output_path: Path | str,
    *,
    db_path: Path | str | None = None,
    base_dir: Path | None = None,
    title: str = DEFAULT_TITLE,
) -> Path:
    """Write clickable search results to output_path and return the path."""

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    html_text = render_search_results_html(
        query=query,
        results=results,
        db_path=db_path,
        base_dir=base_dir,
        title=title,
    )
    output.write_text(html_text, encoding="utf-8")
    return output
