from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Mapping, Iterable
import json
import re
from collections import Counter, defaultdict

DEFAULT_EXPORT_DIR = Path("local_data/organization/export")
DEFAULT_CONTEXT_FILE = Path("local_data/organization/context/page_contexts.json")
DEFAULT_GRAPH_SUMMARY = Path("local_data/organization/graph/graph_summary.json")
DEFAULT_OUTPUT = Path("local_data/organization/page_visual_objects_audit.json")

FIGURE_RE = re.compile(r"\b(?:FIG(?:URE)?\.?|FIGS?\.?)[\s:-]*([0-9]+[A-Z]?)?", re.IGNORECASE)
SHEET_RE = re.compile(r"\bSHEET\s+([0-9]+(?:\s+OF\s+[0-9]+)?)\b", re.IGNORECASE)
TABLE_RE = re.compile(r"\b(?:TABLE|TAB\.)\s*([0-9]+[A-Z]?)?\b", re.IGNORECASE)
ILLUSTRATION_RE = re.compile(r"\b(?:ILLUSTRATION|ILLUSTRATED|ILLUS\.)\b", re.IGNORECASE)
IMAGE_RE = re.compile(r"\b(?:DIAGRAM|DRAWING|SCHEMATIC|VIEW|PHOTO|PICTURE|IMAGE)\b", re.IGNORECASE)
PART_RE = re.compile(r"\b(?:[A-Z]{1,3}\d{3,6}(?:[-/][A-Z0-9]+)+|\d{3}-\d{4,6}-\d{2,3}|\d{3}-\d{5}-\d{2,3}|\d{4,6}-[A-Z0-9]{1,4})\b", re.IGNORECASE)

VISUAL_ROLES = {"figure", "table", "parts_list"}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _as_list_payload(data: Any, keys: Iterable[str]) -> list[Mapping[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, Mapping)]
    if isinstance(data, Mapping):
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, Mapping)]
        # Sometimes exported files are dicts keyed by id.
        if all(isinstance(v, Mapping) for v in data.values()):
            return [v for v in data.values() if isinstance(v, Mapping)]
    return []


def _first_nonempty(data: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _normalize_page_id(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.startswith("page:"):
        text = text.split(":", 1)[1]
    return text


def _repo_path(path_like: Any, repo_root: Path | None = None) -> Path | None:
    if path_like in (None, ""):
        return None
    text = str(path_like)
    if text.startswith("file:///"):
        # Keep this simple and Windows-safe. pathlib can usually handle the raw path after file:///.
        text = text[8:]
        if re.match(r"^[A-Za-z]:/", text):
            return Path(text)
    path = Path(text)
    if not path.is_absolute() and repo_root is not None:
        path = repo_root / path
    return path


def _visible_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\x00", " ")).strip()


def _read_text_file(path: Path | None) -> tuple[str, str | None]:
    if path is None:
        return "", "missing_ocr_path"
    if not path.exists():
        return "", "missing_ocr_file"
    try:
        return path.read_text(encoding="utf-8", errors="replace"), None
    except OSError as exc:
        return "", f"unreadable_ocr_file: {exc}"


def _count_matches(pattern: re.Pattern[str], text: str) -> int:
    return len(pattern.findall(text or ""))


def _sample_matches(pattern: re.Pattern[str], text: str, limit: int = 5) -> list[str]:
    out: list[str] = []
    for match in pattern.finditer(text or ""):
        sample = match.group(0).strip()
        if sample and sample not in out:
            out.append(sample)
        if len(out) >= limit:
            break
    return out


def _normalize_role(role: Any) -> str:
    text = str(role or "unknown").strip().lower().replace(" ", "_")
    return text or "unknown"


def load_page_records(export_dir: Path) -> list[dict[str, Any]]:
    page_index_path = export_dir / "page_index.json"
    if not page_index_path.exists():
        raise FileNotFoundError(f"page_index.json not found in {export_dir}")
    data = _read_json(page_index_path)
    pages = _as_list_payload(data, ("pages", "page_index", "items", "records"))
    records: list[dict[str, Any]] = []
    for raw in pages:
        page_id = _normalize_page_id(_first_nonempty(raw, "page_id", "id", "page", "node_id"))
        if not page_id:
            continue
        records.append({
            "page_id": page_id,
            "manual": _first_nonempty(raw, "manual_title", "manual", "document_title", "document"),
            "ata_code": _first_nonempty(raw, "ata_code", "ata", "section"),
            "page_label": _first_nonempty(raw, "page_label", "label", "display_page", "page_number"),
            "source_url": _first_nonempty(raw, "source_url", "rescarta_url", "source"),
            "tiff_path": _first_nonempty(raw, "source_image_path", "tiff_path", "image_path", "source_tiff_path"),
            "ocr_path": _first_nonempty(raw, "ocr_text_path", "ocr_path", "source_ocr_path"),
            "raw": raw,
        })
    return records


def load_page_contexts(context_file: Path) -> dict[str, dict[str, Any]]:
    if not context_file.exists():
        return {}
    data = _read_json(context_file)
    contexts = _as_list_payload(data, ("contexts", "page_contexts", "items", "records"))
    by_page: dict[str, dict[str, Any]] = {}
    for raw in contexts:
        page_id = _normalize_page_id(_first_nonempty(raw, "page_id", "page", "source_page", "id"))
        if not page_id:
            context_id = _first_nonempty(raw, "context_id", "node_id")
            if context_id and str(context_id).startswith("ctx_"):
                page_id = str(context_id)[4:]
            elif context_id and str(context_id).startswith("page_context:"):
                page_id = str(context_id).split(":", 1)[1]
        if page_id:
            by_page[page_id] = dict(raw)
    return by_page


def _context_summary(ctx: Mapping[str, Any] | None) -> str:
    if not ctx:
        return ""
    return str(_first_nonempty(ctx, "short_summary", "summary", "context", "text") or "")


def _context_topics(ctx: Mapping[str, Any] | None) -> list[str]:
    if not ctx:
        return []
    topics = _first_nonempty(ctx, "topics", "detected_topics", "tags")
    if isinstance(topics, list):
        return [str(x) for x in topics if str(x).strip()]
    if isinstance(topics, str):
        return [x.strip() for x in re.split(r"[,;]", topics) if x.strip()]
    return []


def _context_parts(ctx: Mapping[str, Any] | None) -> list[str]:
    if not ctx:
        return []
    parts = _first_nonempty(ctx, "important_parts", "highlighted_parts", "parts")
    if isinstance(parts, list):
        out: list[str] = []
        for part in parts:
            if isinstance(part, Mapping):
                value = _first_nonempty(part, "part_number", "part", "id", "label")
            else:
                value = part
            if value and str(value).strip():
                out.append(str(value).strip())
        return out
    if isinstance(parts, str):
        return [x.strip() for x in re.split(r"[,;]", parts) if x.strip()]
    return []


@dataclass
class PageVisualObjectRow:
    page_id: str
    manual: str | None
    ata_code: str | None
    page_label: str | None
    role: str
    has_context: bool
    has_source_url: bool
    has_ocr_path: bool
    ocr_status: str
    visible_chars: int
    visible_words: int
    part_refs: int
    figure_refs: int
    sheet_refs: int
    table_refs: int
    illustration_refs: int
    image_terms: int
    visual_signal_score: int
    likely_visual_page: bool
    likely_table_page: bool
    likely_figure_page: bool
    context_summary: str
    topics: list[str]
    highlighted_parts: list[str]
    sample_figure_refs: list[str]
    sample_sheet_refs: list[str]
    sample_table_refs: list[str]
    ocr_path: str | None
    tiff_path: str | None
    source_url: str | None


@dataclass
class PageVisualObjectSummary:
    status: str
    export_dir: str
    context_file: str
    pages_checked: int
    pages_with_context: int
    pages_without_context: int
    pages_with_source_url: int
    pages_with_ocr_text: int
    pages_without_ocr_text: int
    role_counts: dict[str, int]
    figure_role_pages: int
    table_role_pages: int
    parts_list_role_pages: int
    procedure_role_pages: int
    blank_role_pages: int
    pages_with_figure_refs: int
    pages_with_sheet_refs: int
    pages_with_table_refs: int
    pages_with_illustration_refs: int
    pages_with_image_terms: int
    pages_with_visual_signals: int
    likely_visual_pages: int
    likely_figure_pages: int
    likely_table_pages: int
    total_figure_refs: int
    total_sheet_refs: int
    total_table_refs: int
    total_illustration_refs: int
    total_image_terms: int
    total_part_refs: int
    graph_page_context_nodes: int | None
    graph_has_context_edges: int | None
    graph_tagged_as_edges: int | None
    graph_highlights_part_edges: int | None
    sample_rows: list[dict[str, Any]]
    warnings: list[str]


def _load_graph_counts(graph_summary: Path | None) -> dict[str, int | None]:
    """Load page-context graph counts from graph_summary.json.

    The graph exporter has used a few JSON shapes while the project evolved:
    direct keys, nested ``summary`` keys, and sometimes type/count lists.  Keep
    this reader deliberately tolerant because this audit is a reporting layer,
    not the source of truth for the graph.
    """
    counts: dict[str, int | None] = {
        "page_context_nodes": None,
        "has_context_edges": None,
        "tagged_as_edges": None,
        "highlights_part_edges": None,
    }
    if graph_summary is None or not graph_summary.exists():
        return counts
    try:
        data = _read_json(graph_summary)
    except Exception:
        return counts

    def _to_int(value: Any) -> int | None:
        if value in (None, "", [], {}):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _type_count_mapping(value: Any) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return {str(k): v for k, v in value.items()}
        if isinstance(value, list):
            out: dict[str, Any] = {}
            for item in value:
                if not isinstance(item, Mapping):
                    continue
                type_name = _first_nonempty(item, "type", "node_type", "edge_type", "name", "label")
                count = _first_nonempty(item, "count", "value", "total", "n")
                if type_name not in (None, "") and count not in (None, ""):
                    out[str(type_name)] = count
            return out
        return {}

    def _find_first_type_counts(value: Any, keys: tuple[str, ...]) -> dict[str, Any]:
        if isinstance(value, Mapping):
            for key in keys:
                if key in value:
                    mapped = _type_count_mapping(value.get(key))
                    if mapped:
                        return mapped
            # Common summary wrapper first, then generic recursive search.
            for key in ("summary", "graph_summary", "counts"):
                if key in value:
                    mapped = _find_first_type_counts(value.get(key), keys)
                    if mapped:
                        return mapped
            for child in value.values():
                mapped = _find_first_type_counts(child, keys)
                if mapped:
                    return mapped
        elif isinstance(value, list):
            for child in value:
                mapped = _find_first_type_counts(child, keys)
                if mapped:
                    return mapped
        return {}

    node_types = _find_first_type_counts(
        data,
        (
            "node_types",
            "node_type_counts",
            "nodes_by_type",
            "node_counts_by_type",
            "by_node_type",
        ),
    )
    edge_types = _find_first_type_counts(
        data,
        (
            "edge_types",
            "edge_type_counts",
            "edges_by_type",
            "edge_counts_by_type",
            "by_edge_type",
        ),
    )

    page_context_nodes = _to_int(node_types.get("page_context"))
    if page_context_nodes is not None:
        counts["page_context_nodes"] = page_context_nodes

    for output_key, edge_type in (
        ("has_context_edges", "HAS_CONTEXT"),
        ("tagged_as_edges", "TAGGED_AS"),
        ("highlights_part_edges", "HIGHLIGHTS_PART"),
    ):
        value = _to_int(edge_types.get(edge_type) or edge_types.get(edge_type.lower()))
        if value is not None:
            counts[output_key] = value

    return counts

def audit_page_visual_objects(
    export_dir: Path = DEFAULT_EXPORT_DIR,
    context_file: Path = DEFAULT_CONTEXT_FILE,
    graph_summary: Path | None = DEFAULT_GRAPH_SUMMARY,
    repo_root: Path | None = None,
    sample_limit: int = 20,
) -> tuple[PageVisualObjectSummary, list[PageVisualObjectRow]]:
    repo_root = repo_root or Path.cwd()
    pages = load_page_records(export_dir)
    contexts = load_page_contexts(context_file)
    graph_counts = _load_graph_counts(graph_summary)

    rows: list[PageVisualObjectRow] = []
    role_counts: Counter[str] = Counter()
    warnings: list[str] = []

    for page in pages:
        page_id = page["page_id"]
        ctx = contexts.get(page_id)
        role = _normalize_role(_first_nonempty(ctx or {}, "page_role", "role", "type")) if ctx else "unknown"
        role_counts[role] += 1
        ocr_path = _repo_path(page.get("ocr_path"), repo_root)
        ocr_text, ocr_problem = _read_text_file(ocr_path)
        visible = _visible_text(ocr_text)
        ocr_status = ocr_problem or ("empty_ocr" if not visible else "readable_ocr")
        combined = "\n".join([visible, _context_summary(ctx), " ".join(_context_topics(ctx))])
        figure_refs = _count_matches(FIGURE_RE, combined)
        sheet_refs = _count_matches(SHEET_RE, combined)
        table_refs = _count_matches(TABLE_RE, combined)
        illustration_refs = _count_matches(ILLUSTRATION_RE, combined)
        image_terms = _count_matches(IMAGE_RE, combined)
        part_refs = len(PART_RE.findall(combined))
        visual_score = figure_refs + sheet_refs + table_refs + illustration_refs + image_terms
        likely_figure = role == "figure" or figure_refs > 0 or sheet_refs > 0 or image_terms > 0
        likely_table = role == "table" or table_refs > 0 or "table" in " ".join(_context_topics(ctx)).lower()
        likely_visual = role in VISUAL_ROLES or visual_score > 0
        rows.append(PageVisualObjectRow(
            page_id=page_id,
            manual=page.get("manual"),
            ata_code=page.get("ata_code"),
            page_label=page.get("page_label"),
            role=role,
            has_context=ctx is not None,
            has_source_url=bool(page.get("source_url")),
            has_ocr_path=bool(page.get("ocr_path")),
            ocr_status=ocr_status,
            visible_chars=len(visible),
            visible_words=len(visible.split()) if visible else 0,
            part_refs=part_refs,
            figure_refs=figure_refs,
            sheet_refs=sheet_refs,
            table_refs=table_refs,
            illustration_refs=illustration_refs,
            image_terms=image_terms,
            visual_signal_score=visual_score,
            likely_visual_page=likely_visual,
            likely_table_page=likely_table,
            likely_figure_page=likely_figure,
            context_summary=_context_summary(ctx),
            topics=_context_topics(ctx),
            highlighted_parts=_context_parts(ctx),
            sample_figure_refs=_sample_matches(FIGURE_RE, combined),
            sample_sheet_refs=_sample_matches(SHEET_RE, combined),
            sample_table_refs=_sample_matches(TABLE_RE, combined),
            ocr_path=str(page.get("ocr_path")) if page.get("ocr_path") else None,
            tiff_path=str(page.get("tiff_path")) if page.get("tiff_path") else None,
            source_url=str(page.get("source_url")) if page.get("source_url") else None,
        ))

    pages_checked = len(rows)
    pages_with_context = sum(1 for r in rows if r.has_context)
    pages_with_source_url = sum(1 for r in rows if r.has_source_url)
    pages_with_ocr_text = sum(1 for r in rows if r.visible_chars > 0)
    pages_without_ocr_text = pages_checked - pages_with_ocr_text
    if pages_without_ocr_text:
        warnings.append(f"{pages_without_ocr_text} pages have no visible OCR text; they may be blank pages or OCR misses.")
    if pages_with_context < pages_checked:
        warnings.append(f"{pages_checked - pages_with_context} pages do not have AI page context records.")
    if pages_with_source_url < pages_checked:
        warnings.append(f"{pages_checked - pages_with_source_url} pages do not have source URLs.")

    sample_rows = sorted(rows, key=lambda r: (not r.likely_visual_page, -r.visual_signal_score, r.page_id))[:sample_limit]
    status = "OK"
    if pages_checked == 0 or pages_with_source_url < pages_checked:
        status = "NEEDS ATTENTION"

    summary = PageVisualObjectSummary(
        status=status,
        export_dir=str(export_dir),
        context_file=str(context_file),
        pages_checked=pages_checked,
        pages_with_context=pages_with_context,
        pages_without_context=pages_checked - pages_with_context,
        pages_with_source_url=pages_with_source_url,
        pages_with_ocr_text=pages_with_ocr_text,
        pages_without_ocr_text=pages_without_ocr_text,
        role_counts=dict(sorted(role_counts.items())),
        figure_role_pages=role_counts.get("figure", 0),
        table_role_pages=role_counts.get("table", 0),
        parts_list_role_pages=role_counts.get("parts_list", 0),
        procedure_role_pages=role_counts.get("procedure", 0),
        blank_role_pages=role_counts.get("blank", 0),
        pages_with_figure_refs=sum(1 for r in rows if r.figure_refs > 0),
        pages_with_sheet_refs=sum(1 for r in rows if r.sheet_refs > 0),
        pages_with_table_refs=sum(1 for r in rows if r.table_refs > 0),
        pages_with_illustration_refs=sum(1 for r in rows if r.illustration_refs > 0),
        pages_with_image_terms=sum(1 for r in rows if r.image_terms > 0),
        pages_with_visual_signals=sum(1 for r in rows if r.visual_signal_score > 0),
        likely_visual_pages=sum(1 for r in rows if r.likely_visual_page),
        likely_figure_pages=sum(1 for r in rows if r.likely_figure_page),
        likely_table_pages=sum(1 for r in rows if r.likely_table_page),
        total_figure_refs=sum(r.figure_refs for r in rows),
        total_sheet_refs=sum(r.sheet_refs for r in rows),
        total_table_refs=sum(r.table_refs for r in rows),
        total_illustration_refs=sum(r.illustration_refs for r in rows),
        total_image_terms=sum(r.image_terms for r in rows),
        total_part_refs=sum(r.part_refs for r in rows),
        graph_page_context_nodes=graph_counts["page_context_nodes"],
        graph_has_context_edges=graph_counts["has_context_edges"],
        graph_tagged_as_edges=graph_counts["tagged_as_edges"],
        graph_highlights_part_edges=graph_counts["highlights_part_edges"],
        sample_rows=[asdict(r) for r in sample_rows],
        warnings=warnings,
    )
    return summary, rows


def write_visual_object_audit(summary: PageVisualObjectSummary, rows: list[PageVisualObjectRow], output: Path = DEFAULT_OUTPUT) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": asdict(summary),
        "rows": [asdict(r) for r in rows],
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
