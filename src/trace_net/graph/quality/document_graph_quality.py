"""Quality checks for the document organization graph.

This module is intentionally file-based and read-only. It validates the graph
JSON artifacts produced by ``scripts/build/graph/export_document_organization_graph.py`` and
optionally folds in page-context and user-query regression results.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import re
from typing import Any, Iterable, Mapping

DEFAULT_GRAPH_DIR = "local_data/organization/graph"
DEFAULT_CONTEXT_FILE = "local_data/organization/context/page_contexts.json"
DEFAULT_USER_QUERY_RESULTS = "local_data/evals/user_query/user_query_test_results.json"
DEFAULT_REALISTIC_QUERY_TRACE_RESULTS = "local_data/evals/realistic_query_trace/realistic_query_trace_results.json"
DEFAULT_GRAPH_QUALITY_JSON = "local_data/organization/graph/graph_quality.json"


@dataclass(frozen=True)
class GraphQualityThresholds:
    """Thresholds for graph and context coverage checks."""

    min_pages: int = 1
    min_parts: int = 1
    min_source_links: int = 1
    max_pages_without_context: int = 0
    max_pages_without_source_links: int = 0
    max_pages_without_document: int = 0
    max_pages_without_ata: int = 0
    max_context_generation_errors: int = 0
    allow_empty_ocr_contexts: bool = True
    require_user_query_tests: bool = False
    require_realistic_query_trace_tests: bool = False
    require_slow_realistic_query_trace: bool = False


@dataclass(frozen=True)
class GraphQualityCheck:
    name: str
    status: str
    message: str


@dataclass(frozen=True)
class GraphQualityResult:
    status: str
    summary: dict[str, Any]
    checks: list[GraphQualityCheck] = field(default_factory=list)


def _load_json(path: str | Path) -> Any:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _as_list(payload: Any, *keys: str) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, Mapping):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _node_id(node: Mapping[str, Any]) -> str:
    return str(node.get("id") or node.get("node_id") or node.get("key") or "")


def _node_type(node: Mapping[str, Any]) -> str:
    return str(node.get("type") or node.get("node_type") or node.get("kind") or "").strip().lower()


def _node_label(node: Mapping[str, Any]) -> str:
    props = _as_mapping(node.get("properties"))
    for source in (node, props):
        for key in ("label", "name", "title", "part_number", "page_id", "summary", "short_summary"):
            value = source.get(key)
            if value:
                return str(value)
    return _node_id(node)


def _edge_type(edge: Mapping[str, Any]) -> str:
    return str(edge.get("type") or edge.get("edge_type") or edge.get("relationship") or "").strip().upper()


def _edge_source(edge: Mapping[str, Any]) -> str:
    return str(edge.get("source") or edge.get("from") or edge.get("from_id") or edge.get("src") or "")


def _edge_target(edge: Mapping[str, Any]) -> str:
    return str(edge.get("target") or edge.get("to") or edge.get("to_id") or edge.get("dst") or "")


def _prop(mapping: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    props = _as_mapping(mapping.get("properties"))
    for source in (mapping, props):
        for key in keys:
            if key in source and source.get(key) not in (None, ""):
                return source.get(key)
    return default


def _normalize_part(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")


def _normalize_page(value: str) -> str:
    value = str(value).strip()
    if value.startswith("page:"):
        return value
    return f"page:{value}"


def _add_check(checks: list[GraphQualityCheck], name: str, ok: bool, message: str) -> None:
    checks.append(GraphQualityCheck(name=name, status="OK" if ok else "FAIL", message=message))


class GraphIndex:
    """Small in-memory graph index for quality checks."""

    def __init__(self, nodes: Iterable[Mapping[str, Any]], edges: Iterable[Mapping[str, Any]]) -> None:
        self.nodes = [dict(n) for n in nodes]
        self.edges = [dict(e) for e in edges]
        self.node_by_id = {_node_id(n): n for n in self.nodes if _node_id(n)}
        self.out_edges: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        self.in_edges: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for edge in self.edges:
            src = _edge_source(edge)
            dst = _edge_target(edge)
            if src:
                self.out_edges[src].append(edge)
            if dst:
                self.in_edges[dst].append(edge)

    def neighbors(self, node_id: str, edge_type: str) -> list[Mapping[str, Any]]:
        etype = edge_type.upper()
        found = []
        for edge in self.out_edges.get(node_id, []):
            if _edge_type(edge) == etype:
                node = self.node_by_id.get(_edge_target(edge))
                if node is not None:
                    found.append(node)
        return found

    def nodes_of_type(self, node_type: str) -> list[Mapping[str, Any]]:
        target = node_type.lower()
        return [node for node in self.nodes if _node_type(node) == target]

    def find_part(self, part_number: str) -> Mapping[str, Any] | None:
        norm = _normalize_part(part_number)
        for node in self.nodes_of_type("part"):
            label = _node_label(node)
            part_value = str(_prop(node, "part_number", "part", default=label))
            if _normalize_part(part_value) == norm or _node_id(node).upper().endswith(norm):
                return node
        return None

    def find_page(self, page_id: str) -> Mapping[str, Any] | None:
        wanted = _normalize_page(page_id)
        if wanted in self.node_by_id:
            return self.node_by_id[wanted]
        raw = page_id.replace("page:", "")
        for node in self.nodes_of_type("page"):
            if _node_id(node) == wanted or _prop(node, "page_id", default="") == raw:
                return node
        return None


def load_graph(graph_dir: str | Path = DEFAULT_GRAPH_DIR) -> GraphIndex:
    """Load graph_nodes.json and graph_edges.json from a graph directory."""
    root = Path(graph_dir)
    nodes_payload = _load_json(root / "graph_nodes.json")
    edges_payload = _load_json(root / "graph_edges.json")
    nodes = _as_list(nodes_payload, "nodes", "graph_nodes")
    edges = _as_list(edges_payload, "edges", "graph_edges")
    return GraphIndex(nodes, edges)


def _context_records(path: str | Path = DEFAULT_CONTEXT_FILE) -> list[Mapping[str, Any]]:
    payload = _load_json(path)
    return [c for c in _as_list(payload, "contexts", "page_contexts") if isinstance(c, Mapping)]


def _user_query_counts(path: str | Path = DEFAULT_USER_QUERY_RESULTS) -> dict[str, Any]:
    payload = _load_json(path)
    if not isinstance(payload, Mapping):
        return {"present": False, "total": 0, "pass": 0, "fail": 0}
    # Current script writes either top-level results or cases.
    cases = _as_list(payload, "results", "cases", "test_results")
    if not cases and isinstance(payload.get("status_counts"), Mapping):
        counts = _as_mapping(payload.get("status_counts"))
        total = sum(_as_int(v) for v in counts.values())
        return {
            "present": True,
            "total": total,
            "pass": _as_int(counts.get("pass")),
            "fail": total - _as_int(counts.get("pass")),
            "status_counts": dict(counts),
        }
    counts = Counter()
    for case in cases:
        if isinstance(case, Mapping):
            counts[str(case.get("status") or "unknown").lower()] += 1
    total = sum(counts.values())
    return {
        "present": True,
        "total": total,
        "pass": counts.get("pass", 0),
        "fail": total - counts.get("pass", 0),
        "status_counts": dict(counts),
    }


def _realistic_query_counts(path: str | Path = DEFAULT_REALISTIC_QUERY_TRACE_RESULTS) -> dict[str, Any]:
    """Summarize realistic prompt-to-graph trace test results.

    The realistic trace runner writes a payload shaped like::

        {"summary": {...}, "results": [...]}

    Keep this parser tolerant so older/hand-written result files can still be
    used by the quality gate.
    """
    payload = _load_json(path)
    if not isinstance(payload, Mapping):
        return {
            "present": False,
            "total": 0,
            "pass": 0,
            "fail": 0,
            "check_total": 0,
            "check_pass": 0,
            "check_fail": 0,
            "slow_cases": 0,
            "status_counts": {},
        }

    summary = _as_mapping(payload.get("summary"))
    results = _as_list(payload, "results", "cases", "test_results")

    if summary:
        total = _as_int(summary.get("total"), default=len(results))
        passed = _as_int(summary.get("pass"))
        failed = _as_int(summary.get("fail"))
        check_total = _as_int(summary.get("check_total"))
        check_pass = _as_int(summary.get("check_pass"))
        check_fail = _as_int(summary.get("check_fail"))
        status_counts = dict(_as_mapping(summary.get("status_counts")))
    else:
        counts = Counter()
        check_total = 0
        check_pass = 0
        for result in results:
            if not isinstance(result, Mapping):
                continue
            status = str(result.get("status") or "unknown").lower()
            counts[status] += 1
            for check in _as_list(result, "checks"):
                if isinstance(check, Mapping):
                    check_total += 1
                    if str(check.get("status") or "").lower() == "pass":
                        check_pass += 1
        total = sum(counts.values())
        passed = counts.get("pass", 0)
        failed = total - passed
        check_fail = check_total - check_pass
        status_counts = dict(counts)

    slow_cases = 0
    for result in results:
        if not isinstance(result, Mapping):
            continue
        case_id = str(result.get("id") or "").lower()
        category = str(result.get("category") or "").lower()
        if case_id.startswith("slow_") or "slow" in category:
            slow_cases += 1

    return {
        "present": True,
        "total": total,
        "pass": passed,
        "fail": failed,
        "check_total": check_total,
        "check_pass": check_pass,
        "check_fail": check_fail,
        "slow_cases": slow_cases,
        "status_counts": status_counts,
    }


def _count_pages_missing(graph: GraphIndex, edge_type: str) -> int:
    missing = 0
    etype = edge_type.upper()
    for page in graph.nodes_of_type("page"):
        page_id = _node_id(page)
        if not any(_edge_type(e) == etype for e in graph.out_edges.get(page_id, [])):
            missing += 1
    return missing


def _sample_part_trace_ok(graph: GraphIndex, sample_part: str = "120-37313-001") -> bool:
    part = graph.find_part(sample_part)
    if not part:
        # If the known sample is not present, fall back to any part with source/context on a page.
        parts = graph.nodes_of_type("part")
        part = parts[0] if parts else None
    if not part:
        return False
    pages = graph.neighbors(_node_id(part), "APPEARS_ON")
    if not pages:
        # Some graphs only expose mentions through HAS_MENTION -> FOUND_ON.
        for mention in graph.neighbors(_node_id(part), "HAS_MENTION"):
            pages.extend(graph.neighbors(_node_id(mention), "FOUND_ON"))
    if not pages:
        return False
    sampled = pages[:8]
    return all(graph.neighbors(_node_id(page), "HAS_SOURCE_LINK") and graph.neighbors(_node_id(page), "HAS_CONTEXT") for page in sampled)


def _sample_page_trace_ok(graph: GraphIndex, sample_page: str = "t_p_120_1176_p000083") -> bool:
    page = graph.find_page(sample_page)
    if not page:
        pages = graph.nodes_of_type("page")
        page = pages[0] if pages else None
    if not page:
        return False
    page_id = _node_id(page)
    return bool(
        graph.neighbors(page_id, "BELONGS_TO_DOCUMENT")
        and graph.neighbors(page_id, "BELONGS_TO_ATA")
        and graph.neighbors(page_id, "HAS_SOURCE_LINK")
        and graph.neighbors(page_id, "HAS_CONTEXT")
    )


def _sample_vector_resolution_ok(graph: GraphIndex, sample_page: str = "t_p_120_1176_p000495") -> bool:
    page = graph.find_page(sample_page)
    if not page:
        pages = graph.nodes_of_type("page")
        page = pages[0] if pages else None
    if not page:
        return False
    page_id = _node_id(page)
    return bool(
        graph.neighbors(page_id, "BELONGS_TO_DOCUMENT")
        and graph.neighbors(page_id, "HAS_SOURCE_LINK")
        and graph.neighbors(page_id, "HAS_CONTEXT")
    )


def build_graph_quality_result(
    *,
    graph_dir: str | Path = DEFAULT_GRAPH_DIR,
    context_file: str | Path = DEFAULT_CONTEXT_FILE,
    user_query_results: str | Path = DEFAULT_USER_QUERY_RESULTS,
    realistic_query_results: str | Path = DEFAULT_REALISTIC_QUERY_TRACE_RESULTS,
    thresholds: GraphQualityThresholds | None = None,
) -> GraphQualityResult:
    """Build graph quality checks from current graph/context/user-query artifacts."""
    limits = thresholds or GraphQualityThresholds()
    graph_root = Path(graph_dir)
    nodes_path = graph_root / "graph_nodes.json"
    edges_path = graph_root / "graph_edges.json"
    graph_present = nodes_path.exists() and edges_path.exists()

    graph = load_graph(graph_dir) if graph_present else GraphIndex([], [])
    node_counts = Counter(_node_type(n) for n in graph.nodes)
    edge_counts = Counter(_edge_type(e) for e in graph.edges)
    page_nodes = node_counts.get("page", 0)
    source_links = node_counts.get("source_link", 0)
    page_context_nodes = node_counts.get("page_context", 0)
    part_nodes = node_counts.get("part", 0)
    pages_without_context = _count_pages_missing(graph, "HAS_CONTEXT") if graph_present else 0
    pages_without_source_links = _count_pages_missing(graph, "HAS_SOURCE_LINK") if graph_present else 0
    pages_without_document = _count_pages_missing(graph, "BELONGS_TO_DOCUMENT") if graph_present else 0
    pages_without_ata = _count_pages_missing(graph, "BELONGS_TO_ATA") if graph_present else 0

    contexts = _context_records(context_file)
    context_records = len(contexts)
    empty_ocr_contexts = 0
    context_generation_errors = 0
    for context in contexts:
        role = str(_prop(context, "role", "page_role", default="")).lower()
        warnings = _as_list(context.get("warnings"), "warnings") if isinstance(context.get("warnings"), (list, dict)) else []
        errors = _as_list(context.get("errors"), "errors") if isinstance(context.get("errors"), (list, dict)) else []
        # The current generator represents empty OCR as a blank low-confidence context.
        # Treat those as expected review items, not model-generation errors.
        message_blob = " ".join(str(x).lower() for x in list(warnings) + list(errors))
        if role == "blank" and ("empty ocr" in message_blob or "ocr" in message_blob or not errors):
            empty_ocr_contexts += 1
        elif warnings or errors:
            context_generation_errors += 1

    user_counts = _user_query_counts(user_query_results)
    realistic_counts = _realistic_query_counts(realistic_query_results)

    part_trace_ok = _sample_part_trace_ok(graph) if graph_present else False
    page_trace_ok = _sample_page_trace_ok(graph) if graph_present else False
    vector_trace_ok = _sample_vector_resolution_ok(graph) if graph_present else False

    checks: list[GraphQualityCheck] = []
    _add_check(
        checks,
        "graph_artifacts_present",
        graph_present,
        f"Graph artifacts are present in {graph_root}." if graph_present else f"Missing graph_nodes.json or graph_edges.json in {graph_root}.",
    )
    _add_check(checks, "graph_page_nodes", page_nodes >= limits.min_pages, f"Page nodes={page_nodes}; minimum is {limits.min_pages}.")
    _add_check(checks, "graph_part_nodes", part_nodes >= limits.min_parts, f"Part nodes={part_nodes}; minimum is {limits.min_parts}.")
    _add_check(checks, "graph_source_links", source_links >= limits.min_source_links, f"Source-link nodes={source_links}; minimum is {limits.min_source_links}.")
    _add_check(
        checks,
        "graph_source_link_coverage",
        pages_without_source_links <= limits.max_pages_without_source_links,
        f"Pages without source links={pages_without_source_links}; max allowed is {limits.max_pages_without_source_links}.",
    )
    _add_check(
        checks,
        "graph_document_coverage",
        pages_without_document <= limits.max_pages_without_document,
        f"Pages without document edges={pages_without_document}; max allowed is {limits.max_pages_without_document}.",
    )
    _add_check(
        checks,
        "graph_ata_coverage",
        pages_without_ata <= limits.max_pages_without_ata,
        f"Pages without ATA edges={pages_without_ata}; max allowed is {limits.max_pages_without_ata}.",
    )
    _add_check(
        checks,
        "graph_context_coverage",
        page_context_nodes >= page_nodes and pages_without_context <= limits.max_pages_without_context,
        f"Page context nodes={page_context_nodes}, page nodes={page_nodes}, pages without context={pages_without_context}; max missing context is {limits.max_pages_without_context}.",
    )
    _add_check(
        checks,
        "page_context_records",
        context_records >= page_nodes,
        f"Page-context records={context_records}, page nodes={page_nodes}.",
    )
    _add_check(
        checks,
        "page_context_generation_errors",
        context_generation_errors <= limits.max_context_generation_errors,
        f"Page-context generation errors={context_generation_errors}; empty OCR contexts={empty_ocr_contexts}. Empty OCR contexts are {'allowed' if limits.allow_empty_ocr_contexts else 'not allowed'}.",
    )
    _add_check(
        checks,
        "part_traceability_sample",
        part_trace_ok,
        "Sample part traces to source-linked pages with AI context." if part_trace_ok else "Sample part did not trace cleanly to pages/source links/context.",
    )
    _add_check(
        checks,
        "page_traceability_sample",
        page_trace_ok,
        "Sample page traces to document, ATA, source link, and AI context." if page_trace_ok else "Sample page trace is incomplete.",
    )
    _add_check(
        checks,
        "vector_payload_traceability_sample",
        vector_trace_ok,
        "Simulated Qdrant page_id payload resolves to graph document/source/context." if vector_trace_ok else "Simulated vector payload could not resolve to full graph context.",
    )
    user_query_ok = bool(user_counts.get("present")) and _as_int(user_counts.get("fail")) == 0 and _as_int(user_counts.get("total")) > 0
    _add_check(
        checks,
        "user_query_regression_results",
        user_query_ok or not limits.require_user_query_tests,
        (
            f"User-query regression results pass: total={user_counts.get('total')}, pass={user_counts.get('pass')}, fail={user_counts.get('fail')}."
            if user_query_ok
            else "User-query regression results are missing or not all passing. Run scripts/operations/ingestion/run_user_query_tests.py --config local_config.yaml --write-json."
        ),
    )

    realistic_present = bool(realistic_counts.get("present"))
    realistic_fail = _as_int(realistic_counts.get("fail"))
    realistic_check_fail = _as_int(realistic_counts.get("check_fail"))
    realistic_total = _as_int(realistic_counts.get("total"))
    realistic_check_total = _as_int(realistic_counts.get("check_total"))
    realistic_slow_cases = _as_int(realistic_counts.get("slow_cases"))
    realistic_ok = realistic_present and realistic_total > 0 and realistic_fail == 0 and realistic_check_fail == 0
    _add_check(
        checks,
        "realistic_query_trace_results",
        realistic_ok or not limits.require_realistic_query_trace_tests,
        (
            f"Realistic query trace results pass: cases={realistic_total}, failed_cases={realistic_fail}, checks={realistic_check_total}, failed_checks={realistic_check_fail}, slow_cases={realistic_slow_cases}."
            if realistic_ok
            else "Realistic query trace results are missing or not all passing. Run scripts/operations/ingestion/run_realistic_query_trace_tests.py --config local_config.yaml --include-slow --write-json."
        ),
    )
    _add_check(
        checks,
        "realistic_query_trace_slow_case",
        realistic_slow_cases > 0 or not limits.require_slow_realistic_query_trace,
        f"Realistic query trace slow cases included: {realistic_slow_cases}."
        if realistic_slow_cases > 0
        else "Slow realistic query trace case is required but was not present; rerun with --include-slow.",
    )

    status = "ok" if all(c.status == "OK" for c in checks) else "fail"
    summary = {
        "graph_present": graph_present,
        "graph_dir": str(graph_root),
        "nodes_total": len(graph.nodes),
        "edges_total": len(graph.edges),
        "page_nodes": page_nodes,
        "part_nodes": part_nodes,
        "source_link_nodes": source_links,
        "page_context_nodes": page_context_nodes,
        "topic_nodes": node_counts.get("topic", 0),
        "has_context_edges": edge_counts.get("HAS_CONTEXT", 0),
        "has_source_link_edges": edge_counts.get("HAS_SOURCE_LINK", 0),
        "tagged_as_edges": edge_counts.get("TAGGED_AS", 0),
        "highlights_part_edges": edge_counts.get("HIGHLIGHTS_PART", 0),
        "pages_without_context": pages_without_context,
        "pages_without_source_links": pages_without_source_links,
        "pages_without_document": pages_without_document,
        "pages_without_ata": pages_without_ata,
        "context_records": context_records,
        "empty_ocr_contexts": empty_ocr_contexts,
        "context_generation_errors": context_generation_errors,
        "part_traceability_sample_ok": part_trace_ok,
        "page_traceability_sample_ok": page_trace_ok,
        "vector_payload_traceability_sample_ok": vector_trace_ok,
        "user_query_results_present": bool(user_counts.get("present")),
        "user_query_total": user_counts.get("total", 0),
        "user_query_pass": user_counts.get("pass", 0),
        "user_query_fail": user_counts.get("fail", 0),
        "realistic_query_results_present": bool(realistic_counts.get("present")),
        "realistic_query_total": realistic_counts.get("total", 0),
        "realistic_query_pass": realistic_counts.get("pass", 0),
        "realistic_query_fail": realistic_counts.get("fail", 0),
        "realistic_query_check_total": realistic_counts.get("check_total", 0),
        "realistic_query_check_pass": realistic_counts.get("check_pass", 0),
        "realistic_query_check_fail": realistic_counts.get("check_fail", 0),
        "realistic_query_slow_cases": realistic_counts.get("slow_cases", 0),
    }
    return GraphQualityResult(status=status, summary=summary, checks=checks)


def graph_quality_result_to_dict(result: GraphQualityResult) -> dict[str, Any]:
    return asdict(result)


def write_graph_quality_json(result: GraphQualityResult, path: str | Path = DEFAULT_GRAPH_QUALITY_JSON) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(graph_quality_result_to_dict(result), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def format_graph_quality_result(result: GraphQualityResult) -> str:
    lines = [
        "Document graph quality gate",
        f"  Status: {result.status.upper()}",
        "  Summary:",
    ]
    for key, value in result.summary.items():
        lines.append(f"    {key}: {value}")
    lines.append("  Checks:")
    for check in result.checks:
        lines.append(f"    {check.status} {check.name}: {check.message}")
    return "\n".join(lines)
