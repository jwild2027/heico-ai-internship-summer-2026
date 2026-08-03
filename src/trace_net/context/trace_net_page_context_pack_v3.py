"""TRACE-Net Page Context Pack v3.3.

Builds a source-bounded page context pack for page-specific and complex
engineering questions.  The pack is intentionally a *binder*, not a canned
answer: it gives the LLM proof, guidance, source locators, and route-aware
reasoning tasks so the model can synthesize cautiously for harder questions.

Safety contract:
- read-only inputs
- no Postgres/Qdrant/OpenSearch writes
- no source-truth mutation
- no answer permission
- graph/vector/visual/page-summary records are guidance unless backed by proof
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import re
from typing import Any, Iterable, Mapping

PART_NUMBER_RE = re.compile(r"\b\d{2,4}-\d{3,6}(?:-\d{2,4})?\b")
PAGE_RE = re.compile(r"\b(?:page|p\.?|pg\.?|pages)\s*#?\s*(\d{1,5})\b", re.IGNORECASE)
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")

TEXT_KEYS = (
    "ocr_text",
    "source_text",
    "text",
    "excerpt",
    "content",
    "recognized_text",
    "combined_text",
    "cell_text",
    "line_text",
    "tile_text",
    "embedding_text",
    "summary",
    "description",
)

SOURCE_LINK_KEYS = ("source_link", "source_url", "url", "rescarta_url", "display_url", "source_target")
SOURCE_FILE_KEYS = (
    "source_file",
    "source_member",
    "tiff_path",
    "ocr_path",
    "file_path",
    "path",
    "source_path",
    "image_path",
    "tif_path",
    "tiff_file",
)
PAGE_ID_KEYS = (
    "page_id",
    "source_page_id",
    "canonical_page_id",
    "page_key",
    "page",
    "id",
    "record_key",
    "source_member",
    "source_file",
    "tiff_path",
    "ocr_path",
    "source_path",
    "image_path",
)


def load_json(path: str | Path | None, default: Any = None) -> Any:
    if path is None:
        return default
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        return json.loads(p.read_text(encoding="utf-8-sig"))


def write_json(path: str | Path, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _norm_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _first_present(record: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _first_text(record: Mapping[str, Any], keys: Iterable[str] = TEXT_KEYS) -> str:
    value = _first_present(record, keys)
    if value not in (None, "", [], {}):
        return _norm_text(value)
    # Some TRACE-Net artifacts keep OCR snippets inside cells/rows/tiles.
    for container_key in ("cells", "rows", "tiles", "ocr_cells", "ocr_records", "observations"):
        items = record.get(container_key)
        if not isinstance(items, list):
            continue
        pieces: list[str] = []
        for item in items[:80]:
            if isinstance(item, dict):
                piece = _first_text(item, keys)
                if piece:
                    pieces.append(piece)
            elif item not in (None, ""):
                pieces.append(str(item))
            if sum(len(p) for p in pieces) > 1600:
                break
        if pieces:
            return " ".join(pieces)
    return ""


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y", "pass", "ready"}


def _looks_page_or_evidence_like(record: Mapping[str, Any]) -> bool:
    keys = set(record.keys())
    page_keys = {
        "page_id",
        "source_page_id",
        "canonical_page_id",
        "page_key",
        "page",
        "page_number",
        "source_page_number",
        "page_index",
        "page_label",
        "source_page_label",
        "source_file",
        "source_member",
        "tiff_path",
        "ocr_path",
        "source_link",
        "source_url",
        "rescarta_url",
        "image_path",
    }
    evidence_keys = {
        "ocr_text",
        "source_text",
        "excerpt",
        "content",
        "recognized_text",
        "embedding_text",
        "summary",
        "primary_route",
        "route",
        "route_label",
        "page_route",
        "part_number",
        "covered_part_number",
        "ipl_part_number",
    }
    return bool(keys & page_keys) or bool(keys & evidence_keys)


def _as_records(payload: Any) -> list[dict[str, Any]]:
    """Extract records from common and nested TRACE-Net artifact shapes.

    v3.2 deliberately scans more artifact containers than the earlier page
    pack: graph citation maps, visual sample records, sidecar JSONL pointers,
    and nested OCR cells all need to be visible to the page hydrator.
    """
    if payload is None:
        return []
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []

    preferred_keys = (
        "records",
        "page_records",
        "route_records",
        "route_cards",
        "cards",
        "items",
        "evidence_records",
        "source_records",
        "direct_evidence_records",
        "exact_hit_records",
        "family_variant_hit_records",
        "reference_hit_records",
        "citation_map",
        "nodes",
        "edges",
        "pages",
        "page_cards",
        "sample_records",
        "visual_records",
        "visual_observation_records",
        "visual_observation_cards",
        "llava_observer_cards",
        "data",
    )
    collected: list[dict[str, Any]] = []
    for key in preferred_keys:
        value = payload.get(key)
        if isinstance(value, list):
            rows = [r for r in value if isinstance(r, dict)]
            if rows:
                collected.extend(rows)
    if collected:
        return collected

    found: list[dict[str, Any]] = []
    seen: set[int] = set()

    def walk(value: Any, *, parent_key: str | None = None, depth: int = 0) -> None:
        if depth > 6:
            return
        if isinstance(value, list):
            for item in value:
                walk(item, parent_key=parent_key, depth=depth + 1)
            return
        if not isinstance(value, dict):
            return
        oid = id(value)
        if oid in seen:
            return
        seen.add(oid)
        row = dict(value)
        if parent_key and not row.get("record_key"):
            row["record_key"] = parent_key
        if _looks_page_or_evidence_like(row):
            found.append(row)
        for key, child in value.items():
            if isinstance(child, (dict, list)):
                walk(child, parent_key=str(key), depth=depth + 1)

    for key, value in payload.items():
        if isinstance(value, dict):
            row = dict(value)
            row.setdefault("record_key", key)
            if _looks_page_or_evidence_like(row):
                found.append(row)
            walk(value, parent_key=str(key), depth=1)
        elif isinstance(value, list):
            walk(value, parent_key=str(key), depth=1)
    return found


def normalize_page_id(value: Any) -> str | None:
    text = _norm_text(value)
    if not text:
        return None
    if re.search(r"[A-Za-z_]", text):
        return text
    try:
        return f"p{int(text):06d}"
    except ValueError:
        return text


def page_number_from_any(value: Any) -> int | None:
    text = _norm_text(value)
    if not text:
        return None
    preferred_patterns = (
        r"(?:^|[_\-/\s])p0*(\d{1,6})(?:\D|$)",
        r"(?:source[_\-/\s]*page|source[_\-/\s]*p|page|pg)0*[_\-/\s]*(\d{1,6})(?:\D|$)",
        r"(?:^|[\\/])0*(\d{1,6})\.(?:tif|tiff|png|jpg|jpeg)(?:\D|$)",
    )
    for pattern in preferred_patterns:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        if matches:
            try:
                return int(matches[-1])
            except ValueError:
                pass
    matches = re.findall(r"\d{1,6}", text)
    if not matches:
        return None
    try:
        return int(matches[-1])
    except ValueError:
        return None


def page_key(record: Mapping[str, Any]) -> str | None:
    value = _first_present(record, PAGE_ID_KEYS)
    pid = normalize_page_id(value)
    if pid:
        return pid
    pnum = _first_present(record, ("page_number", "source_page_number", "page_index", "page_label", "source_page_label"))
    if pnum is not None:
        num = page_number_from_any(pnum)
        if num is not None:
            return f"p{num:06d}"
    return None


def page_aliases(record: Mapping[str, Any]) -> set[str]:
    """Return safe aliases for a page/evidence record.

    Important boundary: manual/page labels may be numeric and can collide
    with physical/source page numbers.  A user asking for "page 48" in the
    OpenWebUI smoke path means source page 48 unless the planner explicitly
    asks for a page label.  Therefore numeric page labels are exposed only
    through label-qualified aliases and never through the bare alias "48".
    """
    aliases: set[str] = set()
    pid = page_key(record)
    if pid:
        aliases.add(pid)
        embedded = page_number_from_any(pid)
        if embedded is not None:
            aliases.update({str(embedded), f"p{embedded:06d}", f"p{embedded:04d}", f"source_p{embedded:06d}", f"source_p{embedded:04d}"})
    for key in PAGE_ID_KEYS:
        value = _norm_text(record.get(key))
        if value:
            aliases.add(value)
            embedded = page_number_from_any(value)
            if embedded is not None:
                aliases.update({str(embedded), f"p{embedded:06d}", f"p{embedded:04d}", f"source_p{embedded:06d}", f"source_p{embedded:04d}"})
    # Source page numbers get bare numeric aliases.
    for key in ("page_number", "source_page_number", "page_index"):
        num = page_number_from_any(record.get(key))
        if num is not None:
            aliases.update({str(num), f"p{num:06d}", f"p{num:04d}", f"source_p{num:06d}", f"source_p{num:04d}"})
    # Page labels are useful, but they must not collide with source page
    # numbers.  Keep them label-qualified.
    for key in ("page_label", "label", "source_page_label"):
        value = _norm_text(record.get(key))
        if value:
            aliases.update({f"label:{value}", f"page_label:{value}"})
    return aliases


def _dedupe_dicts(items: list[dict[str, Any]], *, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        sig_parts = []
        for key in keys:
            sig_parts.append(str(item.get(key, ""))[:500])
        sig = "|".join(sig_parts)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(item)
    return out


def _record_can_prove(record: Mapping[str, Any], *, proof_kind: str) -> bool:
    """Return whether a record should count as proof, not merely guidance.

    Many TRACE-Net records are source-located but explicitly say they cannot
    prove claims or answer directly.  v3.2 keeps those records in the binder,
    but routes them to guidance/candidate lists so Gemma does not overclaim.
    """
    if proof_kind in {"source_file", "source_link"}:
        return True
    if record.get("can_prove_claims") is False or record.get("can_prove_source_truth") is False:
        return False
    if record.get("answer_use_policy") == "retrieval_only" or record.get("retrieval_only") is True:
        return False
    if proof_kind == "ocr_text":
        return bool(_first_text(record)) and bool(_first_present(record, ("page_id", "source_trace", "source_file", "ocr_path", "source_member")))
    if proof_kind == "exact_part":
        return bool(_first_present(record, ("matched_part_number", "part_number", "covered_part_number", "ipl_part_number"))) and not record.get("unsafe", False)
    if proof_kind == "table_evidence":
        if _truthy(record.get("can_prove_claims")) or _truthy(record.get("can_answer_directly")):
            return True
        # Non-empty normalized rows/cells can support source-table context,
        # but only when the record is citation/source ready and not explicitly
        # marked retrieval-only.
        row_count = record.get("normalized_row_count") or record.get("source_row_count") or record.get("answer_support_row_count") or 0
        cell_count = record.get("normalized_cell_count") or len(record.get("cells", []) or [])
        citation_ready = _truthy(record.get("citation_ready")) or _truthy(record.get("has_citation"))
        try:
            return citation_ready and (int(row_count) > 0 or int(cell_count) > 0)
        except Exception:
            return False
    return False


def _route_evidence_priority(route: str | None) -> list[str]:
    route_text = (route or "").lower()
    if "image" in route_text or "visual" in route_text or "diagram" in route_text:
        return ["source_files", "source_links", "visual_guidance", "ocr_excerpts", "graph_neighbors", "vector_guidance", "table_evidence_if_present"]
    if "table" in route_text:
        return ["source_files", "source_links", "table_evidence", "ocr_excerpts", "exact_part_hits", "graph_neighbors", "vector_guidance"]
    if "blank" in route_text:
        return ["source_files", "source_links", "ocr_excerpts_if_any", "route_guidance"]
    return ["source_files", "source_links", "ocr_excerpts", "exact_part_hits", "table_evidence", "graph_neighbors", "vector_guidance", "visual_guidance"]


def _page_reasoning_tasks(page: "PageContextRecord") -> list[str]:
    tasks = ["Use this page only within its source-trace limits."]
    route = (page.primary_route or "").lower()
    if "table" in route:
        tasks.append("Prioritize table/OCR/source-file evidence; do not invent missing rows or quantities.")
    elif "image" in route or "visual" in route or "diagram" in route:
        tasks.append("Use visual observations as guidance for what the page may depict; require OCR/source proof for factual source claims.")
    elif "blank" in route:
        tasks.append("Treat blank-candidate pages cautiously and say if no text/source evidence is attached.")
    if page.part_mentions:
        tasks.append("Mention part relationships only as far as the attached evidence role allows.")
    if page.route_guidance:
        tasks.append("Candidate/guidance records may help decide what to inspect but are not proof by themselves.")
    return tasks


@dataclass
class PageContextRecord:
    page_id: str
    page_number: int | None = None
    page_label: str | None = None
    ata_section: str | None = None
    primary_route: str | None = None
    source_links: list[dict[str, Any]] = field(default_factory=list)
    source_files: list[dict[str, Any]] = field(default_factory=list)
    ocr_excerpts: list[dict[str, Any]] = field(default_factory=list)
    table_evidence: list[dict[str, Any]] = field(default_factory=list)
    exact_part_hits: list[dict[str, Any]] = field(default_factory=list)
    visual_guidance: list[dict[str, Any]] = field(default_factory=list)
    graph_neighbors: list[dict[str, Any]] = field(default_factory=list)
    vector_guidance: list[dict[str, Any]] = field(default_factory=list)
    route_guidance: list[dict[str, Any]] = field(default_factory=list)
    part_mentions: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def finalize(self) -> None:
        self.source_links = _dedupe_dicts(self.source_links, keys=("value", "route", "proof_role"))
        self.source_files = _dedupe_dicts(self.source_files, keys=("value", "route", "proof_role"))
        self.ocr_excerpts = _dedupe_dicts(self.ocr_excerpts, keys=("text", "route", "proof_role"))
        self.table_evidence = _dedupe_dicts(self.table_evidence, keys=("page_id", "source_table_id", "normalized_table_id", "route", "proof_role"))
        self.exact_part_hits = _dedupe_dicts(self.exact_part_hits, keys=("matched_part_number", "part_number", "page_id", "route"))
        self.visual_guidance = _dedupe_dicts(self.visual_guidance, keys=("summary", "route", "proof_role"))
        self.graph_neighbors = _dedupe_dicts(self.graph_neighbors, keys=("edge_type", "source", "target", "page_id"))
        self.vector_guidance = _dedupe_dicts(self.vector_guidance, keys=("text", "score", "route"))
        self.route_guidance = _dedupe_dicts(self.route_guidance, keys=("route", "reason", "source_table_id", "record_type"))
        self.part_mentions = _dedupe_dicts(self.part_mentions, keys=("part_number", "route", "proof_role"))

    def to_dict(self) -> dict[str, Any]:
        self.finalize()
        proof_count = len(self.ocr_excerpts) + len(self.table_evidence) + len(self.exact_part_hits) + len(self.source_links) + len(self.source_files)
        guidance_count = len(self.visual_guidance) + len(self.graph_neighbors) + len(self.vector_guidance) + len(self.route_guidance)
        source_trace_ready = proof_count > 0 or bool(self.source_links or self.source_files)
        return {
            "page_id": self.page_id,
            "page_number": self.page_number,
            "page_label": self.page_label,
            "ata_section": self.ata_section,
            "primary_route": self.primary_route,
            "route_evidence_priority": _route_evidence_priority(self.primary_route),
            "page_reasoning_tasks": _page_reasoning_tasks(self),
            "source_links": self.source_links,
            "source_files": self.source_files,
            "ocr_excerpts": self.ocr_excerpts,
            "table_evidence": self.table_evidence,
            "exact_part_hits": self.exact_part_hits,
            "visual_guidance": self.visual_guidance,
            "graph_neighbors": self.graph_neighbors,
            "vector_guidance": self.vector_guidance,
            "route_guidance": self.route_guidance,
            "part_mentions": self.part_mentions,
            "proof_record_count": proof_count,
            "guidance_record_count": guidance_count,
            "source_trace_ready": source_trace_ready,
            "warnings": self.warnings,
        }


class PageContextIndex:
    def __init__(self) -> None:
        self.pages: dict[str, PageContextRecord] = {}
        self.alias_to_page: dict[str, str] = {}

    def ensure_page(self, pid: str, *, page_number: int | None = None, page_label: str | None = None) -> PageContextRecord:
        if pid not in self.pages:
            self.pages[pid] = PageContextRecord(page_id=pid, page_number=page_number, page_label=page_label)
        rec = self.pages[pid]
        if rec.page_number is None and page_number is not None:
            rec.page_number = page_number
        if rec.page_label is None and page_label:
            rec.page_label = page_label

        self.alias_to_page[pid] = pid

        # Source/physical page number aliases are authoritative for bare
        # numeric lookups such as --pages 48.
        if page_number is not None:
            for alias in (str(page_number), f"p{page_number:06d}", f"p{page_number:04d}", f"source_p{page_number:06d}", f"source_p{page_number:04d}"):
                self.alias_to_page[alias] = pid

        # Numeric page labels often collide with source page numbers.  Expose
        # them only through qualified aliases, never as bare "48".
        if page_label:
            label = str(page_label)
            self.alias_to_page[f"label:{label}"] = pid
            self.alias_to_page[f"page_label:{label}"] = pid
            if not label.isdigit():
                self.alias_to_page.setdefault(label, pid)
        return rec

    def add_aliases(self, pid: str, aliases: Iterable[str]) -> None:
        for alias in aliases:
            text = _norm_text(alias)
            if not text:
                continue
            # Do not let later label/guidance aliases steal an exact source
            # page-number lookup from an already-indexed page.
            if text.isdigit() and text in self.alias_to_page and self.alias_to_page[text] != pid:
                continue
            self.alias_to_page[text] = pid

    def resolve(self, token: str | int) -> str | None:
        text = _norm_text(token)
        if not text:
            return None
        if text in self.alias_to_page:
            return self.alias_to_page[text]
        norm = normalize_page_id(text)
        if norm and norm in self.pages:
            return norm
        if norm and norm in self.alias_to_page:
            return self.alias_to_page[norm]
        num = page_number_from_any(text)
        if num is not None:
            for alias in (str(num), f"p{num:06d}", f"p{num:04d}", f"source_p{num:06d}", f"source_p{num:04d}"):
                if alias in self.alias_to_page:
                    return self.alias_to_page[alias]
        return None


def _attach_source_locators(page: PageContextRecord, record: Mapping[str, Any], *, source_route: str) -> None:
    source_link = _first_present(record, SOURCE_LINK_KEYS)
    if source_link:
        page.source_links.append({
            "route": "source_link",
            "source_route": source_route,
            "value": source_link,
            "proof_role": "source_locator",
            "citation_ready": True,
        })
    source_file = _first_present(record, SOURCE_FILE_KEYS)
    if source_file:
        page.source_files.append({
            "route": "source_file",
            "source_route": source_route,
            "value": source_file,
            "proof_role": "source_locator",
            "citation_ready": True,
        })


def _make_compact(record: Mapping[str, Any], *, drop_large: bool = True) -> dict[str, Any]:
    drop = {"raw", "tokens", "qdrant_payload_preview"} if drop_large else set()
    compact = {k: v for k, v in record.items() if k not in drop}
    text = _first_text(record)
    if text and "text_preview" not in compact:
        compact["text_preview"] = text[:1000]
    return compact


def build_index(
    *,
    route_manifest: Any = None,
    graph_export: Any = None,
    ocr_records: Any = None,
    table_evidence: Any = None,
    exact_part_records: Any = None,
    visual_summaries: Any = None,
    vector_hits: Any = None,
) -> PageContextIndex:
    idx = PageContextIndex()

    for record in _as_records(route_manifest):
        pid = page_key(record)
        if not pid:
            continue
        pnum = page_number_from_any(_first_present(record, ("page_number", "source_page_number", "page_index", "page_label", "source_member", "source_file")))
        if pnum is None:
            pnum = page_number_from_any(pid)
        plabel = _norm_text(_first_present(record, ("page_label", "label", "source_page_label"))) or None
        page = idx.ensure_page(pid, page_number=pnum, page_label=plabel)
        page.primary_route = _norm_text(_first_present(record, ("primary_route", "route", "route_label", "page_route"))) or page.primary_route
        page.ata_section = _norm_text(_first_present(record, ("ata_section", "ata", "section", "ata_code"))) or page.ata_section
        _attach_source_locators(page, record, source_route="route_manifest")
        idx.add_aliases(pid, page_aliases(record))

    graph_records = _as_records(graph_export)
    for record in graph_records:
        node_type = _norm_text(_first_present(record, ("node_type", "type", "label", "kind"))).lower()
        if node_type != "page":
            continue
        pid = page_key(record)
        if not pid:
            continue
        pnum = page_number_from_any(_first_present(record, ("page_number", "page_label", "label", "source_member", "source_file")))
        if pnum is None:
            pnum = page_number_from_any(pid)
        plabel = _norm_text(_first_present(record, ("page_label", "label", "name"))) or None
        page = idx.ensure_page(pid, page_number=pnum, page_label=plabel)
        page.ata_section = _norm_text(_first_present(record, ("ata_section", "ata", "section", "ata_code"))) or page.ata_section
        _attach_source_locators(page, record, source_route="graph_node")
        idx.add_aliases(pid, page_aliases(record))

    def attach_to_page(record: Mapping[str, Any]) -> PageContextRecord | None:
        pid = page_key(record)
        pnum = page_number_from_any(_first_present(record, ("page_number", "source_page_number", "page_index", "page_label", "source_member", "source_file", "source_path", "image_path")))
        resolved = idx.resolve(pid or "") if pid else None
        if not resolved and pnum is not None:
            resolved = idx.resolve(pnum)
        if not resolved and pid:
            resolved = pid
        if not resolved:
            return None
        if pnum is None:
            pnum = page_number_from_any(resolved)
        plabel = _norm_text(_first_present(record, ("page_label", "label", "source_page_label"))) or None
        page = idx.ensure_page(resolved, page_number=pnum, page_label=plabel)
        idx.add_aliases(page.page_id, page_aliases(record))
        return page

    for record in _as_records(ocr_records):
        page = attach_to_page(record)
        if not page:
            continue
        text = _first_text(record, TEXT_KEYS)
        if text:
            page.ocr_excerpts.append({
                "route": "ocr_text",
                "proof_role": "source_traceable_text_candidate" if _record_can_prove(record, proof_kind="ocr_text") else "ocr_guidance_candidate",
                "text": text[:1600],
                "citation_ready": bool(_first_present(record, ("source_trace", "source_link", "page_id", "source_file", "source_member", "ocr_path"))),
                "can_be_used_as_proof": _record_can_prove(record, proof_kind="ocr_text"),
            })
        _attach_source_locators(page, record, source_route="ocr_records")

    for record in _as_records(table_evidence):
        page = attach_to_page(record)
        if not page:
            continue
        compact = _make_compact(record)
        compact.setdefault("route", "table_evidence")
        compact.setdefault("citation_ready", bool(_first_present(record, ("source_trace", "citation", "page_id", "source_file", "source_member"))))
        if _record_can_prove(record, proof_kind="table_evidence"):
            compact.setdefault("proof_role", "table_source_candidate")
            compact.setdefault("can_be_used_as_proof", True)
            page.table_evidence.append(compact)
        else:
            compact.setdefault("proof_role", "table_candidate_guidance_only")
            compact.setdefault("can_be_used_as_proof", False)
            compact.setdefault("reason", "table_record_not_claim_proof_ready")
            page.route_guidance.append(compact)
        part = _first_present(record, ("part_number", "covered_part_number", "ipl_part_number"))
        if part:
            page.part_mentions.append({"part_number": part, "route": "table_evidence", "proof_role": "part_presence_candidate"})
        _attach_source_locators(page, record, source_route="table_evidence")

    for record in _as_records(exact_part_records):
        page = attach_to_page(record)
        if not page:
            continue
        compact = _make_compact(record)
        compact.setdefault("route", "exact_part")
        compact.setdefault("proof_role", "exact_match_source_candidate" if _record_can_prove(record, proof_kind="exact_part") else "exact_match_guidance_candidate")
        compact.setdefault("citation_ready", bool(_first_present(record, ("source_trace", "citation", "page_id", "source_file", "source_member", "source_path"))))
        compact.setdefault("can_be_used_as_proof", _record_can_prove(record, proof_kind="exact_part"))
        if compact["can_be_used_as_proof"]:
            page.exact_part_hits.append(compact)
        else:
            page.route_guidance.append(compact)
        part = _first_present(record, ("matched_part_number", "part_number", "covered_part_number", "ipl_part_number", "query"))
        if part:
            page.part_mentions.append({"part_number": part, "route": "exact_part", "proof_role": "part_presence_candidate"})
        _attach_source_locators(page, record, source_route="exact_part_records")

    for record in _as_records(visual_summaries):
        page = attach_to_page(record)
        if not page:
            continue
        summary = _norm_text(_first_present(record, ("summary", "visual_summary", "observation", "caption", "text", "description", "llava_summary", "model_observation", "visual_observation")))
        if not summary:
            summary = _first_text(record)
        if summary:
            page.visual_guidance.append({
                "route": "visual_summary",
                "proof_role": "guidance_only",
                "summary": summary[:1200],
                "can_be_used_as_proof": False,
                "source_model": _first_present(record, ("llm_model", "model", "model_id", "vision_model")),
            })
        _attach_source_locators(page, record, source_route="visual_summaries")

    for record in _as_records(vector_hits):
        page = attach_to_page(record)
        if not page:
            continue
        text = _first_text(record, ("text", "chunk", "excerpt", "summary", "embedding_text", "retrieval_cues"))
        page.vector_guidance.append({
            "route": "vector_hit",
            "proof_role": "retrieval_guidance_only",
            "score": _first_present(record, ("score", "similarity", "distance")),
            "text": text[:1000],
            "can_be_used_as_proof": False,
            "candidate_type": _first_present(record, ("candidate_type", "record_type", "embedding_bucket")),
        })

    # Non-edge graph records such as citation_map entries.
    for record in graph_records:
        page = attach_to_page(record)
        if not page:
            continue
        node_type = _norm_text(_first_present(record, ("node_type", "type", "label", "kind"))).lower()
        if node_type == "page":
            continue
        if _first_present(record, SOURCE_FILE_KEYS):
            _attach_source_locators(page, record, source_route="graph_citation_or_source")
        page.graph_neighbors.append({
            "route": "graph_neighbor",
            "page_id": page.page_id,
            "proof_role": "graph_guidance_or_source_resolution",
            "citation_label": _first_present(record, ("citation_label", "citation_id")),
            "proof_strength": _first_present(record, ("proof_strength", "trust_tier", "source_quality_status")),
            "source_member": _first_present(record, ("source_member", "source_file", "source_path")),
            "can_be_used_as_proof": False,
        })

    # Edge-style graph records: attach page-level source/part context.
    graph_payload = graph_export if isinstance(graph_export, dict) else {}
    edges = graph_payload.get("edges", []) if isinstance(graph_payload.get("edges", []), list) else []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        etype = _norm_text(_first_present(edge, ("edge_type", "type", "label", "relationship"))).upper()
        src = _norm_text(_first_present(edge, ("source", "from", "src", "source_id")))
        dst = _norm_text(_first_present(edge, ("target", "to", "dst", "target_id")))
        pid = idx.resolve(src) or idx.resolve(dst)
        if not pid:
            continue
        page = idx.ensure_page(pid)
        neighbor = {"edge_type": etype, "source": src, "target": dst, "proof_role": "graph_guidance_or_source_resolution", "can_be_used_as_proof": False}
        if etype in {"HAS_SOURCE_LINK", "OPENS"}:
            page.source_links.append({"route": "source_link", "value": dst if idx.resolve(src) else src, "proof_role": "source_locator", "citation_ready": True})
        elif etype in {"HAS_TIFF", "POINTS_TO_TIFF"}:
            page.source_files.append({"route": "source_file", "value": dst if idx.resolve(src) else src, "proof_role": "source_locator", "citation_ready": True})
        elif etype in {"MENTIONS_PART", "APPEARS_ON", "REFERS_TO_PART"}:
            part = dst if idx.resolve(src) else src
            if part:
                page.part_mentions.append({"part_number": part, "route": "graph_edge", "proof_role": "graph_relationship_guidance"})
                page.graph_neighbors.append(neighbor)
        else:
            page.graph_neighbors.append(neighbor)

    return idx


def extract_query_entities(question: str | None) -> dict[str, Any]:
    q = question or ""
    parts = sorted(set(PART_NUMBER_RE.findall(q)))
    atas = sorted(set(ATA_RE.findall(q)))
    pages = [int(m.group(1)) for m in PAGE_RE.finditer(q)]
    q_without_parts = PART_NUMBER_RE.sub(" ", q)
    if re.search(r"\bpages?\b|\bpg\.?\b|\bp\.?\b", q_without_parts, flags=re.IGNORECASE):
        for num_text in re.findall(r"\b\d{1,5}\b", q_without_parts):
            try:
                num = int(num_text)
            except ValueError:
                continue
            if num not in pages:
                pages.append(num)
    lowered = q.lower()
    if pages:
        intent = "page_lookup"
    elif parts:
        intent = "part_lookup"
    elif atas:
        intent = "ata_browse"
    elif any(word in lowered for word in ("why", "compare", "summarize", "explain", "find", "where", "paragraph")):
        intent = "complex_retrieval_reasoning"
    else:
        intent = "general_page_context"
    return {"question": q, "intent": intent, "pages": pages, "part_numbers": parts, "ata_sections": atas}


def choose_pages(index: PageContextIndex, *, question: str | None = None, requested_pages: Iterable[str | int] | None = None, max_pages: int = 8) -> list[str]:
    entities = extract_query_entities(question)
    selected: list[str] = []
    for p in requested_pages or []:
        resolved = index.resolve(p)
        if resolved and resolved not in selected:
            selected.append(resolved)
    for p in entities["pages"]:
        resolved = index.resolve(p)
        if resolved and resolved not in selected:
            selected.append(resolved)
    for part in entities["part_numbers"]:
        for pid, page in index.pages.items():
            haystacks: list[str] = []
            for group in (page.exact_part_hits, page.table_evidence, page.part_mentions, page.ocr_excerpts, page.route_guidance):
                for item in group:
                    haystacks.append(json.dumps(item, sort_keys=True, default=str))
            if any(part in h for h in haystacks) and pid not in selected:
                selected.append(pid)
    if not selected:
        ready = [pid for pid, page in index.pages.items() if page.to_dict()["source_trace_ready"]]
        selected.extend(ready[:max_pages])
    if not selected:
        selected.extend(list(index.pages.keys())[:max_pages])
    return selected[:max_pages]


def build_reasoning_work_order(question_entities: Mapping[str, Any], selected_records: list[dict[str, Any]]) -> dict[str, Any]:
    proof_ready_pages = [r["page_id"] for r in selected_records if r.get("source_trace_ready")]
    guidance_only_pages = [r["page_id"] for r in selected_records if r.get("guidance_record_count", 0) and not r.get("source_trace_ready")]
    return {
        "purpose": "Give the LLM a source-bounded binder plus reasoning tasks, not a canned answer.",
        "question_intent": question_entities.get("intent"),
        "model_should_think": True,
        "allowed_reasoning": [
            "Synthesize across multiple proof records when the cited evidence supports the claim.",
            "Use graph/vector/visual/summary records to decide what to inspect or mention, but do not treat them as proof by themselves.",
            "State bounded inferences clearly as inferences and tie them back to source-traceable records.",
            "For complex questions, explain what the evidence supports, what remains unknown, and what additional evidence would be needed.",
        ],
        "disallowed_reasoning": [
            "Do not infer interchangeability, fit, effectivity, replacement approval, installation safety, or procurement authority without explicit source proof.",
            "Do not cite unrelated records.",
            "Do not use Engram, vector hits, graph neighbors, page summaries, route guidance, or visual summaries as factual proof unless a proof record backs them.",
        ],
        "proof_ready_pages": proof_ready_pages,
        "guidance_only_pages": guidance_only_pages,
        "route_awareness": {
            "table_pages": [r["page_id"] for r in selected_records if "table" in str(r.get("primary_route", "")).lower()],
            "image_visual_pages": [r["page_id"] for r in selected_records if any(x in str(r.get("primary_route", "")).lower() for x in ("image", "visual", "diagram"))],
        },
        "answer_sections": ["Answer", "Evidence", "Engineering confidence", "Limits"],
    }


def build_page_context_pack_v3(
    *,
    question: str | None = None,
    requested_pages: Iterable[str | int] | None = None,
    route_manifest: Any = None,
    graph_export: Any = None,
    ocr_records: Any = None,
    table_evidence: Any = None,
    exact_part_records: Any = None,
    visual_summaries: Any = None,
    vector_hits: Any = None,
    max_pages: int = 8,
) -> dict[str, Any]:
    index = build_index(
        route_manifest=route_manifest,
        graph_export=graph_export,
        ocr_records=ocr_records,
        table_evidence=table_evidence,
        exact_part_records=exact_part_records,
        visual_summaries=visual_summaries,
        vector_hits=vector_hits,
    )
    entities = extract_query_entities(question)
    selected_ids = choose_pages(index, question=question, requested_pages=requested_pages, max_pages=max_pages)
    unresolved_pages: list[int] = []
    for p in list(requested_pages or []) + list(entities.get("pages", [])):
        num = page_number_from_any(p)
        if num is not None and not index.resolve(num):
            unresolved_pages.append(num)
    for num in sorted(set(unresolved_pages)):
        pid = f"p{num:06d}"
        if pid not in index.pages:
            placeholder = index.ensure_page(pid, page_number=num, page_label=str(num))
            placeholder.warnings.append("requested_page_not_resolved_in_input_artifacts")
            if pid not in selected_ids:
                selected_ids.append(pid)

    records = [index.pages[pid].to_dict() for pid in selected_ids if pid in index.pages]
    proof_count = sum(r.get("proof_record_count", 0) for r in records)
    guidance_count = sum(r.get("guidance_record_count", 0) for r in records)
    return {
        "artifact_type": "trace_net_page_context_pack_v3",
        "version": "3.3",
        "quality_status": "PASS" if records else "REVIEW",
        "question": question or "",
        "query_entities": entities,
        "summary": {
            "selected_page_count": len(records),
            "source_trace_ready_page_count": sum(1 for r in records if r.get("source_trace_ready")),
            "proof_record_count": proof_count,
            "guidance_record_count": guidance_count,
            "source_link_count": sum(len(r.get("source_links", [])) for r in records),
            "source_file_count": sum(len(r.get("source_files", [])) for r in records),
            "ocr_excerpt_count": sum(len(r.get("ocr_excerpts", [])) for r in records),
            "visual_guidance_count": sum(len(r.get("visual_guidance", [])) for r in records),
            "route_guidance_count": sum(len(r.get("route_guidance", [])) for r in records),
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
        "page_context_records": records,
        "reasoning_work_order": build_reasoning_work_order(entities, records),
        "safety_contract": {
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_allowed": False,
            "qdrant_write_allowed": False,
            "opensearch_write_allowed": False,
            "guidance_can_be_used_as_proof": False,
            "proof_context_required_for_source_claims": True,
        },
    }


def check_page_context_pack_v3_quality(
    pack: Mapping[str, Any],
    *,
    min_pages: int = 1,
    require_no_answer_permission: bool = True,
    require_reasoning_work_order: bool = True,
    min_guidance_records: int = 0,
    min_source_trace_ready_pages: int = 0,
    min_source_locators: int = 0,
) -> dict[str, Any]:
    summary = pack.get("summary", {}) if isinstance(pack.get("summary"), dict) else {}
    records = pack.get("page_context_records", []) if isinstance(pack.get("page_context_records"), list) else []
    failures: list[str] = []
    if len(records) < min_pages:
        failures.append(f"selected_page_count_lt_{min_pages}")
    if require_reasoning_work_order and not pack.get("reasoning_work_order"):
        failures.append("missing_reasoning_work_order")
    if require_no_answer_permission and summary.get("answer_permission_count", 0) != 0:
        failures.append("answer_permission_count_nonzero")
    if summary.get("source_truth_mutation_allowed_count", 0) != 0:
        failures.append("source_truth_mutation_allowed_count_nonzero")
    for db_key in ("postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"):
        if summary.get(db_key, 0) != 0:
            failures.append(f"{db_key}_nonzero")
    if pack.get("safety_contract", {}).get("guidance_can_be_used_as_proof") is not False:
        failures.append("guidance_proof_boundary_not_false")
    if summary.get("guidance_record_count", 0) < min_guidance_records:
        failures.append(f"guidance_record_count_lt_{min_guidance_records}")
    if summary.get("source_trace_ready_page_count", 0) < min_source_trace_ready_pages:
        failures.append(f"source_trace_ready_page_count_lt_{min_source_trace_ready_pages}")
    locator_count = summary.get("source_link_count", 0) + summary.get("source_file_count", 0)
    if locator_count < min_source_locators:
        failures.append(f"source_locator_count_lt_{min_source_locators}")
    status = "PASS" if not failures else "FAIL"
    return {
        "artifact_type": "trace_net_page_context_pack_v3_quality",
        "quality_status": status,
        "failure_reasons": failures,
        "summary": {
            "selected_page_count": len(records),
            "source_trace_ready_page_count": summary.get("source_trace_ready_page_count", 0),
            "proof_record_count": summary.get("proof_record_count", 0),
            "guidance_record_count": summary.get("guidance_record_count", 0),
            "source_link_count": summary.get("source_link_count", 0),
            "source_file_count": summary.get("source_file_count", 0),
            "ocr_excerpt_count": summary.get("ocr_excerpt_count", 0),
            "visual_guidance_count": summary.get("visual_guidance_count", 0),
            "route_guidance_count": summary.get("route_guidance_count", 0),
        },
        "safety_contract": pack.get("safety_contract", {}),
    }
