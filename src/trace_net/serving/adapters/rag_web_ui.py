"""Tiny local web UI for source-backed TIFF RAG."""

from __future__ import annotations

import html
import os
import platform
import subprocess
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from tiff.ollama_client import DEFAULT_OLLAMA_URL
from tiff.rag_answer import RagAnswer, answer_question, format_source_label, source_role


def open_source_path(path: str | None) -> None:
    if not path:
        return
    source = Path(path)
    system = platform.system().lower()
    if system == "windows":
        os.startfile(str(source))  # type: ignore[attr-defined]
    elif system == "darwin":
        subprocess.run(["open", str(source)], check=False)
    else:
        subprocess.run(["xdg-open", str(source)], check=False)


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)




def source_group_name(source: Any) -> str:
    role = source_role(source)
    mapping = {
        "primary cleaned nomenclature source": "Primary nomenclature source",
        "primary catalog nomenclature source": "Catalog nomenclature source",
        "additional part-number mention": "Additional part-number mention",
        "keyword OCR context": "Keyword/OCR context",
        "semantic OCR context": "Semantic/vector context",
    }
    return mapping.get(role, "Other local source")

def _source_sort_key(source: Any) -> tuple[int, int, str]:
    role_rank = {
        "Primary nomenclature source": 0,
        "Catalog nomenclature source": 1,
        "Additional part-number mention": 2,
        "Keyword/OCR context": 3,
        "Semantic/vector context": 4,
    }.get(source_group_name(source), 9)
    page_seq = source.page_sequence if source.page_sequence is not None else 999999
    return (role_rank, int(page_seq), source.source_id or "")


def _render_source_card(source: Any, idx: int) -> str:
    tiff_q = urllib.parse.urlencode({"path": source.tiff_path or ""})
    ocr_q = urllib.parse.urlencode({"path": source.ocr_text_path or ""})
    role = source_group_name(source)
    return f"""
    <article class="source-card {role.lower().replace(' ', '-')}">
      <h3>{idx}. {_esc(format_source_label(source))}</h3>
      <p><b>Role:</b> {_esc(role)}</p>
      <p><b>Source type:</b> {_esc(source.source_type)} | <b>Role:</b> {_esc(source_role(source))} | <b>Score:</b> {_esc(round(source.score, 4))}</p>
      <p><b>Part:</b> {_esc(source.matched_part_number)} &nbsp; <b>Nomenclature:</b> {_esc(source.part_nomenclature)}</p>
      <p><b>Item:</b> {_esc(source.part_item_number)} &nbsp; <b>Quantity:</b> {_esc(source.part_quantity)}</p>
      <p><b>TIFF:</b> <code>{_esc(source.tiff_path)}</code></p>
      <p><b>OCR:</b> <code>{_esc(source.ocr_text_path)}</code></p>
      <p>
        <a class="button" href="/open?{tiff_q}">Open TIFF</a>
        <a class="button" href="/open?{ocr_q}">Open OCR</a>
      </p>
      <details {'open' if role in {'Primary nomenclature source', 'Catalog nomenclature source'} else ''}><summary>Evidence</summary><pre>{_esc(source.evidence_text or source.chunk_text)}</pre></details>
    </article>
    """


def _render_grouped_sources(answer: RagAnswer) -> str:
    if not answer.sources:
        return ""
    grouped: dict[str, list[Any]] = {}
    for source in sorted(answer.sources, key=_source_sort_key):
        grouped.setdefault(source_group_name(source), []).append(source)

    sections: list[str] = []
    running_idx = 1
    preferred_order = [
        "Primary nomenclature source",
        "Catalog nomenclature source",
        "Additional part-number mention",
        "Keyword/OCR context",
        "Semantic/vector context",
        "Other local source",
    ]
    for role in preferred_order:
        sources = grouped.get(role)
        if not sources:
            continue
        cards = []
        for source in sources:
            cards.append(_render_source_card(source, running_idx))
            running_idx += 1
        sections.append(f"<section><h2>{_esc(role)}s</h2>{''.join(cards)}</section>")
    return "".join(sections)


def render_answer_page(
    *,
    db_path: Path,
    question: str = "",
    answer: RagAnswer | None = None,
    embed_model: str = "bge-m3:latest",
    llm_model: str = "llama3.1:8b",
    use_llm: bool = True,
    answer_mode: str = "auto",
    retrieval_mode: str = "auto",
) -> str:
    source_html = ""
    warnings_html = ""
    answer_html = ""
    if answer:
        answer_html = f"""
        <section class="answer">
          <h2>Answer</h2>
          <pre>{_esc(answer.answer)}</pre>
          <p class="muted">LLM used: {_esc(answer.used_llm)} | Embeddings used: {_esc(answer.used_embeddings)}</p>
        </section>
        """
        if answer.warnings:
            warnings_html = "<section class='warnings'><h2>Warnings</h2><ul>" + "".join(
                f"<li>{_esc(w)}</li>" for w in answer.warnings
            ) + "</ul></section>"
        source_html = _render_grouped_sources(answer)

    checked = "checked" if use_llm else ""
    answer_mode_options = "".join(
        f'<option value="{m}" {"selected" if m == answer_mode else ""}>{m}</option>'
        for m in ["auto", "lookup", "locate", "summarize", "compare"]
    )
    retrieval_mode_options = "".join(
        f'<option value="{m}" {"selected" if m == retrieval_mode else ""}>{m}</option>'
        for m in ["auto", "structured", "keyword", "semantic", "hybrid"]
    )
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Local TIFF RAG</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem; line-height: 1.35; background: #fafafa; color: #111; }}
    input[type=text] {{ width: 72%; padding: .7rem; font-size: 1rem; }}
    button, .button {{ display: inline-block; padding: .55rem .8rem; border: 1px solid #444; border-radius: .35rem; background: white; color: #111; text-decoration: none; cursor: pointer; }}
    .muted {{ color: #666; }}
    .answer, .source-card, .warnings {{ background: white; border: 1px solid #ddd; border-radius: .6rem; padding: 1rem; margin: 1rem 0; }}
    .primary-nomenclature-source, .catalog-nomenclature-source {{ border-left: .45rem solid #333; }}
    pre {{ white-space: pre-wrap; overflow-x: auto; }}
    code {{ word-break: break-all; }}
    label {{ margin-right: 1rem; }}
  </style>
</head>
<body>
  <h1>Local TIFF RAG</h1>
  <p class="muted">Database: <code>{_esc(db_path)}</code></p>
  <form method="get" action="/ask">
    <input type="text" name="q" value="{_esc(question)}" placeholder="Ask: What is part number 120-37313-001?">
    <button type="submit">Ask</button>
    <p>
      <label>LLM model <input type="text" name="llm_model" value="{_esc(llm_model)}"></label>
      <label>Embedding model <input type="text" name="embed_model" value="{_esc(embed_model)}"></label>
      <label><input type="checkbox" name="use_llm" value="1" {checked}> Use Ollama LLM</label>
    </p>
    <p>
      <label>Answer mode
        <select name="answer_mode">{answer_mode_options}</select>
      </label>
      <label>Retrieval mode
        <select name="retrieval_mode">{retrieval_mode_options}</select>
      </label>
    </p>
  </form>
  <p>Good first tests: <code>What is part number 120-37313-001?</code> or <code>Where is MAGAZINE HOLDER shown?</code></p>
  {answer_html}
  {warnings_html}
  {source_html}
</body>
</html>"""


class RagUIHandler(BaseHTTPRequestHandler):
    db_path: Path = Path("local_data/db/tiff_search.db")
    embed_model: str = "bge-m3:latest"
    llm_model: str = "llama3.1:8b"
    ollama_url: str = DEFAULT_OLLAMA_URL

    def _send_html(self, body: str, status: int = 200) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - stdlib API
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/open":
            path = params.get("path", [""])[0]
            if path:
                open_source_path(path)
            self._redirect("/")
            return
        if parsed.path == "/ask":
            question = params.get("q", [""])[0].strip()
            embed_model = params.get("embed_model", [self.embed_model])[0] or self.embed_model
            llm_model = params.get("llm_model", [self.llm_model])[0] or self.llm_model
            use_llm = params.get("use_llm", [""])[0] == "1"
            answer_mode = params.get("answer_mode", ["auto"])[0] or "auto"
            retrieval_mode = params.get("retrieval_mode", ["auto"])[0] or "auto"
            answer = None
            if question:
                answer = answer_question(
                    self.db_path,
                    question,
                    embed_model=embed_model,
                    llm_model=llm_model,
                    ollama_url=self.ollama_url,
                    use_llm=use_llm,
                    use_embeddings=True,
                    answer_mode=answer_mode,
                    retrieval_mode=retrieval_mode,
                )
            self._send_html(
                render_answer_page(
                    db_path=self.db_path,
                    question=question,
                    answer=answer,
                    embed_model=embed_model,
                    llm_model=llm_model,
                    use_llm=use_llm,
                    answer_mode=answer_mode,
                    retrieval_mode=retrieval_mode,
                )
            )
            return
        self._send_html(
            render_answer_page(
                db_path=self.db_path,
                embed_model=self.embed_model,
                llm_model=self.llm_model,
                use_llm=True,
            )
        )


def serve_rag_ui(
    *,
    db_path: Path | str,
    host: str = "127.0.0.1",
    port: int = 8090,
    embed_model: str = "bge-m3:latest",
    llm_model: str = "llama3.1:8b",
    ollama_url: str = DEFAULT_OLLAMA_URL,
) -> ThreadingHTTPServer:
    handler = type(
        "ConfiguredRagUIHandler",
        (RagUIHandler,),
        {
            "db_path": Path(db_path),
            "embed_model": embed_model,
            "llm_model": llm_model,
            "ollama_url": ollama_url,
        },
    )
    server = ThreadingHTTPServer((host, int(port)), handler)
    return server
