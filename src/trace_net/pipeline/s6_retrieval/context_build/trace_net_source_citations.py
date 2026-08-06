"""TRACE-Net source citation formatter v1.

Builds consistent source/citation records from the safe TRACE-Net RAG candidate
index and, when present, the most recent local search results. This module does
not search, embed, call an LLM, or decide trust. It formats already-safe evidence
so downstream answer composers and UI views can cite sources consistently.

Default inputs:
  local_data/organization/trace_net/rag_candidates/rag_candidate_chunks.jsonl
  local_data/organization/trace_net/search/trace_net_search_results.jsonl

Default outputs:
  local_data/organization/trace_net/citations/
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_CANDIDATE_PATH = Path("local_data/organization/trace_net/rag_candidates/rag_candidate_chunks.jsonl")
DEFAULT_SEARCH_RESULTS_PATH = Path("local_data/organization/trace_net/search/trace_net_search_results.jsonl")
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/citations")

CITATIONS_FILE = "trace_net_source_citations.jsonl"
CITATION_SUMMARY_FILE = "trace_net_source_citation_summary.json"
SEARCH_WITH_CITATIONS_FILE = "trace_net_search_results_with_citations.jsonl"
REVIEW_MD_FILE = "trace_net_source_citation_review.md"
REVIEW_HTML_FILE = "trace_net_source_citation_review.html"
GRAPH_NODES_FILE = "trace_net_source_citation_graph_nodes.json"
GRAPH_EDGES_FILE = "trace_net_source_citation_graph_edges.json"
QUALITY_FILE = "trace_net_source_citation_quality.json"

VERSION = "trace_net_source_citations_v1"
SAFE_BUCKETS = {"source_evidence", "source_text_evidence", "verified_part_evidence", "derived_context"}
SAFE_ACTIONS = {"include_as_source_evidence", "include_as_verified_part_evidence", "include_as_derived_context"}


@dataclass(frozen=True)
class SourceCitationPaths:
    candidate_path: Path = DEFAULT_CANDIDATE_PATH
    search_results_path: Path = DEFAULT_SEARCH_RESULTS_PATH
    output_dir: Path = DEFAULT_OUTPUT_DIR
    citations_path: Path | None = None
    search_with_citations_path: Path | None = None
    summary_path: Path | None = None
    review_md_path: Path | None = None
    review_html_path: Path | None = None
    graph_nodes_path: Path | None = None
    graph_edges_path: Path | None = None
    quality_path: Path | None = None

    @property
    def citations(self) -> Path:
        return self.citations_path or (self.output_dir / CITATIONS_FILE)

    @property
    def search_with_citations(self) -> Path:
        return self.search_with_citations_path or (self.output_dir / SEARCH_WITH_CITATIONS_FILE)

    @property
    def summary(self) -> Path:
        return self.summary_path or (self.output_dir / CITATION_SUMMARY_FILE)

    @property
    def review_md(self) -> Path:
        return self.review_md_path or (self.output_dir / REVIEW_MD_FILE)

    @property
    def review_html(self) -> Path:
        return self.review_html_path or (self.output_dir / REVIEW_HTML_FILE)

    @property
    def graph_nodes(self) -> Path:
        return self.graph_nodes_path or (self.output_dir / GRAPH_NODES_FILE)

    @property
    def graph_edges(self) -> Path:
        return self.graph_edges_path or (self.output_dir / GRAPH_EDGES_FILE)

    @property
    def quality(self) -> Path:
        return self.quality_path or (self.output_dir / QUALITY_FILE)


@dataclass(frozen=True)
class SourceCitationOptions:
    open_report: bool = False
    max_samples: int = 40
    include_search_results: bool = True


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    out = str(value).strip()
    return out if out else default


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(value, Mapping):
                rows.append(dict(value))
    return rows


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), sort_keys=True, ensure_ascii=False) + "\n")


def _write_text(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")


def _count(values: Iterable[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        text = _text(value)
        if not text:
            continue
        out[text] = out.get(text, 0) + 1
    return dict(sorted(out.items()))


def _clip(text: str, max_chars: int = 240) -> str:
    text = _text(text)
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 1)].rstrip() + "…"


def _short_hash(value: str, length: int = 10) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="replace")).hexdigest()[:length]


def _page_number(page_id: str) -> str:
    page_id = _text(page_id)
    if "_p" in page_id:
        suffix = page_id.rsplit("_p", 1)[-1]
        if suffix.isdigit():
            return str(int(suffix))
    return page_id


def _doc_label(document_id: str) -> str:
    doc = _text(document_id)
    return doc or "unknown document"


# ---------------------------------------------------------------------------
# Citation construction
# ---------------------------------------------------------------------------


def _is_safe_candidate(row: Mapping[str, Any]) -> bool:
    return (
        _text(row.get("rag_bucket")) in SAFE_BUCKETS
        and _text(row.get("final_rag_action")) in SAFE_ACTIONS
        and _text(row.get("final_trust_tier")) != "D"
    )


def _citation_kind(row: Mapping[str, Any]) -> str:
    bucket = _text(row.get("rag_bucket"))
    if bucket == "source_evidence":
        return "source"
    if bucket == "source_text_evidence":
        return "source_text"
    if bucket == "verified_part_evidence":
        return "verified_part"
    if bucket == "derived_context":
        return "derived_context"
    return "unknown"


def _make_citation(row: Mapping[str, Any]) -> dict[str, Any]:
    chunk_id = _text(row.get("chunk_id") or row.get("candidate_id"))
    page_id = _text(row.get("page_id"))
    document_id = _text(row.get("document_id"))
    ata_code = _text(row.get("ata_code"))
    bucket = _text(row.get("rag_bucket"))
    layer = _text(row.get("evidence_layer"))
    trust = _text(row.get("final_trust_tier"))
    action = _text(row.get("final_rag_action"))
    source_url = _text(row.get("source_url"))
    tiff_path = _text(row.get("tiff_path"))
    ocr_path = _text(row.get("ocr_path"))
    confidence = round(_num(row.get("usable_confidence")), 6)
    citation_id = f"cite:{_citation_kind(row)}:{page_id}:{_short_hash(chunk_id or page_id + bucket + layer)}"
    page_no = _page_number(page_id)
    label_parts = []
    if document_id:
        label_parts.append(document_id)
    if ata_code:
        label_parts.append(f"ATA {ata_code}")
    if page_no:
        label_parts.append(f"page {page_no}")
    short_label = " / ".join(label_parts) if label_parts else page_id
    kind = _citation_kind(row)
    citation_text = (
        f"{short_label}. Evidence bucket: {bucket}; layer: {layer}; "
        f"trust: {trust}; confidence: {confidence:.6f}."
    )
    if source_url:
        citation_text += f" Source URL: {source_url}."
    if tiff_path:
        citation_text += f" TIFF: {tiff_path}."
    if ocr_path:
        citation_text += f" OCR: {ocr_path}."
    markdown = f"**{short_label}** — `{bucket}` / `{layer}` / trust `{trust}` / confidence `{confidence:.3f}`"
    if source_url:
        markdown += f" — source: {source_url}"
    return {
        "citation_id": citation_id,
        "chunk_id": chunk_id,
        "candidate_id": _text(row.get("candidate_id") or chunk_id),
        "page_id": page_id,
        "page_number": page_no,
        "document_id": document_id,
        "ata_code": ata_code,
        "page_role": _text(row.get("page_role")),
        "citation_kind": kind,
        "rag_bucket": bucket,
        "candidate_type": _text(row.get("candidate_type")),
        "evidence_layer": layer,
        "final_trust_tier": trust,
        "final_rag_action": action,
        "usable_confidence": confidence,
        "source_url": source_url,
        "tiff_path": tiff_path,
        "ocr_path": ocr_path,
        "short_label": short_label,
        "citation_text": citation_text,
        "citation_markdown": markdown,
        "is_rag_safe": _is_safe_candidate(row),
        "is_source_traceable": bool(page_id and source_url and tiff_path),
        "has_ocr_path": bool(ocr_path),
        "has_tiff_path": bool(tiff_path),
        "has_source_url": bool(source_url),
        "text_preview": _clip(_text(row.get("text")), 500),
        "citation_version": VERSION,
    }


def _citation_lookup(citations: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for citation in citations:
        row = dict(citation)
        for key in (row.get("chunk_id"), row.get("candidate_id"), row.get("citation_id")):
            text = _text(key)
            if text:
                lookup[text] = row
    return lookup


def _annotate_search_results(results: Sequence[Mapping[str, Any]], citations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    lookup = _citation_lookup(citations)
    annotated: list[dict[str, Any]] = []
    for result in results:
        row = dict(result)
        citation = lookup.get(_text(row.get("chunk_id"))) or lookup.get(_text(row.get("candidate_id")))
        if citation:
            row["citation"] = {
                key: citation.get(key)
                for key in (
                    "citation_id", "short_label", "citation_text", "citation_markdown", "source_url", "tiff_path", "ocr_path",
                    "citation_kind", "is_source_traceable", "is_rag_safe",
                )
            }
        else:
            row["citation"] = {}
        annotated.append(row)
    return annotated


def _unsafe_citations(citations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unsafe: list[dict[str, Any]] = []
    for citation in citations:
        reasons: list[str] = []
        if not citation.get("is_rag_safe"):
            reasons.append("not_rag_safe")
        if _text(citation.get("final_trust_tier")) == "D":
            reasons.append("D_tier")
        if _text(citation.get("rag_bucket")) not in SAFE_BUCKETS:
            reasons.append("unsafe_bucket")
        if _text(citation.get("final_rag_action")) not in SAFE_ACTIONS:
            reasons.append("unsafe_rag_action")
        if reasons:
            item = dict(citation)
            item["unsafe_citation_reasons"] = sorted(set(reasons))
            unsafe.append(item)
    return unsafe


def _missing_source_url(citations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(c) for c in citations if not _text(c.get("source_url"))]


def _missing_tiff_path(citations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(c) for c in citations if not _text(c.get("tiff_path"))]


def _missing_ocr_path(citations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(c) for c in citations if not _text(c.get("ocr_path"))]


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_trace_net_source_citations(paths: SourceCitationPaths, options: SourceCitationOptions | None = None) -> dict[str, Any]:
    options = options or SourceCitationOptions()
    candidates = _read_jsonl(paths.candidate_path)
    citations = [_make_citation(row) for row in candidates]
    search_results = _read_jsonl(paths.search_results_path) if options.include_search_results else []
    search_with_citations = _annotate_search_results(search_results, citations) if search_results else []

    unsafe = _unsafe_citations(citations)
    missing_source = _missing_source_url(citations)
    missing_tiff = _missing_tiff_path(citations)
    missing_ocr = _missing_ocr_path(citations)
    pages = sorted({_text(c.get("page_id")) for c in citations if _text(c.get("page_id"))})
    nodes, edges = _build_graph(citations, search_with_citations)
    summary = {
        "status": "OK" if not unsafe else "WARN",
        "version": VERSION,
        "created_at": _utc_now(),
        "candidate_records": len(candidates),
        "citation_records": len(citations),
        "pages": len(pages),
        "search_result_records": len(search_results),
        "search_results_with_citations": len([r for r in search_with_citations if _as_dict(r.get("citation"))]),
        "rag_bucket_counts": _count(_text(c.get("rag_bucket")) for c in citations),
        "citation_kind_counts": _count(_text(c.get("citation_kind")) for c in citations),
        "evidence_layer_counts": _count(_text(c.get("evidence_layer")) for c in citations),
        "trust_tier_counts": _count(_text(c.get("final_trust_tier")) for c in citations),
        "unsafe_citation_records": len(unsafe),
        "missing_source_url_records": len(missing_source),
        "missing_tiff_path_records": len(missing_tiff),
        "missing_ocr_path_records": len(missing_ocr),
        "source_traceable_records": len([c for c in citations if c.get("is_source_traceable")]),
        "graph_nodes": len(nodes),
        "graph_edges": len(edges),
        "paths": {
            "candidates": str(paths.candidate_path),
            "search_results": str(paths.search_results_path),
            "citations": str(paths.citations),
            "search_with_citations": str(paths.search_with_citations),
            "summary": str(paths.summary),
            "review_html": str(paths.review_html),
            "graph_nodes": str(paths.graph_nodes),
            "graph_edges": str(paths.graph_edges),
        },
        "samples": {
            "citations": citations[: options.max_samples],
            "search_results_with_citations": search_with_citations[: options.max_samples],
            "unsafe_citations": unsafe[: options.max_samples],
            "missing_source_url": missing_source[: options.max_samples],
            "missing_tiff_path": missing_tiff[: options.max_samples],
            "missing_ocr_path": missing_ocr[: options.max_samples],
        },
    }
    _write_jsonl(paths.citations, citations)
    _write_jsonl(paths.search_with_citations, search_with_citations)
    _write_json(paths.summary, summary)
    _write_json(paths.graph_nodes, nodes)
    _write_json(paths.graph_edges, edges)
    _write_text(paths.review_md, _render_markdown(summary))
    _write_text(paths.review_html, _render_html(summary))
    if options.open_report:
        try:
            webbrowser.open(paths.review_html.resolve().as_uri())
        except Exception:
            pass
    return summary


# ---------------------------------------------------------------------------
# Graph/report rendering
# ---------------------------------------------------------------------------


def _build_graph(citations: Sequence[Mapping[str, Any]], search_results: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def add_node(node_id: str, kind: str, **props: Any) -> None:
        if not node_id:
            return
        node = nodes.setdefault(node_id, {"id": node_id, "kind": kind})
        node.update({k: v for k, v in props.items() if v is not None})

    def add_edge(src: str, dst: str, kind: str, **props: Any) -> None:
        if not src or not dst:
            return
        edges.append({"source": src, "target": dst, "kind": kind, **{k: v for k, v in props.items() if v is not None}})

    root = "trace_net_source_citations:root"
    add_node(root, "source_citation_root", version=VERSION)
    for citation in citations:
        citation_id = _text(citation.get("citation_id"))
        page_id = _text(citation.get("page_id"))
        bucket = _text(citation.get("rag_bucket"))
        kind = _text(citation.get("citation_kind"))
        add_node(citation_id, "source_citation", page_id=page_id, rag_bucket=bucket, citation_kind=kind, source_url=citation.get("source_url"))
        add_edge(root, citation_id, "HAS_SOURCE_CITATION")
        if page_id:
            page_node = f"page:{page_id}"
            add_node(page_node, "page", page_id=page_id)
            add_edge(citation_id, page_node, "CITES_PAGE")
        bucket_node = f"rag_bucket:{bucket}"
        add_node(bucket_node, "rag_bucket", value=bucket)
        add_edge(citation_id, bucket_node, "IN_RAG_BUCKET")
        kind_node = f"citation_kind:{kind}"
        add_node(kind_node, "citation_kind", value=kind)
        add_edge(citation_id, kind_node, "HAS_CITATION_KIND")
    for result in search_results:
        citation = _as_dict(result.get("citation"))
        citation_id = _text(citation.get("citation_id"))
        if not citation_id:
            continue
        result_id = f"search_result:{_text(result.get('rank'))}:{_text(result.get('chunk_id'))}"
        add_node(result_id, "search_result", page_id=result.get("page_id"), score=result.get("score"))
        add_edge(result_id, citation_id, "USES_SOURCE_CITATION")
    return list(nodes.values()), edges


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("\n", "<br>") for value in row) + " |")
    return "\n".join(lines)


def _render_markdown(summary: Mapping[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# TRACE-Net Source Citation Formatting v1")
    lines.append("")
    lines.append(f"Status: **{summary.get('status')}**   Version: `{summary.get('version')}`")
    lines.append("")
    lines.append("## Summary")
    for key in (
        "candidate_records", "citation_records", "pages", "search_result_records", "search_results_with_citations",
        "unsafe_citation_records", "missing_source_url_records", "missing_tiff_path_records", "missing_ocr_path_records",
        "source_traceable_records", "graph_nodes", "graph_edges",
    ):
        lines.append(f"- **{key}**: {summary.get(key)}")
    lines.append("")
    lines.append("## Counts")
    for key in ("rag_bucket_counts", "citation_kind_counts", "evidence_layer_counts", "trust_tier_counts"):
        lines.append(f"- **{key}**: `{summary.get(key, {})}`")
    samples = _as_dict(summary.get("samples"))
    rows = []
    for citation in _as_list(samples.get("citations"))[:40]:
        rows.append([
            citation.get("page_id"), citation.get("citation_kind"), citation.get("rag_bucket"), citation.get("evidence_layer"),
            citation.get("final_trust_tier"), citation.get("usable_confidence"), citation.get("short_label"), _clip(_text(citation.get("citation_text")), 180),
        ])
    lines.append("")
    lines.append("## Citation samples")
    lines.append(_md_table(["Page", "Kind", "Bucket", "Layer", "Trust", "Conf", "Label", "Citation"], rows) if rows else "No citations.")
    unsafe = _as_list(samples.get("unsafe_citations"))
    lines.append("")
    lines.append("## Unsafe citation samples")
    lines.append("None." if not unsafe else _md_table(["Page", "Bucket", "Reason"], [[u.get("page_id"), u.get("rag_bucket"), u.get("unsafe_citation_reasons")] for u in unsafe]))
    return "\n".join(lines) + "\n"


def _render_html(summary: Mapping[str, Any]) -> str:
    def esc(value: Any) -> str:
        return html.escape(str(value))

    samples = _as_dict(summary.get("samples"))
    sections: list[str] = []
    sections.append("<h1>TRACE-Net Source Citation Formatting v1</h1>")
    sections.append(f"<p><b>Status:</b> {esc(summary.get('status'))} &nbsp; <b>Version:</b> <code>{esc(summary.get('version'))}</code></p>")
    sections.append("<h2>Summary</h2><table><tbody>")
    for key in (
        "candidate_records", "citation_records", "pages", "search_result_records", "search_results_with_citations",
        "unsafe_citation_records", "missing_source_url_records", "missing_tiff_path_records", "missing_ocr_path_records",
        "source_traceable_records", "graph_nodes", "graph_edges",
    ):
        sections.append(f"<tr><th>{esc(key)}</th><td>{esc(summary.get(key))}</td></tr>")
    sections.append("</tbody></table>")
    sections.append("<h2>Counts</h2>")
    for key in ("rag_bucket_counts", "citation_kind_counts", "evidence_layer_counts", "trust_tier_counts"):
        sections.append(f"<h3>{esc(key)}</h3><pre>{esc(json.dumps(summary.get(key, {}), indent=2, sort_keys=True))}</pre>")
    sections.append("<h2>Citation samples</h2><table><thead><tr><th>Page</th><th>Kind</th><th>Bucket</th><th>Layer</th><th>Trust</th><th>Conf</th><th>Label</th><th>Source</th><th>Citation</th></tr></thead><tbody>")
    for citation in _as_list(samples.get("citations"))[:80]:
        sections.append(
            "<tr>"
            f"<td><code>{esc(citation.get('page_id'))}</code></td>"
            f"<td>{esc(citation.get('citation_kind'))}</td>"
            f"<td>{esc(citation.get('rag_bucket'))}</td>"
            f"<td>{esc(citation.get('evidence_layer'))}</td>"
            f"<td>{esc(citation.get('final_trust_tier'))}</td>"
            f"<td>{esc(citation.get('usable_confidence'))}</td>"
            f"<td>{esc(citation.get('short_label'))}</td>"
            f"<td><small>{esc(citation.get('source_url'))}<br>{esc(citation.get('tiff_path'))}<br>{esc(citation.get('ocr_path'))}</small></td>"
            f"<td><pre>{esc(_text(citation.get('citation_text')))}</pre></td>"
            "</tr>"
        )
    sections.append("</tbody></table>")
    sections.append("<h2>Search results with citations</h2><table><thead><tr><th>Rank</th><th>Page</th><th>Score</th><th>Citation</th></tr></thead><tbody>")
    for result in _as_list(samples.get("search_results_with_citations"))[:80]:
        citation = _as_dict(result.get("citation"))
        sections.append(
            "<tr>"
            f"<td>{esc(result.get('rank'))}</td>"
            f"<td><code>{esc(result.get('page_id'))}</code></td>"
            f"<td>{esc(result.get('score'))}</td>"
            f"<td>{esc(citation.get('citation_text', ''))}</td>"
            "</tr>"
        )
    sections.append("</tbody></table>")
    unsafe = _as_list(samples.get("unsafe_citations"))
    sections.append("<h2>Unsafe citation samples</h2>")
    if not unsafe:
        sections.append("<p>None.</p>")
    else:
        sections.append("<pre>" + esc(json.dumps(unsafe, indent=2, sort_keys=True)) + "</pre>")
    css = "body{font-family:Arial,sans-serif;margin:24px;line-height:1.35}table{border-collapse:collapse;width:100%;margin:12px 0}th,td{border:1px solid #ddd;padding:6px;vertical-align:top}th{background:#f6f6f6;text-align:left}pre{white-space:pre-wrap;background:#f6f6f6;padding:8px;max-height:280px;overflow:auto}code{background:#f6f6f6;padding:1px 3px}"
    return "<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Source Citations</title><style>" + css + "</style></head><body>" + "\n".join(sections) + "</body></html>\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Format source citations for TRACE-Net safe RAG candidates.")
    parser.add_argument("--candidates", default=str(DEFAULT_CANDIDATE_PATH))
    parser.add_argument("--search-results", default=str(DEFAULT_SEARCH_RESULTS_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--no-search-results", action="store_true")
    parser.add_argument("--samples", type=int, default=40)
    parser.add_argument("--open", action="store_true", dest="open_report")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    paths = SourceCitationPaths(
        candidate_path=Path(args.candidates),
        search_results_path=Path(args.search_results),
        output_dir=Path(args.output_dir),
    )
    options = SourceCitationOptions(
        open_report=bool(args.open_report),
        max_samples=max(1, int(args.samples or 40)),
        include_search_results=not bool(args.no_search_results),
    )
    summary = build_trace_net_source_citations(paths, options)
    print("TRACE-Net source citation formatter")
    print(f"  Status: {summary.get('status')}")
    print(f"  Output dir: {paths.output_dir}")
    print("  Summary:")
    for key in (
        "candidate_records", "citation_records", "pages", "search_result_records", "search_results_with_citations",
        "unsafe_citation_records", "missing_source_url_records", "missing_tiff_path_records", "missing_ocr_path_records",
    ):
        print(f"    {key}: {summary.get(key)}")
    print("Files written:")
    print(f"  citations: {paths.citations}")
    print(f"  search_with_citations: {paths.search_with_citations}")
    print(f"  summary: {paths.summary}")
    print(f"  review_html: {paths.review_html}")
    print(f"  graph_nodes: {paths.graph_nodes}")
    print(f"  graph_edges: {paths.graph_edges}")
    return 0 if summary.get("status") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
