"""TRACE-Net search result grouper v1.

This module turns chunk-level TRACE-Net local search results into page-level
result groups. It preserves every supporting evidence chunk, source trace fields,
and citation metadata when available. It does not search raw/excluded records,
create embeddings, call an LLM, or mutate source graph artifacts.

Default input:
  local_data/organization/trace_net/search/trace_net_search_results.jsonl

Optional citation inputs:
  local_data/organization/trace_net/citations/trace_net_source_citations.jsonl
  local_data/organization/trace_net/citations/trace_net_search_source_citations.jsonl

Default output:
  local_data/organization/trace_net/search/
"""
from __future__ import annotations

import argparse
import html
import json
import re
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_SEARCH_DIR = Path("local_data/organization/trace_net/search")
DEFAULT_CITATIONS_DIR = Path("local_data/organization/trace_net/citations")
DEFAULT_OUTPUT_DIR = DEFAULT_SEARCH_DIR

SEARCH_RESULTS_JSONL_FILE = "trace_net_search_results.jsonl"
SOURCE_CITATIONS_FILE = "trace_net_source_citations.jsonl"
SEARCH_CITATIONS_FILE = "trace_net_search_source_citations.jsonl"

GROUPED_RESULTS_FILE = "trace_net_search_grouped_results.json"
GROUPED_RESULTS_JSONL_FILE = "trace_net_search_grouped_results.jsonl"
GROUPED_SUMMARY_FILE = "trace_net_search_grouped_summary.json"
GROUPED_REVIEW_MD_FILE = "trace_net_search_grouped_review.md"
GROUPED_REVIEW_HTML_FILE = "trace_net_search_grouped_review.html"
GROUPED_GRAPH_NODES_FILE = "trace_net_search_grouped_graph_nodes.json"
GROUPED_GRAPH_EDGES_FILE = "trace_net_search_grouped_graph_edges.json"
GROUPED_QUALITY_FILE = "trace_net_search_grouped_quality.json"

VERSION = "trace_net_search_grouper_v1"
SAFE_BUCKETS = {"source_evidence", "source_text_evidence", "verified_part_evidence", "derived_context"}
SAFE_RAG_ACTIONS = {"include_as_source_evidence", "include_as_verified_part_evidence", "include_as_derived_context"}
UNSAFE_LAYERS = {"table_candidate", "table_tiles"}
TIER_ORDER = {"D": 0, "C": 1, "B": 2, "A": 3}
BUCKET_ORDER = {
    "source_evidence": 0,
    "verified_part_evidence": 1,
    "source_text_evidence": 2,
    "derived_context": 3,
}
BUCKET_GROUP_BONUS = {
    "source_evidence": 2.0,
    "verified_part_evidence": 3.0,
    "source_text_evidence": 2.5,
    "derived_context": 1.5,
}


@dataclass(frozen=True)
class SearchGroupPaths:
    search_dir: Path = DEFAULT_SEARCH_DIR
    citations_dir: Path = DEFAULT_CITATIONS_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    search_results_path: Path | None = None
    source_citations_path: Path | None = None
    search_citations_path: Path | None = None
    grouped_results_path: Path | None = None
    grouped_results_jsonl_path: Path | None = None
    summary_path: Path | None = None
    review_md_path: Path | None = None
    review_html_path: Path | None = None
    graph_nodes_path: Path | None = None
    graph_edges_path: Path | None = None
    quality_path: Path | None = None

    @property
    def search_results(self) -> Path:
        return self.search_results_path or (self.search_dir / SEARCH_RESULTS_JSONL_FILE)

    @property
    def source_citations(self) -> Path:
        return self.source_citations_path or (self.citations_dir / SOURCE_CITATIONS_FILE)

    @property
    def search_citations(self) -> Path:
        return self.search_citations_path or (self.citations_dir / SEARCH_CITATIONS_FILE)

    @property
    def grouped_results(self) -> Path:
        return self.grouped_results_path or (self.output_dir / GROUPED_RESULTS_FILE)

    @property
    def grouped_results_jsonl(self) -> Path:
        return self.grouped_results_jsonl_path or (self.output_dir / GROUPED_RESULTS_JSONL_FILE)

    @property
    def summary(self) -> Path:
        return self.summary_path or (self.output_dir / GROUPED_SUMMARY_FILE)

    @property
    def review_md(self) -> Path:
        return self.review_md_path or (self.output_dir / GROUPED_REVIEW_MD_FILE)

    @property
    def review_html(self) -> Path:
        return self.review_html_path or (self.output_dir / GROUPED_REVIEW_HTML_FILE)

    @property
    def graph_nodes(self) -> Path:
        return self.graph_nodes_path or (self.output_dir / GROUPED_GRAPH_NODES_FILE)

    @property
    def graph_edges(self) -> Path:
        return self.graph_edges_path or (self.output_dir / GROUPED_GRAPH_EDGES_FILE)

    @property
    def quality(self) -> Path:
        return self.quality_path or (self.output_dir / GROUPED_QUALITY_FILE)


@dataclass(frozen=True)
class SearchGroupOptions:
    top_k_groups: int = 20
    max_supporting_results: int = 20
    max_text_preview_chars: int = 500
    include_full_supporting_results: bool = False
    open_report: bool = False


# ---------------------------------------------------------------------------
# Helpers
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


def _clip(value: Any, max_chars: int) -> str:
    text = _text(value)
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 1)].rstrip() + "…"


def _slug(value: Any) -> str:
    text = _text(value).lower()
    text = re.sub(r"[^a-z0-9._:-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "unknown"


def _unique(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _count(values: Iterable[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        if not value:
            continue
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items()))


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


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


def _safe_result(row: Mapping[str, Any]) -> bool:
    bucket = _text(row.get("rag_bucket"))
    layer = _text(row.get("evidence_layer"))
    action = _text(row.get("final_rag_action"))
    if bucket not in SAFE_BUCKETS:
        return False
    if layer in UNSAFE_LAYERS:
        return False
    if action and action not in SAFE_RAG_ACTIONS:
        return False
    if row.get("safe_candidate") is False:
        return False
    return True


def _result_parts(row: Mapping[str, Any]) -> list[str]:
    parts: list[str] = []
    for key in ("part_numbers", "matched_parts", "matched_part_numbers"):
        value = row.get(key)
        if isinstance(value, list):
            parts.extend(_text(v) for v in value)
        elif isinstance(value, str):
            parts.append(value)
    components = _as_dict(row.get("score_components"))
    for key in ("matched_part_numbers", "matched_parts"):
        value = components.get(key)
        if isinstance(value, list):
            parts.extend(_text(v) for v in value)
    return _unique(parts)


def _result_terms(row: Mapping[str, Any]) -> list[str]:
    terms: list[str] = []
    components = _as_dict(row.get("score_components"))
    value = components.get("matched_terms")
    if isinstance(value, list):
        terms.extend(_text(v) for v in value)
    value2 = row.get("matched_terms")
    if isinstance(value2, list):
        terms.extend(_text(v) for v in value2)
    return _unique(terms)


def _result_pages(row: Mapping[str, Any]) -> list[str]:
    pages: list[str] = []
    components = _as_dict(row.get("score_components"))
    value = components.get("matched_pages")
    if isinstance(value, list):
        pages.extend(_text(v) for v in value)
    return _unique(pages)


def _citation_key(row: Mapping[str, Any]) -> list[str]:
    keys = []
    for key in ("candidate_id", "chunk_id", "citation_id"):
        value = _text(row.get(key))
        if value:
            keys.append(value)
    return _unique(keys)


def _load_citation_maps(paths: SearchGroupPaths) -> dict[str, dict[str, Any]]:
    rows = _read_jsonl(paths.source_citations) + _read_jsonl(paths.search_citations)
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        for key in _citation_key(row):
            out.setdefault(key, dict(row))
    return out


def _citation_for_result(row: Mapping[str, Any], citations_by_key: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    for key in _citation_key(row):
        citation = citations_by_key.get(key)
        if isinstance(citation, Mapping):
            return dict(citation)
    return {}


def _supporting_result(row: Mapping[str, Any], citation: Mapping[str, Any], max_text_preview_chars: int, include_full: bool) -> dict[str, Any]:
    text_preview = _text(row.get("text_preview")) or _text(row.get("snippet")) or _text(row.get("text"))
    out = {
        "rank": int(row.get("rank") or 0),
        "score": round(_num(row.get("score")), 6),
        "candidate_id": _text(row.get("candidate_id") or row.get("chunk_id")),
        "chunk_id": _text(row.get("chunk_id")),
        "page_id": _text(row.get("page_id")),
        "document_id": _text(row.get("document_id")),
        "ata_code": _text(row.get("ata_code")),
        "rag_bucket": _text(row.get("rag_bucket")),
        "evidence_layer": _text(row.get("evidence_layer")),
        "final_trust_tier": _text(row.get("final_trust_tier")),
        "usable_confidence": round(_num(row.get("usable_confidence")), 6),
        "final_rag_action": _text(row.get("final_rag_action")),
        "matched_terms": _result_terms(row),
        "matched_part_numbers": _result_parts(row),
        "matched_pages": _result_pages(row),
        "source_url": _text(row.get("source_url")),
        "tiff_path": _text(row.get("tiff_path")),
        "ocr_path": _text(row.get("ocr_path")),
        "text_preview": _clip(text_preview, max_text_preview_chars),
        "safe_result": _safe_result(row),
    }
    if citation:
        out["citation_id"] = _text(citation.get("citation_id"))
        out["citation_short"] = _text(citation.get("citation_short"))
        out["citation_markdown"] = _text(citation.get("citation_markdown"))
    if include_full:
        out["raw_result"] = dict(row)
    return out


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------


def _group_score(best_score: float, buckets: Sequence[str], layers: Sequence[str], matched_parts: Sequence[str], matched_terms: Sequence[str], supporting_count: int) -> float:
    bucket_bonus = sum(BUCKET_GROUP_BONUS.get(bucket, 0.25) for bucket in set(buckets))
    diversity_bonus = max(0, len(set(buckets)) - 1) * 1.5 + max(0, len(set(layers)) - 1) * 0.5
    match_bonus = len(set(matched_parts)) * 1.0 + len(set(matched_terms)) * 0.25
    support_bonus = min(supporting_count, 6) * 0.15
    return round(float(best_score) + bucket_bonus + diversity_bonus + match_bonus + support_bonus, 6)


def group_search_results(paths: SearchGroupPaths, options: SearchGroupOptions | None = None) -> dict[str, Any]:
    options = options or SearchGroupOptions()
    search_rows = _read_jsonl(paths.search_results)
    citations_by_key = _load_citation_maps(paths)

    groups_raw: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for row in search_rows:
        page_id = _text(row.get("page_id"), "unknown_page")
        citation = _citation_for_result(row, citations_by_key)
        groups_raw.setdefault(page_id, []).append((dict(row), citation))

    groups: list[dict[str, Any]] = []
    for page_id, pairs in groups_raw.items():
        pairs.sort(key=lambda item: (-_num(item[0].get("score")), int(item[0].get("rank") or 999999)))
        rows = [p[0] for p in pairs]
        citations = [p[1] for p in pairs if p[1]]
        best = rows[0] if rows else {}
        all_buckets = _unique(_text(r.get("rag_bucket")) for r in rows)
        all_layers = _unique(_text(r.get("evidence_layer")) for r in rows)
        all_tiers = _unique(_text(r.get("final_trust_tier")) for r in rows)
        all_actions = _unique(_text(r.get("final_rag_action")) for r in rows)
        all_terms = _unique(term for r in rows for term in _result_terms(r))
        all_parts = _unique(part for r in rows for part in _result_parts(r))
        all_matched_pages = _unique(page for r in rows for page in _result_pages(r))
        source_url = next((_text(r.get("source_url")) for r in rows if _text(r.get("source_url"))), "")
        tiff_path = next((_text(r.get("tiff_path")) for r in rows if _text(r.get("tiff_path"))), "")
        ocr_path = next((_text(r.get("ocr_path")) for r in rows if _text(r.get("ocr_path"))), "")
        ata_codes = _unique(_text(r.get("ata_code")) for r in rows)
        document_ids = _unique(_text(r.get("document_id")) for r in rows)
        page_roles = _unique(_text(r.get("page_role")) for r in rows)
        best_score = round(_num(best.get("score")), 6)
        avg_score = round(sum(_num(r.get("score")) for r in rows) / max(len(rows), 1), 6)
        max_confidence = round(max((_num(r.get("usable_confidence")) for r in rows), default=0.0), 6)
        avg_confidence = round(sum(_num(r.get("usable_confidence")) for r in rows) / max(len(rows), 1), 6)
        unsafe_count = sum(1 for r in rows if not _safe_result(r))
        excluded_count = sum(1 for r in rows if _text(r.get("final_rag_action")) and _text(r.get("final_rag_action")) not in SAFE_RAG_ACTIONS)
        supporting = [
            _supporting_result(row, citation, options.max_text_preview_chars, options.include_full_supporting_results)
            for row, citation in pairs[: max(1, int(options.max_supporting_results or 20))]
        ]
        citation_records = [
            {
                "citation_id": _text(c.get("citation_id")),
                "citation_short": _text(c.get("citation_short")),
                "citation_markdown": _text(c.get("citation_markdown")),
                "rag_bucket": _text(c.get("rag_bucket")),
                "evidence_layer": _text(c.get("evidence_layer")),
            }
            for c in citations[: max(1, int(options.max_supporting_results or 20))]
        ]
        group = {
            "group_id": f"search_group:{_slug(page_id)}",
            "page_id": page_id,
            "document_ids": document_ids,
            "ata_codes": ata_codes,
            "page_roles": page_roles,
            "result_count": len(rows),
            "supporting_result_count": len(rows),
            "best_rank": min((int(r.get("rank") or 999999) for r in rows), default=0),
            "best_score": best_score,
            "average_score": avg_score,
            "group_score": _group_score(best_score, all_buckets, all_layers, all_parts, all_terms, len(rows)),
            "rag_buckets": all_buckets,
            "evidence_layers": all_layers,
            "trust_tiers": all_tiers,
            "rag_actions": all_actions,
            "max_usable_confidence": max_confidence,
            "average_usable_confidence": avg_confidence,
            "matched_terms": all_terms,
            "matched_part_numbers": all_parts,
            "matched_pages": all_matched_pages,
            "source_url": source_url,
            "tiff_path": tiff_path,
            "ocr_path": ocr_path,
            "safe_group": unsafe_count == 0,
            "unsafe_supporting_results": unsafe_count,
            "excluded_supporting_results": excluded_count,
            "has_source_url": bool(source_url),
            "has_tiff_path": bool(tiff_path),
            "has_ocr_path": bool(ocr_path),
            "citation_count": len(citations),
            "citations": citation_records,
            "supporting_results": supporting,
        }
        groups.append(group)

    groups.sort(key=lambda g: (-_num(g.get("group_score")), -_num(g.get("best_score")), int(g.get("best_rank") or 999999), _text(g.get("page_id"))))
    top_k = max(1, int(options.top_k_groups or 20))
    groups = groups[:top_k]
    for index, group in enumerate(groups, start=1):
        group["rank"] = index

    unsafe_grouped = sum(1 for g in groups if not g.get("safe_group"))
    excluded_grouped = sum(1 for g in groups if int(g.get("excluded_supporting_results") or 0) > 0)
    pages = _unique(g.get("page_id") for g in groups)
    all_supporting = sum(int(g.get("supporting_result_count") or 0) for g in groups)
    summary = {
        "status": "OK" if groups or not search_rows else "FAIL",
        "version": VERSION,
        "created_at": _utc_now(),
        "search_results_path": str(paths.search_results),
        "source_citations_path": str(paths.source_citations),
        "search_citations_path": str(paths.search_citations),
        "search_result_records": len(search_rows),
        "grouped_page_records": len(groups),
        "pages_found": len(pages),
        "supporting_result_records": all_supporting,
        "unsafe_grouped_records": unsafe_grouped,
        "excluded_grouped_records": excluded_grouped,
        "groups_with_multiple_buckets": sum(1 for g in groups if len(g.get("rag_buckets") or []) > 1),
        "groups_with_multiple_layers": sum(1 for g in groups if len(g.get("evidence_layers") or []) > 1),
        "groups_with_source_url": sum(1 for g in groups if g.get("has_source_url")),
        "groups_with_tiff_path": sum(1 for g in groups if g.get("has_tiff_path")),
        "groups_with_ocr_path": sum(1 for g in groups if g.get("has_ocr_path")),
        "groups_with_citations": sum(1 for g in groups if int(g.get("citation_count") or 0) > 0),
        "bucket_counts": _count(bucket for g in groups for bucket in _as_list(g.get("rag_buckets"))),
        "evidence_layer_counts": _count(layer for g in groups for layer in _as_list(g.get("evidence_layers"))),
        "top_group_score": groups[0]["group_score"] if groups else 0,
        "top_best_score": groups[0]["best_score"] if groups else 0,
        "paths": {
            "grouped_results": str(paths.grouped_results),
            "grouped_results_jsonl": str(paths.grouped_results_jsonl),
            "summary": str(paths.summary),
            "review_md": str(paths.review_md),
            "review_html": str(paths.review_html),
            "graph_nodes": str(paths.graph_nodes),
            "graph_edges": str(paths.graph_edges),
        },
        "samples": groups[: min(len(groups), 20)],
    }

    graph_nodes, graph_edges = _build_graph(groups)
    payload = {"summary": summary, "groups": groups}
    _write_json(paths.grouped_results, payload)
    _write_jsonl(paths.grouped_results_jsonl, groups)
    _write_json(paths.summary, summary)
    _write_json(paths.graph_nodes, graph_nodes)
    _write_json(paths.graph_edges, graph_edges)
    _write_text(paths.review_md, _render_markdown(summary, groups))
    _write_text(paths.review_html, _render_html(summary, groups))
    if options.open_report:
        try:
            webbrowser.open(paths.review_html.resolve().as_uri())
        except Exception:
            pass
    return {"summary": summary, "groups": groups, "graph_nodes": graph_nodes, "graph_edges": graph_edges}


# ---------------------------------------------------------------------------
# Graph/report rendering
# ---------------------------------------------------------------------------


def _build_graph(groups: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def add_node(node_id: str, node_type: str, **attrs: Any) -> None:
        if not node_id:
            return
        node = nodes.setdefault(node_id, {"id": node_id, "type": node_type})
        node.update({k: v for k, v in attrs.items() if v not in (None, "", [])})

    root = "trace_net:search_grouped_results"
    add_node(root, "search_group_overlay", version=VERSION)
    for group in groups:
        gid = _text(group.get("group_id"))
        page_id = _text(group.get("page_id"))
        add_node(gid, "search_page_group", page_id=page_id, group_score=group.get("group_score"), result_count=group.get("result_count"))
        add_node(page_id, "page")
        edges.append({"source": root, "target": gid, "type": "HAS_GROUP"})
        edges.append({"source": gid, "target": page_id, "type": "GROUPS_PAGE"})
        for bucket in _as_list(group.get("rag_buckets")):
            bid = f"rag_bucket:{bucket}"
            add_node(bid, "rag_bucket")
            edges.append({"source": gid, "target": bid, "type": "HAS_BUCKET"})
        for result in _as_list(group.get("supporting_results")):
            rid = _text(result.get("candidate_id") or result.get("chunk_id"))
            if rid:
                add_node(rid, "rag_candidate_chunk", page_id=page_id, rag_bucket=result.get("rag_bucket"), evidence_layer=result.get("evidence_layer"))
                edges.append({"source": gid, "target": rid, "type": "SUPPORTED_BY"})
            cid = _text(result.get("citation_id"))
            if cid:
                add_node(cid, "source_citation", page_id=page_id)
                if rid:
                    edges.append({"source": rid, "target": cid, "type": "HAS_CITATION"})
    return list(nodes.values()), edges


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(_text(cell).replace("\n", "<br>") for cell in row) + " |")
    return "\n".join(lines)


def _render_markdown(summary: Mapping[str, Any], groups: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "# TRACE-Net Search Result Grouper v1",
        "",
        f"Status: **{summary.get('status', 'UNKNOWN')}**  Version: `{summary.get('version', VERSION)}`",
        "",
        "## Summary",
        "",
        _md_table(
            ["Metric", "Value"],
            [[key, summary.get(key)] for key in (
                "search_result_records",
                "grouped_page_records",
                "pages_found",
                "supporting_result_records",
                "unsafe_grouped_records",
                "excluded_grouped_records",
                "groups_with_multiple_buckets",
                "groups_with_citations",
                "top_group_score",
            )],
        ),
        "",
        "## Grouped page results",
        "",
    ]
    rows = []
    for group in groups:
        support_bits = []
        if group.get("matched_part_numbers"):
            support_bits.append("parts=" + ", ".join(_as_list(group.get("matched_part_numbers"))[:6]))
        if group.get("matched_terms"):
            support_bits.append("terms=" + ", ".join(_as_list(group.get("matched_terms"))[:8]))
        rows.append([
            group.get("rank"),
            group.get("page_id"),
            group.get("group_score"),
            ", ".join(_as_list(group.get("rag_buckets"))),
            ", ".join(_as_list(group.get("evidence_layers"))),
            group.get("supporting_result_count"),
            "; ".join(support_bits),
            group.get("source_url"),
        ])
    lines.append(_md_table(["Rank", "Page", "Group score", "Buckets", "Layers", "Support", "Matches", "Source URL"], rows))
    lines.append("")
    lines.append("## Supporting evidence samples")
    lines.append("")
    for group in groups[:10]:
        lines.append(f"### {group.get('rank')}. {group.get('page_id')} — score {group.get('group_score')}")
        lines.append("")
        lines.append(f"Buckets: `{', '.join(_as_list(group.get('rag_buckets')))}`")
        lines.append(f"Source URL: `{group.get('source_url', '')}`")
        lines.append("")
        for result in _as_list(group.get("supporting_results"))[:5]:
            lines.append(f"- rank={result.get('rank')} score={result.get('score')} bucket=`{result.get('rag_bucket')}` layer=`{result.get('evidence_layer')}` trust=`{result.get('final_trust_tier')}`")
            if result.get("matched_part_numbers"):
                lines.append(f"  - matched parts: {', '.join(_as_list(result.get('matched_part_numbers'))[:8])}")
            if result.get("matched_terms"):
                lines.append(f"  - matched terms: {', '.join(_as_list(result.get('matched_terms'))[:8])}")
            if result.get("text_preview"):
                lines.append(f"  - preview: {result.get('text_preview')}")
        lines.append("")
    return "\n".join(lines)


def _render_html(summary: Mapping[str, Any], groups: Sequence[Mapping[str, Any]]) -> str:
    md = _render_markdown(summary, groups)
    body = "\n".join(f"<p>{html.escape(line)}</p>" if line and not line.startswith("|") else f"<pre>{html.escape(line)}</pre>" for line in md.splitlines())
    return """<!doctype html>
<html><head><meta charset=\"utf-8\"><title>TRACE-Net Search Result Grouper v1</title>
<style>
body{font-family:Arial,sans-serif;margin:24px;line-height:1.45;color:#17202a}pre{background:#f6f8fa;padding:8px;white-space:pre-wrap;border-radius:6px}p{margin:0 0 8px}.card{border:1px solid #ddd;border-radius:8px;padding:12px;margin:12px 0}.muted{color:#666}
</style></head><body>
<h1>TRACE-Net Search Result Grouper v1</h1>
""" + body + "\n</body></html>\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Group TRACE-Net local search results by page.")
    parser.add_argument("--search-dir", type=Path, default=DEFAULT_SEARCH_DIR)
    parser.add_argument("--citations-dir", type=Path, default=DEFAULT_CITATIONS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--search-results", type=Path, default=None)
    parser.add_argument("--source-citations", type=Path, default=None)
    parser.add_argument("--search-citations", type=Path, default=None)
    parser.add_argument("--top-k-groups", type=int, default=20)
    parser.add_argument("--max-supporting-results", type=int, default=20)
    parser.add_argument("--max-text-preview-chars", type=int, default=500)
    parser.add_argument("--include-full-supporting-results", action="store_true")
    parser.add_argument("--open", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    paths = SearchGroupPaths(
        search_dir=args.search_dir,
        citations_dir=args.citations_dir,
        output_dir=args.output_dir,
        search_results_path=args.search_results,
        source_citations_path=args.source_citations,
        search_citations_path=args.search_citations,
    )
    result = group_search_results(
        paths,
        SearchGroupOptions(
            top_k_groups=args.top_k_groups,
            max_supporting_results=args.max_supporting_results,
            max_text_preview_chars=args.max_text_preview_chars,
            include_full_supporting_results=args.include_full_supporting_results,
            open_report=args.open,
        ),
    )
    summary = result["summary"]
    print("TRACE-Net search result grouper")
    print(f"  Status: {summary.get('status')}")
    print(f"  Output dir: {args.output_dir}")
    print("  Summary:")
    for key in (
        "search_result_records", "grouped_page_records", "pages_found", "supporting_result_records",
        "unsafe_grouped_records", "excluded_grouped_records", "groups_with_multiple_buckets", "groups_with_citations", "top_group_score",
    ):
        print(f"    {key}: {summary.get(key)}")
    print("  Buckets:", summary.get("bucket_counts"))
    print("  Top groups:")
    for group in result.get("groups", [])[:10]:
        print(f"    {group.get('rank')}. score={group.get('group_score')} page={group.get('page_id')} buckets={','.join(group.get('rag_buckets') or [])} support={group.get('supporting_result_count')}")
    print("Files written:")
    for key, value in summary.get("paths", {}).items():
        print(f"  {key}: {value}")
    return 0 if summary.get("status") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
