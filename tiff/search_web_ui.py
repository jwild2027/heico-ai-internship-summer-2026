"""Small local web UI for the TIFF search catalog.

This module intentionally uses only the Python standard library. It runs on the
same machine as the local TIFF search database and serves a simple browser UI.
It does not upload documents, OCR text, or paths anywhere.
"""

from __future__ import annotations

import csv
import html
import mimetypes
import os
import sqlite3
import sys
import threading
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import parse_qs, quote, unquote, urlparse

from tiff.search_index import SearchResult, collapse_ws, open_source_path, search_db

APP_TITLE = "Local TIFF Search"
DEFAULT_LIMIT = 25
MAX_LIMIT = 200


@dataclass(frozen=True)
class SearchRequest:
    query: str = ""
    mode: str = "auto"
    limit: int = DEFAULT_LIMIT


def clamp_limit(value: str | int | None, default: int = DEFAULT_LIMIT) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(MAX_LIMIT, parsed))


def parse_search_request(params: Mapping[str, list[str] | str]) -> SearchRequest:
    def first(name: str, default: str = "") -> str:
        value = params.get(name, default)
        if isinstance(value, list):
            return value[0] if value else default
        return str(value)

    mode = first("mode", "auto").strip().lower()
    if mode not in {"auto", "part", "keyword"}:
        mode = "auto"
    return SearchRequest(
        query=first("q", "").strip(),
        mode=mode,
        limit=clamp_limit(first("limit", str(DEFAULT_LIMIT))),
    )


def esc(value: object | None) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def resolve_source_path(path_value: str | None, repo_root: Path | None = None) -> Path | None:
    """Resolve stored TIFF/OCR paths for local opening or streaming.

    Stored paths are usually relative to the project root, but the search DB may
    contain Windows-style backslashes. This function accepts normal paths and
    file:// URIs.
    """

    if not path_value:
        return None
    value = unquote(str(path_value).strip())
    if not value:
        return None

    parsed = urlparse(value)
    if parsed.scheme == "file":
        value = unquote(parsed.path)
        # file:///C:/... becomes /C:/... under urlparse on some platforms.
        if os.name == "nt" and len(value) >= 3 and value[0] == "/" and value[2] == ":":
            value = value[1:]
    elif parsed.scheme and len(parsed.scheme) > 1:
        # http(s) and other URI schemes are not local files.
        return None

    if os.name != "nt":
        value = value.replace("\\", "/")

    path = Path(value)
    if not path.is_absolute():
        path = (repo_root or Path.cwd()) / path
    try:
        return path.resolve()
    except OSError:
        return path


def result_file_url(route: str, path_value: str | None) -> str:
    if not path_value:
        return ""
    return f"/{route}?path={quote(str(path_value), safe='')}"


def result_anchor(label: str, href: str, css_class: str = "btn") -> str:
    if not href:
        return f'<span class="btn disabled">{esc(label)} unavailable</span>'
    return f'<a class="{esc(css_class)}" href="{esc(href)}" target="_blank" rel="noopener">{esc(label)}</a>'


def search_form_html(request: SearchRequest) -> str:
    mode_options = []
    for mode, label in [("auto", "Auto"), ("part", "Part number"), ("keyword", "Keyword")]:
        selected = " selected" if request.mode == mode else ""
        mode_options.append(f'<option value="{esc(mode)}"{selected}>{esc(label)}</option>')

    limit_options = []
    for limit in [10, 25, 50, 100, 200]:
        selected = " selected" if request.limit == limit else ""
        limit_options.append(f'<option value="{limit}"{selected}>{limit}</option>')

    return f"""
    <form class="search-form" method="get" action="/">
      <label class="search-label" for="q">Search part number, ATA code, manual code, or keyword</label>
      <div class="search-row">
        <input id="q" name="q" type="search" value="{esc(request.query)}" placeholder="Example: 120-37313-001" autofocus />
        <button type="submit">Search</button>
      </div>
      <div class="filters">
        <label>Mode
          <select name="mode">{''.join(mode_options)}</select>
        </label>
        <label>Results
          <select name="limit">{''.join(limit_options)}</select>
        </label>
        <a class="secondary-link" href="/">Clear</a>
      </div>
    </form>
    """


def result_card_html(result: SearchResult, number: int) -> str:
    title_bits = [f"Result {number}"]
    if result.publication_number:
        title_bits.append(result.publication_number)
    if result.ata_code:
        title_bits.append(f"ATA {result.ata_code}")
    if result.page_sequence is not None:
        title_bits.append(f"Seq {result.page_sequence}")
    if result.page_label:
        title_bits.append(f"Page {result.page_label}")

    rows = [
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
    table_rows = "\n".join(
        f"<tr><th>{esc(label)}</th><td>{esc(value)}</td></tr>"
        for label, value in rows
        if value not in (None, "")
    )

    tiff_view = result_file_url("file", result.tiff_path)
    tiff_open = result_file_url("open", result.tiff_path)
    ocr_view = result_file_url("file", result.ocr_text_path)

    path_for_copy = result.tiff_path or result.ocr_text_path or ""
    snippet = collapse_ws(result.snippet or "")
    part_evidence = collapse_ws(result.part_evidence_text or "")
    evidence_html = ""
    if part_evidence and part_evidence != snippet:
        evidence_html = f'<h3>Nomenclature evidence</h3><p class="snippet evidence">{esc(part_evidence)}</p>'

    return f"""
    <section class="result-card" id="result-{number}">
      <div class="result-heading">
        <h2>{esc(' - '.join(title_bits))}</h2>
        <a href="#top" class="back-link">Back to top</a>
      </div>
      <div class="actions">
        {result_anchor('View TIFF in browser', tiff_view)}
        {result_anchor('Open TIFF in desktop viewer', tiff_open)}
        {result_anchor('View OCR text', ocr_view)}
        <button type="button" class="btn light" onclick="copyText('{esc(path_for_copy)}')">Copy path</button>
      </div>
      <table>{table_rows}</table>
      {evidence_html}
      <h3>Matched text</h3>
      <p class="snippet">{esc(snippet) if snippet else 'No snippet available.'}</p>
    </section>
    """


def csv_text_for_results(results: Iterable[SearchResult]) -> str:
    output = StringIO()
    fieldnames = [
        "match_source",
        "matched_part_number",
        "part_nomenclature",
        "part_item_number",
        "part_quantity",
        "part_figure_number",
        "part_confidence",
        "manual_id",
        "publication_number",
        "ata_code",
        "page_sequence",
        "page_label",
        "page_type",
        "title",
        "tiff_path",
        "ocr_text_path",
        "rescarta_object_id",
        "rescarta_page_id",
        "snippet",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for result in results:
        writer.writerow({
            "match_source": result.match_source,
            "matched_part_number": result.matched_part_number or "",
            "part_nomenclature": result.part_nomenclature or "",
            "part_item_number": result.part_item_number or "",
            "part_quantity": result.part_quantity or "",
            "part_figure_number": result.part_figure_number or "",
            "part_confidence": result.part_confidence or "",
            "manual_id": result.manual_id,
            "publication_number": result.publication_number or "",
            "ata_code": result.ata_code or "",
            "page_sequence": result.page_sequence if result.page_sequence is not None else "",
            "page_label": result.page_label or "",
            "page_type": result.page_type or "",
            "title": result.title or "",
            "tiff_path": result.tiff_path or "",
            "ocr_text_path": result.ocr_text_path or "",
            "rescarta_object_id": result.rescarta_object_id or "",
            "rescarta_page_id": result.rescarta_page_id or "",
            "snippet": collapse_ws(result.snippet or ""),
        })
    return output.getvalue()


def db_summary_html(db_path: Path) -> str:
    if not db_path.exists():
        return f'<p class="warning">Search database not found: {esc(db_path)}</p>'
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            manuals = conn.execute("SELECT count(*) FROM manuals").fetchone()[0]
            pages = conn.execute("SELECT count(*) FROM pages").fetchone()[0]
            parts = conn.execute("SELECT count(*) FROM part_mentions").fetchone()[0]
            has_catalog = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='part_catalog'").fetchone() is not None
            catalog = conn.execute("SELECT count(*) FROM part_catalog").fetchone()[0] if has_catalog else 0
        finally:
            conn.close()
        catalog_html = f" &nbsp; Part catalog: {catalog}" if catalog else ""
        return f"<p class=\"db-summary\">Database: {esc(db_path)} &nbsp; Manuals: {manuals} &nbsp; Pages: {pages} &nbsp; Part mentions: {parts}{catalog_html}</p>"
    except Exception as exc:  # pragma: no cover - defensive display only
        return f'<p class="warning">Could not read database summary: {esc(exc)}</p>'


def render_page(
    request: SearchRequest,
    results: Iterable[SearchResult],
    *,
    db_path: Path,
    error: str | None = None,
) -> str:
    result_list = list(results)
    jump_links = "".join(
        f'<a class="jump" href="#result-{i}">{i}</a>' for i in range(1, len(result_list) + 1)
    )
    csv_link = ""
    if request.query and result_list:
        csv_link = (
            f'<a class="btn light" href="/csv?q={quote(request.query)}&mode={quote(request.mode)}&limit={request.limit}">Export CSV</a>'
        )

    cards = "\n".join(result_card_html(result, i) for i, result in enumerate(result_list, start=1))
    empty = ""
    if request.query and not result_list and not error:
        empty = '<p class="empty">No results found. Try keyword mode or remove punctuation.</p>'

    error_html = f'<p class="warning">{esc(error)}</p>' if error else ""

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{esc(APP_TITLE)}</title>
  <style>
    :root {{
      --bg: #f4f6f8;
      --card: #ffffff;
      --text: #1f2933;
      --muted: #637083;
      --border: #d9dee5;
      --accent: #1f5fbf;
      --accent-dark: #16498f;
      --light: #eef4ff;
      --danger-bg: #fff4e5;
      --danger-border: #f5b041;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.45;
    }}
    header {{
      background: #fff;
      border-bottom: 1px solid var(--border);
      padding: 20px 24px;
      position: sticky;
      top: 0;
      z-index: 5;
      box-shadow: 0 1px 8px rgba(0,0,0,0.05);
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    h1 {{ margin: 0 0 6px 0; font-size: 26px; }}
    h2 {{ margin: 0; font-size: 19px; }}
    h3 {{ margin: 16px 0 6px 0; font-size: 13px; color: var(--muted); letter-spacing: .06em; text-transform: uppercase; }}
    .subtle, .db-summary {{ color: var(--muted); font-size: 14px; margin: 0; }}
    .search-form {{ background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 18px; margin-bottom: 18px; }}
    .search-label {{ display: block; font-weight: 700; margin-bottom: 8px; }}
    .search-row {{ display: flex; gap: 10px; }}
    input[type="search"] {{ flex: 1; min-width: 260px; font-size: 18px; padding: 12px 14px; border: 1px solid var(--border); border-radius: 10px; }}
    button, .btn {{
      border: 1px solid var(--accent);
      background: var(--accent);
      color: #fff;
      border-radius: 9px;
      padding: 10px 13px;
      text-decoration: none;
      font-weight: 700;
      font-size: 14px;
      cursor: pointer;
      display: inline-block;
    }}
    button:hover, .btn:hover {{ background: var(--accent-dark); }}
    .btn.light, button.light {{ background: #fff; color: var(--accent); }}
    .btn.light:hover, button.light:hover {{ background: var(--light); }}
    .btn.disabled {{ border-color: #aab3bf; color: #aab3bf; background: #f2f4f7; cursor: default; }}
    .filters {{ display: flex; gap: 14px; align-items: center; flex-wrap: wrap; margin-top: 12px; }}
    .filters label {{ color: var(--muted); font-weight: 700; }}
    select {{ margin-left: 5px; padding: 7px; border: 1px solid var(--border); border-radius: 8px; }}
    .secondary-link {{ color: var(--accent); font-weight: 700; }}
    .toolbar {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin: 10px 0 18px 0; }}
    .jump {{ display: inline-block; padding: 7px 10px; border: 1px solid var(--border); background: #fff; border-radius: 8px; text-decoration: none; color: var(--accent); font-weight: 700; }}
    .result-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 14px; margin: 0 0 20px 0; padding: 18px; box-shadow: 0 1px 8px rgba(0,0,0,0.04); }}
    .result-heading {{ display: flex; justify-content: space-between; gap: 14px; align-items: baseline; }}
    .back-link {{ color: var(--accent); font-size: 13px; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
    th, td {{ border-top: 1px solid var(--border); padding: 7px 8px; vertical-align: top; text-align: left; }}
    th {{ width: 205px; color: var(--muted); }}
    .snippet {{ background: #f7f9fb; border: 1px solid var(--border); border-radius: 10px; padding: 12px; }}
    .warning {{ background: var(--danger-bg); border: 1px solid var(--danger-border); border-radius: 10px; padding: 12px; }}
    .empty {{ background: #fff; border: 1px solid var(--border); border-radius: 10px; padding: 14px; }}
    code {{ background: #eef1f5; padding: 2px 4px; border-radius: 4px; }}
    @media (max-width: 700px) {{
      .search-row {{ flex-direction: column; }}
      th {{ width: 130px; }}
      header {{ position: static; }}
    }}
  </style>
  <script>
    function copyText(text) {{
      if (!text) return;
      if (navigator.clipboard) {{
        navigator.clipboard.writeText(text).then(function() {{ alert('Path copied.'); }});
      }} else {{
        prompt('Copy path:', text);
      }}
    }}
  </script>
</head>
<body>
  <header id="top">
    <h1>{esc(APP_TITLE)}</h1>
    <p class="subtle">Search the local OCR/metadata catalog and open the matching TIFF page.</p>
    {db_summary_html(db_path)}
  </header>
  <main>
    {search_form_html(request)}
    {error_html}
    <div class="toolbar">
      <strong>{len(result_list)} result{'s' if len(result_list) != 1 else ''}</strong>
      {csv_link}
      {jump_links}
    </div>
    {empty}
    {cards}
  </main>
</body>
</html>"""


class TiffSearchHTTPRequestHandler(BaseHTTPRequestHandler):
    server_version = "TiffSearchHTTP/1.0"

    @property
    def app(self) -> "TiffSearchServer":
        return self.server  # type: ignore[return-value]

    def log_message(self, format: str, *args: object) -> None:
        # Keep standard access logs, but make them concise.
        sys.stderr.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), format % args))

    def send_text(self, text: str, status: int = 200, content_type: str = "text/html; charset=utf-8") -> None:
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if parsed.path in {"/", "/search"}:
            self.handle_search(params)
        elif parsed.path == "/csv":
            self.handle_csv(params)
        elif parsed.path == "/file":
            self.handle_file(params)
        elif parsed.path == "/open":
            self.handle_open(params)
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def handle_search(self, params: Mapping[str, list[str]]) -> None:
        request = parse_search_request(params)
        results: list[SearchResult] = []
        error = None
        if request.query:
            try:
                results = search_db(self.app.db_path, request.query, limit=request.limit, mode=request.mode)
            except Exception as exc:
                error = str(exc)
        self.send_text(render_page(request, results, db_path=self.app.db_path, error=error))

    def handle_csv(self, params: Mapping[str, list[str]]) -> None:
        request = parse_search_request(params)
        try:
            results = search_db(self.app.db_path, request.query, limit=request.limit, mode=request.mode) if request.query else []
            csv_text = csv_text_for_results(results)
        except Exception as exc:
            self.send_text(f"error\n{exc}\n", status=500, content_type="text/plain; charset=utf-8")
            return
        data = csv_text.encode("utf-8-sig")
        filename = "tiff_search_results.csv"
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def handle_file(self, params: Mapping[str, list[str]]) -> None:
        path_value = params.get("path", [""])[0]
        path = resolve_source_path(path_value, repo_root=self.app.repo_root)
        if not path or not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Local file not found")
            return
        mime, _encoding = mimetypes.guess_type(str(path))
        content_type = mime or "application/octet-stream"
        try:
            data = path.read_bytes()
        except OSError as exc:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Could not read file: {exc}")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'inline; filename="{path.name}"')
        self.end_headers()
        self.wfile.write(data)

    def handle_open(self, params: Mapping[str, list[str]]) -> None:
        path_value = params.get("path", [""])[0]
        path = resolve_source_path(path_value, repo_root=self.app.repo_root)
        if not path or not path.exists():
            self.send_text(
                render_page(SearchRequest(), [], db_path=self.app.db_path, error=f"Could not find local file: {path_value}"),
                status=404,
            )
            return
        try:
            open_source_path(str(path))
        except Exception as exc:
            self.send_text(
                render_page(SearchRequest(), [], db_path=self.app.db_path, error=f"Could not open local file: {exc}"),
                status=500,
            )
            return
        self.send_text(
            f"""<!doctype html><html><head><meta charset='utf-8'><title>Opened file</title></head>
            <body style='font-family: Arial, sans-serif; padding: 24px;'>
            <h1>Opening local file</h1>
            <p>{esc(path)}</p>
            <p><a href='javascript:window.close()'>Close this tab</a></p>
            </body></html>"""
        )


class TiffSearchServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], db_path: Path, repo_root: Path):
        super().__init__(server_address, TiffSearchHTTPRequestHandler)
        self.db_path = Path(db_path)
        self.repo_root = Path(repo_root).resolve()


def run_server(
    *,
    db_path: Path | str,
    host: str = "127.0.0.1",
    port: int = 8080,
    repo_root: Path | str = ".",
    open_browser: bool = False,
) -> None:
    server = TiffSearchServer((host, int(port)), Path(db_path), Path(repo_root))
    url = f"http://{host}:{port}/"
    print("Local TIFF search UI is running")
    print(f"  URL: {url}")
    print(f"  DB: {Path(db_path)}")
    print("  Press Ctrl+C to stop")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local TIFF search UI")
    finally:
        server.server_close()
