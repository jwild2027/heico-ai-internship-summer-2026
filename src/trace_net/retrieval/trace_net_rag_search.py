"""TRACE-Net local RAG candidate search harness v1.

This module searches only the TRACE-Net RAG candidate chunks that already passed
Evidence Consensus, Stage 5 confidence policy control, and RAG eligibility.

It is intentionally local and dependency-free:
  * no embeddings
  * no vector database
  * no LLM calls
  * no mutation of source graph artifacts

Default input:
  local_data/organization/trace_net/rag_candidates/rag_candidate_chunks.jsonl

Default output:
  local_data/organization/trace_net/search/
"""
from __future__ import annotations

import argparse
import html
import json
import math
import re
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_CANDIDATE_DIR = Path("local_data/organization/trace_net/rag_candidates")
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/search")
CANDIDATES_FILE = "rag_candidate_chunks.jsonl"
RESULTS_FILE = "trace_net_search_results.json"
RESULTS_JSONL_FILE = "trace_net_search_results.jsonl"
SUMMARY_FILE = "trace_net_search_summary.json"
REVIEW_MD_FILE = "trace_net_search_review.md"
REVIEW_HTML_FILE = "trace_net_search_review.html"
QUALITY_FILE = "trace_net_search_quality.json"

VERSION = "trace_net_local_search_v1_1_source_text"
SAFE_BUCKETS = {"source_evidence", "source_text_evidence", "verified_part_evidence", "derived_context"}
SAFE_RAG_ACTIONS = {"include_as_source_evidence", "include_as_verified_part_evidence", "include_as_derived_context"}
TIER_ORDER = {"D": 0, "C": 1, "B": 2, "A": 3}
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "in", "is", "it", "of", "on", "or", "page",
    "the", "this", "to", "with", "where", "what", "which", "show", "find", "list", "me", "about", "related",
}
PART_RE = re.compile(r"\b(?:\d{3}-\d{4,6}-[A-Z0-9]{2,4}|\d{2,4}TP\d{4,8}[A-Z0-9.\-]*|[A-Z]{1,4}\d{2,6}[A-Z0-9.\-]{1,})\b", re.I)
PAGE_RE = re.compile(r"\bt_p_[A-Za-z0-9_]+_p\d{6}\b")


@dataclass(frozen=True)
class RagSearchPaths:
    candidate_dir: Path = DEFAULT_CANDIDATE_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    candidates_path: Path | None = None
    results_path: Path | None = None
    results_jsonl_path: Path | None = None
    summary_path: Path | None = None
    review_md_path: Path | None = None
    review_html_path: Path | None = None
    quality_path: Path | None = None

    @property
    def candidates(self) -> Path:
        return self.candidates_path or (self.candidate_dir / CANDIDATES_FILE)

    @property
    def results(self) -> Path:
        return self.results_path or (self.output_dir / RESULTS_FILE)

    @property
    def results_jsonl(self) -> Path:
        return self.results_jsonl_path or (self.output_dir / RESULTS_JSONL_FILE)

    @property
    def summary(self) -> Path:
        return self.summary_path or (self.output_dir / SUMMARY_FILE)

    @property
    def review_md(self) -> Path:
        return self.review_md_path or (self.output_dir / REVIEW_MD_FILE)

    @property
    def review_html(self) -> Path:
        return self.review_html_path or (self.output_dir / REVIEW_HTML_FILE)

    @property
    def quality(self) -> Path:
        return self.quality_path or (self.output_dir / QUALITY_FILE)


@dataclass(frozen=True)
class RagSearchOptions:
    query: str = ""
    part_number: str = ""
    page_id: str = ""
    bucket: str = ""
    evidence_layer: str = ""
    min_trust: str = ""
    min_confidence: float | None = None
    top_k: int = 20
    max_text_chars: int = 900
    open_report: bool = False


# ---------------------------------------------------------------------------
# IO helpers
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
        if not value:
            continue
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items()))


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = _text(value).strip(" ,.;:()[]{}\"'")
        if not item:
            continue
        key = item.upper()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _clip(text: str, max_chars: int) -> str:
    value = _text(text)
    if len(value) <= max_chars:
        return value
    return value[: max(0, max_chars - 1)].rstrip() + "…"


# ---------------------------------------------------------------------------
# Search helpers
# ---------------------------------------------------------------------------


def _candidate_safe(row: Mapping[str, Any]) -> bool:
    bucket = _text(row.get("rag_bucket"))
    action = _text(row.get("final_rag_action"))
    text = _text(row.get("text"))
    if bucket not in SAFE_BUCKETS:
        return False
    if action and action not in SAFE_RAG_ACTIONS:
        return False
    if not text:
        return False
    return True


def _metadata_parts(row: Mapping[str, Any]) -> list[str]:
    metadata = _as_dict(row.get("metadata"))
    parts: list[str] = []
    for key in ("catalog_supported_part_numbers", "canonical_part_numbers", "part_numbers", "page_parts"):
        parts.extend(_text(item) for item in _as_list(metadata.get(key)))
    text = _text(row.get("text"))
    parts.extend(match.group(0) for match in PART_RE.finditer(text))
    return _unique(parts)


def _haystack(row: Mapping[str, Any]) -> str:
    metadata = _as_dict(row.get("metadata"))
    fields = [
        row.get("chunk_id"), row.get("candidate_id"), row.get("page_id"), row.get("document_id"), row.get("ata_code"),
        row.get("page_role"), row.get("evidence_layer"), row.get("rag_bucket"), row.get("candidate_type"), row.get("source_url"),
        row.get("tiff_path"), row.get("ocr_path"), row.get("text"),
    ]
    fields.extend(_metadata_parts(row))
    fields.extend(_text(x) for x in _as_list(metadata.get("eligibility_reasons")))
    return "\n".join(_text(item) for item in fields if _text(item))


def _normalize_part(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _tokenize(value: str) -> list[str]:
    raw = re.findall(r"[a-z0-9][a-z0-9_./\-]{1,}", value.lower())
    tokens: list[str] = []
    for token in raw:
        cleaned = token.strip("._-/")
        if not cleaned or cleaned in STOPWORDS:
            continue
        tokens.append(cleaned)
    return tokens


def _query_parts(query: str, explicit_part: str = "") -> list[str]:
    parts = [match.group(0) for match in PART_RE.finditer(query)]
    if explicit_part:
        parts.append(explicit_part)
    return _unique(parts)


def _query_pages(query: str, explicit_page: str = "") -> list[str]:
    pages = [match.group(0) for match in PAGE_RE.finditer(query)]
    if explicit_page:
        pages.append(explicit_page)
    return _unique(pages)


def _parse_csv_filter(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def _passes_filters(row: Mapping[str, Any], options: RagSearchOptions) -> bool:
    bucket_filter = _parse_csv_filter(options.bucket)
    layer_filter = _parse_csv_filter(options.evidence_layer)
    if bucket_filter and _text(row.get("rag_bucket")) not in bucket_filter:
        return False
    if layer_filter and _text(row.get("evidence_layer")) not in layer_filter:
        return False
    if options.page_id and _text(row.get("page_id")) != options.page_id:
        return False
    if options.min_trust:
        if TIER_ORDER.get(_text(row.get("final_trust_tier")), -1) < TIER_ORDER.get(options.min_trust.upper(), 99):
            return False
    if options.min_confidence is not None:
        if _num(row.get("usable_confidence"), 0.0) < options.min_confidence:
            return False
    return True


def _document_frequencies(candidates: Sequence[Mapping[str, Any]], terms: Sequence[str]) -> dict[str, int]:
    dfs: dict[str, int] = {term: 0 for term in terms}
    for row in candidates:
        hay = _haystack(row).lower()
        tokens = set(_tokenize(hay))
        for term in terms:
            if term in tokens or term in hay:
                dfs[term] += 1
    return dfs


def _idf(term: str, df: int, total: int) -> float:
    return math.log(1.0 + (total + 1.0) / (df + 1.0))


def _score_candidate(row: Mapping[str, Any], options: RagSearchOptions, terms: Sequence[str], parts: Sequence[str], pages: Sequence[str], dfs: Mapping[str, int], total: int) -> tuple[float, dict[str, Any]]:
    text = _text(row.get("text"))
    hay = _haystack(row)
    hay_lower = hay.lower()
    token_list = _tokenize(hay)
    token_counts: dict[str, int] = {}
    for token in token_list:
        token_counts[token] = token_counts.get(token, 0) + 1

    components: dict[str, Any] = {
        "token_score": 0.0,
        "phrase_score": 0.0,
        "part_score": 0.0,
        "page_score": 0.0,
        "bucket_score": 0.0,
        "trust_score": 0.0,
        "confidence_score": 0.0,
        "matched_terms": [],
        "matched_part_numbers": [],
        "matched_pages": [],
    }

    for term in terms:
        tf = token_counts.get(term, 0)
        if not tf and term not in hay_lower:
            continue
        score = (1.0 + math.log(tf or 1.0)) * _idf(term, dfs.get(term, 0), total)
        # Exact substring matches are useful for technical labels that tokenization may split.
        if term in hay_lower:
            score += 0.25
        components["token_score"] += score
        components["matched_terms"].append(term)

    query = _text(options.query)
    if query and query.lower() in text.lower():
        components["phrase_score"] = 8.0

    row_parts = _metadata_parts(row)
    normalized_row_parts = {_normalize_part(p): p for p in row_parts}
    for part in parts:
        key = _normalize_part(part)
        if key and (key in normalized_row_parts or key in _normalize_part(hay)):
            components["part_score"] += 35.0
            components["matched_part_numbers"].append(normalized_row_parts.get(key, part))
        elif part.lower() in hay_lower:
            components["part_score"] += 20.0
            components["matched_part_numbers"].append(part)

    page_id = _text(row.get("page_id"))
    for page in pages:
        if page and page == page_id:
            components["page_score"] += 50.0
            components["matched_pages"].append(page)
        elif page and page.lower() in hay_lower:
            components["page_score"] += 20.0
            components["matched_pages"].append(page)

    bucket = _text(row.get("rag_bucket"))
    if parts and bucket == "verified_part_evidence":
        components["bucket_score"] += 5.0
    if pages and bucket == "source_evidence":
        components["bucket_score"] += 5.0
    if terms and bucket == "source_text_evidence":
        components["bucket_score"] += 2.5
    if terms and bucket == "derived_context":
        components["bucket_score"] += 1.0

    tier = _text(row.get("final_trust_tier"))
    components["trust_score"] = {"A": 2.0, "B": 1.0, "C": 0.25}.get(tier, 0.0)
    components["confidence_score"] = min(2.0, max(0.0, _num(row.get("usable_confidence"), 0.0) * 2.0))

    total_score = round(
        float(components["token_score"])
        + float(components["phrase_score"])
        + float(components["part_score"])
        + float(components["page_score"])
        + float(components["bucket_score"])
        + float(components["trust_score"])
        + float(components["confidence_score"]),
        6,
    )
    components["token_score"] = round(float(components["token_score"]), 6)
    components["matched_terms"] = _unique(components["matched_terms"])
    components["matched_part_numbers"] = _unique(components["matched_part_numbers"])
    components["matched_pages"] = _unique(components["matched_pages"])
    return total_score, components


def _make_result(rank: int, score: float, row: Mapping[str, Any], components: Mapping[str, Any], max_text_chars: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "score": score,
        "score_components": dict(components),
        "chunk_id": _text(row.get("chunk_id")),
        "candidate_id": _text(row.get("candidate_id") or row.get("chunk_id")),
        "page_id": _text(row.get("page_id")),
        "document_id": _text(row.get("document_id")),
        "ata_code": _text(row.get("ata_code")),
        "page_role": _text(row.get("page_role")),
        "rag_bucket": _text(row.get("rag_bucket")),
        "candidate_type": _text(row.get("candidate_type")),
        "evidence_layer": _text(row.get("evidence_layer")),
        "final_trust_tier": _text(row.get("final_trust_tier")),
        "usable_confidence": round(_num(row.get("usable_confidence")), 6),
        "final_rag_action": _text(row.get("final_rag_action")),
        "source_url": _text(row.get("source_url")),
        "tiff_path": _text(row.get("tiff_path")),
        "ocr_path": _text(row.get("ocr_path")),
        "text_preview": _clip(_text(row.get("text")), max_text_chars),
        "safe_candidate": _candidate_safe(row),
    }


# ---------------------------------------------------------------------------
# Main search
# ---------------------------------------------------------------------------


def search_rag_candidates(paths: RagSearchPaths, options: RagSearchOptions | None = None) -> dict[str, Any]:
    options = options or RagSearchOptions()
    all_candidates = _read_jsonl(paths.candidates)
    safe_candidates = [row for row in all_candidates if _candidate_safe(row)]
    filtered = [row for row in safe_candidates if _passes_filters(row, options)]

    effective_query = " ".join(part for part in [options.query, options.part_number, options.page_id] if part).strip()
    terms = _tokenize(effective_query)
    parts = _query_parts(effective_query, options.part_number)
    pages = _query_pages(effective_query, options.page_id)
    dfs = _document_frequencies(filtered, terms) if terms else {}

    scored: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    for row in filtered:
        score, components = _score_candidate(row, options, terms, parts, pages, dfs, max(len(filtered), 1))
        # If no query is supplied, return highest-trust/high-confidence records.
        if not effective_query:
            score = round(TIER_ORDER.get(_text(row.get("final_trust_tier")), 0) * 10 + _num(row.get("usable_confidence")) * 5, 6)
            scored.append((score, dict(row), components))
            continue
        # Trust/confidence/bucket boosts are only tie-breakers. A queried result
        # must have at least one lexical, part-number, page-id, or phrase match.
        match_signal = (
            float(components.get("token_score") or 0.0)
            + float(components.get("phrase_score") or 0.0)
            + float(components.get("part_score") or 0.0)
            + float(components.get("page_score") or 0.0)
        )
        if match_signal > 0:
            scored.append((score, dict(row), components))

    scored.sort(key=lambda item: (-item[0], _text(item[1].get("rag_bucket")), _text(item[1].get("page_id")), _text(item[1].get("chunk_id"))))
    top_k = max(1, int(options.top_k or 20))
    results = [_make_result(rank + 1, score, row, components, options.max_text_chars) for rank, (score, row, components) in enumerate(scored[:top_k])]
    unsafe_results = [row for row in results if not row.get("safe_candidate")]
    excluded_results = [row for row in results if row.get("final_rag_action") not in SAFE_RAG_ACTIONS]
    pages_found = sorted({_text(row.get("page_id")) for row in results if _text(row.get("page_id"))})

    summary = {
        "status": "OK",
        "version": VERSION,
        "created_at": _utc_now(),
        "query": options.query,
        "part_number": options.part_number,
        "page_id": options.page_id,
        "effective_query": effective_query,
        "filters": {
            "bucket": options.bucket,
            "evidence_layer": options.evidence_layer,
            "min_trust": options.min_trust,
            "min_confidence": options.min_confidence,
            "top_k": top_k,
        },
        "candidate_records": len(all_candidates),
        "safe_candidate_records": len(safe_candidates),
        "searched_records": len(filtered),
        "result_records": len(results),
        "pages_found": len(pages_found),
        "top_score": results[0]["score"] if results else 0,
        "unsafe_result_records": len(unsafe_results),
        "excluded_result_records": len(excluded_results),
        "bucket_counts": _count(_text(row.get("rag_bucket")) for row in results),
        "evidence_layer_counts": _count(_text(row.get("evidence_layer")) for row in results),
        "trust_tier_counts": _count(_text(row.get("final_trust_tier")) for row in results),
        "matched_part_number_records": len([row for row in results if row.get("score_components", {}).get("matched_part_numbers")]),
        "matched_page_records": len([row for row in results if row.get("score_components", {}).get("matched_pages")]),
        "matched_term_records": len([row for row in results if row.get("score_components", {}).get("matched_terms")]),
        "paths": {
            "candidates": str(paths.candidates),
            "results": str(paths.results),
            "results_jsonl": str(paths.results_jsonl),
            "summary": str(paths.summary),
            "review_md": str(paths.review_md),
            "review_html": str(paths.review_html),
        },
        "samples": results[: min(len(results), 20)],
    }

    payload = {"summary": summary, "results": results}
    _write_json(paths.results, payload)
    _write_jsonl(paths.results_jsonl, results)
    _write_json(paths.summary, summary)
    _write_text(paths.review_md, _render_markdown(summary, results))
    _write_text(paths.review_html, _render_html(summary, results))
    if options.open_report:
        try:
            webbrowser.open(paths.review_html.resolve().as_uri())
        except Exception:
            pass
    return summary


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("\n", "<br>") for value in row) + " |")
    return "\n".join(lines)


def _render_markdown(summary: Mapping[str, Any], results: Sequence[Mapping[str, Any]]) -> str:
    lines: list[str] = []
    lines.append("# TRACE-Net Local RAG Candidate Search v1")
    lines.append("")
    lines.append(f"Status: **{summary.get('status')}**")
    lines.append(f"Version: `{summary.get('version')}`")
    lines.append("")
    lines.append("## Query")
    lines.append(f"- **query**: `{summary.get('query')}`")
    lines.append(f"- **part_number**: `{summary.get('part_number')}`")
    lines.append(f"- **page_id**: `{summary.get('page_id')}`")
    lines.append(f"- **effective_query**: `{summary.get('effective_query')}`")
    lines.append("")
    lines.append("## Summary")
    for key in ("candidate_records", "safe_candidate_records", "searched_records", "result_records", "pages_found", "top_score", "unsafe_result_records", "excluded_result_records"):
        lines.append(f"- **{key}**: {summary.get(key)}")
    lines.append("")
    lines.append("## Result counts")
    for key in ("bucket_counts", "evidence_layer_counts", "trust_tier_counts"):
        lines.append(f"- **{key}**: `{summary.get(key, {})}`")
    lines.append("")
    rows = []
    for row in results:
        components = _as_dict(row.get("score_components"))
        matches = []
        if components.get("matched_part_numbers"):
            matches.append("parts=" + ", ".join(components.get("matched_part_numbers", [])[:5]))
        if components.get("matched_terms"):
            matches.append("terms=" + ", ".join(components.get("matched_terms", [])[:8]))
        if components.get("matched_pages"):
            matches.append("pages=" + ", ".join(components.get("matched_pages", [])[:3]))
        rows.append([
            row.get("rank"), row.get("score"), row.get("page_id"), row.get("rag_bucket"), row.get("evidence_layer"), row.get("final_trust_tier"), row.get("usable_confidence"), "; ".join(matches), _clip(_text(row.get("text_preview")), 220),
        ])
    lines.append("## Results")
    lines.append(_md_table(["Rank", "Score", "Page", "Bucket", "Layer", "Trust", "Conf", "Matches", "Preview"], rows) if rows else "No results.")
    return "\n".join(lines) + "\n"


def _render_html(summary: Mapping[str, Any], results: Sequence[Mapping[str, Any]]) -> str:
    def esc(value: Any) -> str:
        return html.escape(str(value))

    sections: list[str] = []
    sections.append("<h1>TRACE-Net Local RAG Candidate Search v1</h1>")
    sections.append(f"<p><b>Status:</b> {esc(summary.get('status'))} &nbsp; <b>Version:</b> <code>{esc(summary.get('version'))}</code></p>")
    sections.append("<h2>Query</h2><table><tbody>")
    for key in ("query", "part_number", "page_id", "effective_query"):
        sections.append(f"<tr><th>{esc(key)}</th><td><code>{esc(summary.get(key, ''))}</code></td></tr>")
    sections.append("</tbody></table>")
    sections.append("<h2>Summary</h2><table><tbody>")
    for key in ("candidate_records", "safe_candidate_records", "searched_records", "result_records", "pages_found", "top_score", "unsafe_result_records", "excluded_result_records"):
        sections.append(f"<tr><th>{esc(key)}</th><td>{esc(summary.get(key))}</td></tr>")
    sections.append("</tbody></table>")
    sections.append("<h2>Counts</h2>")
    for key in ("bucket_counts", "evidence_layer_counts", "trust_tier_counts"):
        sections.append(f"<h3>{esc(key)}</h3><pre>{esc(json.dumps(summary.get(key, {}), indent=2, sort_keys=True))}</pre>")
    sections.append("<h2>Results</h2><table><thead><tr><th>Rank</th><th>Score</th><th>Page</th><th>Bucket</th><th>Layer</th><th>Trust</th><th>Conf</th><th>Matches</th><th>Source</th><th>Text</th></tr></thead><tbody>")
    for row in results:
        components = _as_dict(row.get("score_components"))
        matches = []
        if components.get("matched_part_numbers"):
            matches.append("parts=" + ", ".join(components.get("matched_part_numbers", [])[:8]))
        if components.get("matched_terms"):
            matches.append("terms=" + ", ".join(components.get("matched_terms", [])[:10]))
        if components.get("matched_pages"):
            matches.append("pages=" + ", ".join(components.get("matched_pages", [])[:4]))
        sections.append(
            "<tr>"
            f"<td>{esc(row.get('rank'))}</td>"
            f"<td>{esc(row.get('score'))}</td>"
            f"<td><code>{esc(row.get('page_id'))}</code></td>"
            f"<td>{esc(row.get('rag_bucket'))}</td>"
            f"<td>{esc(row.get('evidence_layer'))}</td>"
            f"<td>{esc(row.get('final_trust_tier'))}</td>"
            f"<td>{esc(row.get('usable_confidence'))}</td>"
            f"<td>{esc('; '.join(matches))}</td>"
            f"<td><small>{esc(row.get('source_url'))}</small></td>"
            f"<td><pre>{esc(_clip(_text(row.get('text_preview')), 1000))}</pre></td>"
            "</tr>"
        )
    sections.append("</tbody></table>")
    css = "body{font-family:Arial,sans-serif;margin:24px;line-height:1.35}table{border-collapse:collapse;width:100%;margin:12px 0}th,td{border:1px solid #ddd;padding:6px;vertical-align:top}th{background:#f6f6f6;text-align:left}pre{white-space:pre-wrap;background:#f6f6f6;padding:8px;max-height:260px;overflow:auto}code{background:#f6f6f6;padding:1px 3px}"
    return "<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Search</title><style>" + css + "</style></head><body>" + "\n".join(sections) + "</body></html>\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Search TRACE-Net RAG candidate chunks locally.")
    parser.add_argument("--candidate-dir", type=Path, default=DEFAULT_CANDIDATE_DIR)
    parser.add_argument("--candidates", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--query", default="")
    parser.add_argument("--part-number", default="")
    parser.add_argument("--page-id", default="")
    parser.add_argument("--bucket", default="", help="Comma-separated bucket filter, e.g. source_evidence,source_text_evidence,verified_part_evidence,derived_context")
    parser.add_argument("--evidence-layer", default="", help="Comma-separated evidence-layer filter")
    parser.add_argument("--min-trust", default="")
    parser.add_argument("--min-confidence", type=float, default=None)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--max-text-chars", type=int, default=900)
    parser.add_argument("--open", action="store_true", dest="open_report")
    args = parser.parse_args(argv)

    paths = RagSearchPaths(candidate_dir=args.candidate_dir, output_dir=args.output_dir, candidates_path=args.candidates)
    options = RagSearchOptions(
        query=args.query,
        part_number=args.part_number,
        page_id=args.page_id,
        bucket=args.bucket,
        evidence_layer=args.evidence_layer,
        min_trust=args.min_trust,
        min_confidence=args.min_confidence,
        top_k=args.top_k,
        max_text_chars=args.max_text_chars,
        open_report=args.open_report,
    )
    result = search_rag_candidates(paths, options)
    print("TRACE-Net local RAG candidate search")
    print(f"  Status: {result['status']}")
    print(f"  Output dir: {args.output_dir}")
    print("  Query:")
    print(f"    query: {result.get('query')}")
    print(f"    part_number: {result.get('part_number')}")
    print(f"    page_id: {result.get('page_id')}")
    print(f"    effective_query: {result.get('effective_query')}")
    print("  Summary:")
    for key in ("candidate_records", "safe_candidate_records", "searched_records", "result_records", "pages_found", "top_score", "unsafe_result_records", "excluded_result_records"):
        print(f"    {key}: {result.get(key)}")
    print("  Buckets:", result.get("bucket_counts"))
    print("  Top results:")
    for row in result.get("samples", [])[: min(10, int(args.top_k or 10))]:
        parts = row.get("score_components", {}).get("matched_part_numbers") or []
        terms = row.get("score_components", {}).get("matched_terms") or []
        match = ""
        if parts:
            match = " parts=" + ",".join(parts[:3])
        elif terms:
            match = " terms=" + ",".join(terms[:5])
        print(f"    {row.get('rank')}. score={row.get('score')} page={row.get('page_id')} bucket={row.get('rag_bucket')} layer={row.get('evidence_layer')}{match}")
    print("Files written:")
    for key, value in result.get("paths", {}).items():
        print(f"  {key}: {value}")
    return 0 if result.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
