"""Generate local visualizations for the HEICO TIFF document graph.

The exporter is intentionally read-only. It consumes the graph and entity-trait
artifacts already written under local_data and produces small, self-contained
HTML files that can be opened directly in a browser.

The visualizations avoid a full force layout of every node because a graph with
thousands of trait assertion nodes quickly becomes a hairball. Instead, the
outputs show the graph in the same way the system should reason over it:

* document -> ATA -> page layout
* page "character sheet" cards
* trait/assertion overlay summaries
* focused page neighborhoods
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import html
import json
import re
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_GRAPH_DIR = "local_data/organization/graph"
DEFAULT_ENTITY_TRAIT_DIR = "local_data/organization/entity_traits"
DEFAULT_VISUALIZATION_DIR = "local_data/organization/visualizations"

GRAPH_NODES_FILE = "graph_nodes.json"
GRAPH_EDGES_FILE = "graph_edges.json"
PAGE_CARDS_FILE = "page_character_cards.json"
PART_CARDS_FILE = "part_character_cards.json"
ENTITY_TRAITS_FILE = "entity_traits.json"
TRAIT_SUMMARY_FILE = "trait_graph_summary.json"
VISUALIZATION_SUMMARY_FILE = "graph_visualization_summary.json"


@dataclass(frozen=True)
class GraphVisualizationResult:
    """Result returned by the visualization exporter."""

    status: str
    output_dir: str
    files: dict[str, str]
    summary: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


def _load_json(path: str | Path) -> Any:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_text(path: str | Path, text: str) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _write_json(path: str | Path, data: Any) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return p


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(payload: Any, *keys: str) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, Mapping):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return value
        for key in ("items", "records", "pages", "parts", "nodes", "edges", "assertions", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    out = str(value).strip()
    return out if out else default


def _slug(value: Any) -> str:
    text = _text(value).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "unknown"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return default


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _node_id(node: Mapping[str, Any]) -> str:
    return _text(node.get("id") or node.get("node_id") or node.get("key"))


def _node_type(node: Mapping[str, Any]) -> str:
    return _text(node.get("type") or node.get("node_type") or node.get("kind")).lower()


def _node_label(node: Mapping[str, Any] | None) -> str:
    if not node:
        return ""
    props = _as_mapping(node.get("properties"))
    for source in (node, props):
        for key in ("label", "name", "title", "page_id", "part_number", "ata_code", "short_summary"):
            value = source.get(key)
            if value not in (None, "", [], {}):
                return _text(value)
    return _node_id(node)


def _edge_type(edge: Mapping[str, Any]) -> str:
    return _text(edge.get("type") or edge.get("edge_type") or edge.get("relationship")).upper()


def _edge_source(edge: Mapping[str, Any]) -> str:
    return _text(edge.get("from") or edge.get("source") or edge.get("from_id") or edge.get("src"))


def _edge_target(edge: Mapping[str, Any]) -> str:
    return _text(edge.get("to") or edge.get("target") or edge.get("to_id") or edge.get("dst"))


def _prop(mapping: Mapping[str, Any] | None, *keys: str, default: Any = None) -> Any:
    if not mapping:
        return default
    props = _as_mapping(mapping.get("properties"))
    for source in (mapping, props):
        for key in keys:
            if key in source and source.get(key) not in (None, "", [], {}):
                return source.get(key)
    return default


def _extract_page_sort_key(card: Mapping[str, Any]) -> tuple[str, int, str]:
    parents = _as_mapping(card.get("parents"))
    ata = _text(parents.get("ata_code") or card.get("ata_code"), "unknown")
    page_id = _text(card.get("page_id") or card.get("entity_id") or card.get("label"))
    match = re.search(r"p0*(\d+)", page_id.lower()) or re.search(r"(\d+)", page_id)
    page_num = int(match.group(1)) if match else 10**9
    return (ata, page_num, page_id)


def _shorten(value: Any, limit: int = 80) -> str:
    text = _text(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def _escape(value: Any) -> str:
    return html.escape(_text(value), quote=True)


def _json_for_html(value: Any) -> str:
    # Keep embedded JSON safe inside <script type="application/json">.
    text = json.dumps(value, ensure_ascii=False)
    return text.replace("</", "<\\/")


def _load_graph_artifacts(graph_dir: str | Path) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    root = Path(graph_dir)
    nodes = _as_list(_load_json(root / GRAPH_NODES_FILE), "nodes")
    edges = _as_list(_load_json(root / GRAPH_EDGES_FILE), "edges")
    return [n for n in nodes if isinstance(n, Mapping)], [e for e in edges if isinstance(e, Mapping)]


def _load_trait_artifacts(trait_dir: str | Path) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]], list[Mapping[str, Any]], Mapping[str, Any]]:
    root = Path(trait_dir)
    page_cards = _as_list(_load_json(root / PAGE_CARDS_FILE), "pages")
    part_cards = _as_list(_load_json(root / PART_CARDS_FILE), "parts")
    assertions = _as_list(_load_json(root / ENTITY_TRAITS_FILE), "assertions")
    summary = _as_mapping(_load_json(root / TRAIT_SUMMARY_FILE))
    return (
        [c for c in page_cards if isinstance(c, Mapping)],
        [c for c in part_cards if isinstance(c, Mapping)],
        [a for a in assertions if isinstance(a, Mapping)],
        summary,
    )


def _fallback_page_cards_from_graph(nodes: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    node_by_id = {_node_id(node): node for node in nodes if _node_id(node)}
    out_edges: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for edge in edges:
        out_edges[_edge_source(edge)].append(edge)

    cards: list[dict[str, Any]] = []
    for page in nodes:
        if _node_type(page) != "page":
            continue
        page_id = _node_id(page)
        parents: dict[str, Any] = {}
        source: dict[str, Any] = {}
        context: dict[str, Any] = {}
        parts: list[str] = []
        for edge in out_edges.get(page_id, []):
            target = node_by_id.get(_edge_target(edge))
            etype = _edge_type(edge)
            if not target:
                continue
            if etype == "BELONGS_TO_DOCUMENT":
                parents["document_id"] = _node_id(target)
                parents["document_label"] = _node_label(target)
            elif etype == "BELONGS_TO_ATA":
                parents["ata_id"] = _node_id(target)
                parents["ata_code"] = _prop(target, "ata_code", "code", default=_node_label(target))
            elif etype == "HAS_SOURCE_LINK":
                source["source_url"] = _prop(target, "source_url", "url", default=_node_label(target))
            elif etype == "HAS_TIFF":
                source["tiff_path"] = _prop(target, "path", "tiff_path", default=_node_label(target))
            elif etype == "HAS_OCR":
                source["ocr_path"] = _prop(target, "path", "ocr_path", default=_node_label(target))
            elif etype == "HAS_CONTEXT":
                context["context_node_id"] = _node_id(target)
                context["page_role"] = _prop(target, "page_role", "role", "context_role", default=None)
                context["summary"] = _prop(target, "summary", "short_summary", default=None)
            elif etype == "MENTIONS_PART":
                parts.append(_text(_prop(target, "part_number", default=_node_label(target))))
        cards.append(
            {
                "entity_id": page_id,
                "entity_type": "page",
                "page_id": _prop(page, "page_id", default=page_id.removeprefix("page:")),
                "label": _node_label(page),
                "parents": parents,
                "source": source,
                "context": context,
                "signals": {},
                "parts": sorted(set(parts)),
                "direct_traits": [],
                "derived_traits": [],
                "traits": [],
            }
        )
    return sorted(cards, key=_extract_page_sort_key)


def _counts_for_pages(page_cards: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ata_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    image_class_counts: Counter[str] = Counter()
    derived_counts: Counter[str] = Counter()
    direct_trait_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()

    for card in page_cards:
        parents = _as_mapping(card.get("parents"))
        context = _as_mapping(card.get("context"))
        signals = _as_mapping(card.get("signals"))
        source = _as_mapping(card.get("source"))
        ata_counts[_text(parents.get("ata_code"), "unknown")] += 1
        role_counts[_text(context.get("page_role"), "unknown")] += 1
        image_class_counts[_text(signals.get("image_classification"), "unknown")] += 1
        if source.get("source_url"):
            source_counts["has_source_url"] += 1
        if source.get("tiff_path"):
            source_counts["has_tiff_path"] += 1
        if source.get("ocr_path"):
            source_counts["has_ocr_path"] += 1
        for trait in _as_list(card.get("derived_traits")):
            derived_counts[_text(trait)] += 1
        for trait in _as_list(card.get("direct_traits")):
            direct_trait_counts[_text(trait)] += 1

    def sorted_counts(counter: Counter[str]) -> dict[str, int]:
        return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))

    return {
        "ata_counts": sorted_counts(ata_counts),
        "role_counts": sorted_counts(role_counts),
        "image_class_counts": sorted_counts(image_class_counts),
        "derived_trait_counts": sorted_counts(derived_counts),
        "direct_trait_counts_top": dict(sorted(direct_trait_counts.items(), key=lambda item: (-item[1], item[0]))[:30]),
        "source_counts": sorted_counts(source_counts),
    }


def _counts_for_assertions(assertions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    trait_type_counts: Counter[str] = Counter()
    trait_key_counts: Counter[str] = Counter()
    trait_value_counts: Counter[str] = Counter()
    scope_counts: Counter[str] = Counter()
    entity_type_counts: Counter[str] = Counter()
    top_traits: Counter[str] = Counter()

    for assertion in assertions:
        trait_type = _text(assertion.get("trait_type"), "unknown")
        trait_key = _text(assertion.get("trait_key"), "unknown")
        trait_value = _text(assertion.get("trait_value"), "unknown")
        scope = _text(assertion.get("scope"), "unknown")
        entity_type = _text(assertion.get("entity_type"), "unknown")
        trait_type_counts[trait_type] += 1
        trait_key_counts[f"{trait_type}:{trait_key}"] += 1
        trait_value_counts[f"{trait_type}:{trait_key}={trait_value}"] += 1
        scope_counts[scope] += 1
        entity_type_counts[entity_type] += 1
        top_traits[f"{trait_type}:{trait_key}={trait_value}"] += 1

    def sorted_top(counter: Counter[str], limit: int = 40) -> dict[str, int]:
        return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit])

    return {
        "trait_type_counts": sorted_top(trait_type_counts, 100),
        "trait_key_counts": sorted_top(trait_key_counts, 100),
        "trait_value_counts_top": sorted_top(trait_value_counts, 80),
        "scope_counts": sorted_top(scope_counts, 20),
        "entity_type_counts": sorted_top(entity_type_counts, 20),
        "top_traits": sorted_top(top_traits, 80),
    }


def _summarize_graph(nodes: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    node_counts = Counter(_node_type(node) or "unknown" for node in nodes)
    edge_counts = Counter(_edge_type(edge) or "UNKNOWN" for edge in edges)
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_counts": dict(sorted(node_counts.items(), key=lambda item: (-item[1], item[0]))),
        "edge_counts": dict(sorted(edge_counts.items(), key=lambda item: (-item[1], item[0]))),
    }


def _make_summary(
    graph_dir: str | Path,
    trait_dir: str | Path,
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    page_cards: Sequence[Mapping[str, Any]],
    part_cards: Sequence[Mapping[str, Any]],
    assertions: Sequence[Mapping[str, Any]],
    trait_summary: Mapping[str, Any],
) -> dict[str, Any]:
    page_counts = _counts_for_pages(page_cards)
    assertion_counts = _counts_for_assertions(assertions)
    graph_summary = _summarize_graph(nodes, edges)
    overlay_counts = _as_mapping(trait_summary.get("overlay_counts"))
    input_counts = _as_mapping(trait_summary.get("input_counts"))
    return {
        "status": "ok" if page_cards else "needs_attention",
        "graph_dir": str(graph_dir),
        "trait_dir": str(trait_dir),
        "graph": graph_summary,
        "processed_corpus": {
            "documents": graph_summary["node_counts"].get("document", 0),
            "ata_sections": graph_summary["node_counts"].get("ata_section", 0),
            "pages": len(page_cards),
            "parts": len(part_cards),
            "page_context_nodes": graph_summary["node_counts"].get("page_context", 0),
            "source_link_nodes": graph_summary["node_counts"].get("source_link", 0),
        },
        "trait_overlay": {
            "present": bool(assertions or trait_summary),
            "status": _text(trait_summary.get("status"), default="unknown") if trait_summary else "missing",
            "nodes": _safe_int(overlay_counts.get("nodes"), default=0),
            "edges": _safe_int(overlay_counts.get("edges"), default=0),
            "assertions": len(assertions) or _safe_int(overlay_counts.get("assertions"), default=0),
            "trait_nodes": _safe_int(overlay_counts.get("trait_nodes"), default=0),
            "trait_assertion_nodes": _safe_int(overlay_counts.get("trait_assertion_nodes"), default=0),
            "evidence_source_nodes": _safe_int(overlay_counts.get("evidence_source_nodes"), default=0),
            "derived_assertions": _safe_int(overlay_counts.get("derived_assertions"), default=0),
            "page_cards": len(page_cards) or _safe_int(overlay_counts.get("page_cards"), default=0),
            "part_cards": len(part_cards) or _safe_int(overlay_counts.get("part_cards"), default=0),
            "input_counts": dict(input_counts),
        },
        "page_counts": page_counts,
        "assertion_counts": assertion_counts,
    }


def _stat_card(label: str, value: Any, hint: str = "") -> str:
    return (
        '<div class="stat-card">'
        f'<div class="stat-value">{_escape(value)}</div>'
        f'<div class="stat-label">{_escape(label)}</div>'
        f'<div class="stat-hint">{_escape(hint)}</div>'
        '</div>'
    )


def _html_shell(title: str, body: str, extra_head: str = "") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_escape(title)}</title>
<style>
:root {{
  --bg: #0f172a;
  --panel: #111827;
  --panel-2: #1f2937;
  --text: #e5e7eb;
  --muted: #94a3b8;
  --line: #334155;
  --accent: #38bdf8;
  --good: #34d399;
  --warn: #fbbf24;
  --bad: #fb7185;
  --page: #60a5fa;
  --part: #c084fc;
  --source: #22c55e;
  --trait: #f59e0b;
  --context: #14b8a6;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: Inter, Segoe UI, Arial, sans-serif; background: var(--bg); color: var(--text); }}
a {{ color: var(--accent); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
header {{ padding: 28px 34px 18px; border-bottom: 1px solid var(--line); background: linear-gradient(135deg, #111827, #172554); }}
header h1 {{ margin: 0 0 8px; font-size: 28px; }}
header p {{ margin: 0; color: var(--muted); max-width: 980px; line-height: 1.5; }}
main {{ padding: 24px 34px 48px; }}
.nav {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }}
.nav a {{ padding: 8px 12px; border: 1px solid var(--line); border-radius: 999px; background: rgba(15,23,42,.65); }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; }}
.stat-card, .panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 16px; box-shadow: 0 12px 30px rgba(0,0,0,.18); }}
.stat-value {{ font-size: 26px; font-weight: 750; }}
.stat-label {{ margin-top: 4px; color: var(--muted); font-size: 13px; }}
.stat-hint {{ margin-top: 8px; color: #64748b; font-size: 12px; min-height: 16px; }}
.section {{ margin-top: 26px; }}
.section h2 {{ margin: 0 0 12px; font-size: 22px; }}
.section h3 {{ margin: 0 0 10px; font-size: 17px; }}
.flow {{ display: grid; grid-template-columns: repeat(5, minmax(150px, 1fr)); gap: 12px; align-items: stretch; }}
.flow-node {{ min-height: 100px; border-radius: 18px; padding: 14px; border: 1px solid var(--line); background: var(--panel); position: relative; }}
.flow-node:after {{ content: "→"; position: absolute; right: -15px; top: 38%; color: var(--muted); font-size: 20px; }}
.flow-node:last-child:after {{ content: ""; }}
.flow-title {{ font-weight: 750; margin-bottom: 6px; }}
.flow-sub {{ color: var(--muted); font-size: 13px; line-height: 1.4; }}
.badge {{ display: inline-block; padding: 3px 8px; border: 1px solid var(--line); border-radius: 999px; margin: 2px 4px 2px 0; color: var(--text); background: #0b1220; font-size: 12px; }}
.badge.good {{ border-color: rgba(52,211,153,.6); color: #bbf7d0; }}
.badge.warn {{ border-color: rgba(251,191,36,.6); color: #fde68a; }}
.badge.trait {{ border-color: rgba(245,158,11,.7); color: #fef3c7; }}
.badge.part {{ border-color: rgba(192,132,252,.7); color: #e9d5ff; }}
.controls {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; margin-bottom: 18px; }}
input, select {{ width: 100%; padding: 9px 10px; border-radius: 10px; border: 1px solid var(--line); background: #0b1220; color: var(--text); }}
.page-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(86px, 1fr)); gap: 8px; }}
.page-tile {{ min-height: 76px; border-radius: 12px; border: 1px solid var(--line); padding: 8px; cursor: pointer; background: #1e293b; }}
.page-tile:hover {{ outline: 2px solid var(--accent); }}
.page-num {{ font-weight: 750; font-size: 12px; }}
.page-role {{ color: var(--muted); font-size: 11px; margin-top: 4px; }}
.page-meta {{ color: #64748b; font-size: 10px; margin-top: 4px; }}
.role-parts-list {{ background: linear-gradient(135deg, #1d4ed8, #0f172a); }}
.role-figure {{ background: linear-gradient(135deg, #7e22ce, #0f172a); }}
.role-table {{ background: linear-gradient(135deg, #b45309, #0f172a); }}
.role-procedure {{ background: linear-gradient(135deg, #15803d, #0f172a); }}
.role-blank {{ background: linear-gradient(135deg, #475569, #0f172a); }}
.role-front-matter {{ background: linear-gradient(135deg, #0f766e, #0f172a); }}
.role-unknown {{ background: #1f2937; }}
.details {{ margin-top: 20px; white-space: pre-wrap; font-size: 13px; color: #cbd5e1; }}
.bar-row {{ display: grid; grid-template-columns: minmax(170px, 300px) 1fr 54px; gap: 10px; align-items: center; margin: 7px 0; }}
.bar-label {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #cbd5e1; }}
.bar-track {{ height: 12px; background: #020617; border-radius: 999px; border: 1px solid var(--line); overflow: hidden; }}
.bar-fill {{ height: 100%; background: linear-gradient(90deg, #38bdf8, #818cf8); border-radius: 999px; }}
.bar-value {{ text-align: right; color: var(--muted); font-size: 12px; }}
.neighborhood {{ display: grid; grid-template-columns: 1fr; gap: 14px; }}
.network-card {{ border: 1px solid var(--line); border-radius: 18px; padding: 16px; background: var(--panel); overflow: hidden; }}
.network-title {{ font-weight: 750; margin-bottom: 12px; }}
.network-lanes {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; align-items: start; }}
.lane-title {{ color: var(--muted); font-size: 12px; margin-bottom: 8px; text-transform: uppercase; letter-spacing: .05em; }}
.node-pill {{ border: 1px solid var(--line); border-radius: 12px; padding: 8px; margin-bottom: 8px; background: #0b1220; font-size: 12px; word-break: break-word; }}
.node-pill.page {{ border-color: rgba(96,165,250,.8); }}
.node-pill.part {{ border-color: rgba(192,132,252,.8); }}
.node-pill.source {{ border-color: rgba(34,197,94,.8); }}
.node-pill.trait {{ border-color: rgba(245,158,11,.8); }}
.node-pill.context {{ border-color: rgba(20,184,166,.8); }}
.footer-note {{ color: var(--muted); font-size: 12px; margin-top: 26px; }}
@media (max-width: 900px) {{ .flow, .network-lanes {{ grid-template-columns: 1fr; }} .flow-node:after {{ content: "↓"; right: 50%; top: auto; bottom: -18px; }} .flow-node:last-child:after {{ content: ""; }} }}
</style>
{extra_head}
</head>
<body>
<header>
<h1>{_escape(title)}</h1>
<p>Local visual report generated from the HEICO TIFF document graph and entity-trait overlay artifacts.</p>
<div class="nav">
<a href="index.html">Overview</a>
<a href="page_grid.html">509-page grid</a>
<a href="trait_overlay.html">Trait overlay</a>
<a href="neighborhoods.html">Sample neighborhoods</a>
</div>
</header>
<main>
{body}
</main>
</body>
</html>
"""


def _render_count_bars(counts: Mapping[str, int], *, max_items: int = 20) -> str:
    clean_items = [(str(k), int(v)) for k, v in counts.items() if k]
    clean_items.sort(key=lambda item: (-item[1], item[0]))
    max_value = max([value for _, value in clean_items[:max_items]] or [1])
    rows = []
    for label, value in clean_items[:max_items]:
        width = max(3, int(100 * value / max_value))
        rows.append(
            '<div class="bar-row">'
            f'<div class="bar-label" title="{_escape(label)}">{_escape(label)}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{width}%"></div></div>'
            f'<div class="bar-value">{value}</div>'
            '</div>'
        )
    return "\n".join(rows) if rows else '<div class="footer-note">No counts available.</div>'


def _index_html(summary: Mapping[str, Any]) -> str:
    corpus = _as_mapping(summary.get("processed_corpus"))
    graph = _as_mapping(summary.get("graph"))
    trait = _as_mapping(summary.get("trait_overlay"))
    page_counts = _as_mapping(summary.get("page_counts"))

    body = f"""
<div class="grid">
{_stat_card('documents', corpus.get('documents', 0), 'manual-level roots')}
{_stat_card('pages', corpus.get('pages', 0), 'processed TIFF pages')}
{_stat_card('ATA sections', corpus.get('ata_sections', 0), 'document organization groups')}
{_stat_card('parts', corpus.get('parts', 0), 'part character cards')}
{_stat_card('core graph nodes', graph.get('node_count', 0), 'document/source/context graph')}
{_stat_card('core graph edges', graph.get('edge_count', 0), 'typed relationships')}
{_stat_card('trait assertions', trait.get('assertions', 0), 'character-sheet traits')}
{_stat_card('trait overlay edges', trait.get('edges', 0), 'assertion/trait/evidence links')}
</div>

<div class="section">
<h2>How to read this graph</h2>
<div class="flow">
  <div class="flow-node"><div class="flow-title">Document</div><div class="flow-sub">The scanned manual/package root. In this run it should be one document.</div></div>
  <div class="flow-node"><div class="flow-title">ATA section</div><div class="flow-sub">Groups pages by technical section, such as 25-21-00.</div></div>
  <div class="flow-node"><div class="flow-title">Page</div><div class="flow-sub">The main hub. Every answer should resolve back to a page.</div></div>
  <div class="flow-node"><div class="flow-title">Evidence</div><div class="flow-sub">Source link, TIFF file, OCR file, page context, part mentions.</div></div>
  <div class="flow-node"><div class="flow-title">Traits</div><div class="flow-sub">Game-character style status effects: role, visual class, source-ready, blank, answer-ready.</div></div>
</div>
</div>

<div class="section grid">
  <div class="panel">
    <h3>Page roles</h3>
    {_render_count_bars(_as_mapping(page_counts.get('role_counts')), max_items=12)}
  </div>
  <div class="panel">
    <h3>Image classes</h3>
    {_render_count_bars(_as_mapping(page_counts.get('image_class_counts')), max_items=12)}
  </div>
  <div class="panel">
    <h3>ATA distribution</h3>
    {_render_count_bars(_as_mapping(page_counts.get('ata_counts')), max_items=12)}
  </div>
  <div class="panel">
    <h3>Derived traits</h3>
    {_render_count_bars(_as_mapping(page_counts.get('derived_trait_counts')), max_items=12)}
  </div>
</div>

<div class="footer-note">
This is intentionally not a full force-directed graph of every assertion node. The focused views match how the system should query the graph: start from an entity, expand its parents/evidence/traits, and stop at source-backed evidence.
</div>
"""
    return _html_shell("HEICO TIFF graph visual overview", body)


def _page_grid_html(page_cards: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]) -> str:
    pages: list[dict[str, Any]] = []
    for card in sorted(page_cards, key=_extract_page_sort_key):
        context = _as_mapping(card.get("context"))
        parents = _as_mapping(card.get("parents"))
        signals = _as_mapping(card.get("signals"))
        source = _as_mapping(card.get("source"))
        pages.append(
            {
                "entity_id": card.get("entity_id"),
                "page_id": card.get("page_id") or card.get("entity_id"),
                "label": card.get("label") or card.get("page_id") or card.get("entity_id"),
                "ata_code": parents.get("ata_code") or "unknown",
                "document_label": parents.get("document_label") or "unknown",
                "page_role": context.get("page_role") or "unknown",
                "summary": context.get("summary") or "",
                "topics": _as_list(context.get("topics")),
                "image_classification": signals.get("image_classification") or "unknown",
                "ink_ratio": signals.get("ink_ratio"),
                "large_components": signals.get("large_components"),
                "empty_ocr": bool(signals.get("empty_ocr")),
                "parts": _as_list(card.get("parts")),
                "direct_traits": _as_list(card.get("direct_traits")),
                "derived_traits": _as_list(card.get("derived_traits")),
                "source": {
                    "source_url": source.get("source_url"),
                    "tiff_path": source.get("tiff_path"),
                    "ocr_path": source.get("ocr_path"),
                },
            }
        )

    role_counts = _as_mapping(_as_mapping(summary.get("page_counts")).get("role_counts"))
    legends = "".join(f'<span class="badge">{_escape(k)}: {_escape(v)}</span>' for k, v in role_counts.items())

    body = f"""
<div class="section panel">
<h2>509-page grid</h2>
<p class="footer-note">Each tile is a page character. Colors come from the context page role. Click a tile to inspect the page's parents, evidence, parts, visual signal, and derived traits.</p>
<div class="controls">
  <input id="searchBox" placeholder="Search page, part, topic, ATA, role...">
  <select id="ataFilter"><option value="">All ATA sections</option></select>
  <select id="roleFilter"><option value="">All page roles</option></select>
  <select id="derivedFilter"><option value="">All derived traits</option></select>
</div>
<div>{legends}</div>
</div>
<div id="pageGrid" class="page-grid section"></div>
<div id="details" class="panel details">Click a page tile to see its character sheet.</div>
<script type="application/json" id="page-data">{_json_for_html(pages)}</script>
<script>
const pages = JSON.parse(document.getElementById('page-data').textContent);
const grid = document.getElementById('pageGrid');
const details = document.getElementById('details');
const searchBox = document.getElementById('searchBox');
const ataFilter = document.getElementById('ataFilter');
const roleFilter = document.getElementById('roleFilter');
const derivedFilter = document.getElementById('derivedFilter');
function uniq(values) {{ return [...new Set(values.filter(Boolean))].sort(); }}
function optionize(select, values) {{ values.forEach(v => {{ const o = document.createElement('option'); o.value = v; o.textContent = v; select.appendChild(o); }}); }}
optionize(ataFilter, uniq(pages.map(p => p.ata_code)));
optionize(roleFilter, uniq(pages.map(p => p.page_role)));
optionize(derivedFilter, uniq(pages.flatMap(p => p.derived_traits || [])));
function roleClass(role) {{ return 'role-' + String(role || 'unknown').toLowerCase().replace(/[^a-z0-9]+/g, '-'); }}
function searchable(p) {{ return JSON.stringify(p).toLowerCase(); }}
function renderDetails(p) {{
  details.textContent =
`PAGE CHARACTER SHEET\n\n` +
`entity_id: ${{p.entity_id}}\n` +
`page_id: ${{p.page_id}}\n` +
`document: ${{p.document_label}}\n` +
`ata: ${{p.ata_code}}\n` +
`role: ${{p.page_role}}\n` +
`image_classification: ${{p.image_classification}}\n` +
`ink_ratio: ${{p.ink_ratio ?? ''}}\n` +
`large_components: ${{p.large_components ?? ''}}\n` +
`empty_ocr: ${{p.empty_ocr}}\n\n` +
`source_url: ${{p.source.source_url || ''}}\n` +
`tiff_path: ${{p.source.tiff_path || ''}}\n` +
`ocr_path: ${{p.source.ocr_path || ''}}\n\n` +
`parts: ${{(p.parts || []).join(', ')}}\n\n` +
`topics: ${{(p.topics || []).join(', ')}}\n\n` +
`derived_traits:\n  ${{(p.derived_traits || []).join('\n  ')}}\n\n` +
`direct_traits sample:\n  ${{(p.direct_traits || []).slice(0, 25).join('\n  ')}}\n\n` +
`summary:\n${{p.summary || ''}}`;
}}
function render() {{
  const q = searchBox.value.toLowerCase().trim();
  const ata = ataFilter.value;
  const role = roleFilter.value;
  const derived = derivedFilter.value;
  grid.innerHTML = '';
  let shown = 0;
  for (const p of pages) {{
    if (ata && p.ata_code !== ata) continue;
    if (role && p.page_role !== role) continue;
    if (derived && !(p.derived_traits || []).includes(derived)) continue;
    if (q && !searchable(p).includes(q)) continue;
    shown += 1;
    const div = document.createElement('div');
    div.className = 'page-tile ' + roleClass(p.page_role);
    div.innerHTML = `<div class="page-num">${{p.page_id}}</div><div class="page-role">${{p.page_role}}</div><div class="page-meta">${{p.ata_code}} · parts:${{(p.parts || []).length}}</div>`;
    div.title = `${{p.page_id}} | ${{p.page_role}} | ${{p.image_classification}}`;
    div.onclick = () => renderDetails(p);
    grid.appendChild(div);
  }}
  if (!shown) grid.innerHTML = '<div class="footer-note">No pages match the current filters.</div>';
}}
for (const el of [searchBox, ataFilter, roleFilter, derivedFilter]) el.addEventListener('input', render);
render();
if (pages.length) renderDetails(pages[0]);
</script>
"""
    return _html_shell("HEICO TIFF 509-page grid", body)


def _trait_overlay_html(assertions: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]) -> str:
    assertion_counts = _as_mapping(summary.get("assertion_counts"))
    trait_overlay = _as_mapping(summary.get("trait_overlay"))
    body = f"""
<div class="grid">
{_stat_card('assertions', trait_overlay.get('assertions', len(assertions)), 'Entity -> Assertion -> Trait')}
{_stat_card('trait nodes', trait_overlay.get('trait_nodes', 0), 'deduped reusable traits')}
{_stat_card('evidence sources', trait_overlay.get('evidence_source_nodes', 0), 'where traits came from')}
{_stat_card('derived assertions', trait_overlay.get('derived_assertions', 0), 'combo/game-effect traits')}
</div>

<div class="section grid">
  <div class="panel"><h3>Assertions by trait type</h3>{_render_count_bars(_as_mapping(assertion_counts.get('trait_type_counts')), max_items=20)}</div>
  <div class="panel"><h3>Assertions by scope</h3>{_render_count_bars(_as_mapping(assertion_counts.get('scope_counts')), max_items=20)}</div>
  <div class="panel"><h3>Assertions by entity type</h3>{_render_count_bars(_as_mapping(assertion_counts.get('entity_type_counts')), max_items=20)}</div>
  <div class="panel"><h3>Top trait keys</h3>{_render_count_bars(_as_mapping(assertion_counts.get('trait_key_counts')), max_items=25)}</div>
</div>

<div class="section panel">
<h2>Top individual traits</h2>
{_render_count_bars(_as_mapping(assertion_counts.get('top_traits')), max_items=50)}
</div>

<div class="footer-note">
The trait overlay is a game-style character system: traits attach to entities through assertion nodes, and assertion nodes keep source/method/evidence metadata.
</div>
"""
    return _html_shell("HEICO TIFF trait overlay", body)


def _sample_page_cards(page_cards: Sequence[Mapping[str, Any]], sample_limit: int) -> list[Mapping[str, Any]]:
    if sample_limit <= 0:
        return []
    sorted_cards = sorted(page_cards, key=_extract_page_sort_key)
    # Prefer a diverse sample across roles and ATA sections.
    selected: list[Mapping[str, Any]] = []
    seen_roles: set[str] = set()
    seen_ata: set[str] = set()
    for card in sorted_cards:
        context = _as_mapping(card.get("context"))
        parents = _as_mapping(card.get("parents"))
        role = _text(context.get("page_role"), "unknown")
        ata = _text(parents.get("ata_code"), "unknown")
        if role not in seen_roles or ata not in seen_ata:
            selected.append(card)
            seen_roles.add(role)
            seen_ata.add(ata)
        if len(selected) >= sample_limit:
            return selected
    for card in sorted_cards:
        if card not in selected:
            selected.append(card)
        if len(selected) >= sample_limit:
            break
    return selected


def _neighborhoods_html(page_cards: Sequence[Mapping[str, Any]], sample_limit: int) -> str:
    cards = _sample_page_cards(page_cards, sample_limit)
    chunks: list[str] = []
    for card in cards:
        parents = _as_mapping(card.get("parents"))
        context = _as_mapping(card.get("context"))
        source = _as_mapping(card.get("source"))
        signals = _as_mapping(card.get("signals"))
        parts = _as_list(card.get("parts"))[:12]
        derived = _as_list(card.get("derived_traits"))[:12]
        direct = _as_list(card.get("direct_traits"))[:12]
        chunks.append(
            '<div class="network-card">'
            f'<div class="network-title">{_escape(card.get("page_id") or card.get("entity_id"))} · {_escape(context.get("page_role") or "unknown")}</div>'
            '<div class="network-lanes">'
            '<div><div class="lane-title">Parents</div>'
            f'<div class="node-pill">Document<br>{_escape(parents.get("document_label") or parents.get("document_id") or "unknown")}</div>'
            f'<div class="node-pill">ATA<br>{_escape(parents.get("ata_code") or parents.get("ata_id") or "unknown")}</div>'
            '</div>'
            '<div><div class="lane-title">Page</div>'
            f'<div class="node-pill page">{_escape(card.get("entity_id"))}<br>{_escape(card.get("label") or "")}</div>'
            f'<div class="node-pill page">image: {_escape(signals.get("image_classification") or "unknown")}<br>ink: {_escape(signals.get("ink_ratio") or "")}</div>'
            '</div>'
            '<div><div class="lane-title">Evidence</div>'
            f'<div class="node-pill source">source<br>{_escape(_shorten(source.get("source_url"), 80))}</div>'
            f'<div class="node-pill source">TIFF<br>{_escape(_shorten(source.get("tiff_path"), 80))}</div>'
            f'<div class="node-pill source">OCR<br>{_escape(_shorten(source.get("ocr_path"), 80))}</div>'
            '</div>'
            '<div><div class="lane-title">Parts / context</div>'
            + ''.join(f'<div class="node-pill part">part<br>{_escape(part)}</div>' for part in parts)
            + (f'<div class="node-pill context">summary<br>{_escape(_shorten(context.get("summary"), 130))}</div>' if context.get("summary") else '')
            + '</div>'
            '<div><div class="lane-title">Traits</div>'
            + ''.join(f'<div class="node-pill trait">{_escape(trait)}</div>' for trait in derived)
            + ''.join(f'<div class="node-pill trait">{_escape(trait)}</div>' for trait in direct[: max(0, 12 - len(derived))])
            + '</div>'
            '</div></div>'
        )
    body = """
<div class="section panel">
<h2>Focused page neighborhoods</h2>
<p class="footer-note">This is the graph style you want for debugging and demos: one page at the center, parents to the left, evidence and traits to the right.</p>
</div>
<div class="neighborhood">
""" + "\n".join(chunks) + "\n</div>"
    return _html_shell("HEICO TIFF sample graph neighborhoods", body)


def export_graph_visualizations(
    graph_dir: str | Path = DEFAULT_GRAPH_DIR,
    trait_dir: str | Path = DEFAULT_ENTITY_TRAIT_DIR,
    output_dir: str | Path = DEFAULT_VISUALIZATION_DIR,
    *,
    sample_limit: int = 10,
) -> GraphVisualizationResult:
    """Write local HTML visualizations for the graph and trait overlay."""

    nodes, edges = _load_graph_artifacts(graph_dir)
    page_cards, part_cards, assertions, trait_summary = _load_trait_artifacts(trait_dir)
    warnings: list[str] = []

    if not nodes:
        warnings.append(f"No graph nodes found at {Path(graph_dir) / GRAPH_NODES_FILE}")
    if not edges:
        warnings.append(f"No graph edges found at {Path(graph_dir) / GRAPH_EDGES_FILE}")
    if not page_cards:
        warnings.append(f"No page character cards found at {Path(trait_dir) / PAGE_CARDS_FILE}; using graph fallback")
        page_cards = _fallback_page_cards_from_graph(nodes, edges)
    if not assertions:
        warnings.append(f"No trait assertions found at {Path(trait_dir) / ENTITY_TRAITS_FILE}")

    page_cards = sorted(page_cards, key=_extract_page_sort_key)
    summary = _make_summary(graph_dir, trait_dir, nodes, edges, page_cards, part_cards, assertions, trait_summary)
    status = "ok" if page_cards else "needs_attention"
    summary["status"] = status
    summary["warnings"] = warnings

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    files = {
        "index": str(_write_text(root / "index.html", _index_html(summary))),
        "page_grid": str(_write_text(root / "page_grid.html", _page_grid_html(page_cards, summary))),
        "trait_overlay": str(_write_text(root / "trait_overlay.html", _trait_overlay_html(assertions, summary))),
        "neighborhoods": str(_write_text(root / "neighborhoods.html", _neighborhoods_html(page_cards, sample_limit))),
        "summary_json": str(_write_json(root / VISUALIZATION_SUMMARY_FILE, summary)),
    }

    return GraphVisualizationResult(
        status=status,
        output_dir=str(root),
        files=files,
        summary=summary,
        warnings=warnings,
    )


def format_graph_visualization_result(result: GraphVisualizationResult) -> str:
    """Return a terminal-friendly summary for CLI use."""

    corpus = _as_mapping(result.summary.get("processed_corpus"))
    graph = _as_mapping(result.summary.get("graph"))
    trait = _as_mapping(result.summary.get("trait_overlay"))
    page_counts = _as_mapping(result.summary.get("page_counts"))

    lines = [
        "Current graph visualizations",
        f"  Status: {result.status.upper()}",
        f"  Output dir: {result.output_dir}",
        "  Processed corpus:",
        f"    documents: {corpus.get('documents', 0)}",
        f"    ata_sections: {corpus.get('ata_sections', 0)}",
        f"    pages: {corpus.get('pages', 0)}",
        f"    parts: {corpus.get('parts', 0)}",
        f"    page_context_nodes: {corpus.get('page_context_nodes', 0)}",
        f"    source_link_nodes: {corpus.get('source_link_nodes', 0)}",
        "  Core graph:",
        f"    nodes: {graph.get('node_count', 0)}",
        f"    edges: {graph.get('edge_count', 0)}",
        "  Entity-trait overlay:",
        f"    assertions: {trait.get('assertions', 0)}",
        f"    trait_nodes: {trait.get('trait_nodes', 0)}",
        f"    derived_assertions: {trait.get('derived_assertions', 0)}",
        f"    page_cards: {trait.get('page_cards', 0)}",
        f"    part_cards: {trait.get('part_cards', 0)}",
        "  Page roles:",
    ]
    for role, count in _as_mapping(page_counts.get("role_counts")).items():
        lines.append(f"    {role}: {count}")

    if result.warnings:
        lines.append("  Warnings:")
        for warning in result.warnings:
            lines.append(f"    {warning}")

    lines.append("  Files written:")
    for label, path in result.files.items():
        lines.append(f"    {label}: {path}")
    return "\n".join(lines)
