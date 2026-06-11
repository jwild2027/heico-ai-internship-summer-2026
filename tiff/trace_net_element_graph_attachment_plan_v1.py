"""TRACE-Net Element-to-Graph Attachment Plan v1.

This module builds a read-only graph writeback plan from TRACE-Net page elements,
structured tables, visual/figure records, fishnet retry dispositions, embedding
candidates, citations, and trust/authority fields.

It intentionally does not mutate Postgres, Qdrant, source files, trust records,
or source truth.  The output is a set of planned nodes and edges that a later
writeback step can validate and apply.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_element_graph_attachment_plan_v1"
ALGORITHM = "trace_net_read_only_element_graph_attachment_planner_v1"

ANSWER_SUPPORT_BUCKETS = {
    "source_text_evidence",
    "verified_part_evidence",
    "table_structured_evidence",
    "table_part_catalog_evidence",
    "table_source_text_evidence",
    "figure_verified_part_evidence",
}
RETRIEVAL_ONLY_BUCKETS = {
    "source_evidence",
    "derived_context",
    "context_retrieval_helper",
    "page_retrieval_profile",
    "figure_part_catalog_retrieval_helper",
    "chart_retrieval_helper",
    "visual_model_retrieval_helper",
    "table_retrieval_helper",
    "unknown_table_retrieval_helper",
}
FORBIDDEN_TEXT_MARKERS = (
    "local_data\\",
    "local_data/",
    "rescarta_exports",
    "C:\\Users\\",
    "TIFF path:",
    "OCR path:",
    "OCR text: [b",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(prefix: str, *parts: Any, length: int = 16) -> str:
    joined = "||".join(str(p) for p in parts if p is not None)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:length]
    safe_prefix = re.sub(r"[^A-Za-z0-9_:-]+", "_", prefix).strip("_")
    return f"{safe_prefix}::{digest}"


def safe_node_id(prefix: str, raw: Any) -> str:
    text = str(raw or "unknown")
    text = text.replace(" ", "_")
    text = re.sub(r"[^A-Za-z0-9_.:-]+", "_", text)
    return f"{prefix}::{text}"


def read_json(path: str | Path | None, default: Any = None) -> Any:
    if not path:
        return default
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def iter_jsonl(path: str | Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def records_from_payload(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in (
            "records",
            "attachment_records",
            "clean_snippet_claims",
            "snippet_claims",
            "claims",
            "final_claims",
            "candidates",
            "results",
        ):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return [value]


def compact_props(record: dict[str, Any], keys: Iterable[str]) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for key in keys:
        value = record.get(key)
        if value is not None:
            props[key] = value
    return props


def any_forbidden_text(value: Any) -> bool:
    if isinstance(value, dict):
        return any(any_forbidden_text(v) for v in value.values())
    if isinstance(value, list):
        return any(any_forbidden_text(v) for v in value)
    if isinstance(value, str):
        return any(marker in value for marker in FORBIDDEN_TEXT_MARKERS)
    return False


def get_page_id(record: dict[str, Any]) -> str:
    return str(record.get("page_id") or record.get("pageId") or record.get("page") or "")


def get_page_number(page_id: str, fallback: Any = None) -> int | None:
    if fallback is not None:
        try:
            return int(fallback)
        except (TypeError, ValueError):
            pass
    match = re.search(r"p0*(\d+)$", page_id)
    if match:
        return int(match.group(1))
    return None


def get_citation_ids(record: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for key in ("citation_ids", "citations", "source_citation_ids"):
        for item in as_list(record.get(key)):
            if isinstance(item, dict):
                cid = item.get("citation_id") or item.get("id")
            else:
                cid = item
            if cid:
                ids.append(str(cid))
    for key in ("citation_id", "source_citation_id"):
        value = record.get(key)
        if value:
            ids.append(str(value))
    return sorted(dict.fromkeys(ids))


def node_label(node_type: str, page_id: str | None = None, suffix: str | None = None) -> str:
    parts = [node_type]
    if page_id:
        parts.append(page_id)
    if suffix:
        parts.append(suffix)
    return " | ".join(parts)


@dataclass
class AttachmentBuilder:
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    edges: dict[str, dict[str, Any]] = field(default_factory=dict)
    page_records: dict[str, dict[str, Any]] = field(default_factory=dict)
    quality_warnings: list[str] = field(default_factory=list)

    def add_node(
        self,
        node_id: str,
        node_type: str,
        label: str,
        page_id: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> str:
        if node_id not in self.nodes:
            self.nodes[node_id] = {
                "node_id": node_id,
                "node_type": node_type,
                "label": label,
                "page_id": page_id,
                "properties": properties or {},
                "writeback_status": "planned_only",
                "can_answer_directly": False,
                "can_prove_claims": False,
                "can_mutate_source_truth": False,
            }
        else:
            existing = self.nodes[node_id]
            if page_id and not existing.get("page_id"):
                existing["page_id"] = page_id
            if properties:
                existing.setdefault("properties", {}).update(properties)
        return node_id

    def add_edge(
        self,
        source: str,
        target: str,
        edge_type: str,
        page_id: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> str:
        edge_id = stable_id("edge", source, edge_type, target, length=20)
        if edge_id not in self.edges:
            self.edges[edge_id] = {
                "edge_id": edge_id,
                "source_node_id": source,
                "target_node_id": target,
                "edge_type": edge_type,
                "page_id": page_id,
                "properties": properties or {},
                "writeback_status": "planned_only",
                "can_answer_directly": False,
                "can_prove_claims": False,
                "can_mutate_source_truth": False,
            }
        return edge_id

    def page_record(self, page_id: str) -> dict[str, Any]:
        if page_id not in self.page_records:
            self.page_records[page_id] = {
                "page_id": page_id,
                "node_ids": [],
                "edge_ids": [],
                "planned_node_count": 0,
                "planned_edge_count": 0,
                "table_node_count": 0,
                "table_row_node_count": 0,
                "table_cell_node_count": 0,
                "visual_region_node_count": 0,
                "callout_node_count": 0,
                "fishnet_node_count": 0,
                "evidence_candidate_node_count": 0,
                "citation_node_count": 0,
                "trust_authority_node_count": 0,
                "confirmed_blank_preserves_source_trace": False,
                "retrieval_only_answer_allowed": False,
                "answer_capable_without_citation": False,
                "unsafe_attachment_record": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "can_mutate_source_truth": False,
                "requires_source_resolution": True,
                "requires_citation": True,
                "requires_authority_gate": True,
            }
        return self.page_records[page_id]

    def link_to_page(self, page_id: str, node_id: str, edge_type: str, properties: dict[str, Any] | None = None) -> str:
        page_node = safe_node_id("page", page_id)
        self.add_node(page_node, "Page", page_id, page_id, {"page_id": page_id, "source_truth_anchor": True})
        edge_id = self.add_edge(page_node, node_id, edge_type, page_id, properties)
        pr = self.page_record(page_id)
        pr["node_ids"].append(node_id)
        pr["edge_ids"].append(edge_id)
        return edge_id

    def finish_page_records(self) -> list[dict[str, Any]]:
        for page_id, record in self.page_records.items():
            record["node_ids"] = sorted(dict.fromkeys(record["node_ids"]))
            record["edge_ids"] = sorted(dict.fromkeys(record["edge_ids"]))
            record["planned_node_count"] = len(record["node_ids"])
            record["planned_edge_count"] = len(record["edge_ids"])
        return [self.page_records[k] for k in sorted(self.page_records)]


def add_page_registry(builder: AttachmentBuilder, registry_records: list[dict[str, Any]]) -> None:
    for rec in registry_records:
        page_id = get_page_id(rec)
        if not page_id:
            builder.quality_warnings.append("missing_page_id_in_page_registry")
            continue
        page_num = get_page_number(page_id, rec.get("page_number"))
        page_node = safe_node_id("page", page_id)
        builder.add_node(
            page_node,
            "Page",
            page_id,
            page_id,
            {
                "page_id": page_id,
                "page_number": page_num,
                "traits": rec.get("page_traits", []),
                "source_trace_present": "source_trace_present" in as_list(rec.get("page_traits")) or rec.get("source_trace_present"),
                "writeback_mode": "anchor_existing_page_node",
            },
        )
        pr = builder.page_record(page_id)
        pr["node_ids"].append(page_node)

        element_summary_id = safe_node_id("page_element_registry", page_id)
        builder.add_node(
            element_summary_id,
            "PageElementRegistry",
            node_label("PageElementRegistry", page_id),
            page_id,
            compact_props(
                rec,
                [
                    "page_traits",
                    "detected_elements",
                    "recommended_extraction_routes",
                    "candidate_bucket_counts",
                    "answer_support_candidate_count",
                    "context_v2_present",
                    "quality_status",
                ],
            ),
        )
        builder.link_to_page(page_id, element_summary_id, "HAS_PAGE_ELEMENT_REGISTRY")

        for route in as_list(rec.get("recommended_extraction_routes")):
            route_id = stable_id("extraction_route", page_id, route)
            builder.add_node(
                route_id,
                "ExtractionRoutePlan",
                node_label("ExtractionRoutePlan", page_id, str(route)),
                page_id,
                {"route": route, "authority": "routing_only"},
            )
            builder.add_edge(element_summary_id, route_id, "RECOMMENDS_EXTRACTION_ROUTE", page_id)
            pr["node_ids"].append(route_id)


def add_citation_nodes(builder: AttachmentBuilder, parent_node: str, page_id: str, citation_ids: Iterable[str]) -> None:
    pr = builder.page_record(page_id)
    for cid in sorted(dict.fromkeys(str(c) for c in citation_ids if c)):
        citation_node = safe_node_id("citation", cid)
        builder.add_node(
            citation_node,
            "Citation",
            cid,
            page_id,
            {"citation_id": cid, "authority": "source_trace_reference"},
        )
        edge_id = builder.add_edge(parent_node, citation_node, "HAS_CITATION", page_id)
        pr["node_ids"].append(citation_node)
        pr["edge_ids"].append(edge_id)
        pr["citation_node_count"] += 1


def add_trust_node(builder: AttachmentBuilder, parent_node: str, page_id: str, authority: str | None, trust_tier: str | None = None) -> None:
    if not authority and not trust_tier:
        return
    key = authority or f"trust_tier_{trust_tier}"
    trust_node = safe_node_id("trust_authority", key)
    builder.add_node(
        trust_node,
        "TrustAuthority",
        key,
        None,
        {"authority": authority, "trust_tier": trust_tier, "can_answer_directly": False},
    )
    edge_id = builder.add_edge(parent_node, trust_node, "HAS_TRUST_AUTHORITY", page_id)
    pr = builder.page_record(page_id)
    pr["node_ids"].append(trust_node)
    pr["edge_ids"].append(edge_id)
    pr["trust_authority_node_count"] += 1


def add_embedding_candidates(builder: AttachmentBuilder, candidate_records: list[dict[str, Any]]) -> None:
    for rec in candidate_records:
        page_id = get_page_id(rec)
        if not page_id:
            continue
        source_candidate_id = rec.get("source_candidate_id") or rec.get("candidate_id") or rec.get("embedding_candidate_id")
        if not source_candidate_id:
            source_candidate_id = stable_id("candidate", page_id, json.dumps(rec, sort_keys=True)[:200])
        candidate_node = safe_node_id("evidence_candidate", source_candidate_id)
        bucket = rec.get("rag_bucket") or rec.get("safety_bucket") or rec.get("bucket")
        authority = rec.get("authority")
        trust_tier = rec.get("trust_tier") or rec.get("candidate_trust_tier")
        citation_ids = get_citation_ids(rec)
        answer_support = bucket in ANSWER_SUPPORT_BUCKETS or bool(rec.get("answer_support_candidate"))
        retrieval_only = bucket in RETRIEVAL_ONLY_BUCKETS or rec.get("authority") in {"retrieval_helper_only", "page_route_only", "source_exists_only"}

        builder.add_node(
            candidate_node,
            "EvidenceCandidate",
            str(source_candidate_id),
            page_id,
            {
                "source_candidate_id": source_candidate_id,
                "embedding_candidate_id": rec.get("embedding_candidate_id"),
                "rag_bucket": bucket,
                "authority": authority,
                "trust_tier": trust_tier,
                "answer_support_candidate": answer_support,
                "retrieval_only": retrieval_only,
                "requires_source_resolution": rec.get("requires_source_resolution", True),
                "requires_citation": rec.get("requires_citation", True),
                "requires_authority_gate": rec.get("requires_authority_gate", True),
                "can_answer_directly": False,
                "can_prove_claims": False,
            },
        )
        builder.link_to_page(page_id, candidate_node, "HAS_EVIDENCE_CANDIDATE")
        pr = builder.page_record(page_id)
        pr["evidence_candidate_node_count"] += 1
        if retrieval_only and rec.get("can_answer_directly"):
            pr["retrieval_only_answer_allowed"] = True
        if answer_support and not citation_ids:
            pr["answer_capable_without_citation"] = True
        add_citation_nodes(builder, candidate_node, page_id, citation_ids)
        add_trust_node(builder, candidate_node, page_id, str(authority) if authority else None, str(trust_tier) if trust_tier else None)



def row_match_aliases(row: dict[str, Any], idx: int, table_id: str) -> list[str]:
    """Return stable aliases that may identify a table row across artifacts.

    Step 15.1 normalized rows usually expose ``normalized_row_id`` and
    ``source_row_id`` while normalized cells keep ``row_id`` as the original
    source row id.  The graph planner must match all of those forms; otherwise
    it can create row nodes but no cell nodes.
    """
    aliases: list[str] = []
    for key in ("row_id", "normalized_row_id", "source_row_id", "row_key", "id"):
        value = row.get(key)
        if value is not None and str(value):
            aliases.append(str(value))
    for key in ("row_index", "index", "row_number"):
        value = row.get(key)
        if value is not None and str(value):
            aliases.append(str(value))
            try:
                aliases.append(str(int(value)))
            except (TypeError, ValueError):
                pass
    one_based = idx + 1
    aliases.extend([
        str(idx),
        str(one_based),
        f"{table_id}:row:{one_based}",
        f"row_{one_based}",
        f"row:{one_based}",
    ])
    return sorted(dict.fromkeys(a for a in aliases if a))


def cell_match_aliases(cell: dict[str, Any]) -> list[str]:
    """Return aliases that may identify the parent row for a cell."""
    aliases: list[str] = []
    for key in ("row_id", "normalized_row_id", "source_row_id", "row_key", "parent_row_id"):
        value = cell.get(key)
        if value is not None and str(value):
            aliases.append(str(value))
    for key in ("row_index", "index", "row_number"):
        value = cell.get(key)
        if value is not None and str(value):
            aliases.append(str(value))
            try:
                aliases.append(str(int(value)))
            except (TypeError, ValueError):
                pass
    # Some cell identifiers embed the row number/id, e.g. row_12_cell_3.
    cell_id = str(cell.get("cell_id") or cell.get("normalized_cell_id") or cell.get("source_cell_id") or "")
    for pattern in (r"row[_:-]?(\d+)", r"r[_:-]?(\d+)"):
        match = re.search(pattern, cell_id, flags=re.IGNORECASE)
        if match:
            aliases.append(str(int(match.group(1))))
    return sorted(dict.fromkeys(a for a in aliases if a))


def dedupe_cells(cells: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for idx, cell in enumerate(cells):
        key = str(
            cell.get("cell_id")
            or cell.get("normalized_cell_id")
            or cell.get("source_cell_id")
            or stable_id("cell_key", cell.get("row_id"), cell.get("col_index"), cell.get("normalized_text"), idx)
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(cell)
    return sorted(out, key=lambda c: int(c.get("col_index") or c.get("column_index") or c.get("col") or 0))

def add_table_records(builder: AttachmentBuilder, table_records: list[dict[str, Any]]) -> None:
    for rec in table_records:
        page_id = get_page_id(rec)
        if not page_id:
            continue
        table_type = rec.get("table_type") or "unknown_table"
        table_id = rec.get("table_id") or rec.get("normalized_table_id") or rec.get("source_table_id") or rec.get("record_id") or stable_id("table", page_id, table_type, rec.get("source_record_id"))
        table_node = safe_node_id("table_element", table_id)
        citation_ids = get_citation_ids(rec)
        answer_support = bool(rec.get("answer_support_candidate")) or table_type not in {"unknown_table", "none"}
        builder.add_node(
            table_node,
            "TableElement",
            node_label("TableElement", page_id, str(table_type)),
            page_id,
            {
                "table_id": table_id,
                "table_type": table_type,
                "trust_tier": rec.get("trust_tier"),
                "rag_bucket": rec.get("rag_bucket"),
                "row_count": rec.get("row_count") or rec.get("normalized_row_count"),
                "cell_count": rec.get("cell_count") or rec.get("normalized_cell_count"),
                "answer_support_candidate": answer_support,
                "can_answer_directly": False,
            },
        )
        builder.link_to_page(page_id, table_node, "HAS_TABLE_ELEMENT")
        pr = builder.page_record(page_id)
        pr["table_node_count"] += 1
        if answer_support and not citation_ids:
            pr["answer_capable_without_citation"] = True
        add_citation_nodes(builder, table_node, page_id, citation_ids)
        add_trust_node(builder, table_node, page_id, rec.get("authority") or "table_structured_evidence_requires_gate", rec.get("trust_tier"))

        rows = [x for x in as_list(rec.get("rows")) if isinstance(x, dict)]
        cells = [x for x in as_list(rec.get("cells")) if isinstance(x, dict)]
        cells_by_row: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for cell in cells:
            aliases = cell_match_aliases(cell)
            if not aliases:
                aliases = ["unknown_row"]
            for alias in aliases:
                cells_by_row[alias].append(cell)

        for idx, row in enumerate(rows):
            row_id_raw = row.get("row_id") or row.get("normalized_row_id") or row.get("source_row_id") or f"{table_id}:row:{idx+1}"
            row_node = safe_node_id("table_row", row_id_raw)
            row_citations = get_citation_ids(row) or citation_ids
            row_support = bool(row.get("answer_support_candidate"))
            builder.add_node(
                row_node,
                "TableRow",
                node_label("TableRow", page_id, str(idx + 1)),
                page_id,
                {
                    "row_id": row_id_raw,
                    "row_index": row.get("row_index", idx + 1),
                    "row_type": row.get("row_type"),
                    "row_text": row.get("row_text"),
                    "answer_support_candidate": row_support,
                    "can_answer_directly": False,
                },
            )
            edge_id = builder.add_edge(table_node, row_node, "HAS_TABLE_ROW", page_id)
            pr["node_ids"].append(row_node)
            pr["edge_ids"].append(edge_id)
            pr["table_row_node_count"] += 1
            if row_support and not row_citations:
                pr["answer_capable_without_citation"] = True
            add_citation_nodes(builder, row_node, page_id, row_citations)

            row_cells: list[dict[str, Any]] = []
            for alias in row_match_aliases(row, idx, str(table_id)):
                row_cells.extend(cells_by_row.get(alias, []))
            row_cells = dedupe_cells(row_cells)
            for cell_idx, cell in enumerate(row_cells):
                cell_id_raw = cell.get("cell_id") or cell.get("normalized_cell_id") or cell.get("source_cell_id") or f"{row_id_raw}:cell:{cell_idx+1}"
                cell_node = safe_node_id("table_cell", cell_id_raw)
                builder.add_node(
                    cell_node,
                    "TableCell",
                    node_label("TableCell", page_id, str(cell_idx + 1)),
                    page_id,
                    {
                        "cell_id": cell_id_raw,
                        "text": cell.get("text") or cell.get("normalized_text") or cell.get("original_text"),
                        "cell_kind": cell.get("cell_kind") or cell.get("kind") or cell.get("normalized_kind"),
                        "column_index": cell.get("column_index") or cell.get("col_index") or cell.get("col"),
                        "confidence": cell.get("confidence"),
                        "can_answer_directly": False,
                    },
                )
                ce = builder.add_edge(row_node, cell_node, "HAS_TABLE_CELL", page_id)
                pr["node_ids"].append(cell_node)
                pr["edge_ids"].append(ce)
                pr["table_cell_node_count"] += 1

        for repair in [x for x in as_list(rec.get("repairs")) if isinstance(x, dict)]:
            repair_node = stable_id("table_cell_repair", page_id, repair.get("merged_part_number"), repair.get("source_cell_texts"))
            builder.add_node(
                repair_node,
                "TableCellRepair",
                node_label("TableCellRepair", page_id, repair.get("merged_part_number")),
                page_id,
                {
                    "source_cell_texts": repair.get("source_cell_texts"),
                    "merged_part_number": repair.get("merged_part_number"),
                    "repair_status": repair.get("repair_status"),
                    "can_answer_directly": False,
                },
            )
            re = builder.add_edge(table_node, repair_node, "HAS_TABLE_CELL_REPAIR", page_id)
            pr["node_ids"].append(repair_node)
            pr["edge_ids"].append(re)


def add_visual_records(builder: AttachmentBuilder, visual_records: list[dict[str, Any]]) -> None:
    for rec in visual_records:
        page_id = get_page_id(rec)
        if not page_id:
            continue
        visual_type = rec.get("visual_type") or "unknown_visual"
        region_count = int(rec.get("visual_region_count") or len(as_list(rec.get("visual_regions"))) or 1)
        region_count = max(region_count, 1)
        page_visual_node = safe_node_id("visual_understanding", page_id)
        builder.add_node(
            page_visual_node,
            "VisualUnderstanding",
            node_label("VisualUnderstanding", page_id, visual_type),
            page_id,
            {
                "visual_type": visual_type,
                "rag_bucket": rec.get("rag_bucket"),
                "trust_tier": rec.get("trust_tier"),
                "requires_catalog_compare": rec.get("requires_catalog_compare"),
                "needs_human_review": rec.get("needs_human_review"),
                "visual_answer_allowed": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
            },
        )
        builder.link_to_page(page_id, page_visual_node, "HAS_VISUAL_UNDERSTANDING")
        pr = builder.page_record(page_id)

        for i in range(region_count):
            region_node = safe_node_id("visual_region", f"{page_id}:{i+1:03d}")
            builder.add_node(
                region_node,
                "VisualRegion",
                node_label("VisualRegion", page_id, str(i + 1)),
                page_id,
                {
                    "region_index": i + 1,
                    "visual_type": visual_type,
                    "authority": "visual_region_retrieval_only",
                    "can_answer_directly": False,
                    "can_prove_claims": False,
                },
            )
            ve = builder.add_edge(page_visual_node, region_node, "HAS_VISUAL_REGION", page_id)
            pr["node_ids"].append(region_node)
            pr["edge_ids"].append(ve)
            pr["visual_region_node_count"] += 1

        for label in as_list(rec.get("callout_labels")):
            callout_node = stable_id("callout_candidate", page_id, label)
            builder.add_node(
                callout_node,
                "CalloutCandidate",
                node_label("CalloutCandidate", page_id, str(label)),
                page_id,
                {
                    "callout_label": label,
                    "authority": "callout_candidate_retrieval_only",
                    "can_answer_directly": False,
                    "can_prove_claims": False,
                },
            )
            edge_id = builder.add_edge(page_visual_node, callout_node, "HAS_CALLOUT_CANDIDATE", page_id)
            pr["node_ids"].append(callout_node)
            pr["edge_ids"].append(edge_id)
            pr["callout_node_count"] += 1

        for part in as_list(rec.get("linked_part_candidates")):
            part_node = safe_node_id("part_candidate", part)
            builder.add_node(
                part_node,
                "PartCandidate",
                str(part),
                None,
                {"part_candidate": part, "authority": "catalog_compare_required"},
            )
            edge_id = builder.add_edge(page_visual_node, part_node, "MAY_REFER_TO_PART", page_id, {"requires_catalog_compare": True})
            pr["node_ids"].append(part_node)
            pr["edge_ids"].append(edge_id)


def normalize_action_list(record: dict[str, Any], key: str) -> list[str]:
    values = record.get(key) or []
    out: list[str] = []
    for value in as_list(values):
        if isinstance(value, dict):
            label = value.get("action") or value.get("retry_route") or value.get("name")
        else:
            label = value
        if label:
            out.append(str(label))
    return out


def add_fishnet_records(builder: AttachmentBuilder, fishnet_records: list[dict[str, Any]]) -> None:
    action_fields = [
        ("baseline_validation_actions", "baseline_validation"),
        ("actual_retry_actions", "actual_retry"),
        ("review_actions", "review_required"),
        ("optional_enrichment_actions", "optional_enrichment"),
        ("block_or_downgrade_actions", "block_or_downgrade"),
        ("blank_handling_actions", "blank_handling"),
    ]
    for rec in fishnet_records:
        page_id = get_page_id(rec)
        if not page_id:
            continue
        disposition = rec.get("fishnet_disposition") or rec.get("disposition") or "fishnet_plan"
        fishnet_node = safe_node_id("fishnet_plan", page_id)
        builder.add_node(
            fishnet_node,
            "FishnetRetryPlan",
            node_label("FishnetRetryPlan", page_id, disposition),
            page_id,
            {
                "fishnet_disposition": disposition,
                "priority": rec.get("priority"),
                "layout_class": rec.get("layout_class"),
                "ocr_state": rec.get("ocr_state"),
                "needs_retry": rec.get("needs_retry"),
                "needs_human_review": rec.get("needs_human_review"),
                "needs_vision_model": rec.get("needs_vision_model"),
                "can_answer_directly": False,
                "can_prove_claims": False,
            },
        )
        builder.link_to_page(page_id, fishnet_node, "HAS_FISHNET_RETRY_PLAN")
        pr = builder.page_record(page_id)
        pr["fishnet_node_count"] += 1
        if disposition == "source_confirmed_blank_preserve_trace" or rec.get("ocr_state") == "source_confirmed_blank":
            pr["confirmed_blank_preserves_source_trace"] = bool(normalize_action_list(rec, "blank_handling_actions") or True)

        for field_name, severity in action_fields:
            for action in normalize_action_list(rec, field_name):
                action_node = stable_id("fishnet_action", page_id, severity, action)
                builder.add_node(
                    action_node,
                    "FishnetRetryAction",
                    node_label("FishnetRetryAction", page_id, action),
                    page_id,
                    {
                        "action": action,
                        "severity": severity,
                        "can_answer_directly": False,
                        "can_prove_claims": False,
                        "can_mutate_source_truth": False,
                    },
                )
                edge_id = builder.add_edge(fishnet_node, action_node, "HAS_FISHNET_ACTION", page_id, {"severity": severity})
                pr["node_ids"].append(action_node)
                pr["edge_ids"].append(edge_id)


def add_blank_source_trace_nodes(builder: AttachmentBuilder) -> None:
    for page_id, pr in builder.page_records.items():
        if pr.get("confirmed_blank_preserves_source_trace"):
            node_id = safe_node_id("blank_source_trace_preservation", page_id)
            builder.add_node(
                node_id,
                "BlankSourceTracePreservation",
                node_label("BlankSourceTracePreservation", page_id),
                page_id,
                {
                    "blank_policy": "source_confirmed_blank_preserve_trace",
                    "can_answer_directly": False,
                    "can_prove_claims": False,
                    "can_mutate_source_truth": False,
                },
            )
            builder.link_to_page(page_id, node_id, "HAS_BLANK_SOURCE_TRACE_PRESERVATION")


def summarize(builder: AttachmentBuilder, attachment_records: list[dict[str, Any]], source_summaries: dict[str, Any]) -> dict[str, Any]:
    node_type_counts = Counter(node["node_type"] for node in builder.nodes.values())
    edge_type_counts = Counter(edge["edge_type"] for edge in builder.edges.values())
    orphan_edges = [
        edge for edge in builder.edges.values()
        if edge["source_node_id"] not in builder.nodes or edge["target_node_id"] not in builder.nodes
    ]
    answer_capable_without_citation = sum(1 for r in attachment_records if r.get("answer_capable_without_citation"))
    retrieval_only_answer_allowed = sum(1 for r in attachment_records if r.get("retrieval_only_answer_allowed"))
    unsafe_attachment = sum(1 for r in attachment_records if r.get("unsafe_attachment_record"))
    direct_answer_allowed = sum(1 for n in builder.nodes.values() if n.get("can_answer_directly")) + sum(1 for e in builder.edges.values() if e.get("can_answer_directly"))
    claim_proof_allowed = sum(1 for n in builder.nodes.values() if n.get("can_prove_claims")) + sum(1 for e in builder.edges.values() if e.get("can_prove_claims"))
    source_truth_mutation = sum(1 for n in builder.nodes.values() if n.get("can_mutate_source_truth")) + sum(1 for e in builder.edges.values() if e.get("can_mutate_source_truth"))
    forbidden_leaks = sum(1 for n in builder.nodes.values() if any_forbidden_text(n.get("properties")))

    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "page_count": len(attachment_records),
        "node_plan_count": len(builder.nodes),
        "edge_plan_count": len(builder.edges),
        "node_type_counts": dict(sorted(node_type_counts.items())),
        "edge_type_counts": dict(sorted(edge_type_counts.items())),
        "page_node_count": node_type_counts.get("Page", 0),
        "table_node_plan_count": node_type_counts.get("TableElement", 0),
        "table_row_node_plan_count": node_type_counts.get("TableRow", 0),
        "table_cell_node_plan_count": node_type_counts.get("TableCell", 0),
        "visual_node_plan_count": node_type_counts.get("VisualUnderstanding", 0) + node_type_counts.get("VisualRegion", 0),
        "callout_node_plan_count": node_type_counts.get("CalloutCandidate", 0),
        "fishnet_node_plan_count": node_type_counts.get("FishnetRetryPlan", 0),
        "fishnet_action_node_plan_count": node_type_counts.get("FishnetRetryAction", 0),
        "evidence_candidate_node_plan_count": node_type_counts.get("EvidenceCandidate", 0),
        "citation_node_plan_count": node_type_counts.get("Citation", 0),
        "trust_authority_node_plan_count": node_type_counts.get("TrustAuthority", 0),
        "citation_edge_plan_count": edge_type_counts.get("HAS_CITATION", 0),
        "orphan_edge_count": len(orphan_edges),
        "missing_page_id_count": sum(1 for r in attachment_records if not r.get("page_id")),
        "answer_capable_without_citation_count": answer_capable_without_citation,
        "retrieval_only_answer_allowed_count": retrieval_only_answer_allowed,
        "unsafe_attachment_record_count": unsafe_attachment,
        "direct_answer_allowed_count": direct_answer_allowed,
        "claim_proof_allowed_count": claim_proof_allowed,
        "source_truth_mutation_allowed_count": source_truth_mutation,
        "forbidden_property_leak_count": forbidden_leaks,
        "confirmed_blank_pages_preserve_source_trace_count": sum(1 for r in attachment_records if r.get("confirmed_blank_preserves_source_trace")),
        "records_with_table_nodes_count": sum(1 for r in attachment_records if r.get("table_node_count", 0) > 0),
        "records_with_visual_nodes_count": sum(1 for r in attachment_records if r.get("visual_region_node_count", 0) > 0),
        "records_with_fishnet_nodes_count": sum(1 for r in attachment_records if r.get("fishnet_node_count", 0) > 0),
        "records_with_evidence_candidates_count": sum(1 for r in attachment_records if r.get("evidence_candidate_node_count", 0) > 0),
        "writeback_mode": "read_only_plan",
        "source_summaries": source_summaries,
    }


def evaluate_quality(summary: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, actual: Any = None, expected: Any = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected})

    require_page_count = thresholds.get("require_page_count")
    if require_page_count is not None:
        add("required_page_count", summary.get("page_count") == require_page_count, summary.get("page_count"), require_page_count)

    for arg_name, summary_key in [
        ("min_page_nodes", "page_node_count"),
        ("min_element_node_plans", "node_plan_count"),
        ("min_edge_plans", "edge_plan_count"),
        ("min_table_node_plans", "table_node_plan_count"),
        ("min_table_row_node_plans", "table_row_node_plan_count"),
        ("min_table_cell_node_plans", "table_cell_node_plan_count"),
        ("min_visual_node_plans", "visual_node_plan_count"),
        ("min_fishnet_node_plans", "fishnet_node_plan_count"),
        ("min_citation_edge_plans", "citation_edge_plan_count"),
        ("min_confirmed_blank_preserve_source_trace", "confirmed_blank_pages_preserve_source_trace_count"),
    ]:
        expected = thresholds.get(arg_name)
        if expected is not None:
            add(arg_name, summary.get(summary_key, 0) >= expected, summary.get(summary_key, 0), f">= {expected}")

    add("no_orphan_edges", summary.get("orphan_edge_count", 0) == 0, summary.get("orphan_edge_count", 0), 0)
    add("no_missing_page_ids", summary.get("missing_page_id_count", 0) == 0, summary.get("missing_page_id_count", 0), 0)
    add("no_answer_capable_without_citation", summary.get("answer_capable_without_citation_count", 0) == 0, summary.get("answer_capable_without_citation_count", 0), 0)
    add("no_retrieval_only_answer_allowed", summary.get("retrieval_only_answer_allowed_count", 0) == 0, summary.get("retrieval_only_answer_allowed_count", 0), 0)
    add("no_direct_answer_allowed", summary.get("direct_answer_allowed_count", 0) == 0, summary.get("direct_answer_allowed_count", 0), 0)
    add("no_claim_proof_allowed", summary.get("claim_proof_allowed_count", 0) == 0, summary.get("claim_proof_allowed_count", 0), 0)
    add("no_source_truth_mutation_allowed", summary.get("source_truth_mutation_allowed_count", 0) == 0, summary.get("source_truth_mutation_allowed_count", 0), 0)
    add("no_unsafe_attachment_records", summary.get("unsafe_attachment_record_count", 0) == 0, summary.get("unsafe_attachment_record_count", 0), 0)
    add("no_forbidden_property_leaks", summary.get("forbidden_property_leak_count", 0) == 0, summary.get("forbidden_property_leak_count", 0), 0)

    source_summaries = summary.get("source_summaries") or {}
    if thresholds.get("require_page_registry_quality_pass"):
        status = source_summaries.get("page_registry_quality_status")
        add("page_registry_quality_pass", status == "PASS", status, "PASS")
    if thresholds.get("require_fishnet_refinement_quality_pass"):
        status = source_summaries.get("fishnet_refinement_quality_status")
        add("fishnet_refinement_quality_pass", status == "PASS", status, "PASS")

    status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    return {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": status,
        "checks": checks,
        "summary": {k: summary.get(k) for k in sorted(summary) if not k.endswith("counts")},
        "created_at": utc_now(),
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True) + "\n")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    summary = report.get("summary", {})
    lines = [
        "# TRACE-Net Element-to-Graph Attachment Plan v1",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "page_count",
        "node_plan_count",
        "edge_plan_count",
        "table_node_plan_count",
        "table_row_node_plan_count",
        "table_cell_node_plan_count",
        "visual_node_plan_count",
        "fishnet_node_plan_count",
        "evidence_candidate_node_plan_count",
        "citation_edge_plan_count",
        "orphan_edge_count",
        "answer_capable_without_citation_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
        "confirmed_blank_pages_preserve_source_trace_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend([
        "",
        "## Safety Contract",
        "",
        "- This artifact is read-only and plan-only.",
        "- It does not mutate Postgres, Qdrant, source files, trust records, or source truth.",
        "- Planned retrieval-only nodes cannot answer directly.",
        "- Answer-support evidence must keep citation and authority edges.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_html(path: Path, markdown_text: str) -> None:
    body = html.escape(markdown_text).replace("\n", "<br>\n")
    path.write_text(f"<!doctype html><html><body><pre>{body}</pre></body></html>", encoding="utf-8")


def build_element_graph_attachment_plan(
    *,
    page_registry_path: str | Path,
    output_dir: str | Path,
    table_understanding_path: str | Path | None = None,
    table_cell_normalizer_path: str | Path | None = None,
    figure_chart_understanding_path: str | Path | None = None,
    fishnet_retry_refined_path: str | Path | None = None,
    embedding_candidates_path: str | Path | None = None,
    thresholds: dict[str, Any] | None = None,
    write_quality: bool = False,
) -> dict[str, Any]:
    thresholds = thresholds or {}
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    page_registry = read_json(page_registry_path, {})
    table_understanding = read_json(table_understanding_path, {})
    table_normalizer = read_json(table_cell_normalizer_path, {})
    figure_chart = read_json(figure_chart_understanding_path, {})
    fishnet_refined = read_json(fishnet_retry_refined_path, {})
    embedding_candidates = read_json(embedding_candidates_path, {})

    registry_records = records_from_payload(page_registry)
    table_records = records_from_payload(table_normalizer) or records_from_payload(table_understanding)
    visual_records = records_from_payload(figure_chart)
    fishnet_records = records_from_payload(fishnet_refined)
    candidate_records = records_from_payload(embedding_candidates)

    builder = AttachmentBuilder()
    add_page_registry(builder, registry_records)
    add_table_records(builder, table_records)
    add_visual_records(builder, visual_records)
    add_fishnet_records(builder, fishnet_records)
    add_embedding_candidates(builder, candidate_records)
    add_blank_source_trace_nodes(builder)

    attachment_records = builder.finish_page_records()
    source_summaries = {
        "page_registry_quality_status": page_registry.get("quality_status") or (page_registry.get("quality") or {}).get("status"),
        "table_understanding_quality_status": table_understanding.get("quality_status") or (table_understanding.get("quality") or {}).get("status"),
        "table_cell_normalizer_quality_status": table_normalizer.get("quality_status") or (table_normalizer.get("quality") or {}).get("status"),
        "figure_chart_understanding_quality_status": figure_chart.get("quality_status") or (figure_chart.get("quality") or {}).get("status"),
        "fishnet_refinement_quality_status": fishnet_refined.get("quality_status") or (fishnet_refined.get("quality") or {}).get("status"),
        "embedding_candidates_quality_status": embedding_candidates.get("quality_status") or (embedding_candidates.get("quality") or {}).get("status"),
    }
    summary = summarize(builder, attachment_records, source_summaries)
    quality = evaluate_quality(summary, thresholds)

    report = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "ELEMENT_GRAPH_ATTACHMENT_PLAN_BUILT",
        "quality_status": quality["status"],
        "created_at": utc_now(),
        "writeback_mode": "read_only_plan",
        "can_mutate_source_truth": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "summary": summary,
        "quality": quality,
        "records": attachment_records,
        "node_plans": [builder.nodes[k] for k in sorted(builder.nodes)],
        "edge_plans": [builder.edges[k] for k in sorted(builder.edges)],
    }

    base = output / "trace_net_element_graph_attachment_plan_v1"
    report_path = base.with_suffix(".json")
    nodes_path = output / "trace_net_element_graph_attachment_plan_v1_nodes.jsonl"
    edges_path = output / "trace_net_element_graph_attachment_plan_v1_edges.jsonl"
    records_path = output / "trace_net_element_graph_attachment_plan_v1_records.jsonl"
    summary_path = output / "trace_net_element_graph_attachment_plan_v1_summary.json"
    manifest_path = output / "trace_net_element_graph_attachment_plan_v1_manifest.json"
    quality_path = output / "trace_net_element_graph_attachment_plan_v1_quality.json"
    markdown_path = output / "trace_net_element_graph_attachment_plan_v1.md"
    html_path = output / "trace_net_element_graph_attachment_plan_v1.html"

    write_json(report_path, report)
    write_jsonl(nodes_path, report["node_plans"])
    write_jsonl(edges_path, report["edge_plans"])
    write_jsonl(records_path, attachment_records)
    write_json(summary_path, summary)
    write_json(manifest_path, {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "created_at": utc_now(),
        "report_path": str(report_path),
        "nodes_path": str(nodes_path),
        "edges_path": str(edges_path),
        "records_path": str(records_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "markdown_path": str(markdown_path),
        "html_path": str(html_path),
        "input_paths": {
            "page_registry": str(page_registry_path),
            "table_understanding": str(table_understanding_path) if table_understanding_path else None,
            "table_cell_normalizer": str(table_cell_normalizer_path) if table_cell_normalizer_path else None,
            "figure_chart_understanding": str(figure_chart_understanding_path) if figure_chart_understanding_path else None,
            "fishnet_retry_refined": str(fishnet_retry_refined_path) if fishnet_retry_refined_path else None,
            "embedding_candidates": str(embedding_candidates_path) if embedding_candidates_path else None,
        },
        "writeback_mode": "read_only_plan",
    })
    if write_quality:
        write_json(quality_path, quality)
    md_text = ""
    write_markdown(markdown_path, report)
    md_text = markdown_path.read_text(encoding="utf-8")
    write_html(html_path, md_text)

    report.update({
        "report_path": str(report_path),
        "nodes_path": str(nodes_path),
        "edges_path": str(edges_path),
        "records_path": str(records_path),
        "summary_path": str(summary_path),
        "manifest_path": str(manifest_path),
        "quality_path": str(quality_path),
        "markdown_path": str(markdown_path),
        "html_path": str(html_path),
    })
    return report


def check_quality_from_report(
    report_path: str | Path,
    thresholds: dict[str, Any] | None = None,
    write_json_flag: bool = False,
) -> dict[str, Any]:
    report = read_json(report_path, {})
    summary = report.get("summary") or {}
    quality = evaluate_quality(summary, thresholds or {})
    if write_json_flag:
        out = Path(report_path).with_name("trace_net_element_graph_attachment_plan_v1_quality.json")
        write_json(out, quality)
        quality["quality_path"] = str(out)
    return quality


def add_common_threshold_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--require-page-count", type=int, default=None)
    parser.add_argument("--min-page-nodes", type=int, default=None)
    parser.add_argument("--min-element-node-plans", type=int, default=None)
    parser.add_argument("--min-edge-plans", type=int, default=None)
    parser.add_argument("--min-table-node-plans", type=int, default=None)
    parser.add_argument("--min-table-row-node-plans", type=int, default=None)
    parser.add_argument("--min-table-cell-node-plans", type=int, default=None)
    parser.add_argument("--min-visual-node-plans", type=int, default=None)
    parser.add_argument("--min-fishnet-node-plans", type=int, default=None)
    parser.add_argument("--min-citation-edge-plans", type=int, default=None)
    parser.add_argument("--min-confirmed-blank-preserve-source-trace", type=int, default=None)
    parser.add_argument("--require-page-registry-quality-pass", action="store_true")
    parser.add_argument("--require-fishnet-refinement-quality-pass", action="store_true")


def thresholds_from_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "require_page_count": args.require_page_count,
        "min_page_nodes": args.min_page_nodes,
        "min_element_node_plans": args.min_element_node_plans,
        "min_edge_plans": args.min_edge_plans,
        "min_table_node_plans": args.min_table_node_plans,
        "min_table_row_node_plans": args.min_table_row_node_plans,
        "min_table_cell_node_plans": args.min_table_cell_node_plans,
        "min_visual_node_plans": args.min_visual_node_plans,
        "min_fishnet_node_plans": args.min_fishnet_node_plans,
        "min_citation_edge_plans": args.min_citation_edge_plans,
        "min_confirmed_blank_preserve_source_trace": args.min_confirmed_blank_preserve_source_trace,
        "require_page_registry_quality_pass": args.require_page_registry_quality_pass,
        "require_fishnet_refinement_quality_pass": args.require_fishnet_refinement_quality_pass,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Element-to-Graph Attachment Plan v1")
    parser.add_argument("--page-registry", required=True)
    parser.add_argument("--table-understanding")
    parser.add_argument("--table-cell-normalizer")
    parser.add_argument("--figure-chart-understanding")
    parser.add_argument("--fishnet-retry-refined")
    parser.add_argument("--embedding-candidates")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", action="store_true")
    add_common_threshold_args(parser)
    return parser


def quality_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Element-to-Graph Attachment Plan v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    add_common_threshold_args(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_element_graph_attachment_plan(
        page_registry_path=args.page_registry,
        table_understanding_path=args.table_understanding,
        table_cell_normalizer_path=args.table_cell_normalizer,
        figure_chart_understanding_path=args.figure_chart_understanding,
        fishnet_retry_refined_path=args.fishnet_retry_refined,
        embedding_candidates_path=args.embedding_candidates,
        output_dir=args.output_dir,
        thresholds=thresholds_from_args(args),
        write_quality=args.quality,
    )
    summary = report["summary"]
    print("TRACE-Net element-to-graph attachment plan v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "page_count",
        "node_plan_count",
        "edge_plan_count",
        "table_node_plan_count",
        "table_row_node_plan_count",
        "table_cell_node_plan_count",
        "visual_node_plan_count",
        "fishnet_node_plan_count",
        "evidence_candidate_node_plan_count",
        "citation_edge_plan_count",
        "orphan_edge_count",
        "answer_capable_without_citation_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
        "confirmed_blank_pages_preserve_source_trace_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report['report_path']}")
    print(f" nodes_path: {report['nodes_path']}")
    print(f" edges_path: {report['edges_path']}")
    if report["quality_status"] != "PASS":
        return 1
    return 0


def quality_main(argv: list[str] | None = None) -> int:
    args = quality_parser().parse_args(argv)
    quality = check_quality_from_report(args.report_path, thresholds_from_args(args), args.write_json)
    summary = read_json(args.report_path, {}).get("summary", {})
    print("TRACE-Net element-to-graph attachment plan v1 quality")
    print(f" Status: {quality['status']}")
    for key in [
        "page_count",
        "node_plan_count",
        "edge_plan_count",
        "table_node_plan_count",
        "table_row_node_plan_count",
        "table_cell_node_plan_count",
        "visual_node_plan_count",
        "fishnet_node_plan_count",
        "evidence_candidate_node_plan_count",
        "citation_edge_plan_count",
        "orphan_edge_count",
        "answer_capable_without_citation_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
        "confirmed_blank_pages_preserve_source_trace_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    if args.write_json:
        print(f" quality_path: {quality.get('quality_path')}")
    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
