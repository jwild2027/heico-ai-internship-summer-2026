#!/usr/bin/env python3
"""H30 retrieval-completion and route-specific rendering layer.

This module is read-only. It searches only existing local TRACE-Net JSON/JSONL
artifacts, calls no external service, performs no database writes, and never
promotes guidance to source truth without an explicit citation/source-trace flag.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

MODULE = "trace_net_h30_retrieval_completion_v2"
PART_RE = re.compile(r"\b\d{2,3}-\d{5}(?:-\d{3})?\b", re.I)
PAGE_RE = re.compile(r"\bt_p_[A-Za-z0-9_]+\b", re.I)

LIKELY_PATH_TOKENS = (
    "source", "citation", "ocr", "table", "ipl", "visual", "figure",
    "graph", "page", "context", "candidate", "rag", "summary",
    "nomenclature", "part", "evidence",
)
TEXT_KEYS = (
    "ocr_text", "page_text", "normalized_text", "raw_text", "text",
    "content", "snippet", "value", "normalized_value", "description",
    "summary", "v2_summary", "v3_summary",
)
PAGE_KEYS = (
    "page_id", "source_page_id", "page", "trace_page_id", "document_page_id",
)
DOCUMENT_KEYS = (
    "document", "document_id", "source_document", "manual", "manual_id",
    "source_file", "filename",
)
CONFIDENCE_KEYS = (
    "confidence", "ocr_confidence", "mean_confidence", "score",
)
ENGINE_KEYS = (
    "ocr_engine", "engine", "ocr_model", "model",
)
FIELD_KEYS = (
    "field_name", "field", "claim_type", "record_type", "candidate_type",
)


def _compact(value: Any, limit: int = 1200) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            text = str(value)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _first(row: Mapping[str, Any], keys: Sequence[str], limit: int = 1200) -> str:
    for key in keys:
        value = _compact(row.get(key), limit)
        if value:
            return value
    return ""


def _truthy(value: Any) -> bool:
    if value is True:
        return True
    return str(value or "").strip().lower() in {"1", "true", "yes", "pass", "ready"}


def _walk_records(value: Any, *, depth: int = 0, maximum_depth: int = 8) -> Iterable[Mapping[str, Any]]:
    if depth > maximum_depth:
        return
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            if isinstance(child, (Mapping, list)):
                yield from _walk_records(child, depth=depth + 1, maximum_depth=maximum_depth)
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, (Mapping, list)):
                yield from _walk_records(child, depth=depth + 1, maximum_depth=maximum_depth)


def _dedupe(rows: Iterable[Mapping[str, Any]], keys: Sequence[str]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    seen = set()
    for raw in rows:
        row = dict(raw)
        key = tuple(_compact(row.get(name), 2000).casefold() for name in keys)
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def _source_type(path: Path, row: Mapping[str, Any]) -> str:
    blob = (str(path) + " " + " ".join(str(key) for key in row.keys())).lower()
    if "ocr" in blob:
        return "ocr"
    if any(token in blob for token in ("table", "ipl", "row", "cell")):
        return "table"
    if any(token in blob for token in ("visual", "figure", "llava", "diagram", "callout")):
        return "visual"
    if any(token in blob for token in ("graph", "edge", "community", "leiden", "relationship")):
        return "graph"
    if any(token in blob for token in ("source_citation", "source-trace", "source_trace", "citation")):
        return "source_citation"
    if any(token in blob for token in ("summary", "context", "qdrant", "embedding", "rag")):
        return "semantic"
    return "record"


def _direct_scalar_blob(row: Mapping[str, Any]) -> str:
    """Return only direct scalar/list-scalar values from one record.

    Parent container objects often hold many child records. Searching their full
    recursive JSON can combine a requested part with unrelated child parts and
    make the container look entity-consistent. Record matching must therefore be
    based on direct fields only.
    """
    values = []
    for value in row.values():
        if isinstance(value, (str, int, float, bool)):
            values.append(str(value))
        elif isinstance(value, list):
            values.extend(
                str(item)
                for item in value
                if isinstance(item, (str, int, float, bool))
            )
    return " ".join(values)


def _row_parts(row: Mapping[str, Any]) -> set[str]:
    return {
        value.upper()
        for value in PART_RE.findall(_direct_scalar_blob(row))
    }


def _row_pages(row: Mapping[str, Any]) -> set[str]:
    values = set()
    for key in PAGE_KEYS:
        value = _compact(row.get(key), 300)
        values.update(PAGE_RE.findall(value))
    if values:
        return values
    # Search only direct scalar fields. Do not let a parent container inherit
    # page identifiers from multiple nested child records.
    return set(PAGE_RE.findall(_direct_scalar_blob(row)))


def _direct_ready(path: Path, row: Mapping[str, Any]) -> bool:
    explicit = any(
        _truthy(row.get(key))
        for key in (
            "citation_ready", "source_trace_ready", "direct_proof_authority",
            "source_truth", "source_truth_ready",
        )
    )
    source_file = any(
        token in str(path).lower()
        for token in ("source_citation", "source_trace", "source-truth", "source_truth")
    )
    return explicit or source_file


def _record_from_row(path: Path, row: Mapping[str, Any], source_type: str) -> Dict[str, Any]:
    pages = sorted(_row_pages(row))
    parts = sorted(_row_parts(row))
    page_id = pages[0] if pages else ""
    document = _first(row, DOCUMENT_KEYS, 600)
    text = _first(row, TEXT_KEYS, 2400)
    field_name = _first(row, FIELD_KEYS, 300) or source_type
    confidence = _first(row, CONFIDENCE_KEYS, 100)
    engine = _first(row, ENGINE_KEYS, 200)
    figure_refs = row.get("figure_refs") if isinstance(row.get("figure_refs"), list) else []
    item = _compact(row.get("item") or row.get("item_number"), 100)
    direct_ready = _direct_ready(path, row)
    return {
        "page_id": page_id,
        "document": document,
        "part_numbers": parts,
        "source_type": source_type,
        "field_name": field_name,
        "value": text,
        "snippet": text[:700],
        "confidence": confidence,
        "engine": engine,
        "figure_refs": list(figure_refs)[:8],
        "item": item,
        "source_path": str(path),
        "citation_ready": direct_ready,
        "source_trace_ready": direct_ready,
        "guidance_only": not direct_ready,
        "source_truth": direct_ready,
    }


class LocalArtifactResolver:
    """Bounded, cached resolver over the current indexed TRACE-Net artifacts."""

    def __init__(
        self,
        root: Path,
        *,
        maximum_files: int = 400,
        maximum_file_bytes: int = 96_000_000,
        maximum_records_per_file: int = 150_000,
    ) -> None:
        self.root = Path(root)
        self.maximum_files = max(1, int(maximum_files))
        self.maximum_file_bytes = max(100_000, int(maximum_file_bytes))
        self.maximum_records_per_file = max(1000, int(maximum_records_per_file))
        self._file_cache: Optional[List[Path]] = None
        self._result_cache: Dict[Tuple[Any, ...], Dict[str, Any]] = {}

    @classmethod
    def from_environment(cls) -> "LocalArtifactResolver":
        repo = Path(os.environ.get("TRACE_NET_REPO") or os.getcwd())
        root = Path(
            os.environ.get("TRACE_NET_LOCAL_ARTIFACT_ROOT")
            or repo / "local_data" / "organization" / "trace_net"
        )
        return cls(
            root,
            maximum_files=int(os.environ.get("TRACE_NET_LOCAL_RESOLVER_MAX_FILES", "400")),
            maximum_file_bytes=int(os.environ.get("TRACE_NET_LOCAL_RESOLVER_MAX_FILE_BYTES", "96000000")),
            maximum_records_per_file=int(os.environ.get("TRACE_NET_LOCAL_RESOLVER_MAX_RECORDS_PER_FILE", "150000")),
        )

    def _candidate_files(self) -> List[Path]:
        if self._file_cache is not None:
            return self._file_cache
        if not self.root.is_dir():
            self._file_cache = []
            return []
        rows: List[Tuple[int, str, Path]] = []
        for path in self.root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl", ".ndjson"}:
                continue
            low = str(path).lower()
            if not any(token in low for token in LIKELY_PATH_TOKENS):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size <= 0 or size > self.maximum_file_bytes:
                continue
            priority = 50
            for index, token in enumerate(
                ("source_citation", "source_trace", "ocr", "table", "ipl", "visual",
                 "figure", "graph", "candidate", "page", "context", "summary")
            ):
                if token in low:
                    priority = min(priority, index)
            rows.append((priority, low, path))
        rows.sort(key=lambda item: (item[0], item[1]))
        self._file_cache = [item[2] for item in rows[: self.maximum_files]]
        return self._file_cache

    def _load(self, path: Path, text: str) -> Iterable[Mapping[str, Any]]:
        if path.suffix.lower() in {".jsonl", ".ndjson"}:
            count = 0
            for line in text.splitlines():
                if count >= self.maximum_records_per_file:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except Exception:
                    continue
                for row in _walk_records(value):
                    yield row
                    count += 1
                    if count >= self.maximum_records_per_file:
                        break
            return
        try:
            value = json.loads(text)
        except Exception:
            return
        count = 0
        for row in _walk_records(value):
            yield row
            count += 1
            if count >= self.maximum_records_per_file:
                break

    def resolve(
        self,
        *,
        query: str,
        route: str,
        requested_parts: Sequence[str],
        seed_pages: Sequence[str],
        limit: int = 200,
    ) -> Dict[str, Any]:
        parts = tuple(sorted({str(value).upper() for value in requested_parts if value}))
        pages = tuple(sorted({str(value) for value in seed_pages if value}))
        key = (route, parts, pages, str(query or "")[:400], int(limit))
        if key in self._result_cache:
            return dict(self._result_cache[key])

        needles = [value.casefold() for value in parts + pages]
        candidate_files = self._candidate_files()
        navigation: List[Dict[str, Any]] = []
        ocr: List[Dict[str, Any]] = []
        aggregate: List[Dict[str, Any]] = []
        direct: List[Dict[str, Any]] = []
        visual: List[Dict[str, Any]] = []
        table: List[Dict[str, Any]] = []
        graph: List[Dict[str, Any]] = []
        scanned = 0
        matched_files = 0
        record_count = 0
        skipped_unreadable = 0

        if not needles:
            result = {
                "quality_status": "WARN",
                "reason": "no_exact_part_or_seed_page_for_local_resolution",
                "root": str(self.root),
                "candidate_file_count": len(candidate_files),
                "scanned_file_count": 0,
                "matched_file_count": 0,
                "navigation_leads": [],
                "ocr_evidence": [],
                "aggregate_records": [],
                "direct_evidence": [],
                "visual_guidance": [],
                "table_guidance": [],
                "graph_guidance": [],
                "coverage_complete_for_candidate_files": True,
                "result_was_capped": False,
            }
            self._result_cache[key] = result
            return dict(result)

        for path in candidate_files:
            scanned += 1
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                skipped_unreadable += 1
                continue
            low_text = text.casefold()
            if not any(needle in low_text for needle in needles):
                continue
            matched_files += 1
            for raw in self._load(path, text):
                row = dict(raw)
                observed_parts = _row_parts(row)
                observed_pages = _row_pages(row)
                if parts and observed_parts and observed_parts.isdisjoint(set(parts)):
                    continue
                matched_by_part = bool(parts and observed_parts.intersection(set(parts)))
                matched_by_page = bool(pages and observed_pages.intersection(set(pages)))
                if not matched_by_part and not matched_by_page:
                    continue
                source_type = _source_type(path, row)
                record = _record_from_row(path, row, source_type)
                record["match_basis"] = "exact_part" if matched_by_part else "seed_page"
                record["exact_entity_match"] = matched_by_part
                if not record["page_id"] and not record["value"]:
                    continue
                record_count += 1
                aggregate.append(record)
                if record["page_id"]:
                    navigation.append(record)
                if source_type == "ocr":
                    ocr.append(record)
                elif source_type == "visual":
                    visual.append(record)
                elif source_type == "table":
                    table.append(record)
                elif source_type == "graph":
                    graph.append(record)
                if record["citation_ready"] and record["page_id"] and record["value"]:
                    direct.append({
                        "page_id": record["page_id"],
                        "document": record["document"],
                        "field_name": record["field_name"],
                        "normalized_value": record["value"],
                        "value": record["value"],
                        "source_path": record["source_path"],
                        "source_trace_ready": True,
                        "citation_ready": True,
                        "direct_proof_authority": True,
                    })
                if record_count >= limit * 20:
                    break
            if record_count >= limit * 20:
                break

        navigation = _dedupe(navigation, ("page_id", "document", "source_type", "snippet"))
        ocr = _dedupe(ocr, ("page_id", "engine", "snippet"))
        aggregate = _dedupe(aggregate, ("page_id", "document", "source_type", "snippet"))
        direct = _dedupe(direct, ("page_id", "field_name", "normalized_value"))
        visual = _dedupe(visual, ("page_id", "snippet", "figure_refs"))
        table = _dedupe(table, ("page_id", "item", "snippet"))
        graph = _dedupe(graph, ("page_id", "snippet", "field_name"))

        unique_pages = sorted({row["page_id"] for row in aggregate if row.get("page_id")})
        unique_documents = sorted({row["document"] for row in aggregate if row.get("document")})
        source_type_counts: Dict[str, int] = {}
        for row in aggregate:
            source_type = str(row.get("source_type") or "record")
            source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1

        capped = (
            len(candidate_files) >= self.maximum_files
            or record_count >= limit * 20
            or len(aggregate) > limit
        )
        result = {
            "quality_status": "PASS",
            "root": str(self.root),
            "route": route,
            "requested_parts": list(parts),
            "seed_pages": list(pages),
            "candidate_file_count": len(candidate_files),
            "scanned_file_count": scanned,
            "matched_file_count": matched_files,
            "skipped_file_count": skipped_unreadable,
            "matched_record_count": record_count,
            "unique_page_count": len(unique_pages),
            "unique_document_count": len(unique_documents),
            "unique_pages": unique_pages[:limit],
            "unique_documents": unique_documents[:limit],
            "source_type_counts": source_type_counts,
            "navigation_leads": navigation[:limit],
            "ocr_evidence": ocr[:limit],
            "aggregate_records": aggregate[:limit],
            "direct_evidence": direct[:limit],
            "visual_guidance": visual[:limit],
            "table_guidance": table[:limit],
            "graph_guidance": graph[:limit],
            "coverage_complete_for_candidate_files": not capped,
            "result_was_capped": capped,
            "read_only": True,
            "source_truth_mutation_allowed": False,
        }
        self._result_cache[key] = result
        return dict(result)


def _seed_pages(
    envelope: Any,
    requested_parts: Sequence[str] = (),
) -> List[str]:
    """Return entity-grounded page seeds.

    Exact-part navigation must not expand every semantic hit into page-local OCR
    tokens. Direct, candidate, and visual rows may establish a page seed. Pure
    semantic guidance is intentionally excluded when an exact entity is known.
    """
    requested = {
        str(value).upper()
        for value in requested_parts
        if value
    }
    output = []
    attributes = (
        "direct_evidence",
        "candidate_evidence",
        "visual_guidance",
    )
    if not requested:
        attributes = attributes + ("semantic_guidance",)

    for attribute in attributes:
        for raw in getattr(envelope, attribute, []) or []:
            if not isinstance(raw, Mapping):
                continue
            row = dict(raw)
            observed = _row_parts(row)
            if requested and observed and observed.isdisjoint(requested):
                continue
            page = _compact(row.get("page_id"), 300)
            if page and page not in output:
                output.append(page)
    return output


def _merge_unique(target: List[Dict[str, Any]], rows: Iterable[Mapping[str, Any]], keys: Sequence[str]) -> None:
    target[:] = _dedupe(list(target) + [dict(row) for row in rows if isinstance(row, Mapping)], keys)


def merge_local_resolution(envelope: Any, resolution: Mapping[str, Any], router: Mapping[str, Any]) -> None:
    _merge_unique(
        envelope.direct_evidence,
        resolution.get("direct_evidence", []),
        ("page_id", "field_name", "normalized_value", "value"),
    )
    _merge_unique(
        envelope.visual_guidance,
        resolution.get("visual_guidance", []),
        ("page_id", "subject", "figure_refs", "part_numbers", "snippet"),
    )
    coverage = envelope.coverage if isinstance(envelope.coverage, MutableMapping) else {}
    coverage["retrieval_completion"] = {
        key: value
        for key, value in resolution.items()
        if key not in {
            "navigation_leads", "ocr_evidence", "aggregate_records",
            "direct_evidence", "visual_guidance", "table_guidance", "graph_guidance",
        }
    }
    coverage["navigation_leads"] = list(resolution.get("navigation_leads", []))
    coverage["ocr_evidence"] = list(resolution.get("ocr_evidence", []))
    coverage["aggregate_records"] = list(resolution.get("aggregate_records", []))
    coverage["table_guidance"] = list(resolution.get("table_guidance", []))
    coverage["graph_guidance"] = list(resolution.get("graph_guidance", []))
    envelope.coverage = coverage

    hints = router.get("AUTHORITY_FIELD_HINTS", set())
    compact = router["compact"]
    envelope.authority_evidence = [
        row for row in envelope.direct_evidence
        if any(hint in compact(row.get("field_name"), 300).lower() for hint in hints)
    ]


def _claim_rows(envelope: Any, claim: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    coverage = envelope.coverage if isinstance(envelope.coverage, Mapping) else {}
    direct = [dict(row) for row in envelope.direct_evidence if isinstance(row, Mapping)]
    candidates = [dict(row) for row in envelope.candidate_evidence if isinstance(row, Mapping)]
    visuals = [dict(row) for row in envelope.visual_guidance if isinstance(row, Mapping)]
    table = [dict(row) for row in coverage.get("table_guidance", []) if isinstance(row, Mapping)]
    graph = [dict(row) for row in coverage.get("graph_guidance", []) if isinstance(row, Mapping)]
    ocr = [dict(row) for row in coverage.get("ocr_evidence", []) if isinstance(row, Mapping)]
    navigation = [dict(row) for row in coverage.get("navigation_leads", []) if isinstance(row, Mapping)]
    authority = [dict(row) for row in envelope.authority_evidence if isinstance(row, Mapping)]

    def direct_fields(*markers: str) -> List[Dict[str, Any]]:
        return [
            row for row in direct
            if any(marker in _compact(row.get("field_name"), 300).lower() for marker in markers)
        ]

    if claim == "exact_identifier":
        return direct, candidates + visuals + navigation
    if claim == "nomenclature":
        return direct_fields("nomenclature", "part_name", "component_name"), table + candidates
    if claim == "relationship":
        return direct_fields("assembly", "parent", "relationship", "contains"), graph
    if claim == "visual_identity":
        return direct_fields("figure", "diagram", "callout", "visual"), visuals + navigation
    if claim == "table_value":
        return direct_fields("table", "ipl", "item", "quantity", "vendor", "nomenclature"), table
    if claim == "procedure":
        return direct_fields("procedure", "step", "remove", "install", "task"), []
    if claim == "warning":
        return direct_fields("warning", "caution", "note", "hazard", "safety"), []
    if claim == "authority":
        return authority, []
    if claim == "comparison":
        return direct, list(envelope.contradictions or [])
    if claim == "ocr":
        return [row for row in direct if "ocr" in _compact(row.get("field_name"), 300).lower()], ocr
    return [], []


def build_claim_results(atoms: Any, envelope: Any) -> Dict[str, Any]:
    claims = list(getattr(atoms, "requested_claims", []) or [])
    query = str(getattr(atoms, "latest_query", "") or "").lower()
    if "nomenclature" in query and "nomenclature" not in claims:
        claims.append("nomenclature")
    if getattr(atoms, "ocr_requested", False) and "ocr" not in claims:
        claims.append("ocr")
    order = (
        "exact_identifier", "nomenclature", "relationship", "visual_identity",
        "table_value", "procedure", "warning", "ocr", "comparison", "authority",
    )
    ordered = [claim for claim in order if claim in claims]
    output: Dict[str, Any] = {}
    for claim in ordered:
        direct, guidance = _claim_rows(envelope, claim)
        status = "DIRECT" if direct else ("GUIDANCE_ONLY" if guidance else "NOT_FOUND")
        output[claim] = {
            "claim": claim,
            "status": status,
            "direct_evidence": direct[:5],
            "guidance": guidance[:5],
            "direct_count": len(direct),
            "guidance_count": len(guidance),
            "authority_required": claim == "authority",
        }
    return output


def _lead_rows(
    envelope: Any,
    requested_parts: Sequence[str] = (),
) -> List[Dict[str, Any]]:
    coverage = envelope.coverage if isinstance(envelope.coverage, Mapping) else {}
    rows = [dict(row) for row in coverage.get("navigation_leads", []) if isinstance(row, Mapping)]
    for raw in envelope.visual_guidance or []:
        if isinstance(raw, Mapping):
            row = dict(raw)
            row.setdefault("source_type", "visual")
            row.setdefault("guidance_only", True)
            rows.append(row)
    for raw in envelope.candidate_evidence or []:
        if isinstance(raw, Mapping):
            row = dict(raw)
            row.setdefault("source_type", "candidate")
            row.setdefault("guidance_only", True)
            rows.append(row)
    for raw in envelope.semantic_guidance or []:
        if isinstance(raw, Mapping):
            row = dict(raw)
            row.setdefault("source_type", "semantic")
            row.setdefault("guidance_only", True)
            rows.append(row)

    requested = {
        str(value).upper()
        for value in requested_parts
        if value
    }
    for row in rows:
        observed = _row_parts(row)
        row["_exact_entity_match"] = bool(
            requested and observed.intersection(requested)
        )

    exact_rows = [
        row
        for row in rows
        if row.get("_exact_entity_match")
    ]
    if exact_rows:
        rows = exact_rows

    rank = {
        "source_citation": 0,
        "visual": 1,
        "table": 2,
        "ocr": 3,
        "candidate": 4,
        "semantic": 5,
        "record": 6,
    }
    rows = _dedupe(
        rows,
        ("page_id", "document", "source_type", "snippet", "subject"),
    )
    rows.sort(
        key=lambda row: (
            0 if row.get("_exact_entity_match") else 1,
            0 if row.get("citation_ready") else 1,
            rank.get(str(row.get("source_type") or "record"), 9),
            0 if row.get("figure_refs") else 1,
            _compact(row.get("page_id"), 200),
        )
    )

    # Navigation is page-oriented, so keep only the strongest row per page.
    page_best: List[Dict[str, Any]] = []
    seen_pages = set()
    for row in rows:
        page = _compact(row.get("page_id"), 200)
        if not page or page in seen_pages:
            continue
        seen_pages.add(page)
        row.pop("_exact_entity_match", None)
        page_best.append(row)
    return page_best


def render_navigation_answer(atoms: Any, envelope: Any, critic: Mapping[str, Any]) -> str:
    if envelope.direct_evidence:
        lines = ["TRACE-Net found citation-ready source-location evidence:"]
        for index, row in enumerate(envelope.direct_evidence[:8], 1):
            page = _compact(row.get("page_id"), 200) or "unknown page"
            document = _compact(row.get("document"), 500)
            value = _compact(row.get("normalized_value") or row.get("value"), 600)
            lines.append(f"- [{index}] {document + '; ' if document else ''}page {page}: {value}")
        return "\n".join(lines)

    leads = [
        row
        for row in _lead_rows(
            envelope,
            getattr(atoms, "exact_part_numbers", ()) or (),
        )
        if _compact(row.get("page_id"), 200)
    ]
    if not leads:
        return (
            "TRACE-Net did not resolve a direct source page or a matching navigation lead for the requested identifier. "
            "No source-location claim is made."
        )
    lines = ["Strongest currently resolved navigation lead(s):"]
    for row in leads[:8]:
        page = _compact(row.get("page_id"), 200)
        document = _compact(row.get("document"), 500)
        source_type = _compact(row.get("source_type"), 100) or "guidance"
        figures = row.get("figure_refs") if isinstance(row.get("figure_refs"), list) else []
        subject = _compact(row.get("subject") or row.get("snippet") or row.get("value"), 450)
        details = []
        if document:
            details.append(document)
        details.append(f"page {page}")
        if figures:
            details.append(", ".join(str(value) for value in figures[:5]))
        if subject:
            details.append(subject)
        lines.append(f"- {'; '.join(details)} — {source_type} guidance")
    lines.append(
        "These page locations are navigation guidance only. They identify where to inspect next but do not establish any technical claim."
    )
    return "\n".join(lines)


def render_ocr_answer(atoms: Any, envelope: Any, critic: Mapping[str, Any]) -> str:
    coverage = envelope.coverage if isinstance(envelope.coverage, Mapping) else {}
    rows = [dict(row) for row in coverage.get("ocr_evidence", []) if isinstance(row, Mapping)]
    if not rows:
        pages = []
        for row in _lead_rows(
            envelope,
            getattr(atoms, "exact_part_numbers", ()) or (),
        ):
            page = _compact(row.get("page_id"), 200)
            if page and page not in pages:
                pages.append(page)
        lines = ["TRACE-Net did not resolve a matching OCR record from the current indexed OCR artifacts."]
        if pages:
            lines.append("Pages available for an OCR retry or visual inspection: " + ", ".join(pages[:8]) + ".")
        lines.append("Semantic or visual page leads are not readable OCR text and were not reported as recovered labels.")
        return "\n".join(lines)

    lines = ["OCR recovery results from indexed OCR records:"]
    for row in rows[:8]:
        page = _compact(row.get("page_id"), 200) or "unknown page"
        engine = _compact(row.get("engine"), 150)
        confidence = _compact(row.get("confidence"), 100)
        snippet = _compact(row.get("snippet") or row.get("value"), 500)
        metadata = [f"page {page}"]
        if engine:
            metadata.append(f"engine {engine}")
        if confidence:
            metadata.append(f"confidence {confidence}")
        role = "citation-ready" if row.get("citation_ready") else "guidance-only"
        lines.append(f"- {'; '.join(metadata)}; {role}: {snippet or '[no readable text stored]'}")
    lines.append(
        "OCR text remains uncertain unless the record is explicitly source-trace-ready. Unclear characters, labels, or callouts are not silently corrected."
    )
    return "\n".join(lines)


def render_aggregation_answer(atoms: Any, envelope: Any, critic: Mapping[str, Any]) -> str:
    coverage = envelope.coverage if isinstance(envelope.coverage, Mapping) else {}
    local = coverage.get("retrieval_completion", {}) if isinstance(coverage.get("retrieval_completion"), Mapping) else {}
    rows = [dict(row) for row in coverage.get("aggregate_records", []) if isinstance(row, Mapping)]
    if not rows:
        for row in _lead_rows(
            envelope,
            getattr(atoms, "exact_part_numbers", ()) or (),
        ):
            rows.append({
                "page_id": _compact(row.get("page_id"), 200),
                "document": _compact(row.get("document"), 500),
                "source_type": _compact(row.get("source_type"), 100) or "guidance",
                "snippet": _compact(row.get("snippet") or row.get("subject"), 300),
            })
    rows = _dedupe(rows, ("page_id", "document", "source_type", "snippet"))
    pages = sorted({_compact(row.get("page_id"), 200) for row in rows if _compact(row.get("page_id"), 200)})
    documents = sorted({_compact(row.get("document"), 500) for row in rows if _compact(row.get("document"), 500)})
    types: Dict[str, int] = {}
    for row in rows:
        key = _compact(row.get("source_type"), 100) or "guidance"
        types[key] = types.get(key, 0) + 1

    lines = ["Indexed TRACE-Net coverage summary:"]
    lines.append(f"- Unique matching pages currently resolved: {len(pages)}")
    lines.append(f"- Unique matching documents currently resolved: {len(documents)}")
    if types:
        lines.append("- Evidence-family counts: " + ", ".join(f"{key}={value}" for key, value in sorted(types.items())))
    if local:
        lines.append(
            f"- Local artifact files scanned: {local.get('scanned_file_count', 0)}; "
            f"files containing the requested entity/page: {local.get('matched_file_count', 0)}"
        )
        lines.append(
            "- Coverage status: "
            + ("complete for the bounded candidate artifact set" if local.get("coverage_complete_for_candidate_files") else "capped or incomplete")
        )
    if rows:
        lines.append("Resolved page coverage:")
        for row in rows[:12]:
            page = _compact(row.get("page_id"), 200) or "unknown page"
            document = _compact(row.get("document"), 500)
            source_type = _compact(row.get("source_type"), 100) or "guidance"
            lines.append(f"- {document + '; ' if document else ''}page {page} — {source_type}")
    else:
        lines.append("- No matching indexed artifact records were resolved.")
    lines.append(
        "This is coverage of the currently indexed TRACE-Net artifact set, not an unqualified claim that every page in all external or not-yet-indexed manuals was searched."
    )
    return "\n".join(lines)


CLAIM_LABELS = {
    "exact_identifier": "Exact part identity",
    "nomenclature": "Nomenclature",
    "relationship": "Parent assembly / relationships",
    "visual_identity": "Figure / diagram",
    "table_value": "IPL / table row",
    "procedure": "Procedure",
    "warning": "Warnings / cautions / notes",
    "ocr": "OCR recovery",
    "comparison": "Cross-source comparison",
    "authority": "Replacement / applicability authority",
}


def _summarize_claim_row(row: Mapping[str, Any]) -> str:
    page = _compact(row.get("page_id"), 160)
    document = _compact(row.get("document"), 300)
    value = _compact(
        row.get("normalized_value") or row.get("value") or row.get("snippet")
        or row.get("subject") or row.get("candidate_value") or row.get("candidate_part_number"),
        420,
    )
    parts = []
    if document:
        parts.append(document)
    if page:
        parts.append(f"page {page}")
    if value:
        parts.append(value)
    return "; ".join(parts) or "matching guidance record"


def render_claim_results(atoms: Any, envelope: Any, critic: Mapping[str, Any]) -> str:
    coverage = envelope.coverage if isinstance(envelope.coverage, Mapping) else {}
    results = coverage.get("claim_results", {}) if isinstance(coverage.get("claim_results"), Mapping) else {}
    if not results:
        return "TRACE-Net decomposed the request, but no claim-level evidence buckets were produced. No technical claim is made."
    lines = ["Claim-by-claim result:"]
    for claim, result in results.items():
        label = CLAIM_LABELS.get(claim, claim.replace("_", " ").title())
        status = str(result.get("status") or "NOT_FOUND")
        direct = result.get("direct_evidence") if isinstance(result.get("direct_evidence"), list) else []
        guidance = result.get("guidance") if isinstance(result.get("guidance"), list) else []
        if status == "DIRECT" and direct:
            lines.append(f"- {label}: citation-ready evidence found.")
            for row in direct[:2]:
                if isinstance(row, Mapping):
                    lines.append(f"  - {_summarize_claim_row(row)}")
        elif status == "GUIDANCE_ONLY" and guidance:
            lines.append(f"- {label}: guidance found, but not direct proof.")
            for row in guidance[:2]:
                if isinstance(row, Mapping):
                    lines.append(f"  - {_summarize_claim_row(row)}")
        else:
            if claim == "authority":
                lines.append(f"- {label}: no explicit authority evidence found; approval or interchangeability is not confirmed.")
            else:
                lines.append(f"- {label}: not resolved from citation-ready evidence.")
    lines.append(
        "Each claim is evaluated separately. Evidence for a figure, candidate, OCR label, or shared part family cannot satisfy a different claim such as nomenclature, table value, parent assembly, or replacement authority."
    )
    return "\n".join(lines)


def install_retrieval_completion(router: MutableMapping[str, Any]) -> None:
    """Install wrappers into the already-defined cognitive-router module."""
    if router.get("_H30_RETRIEVAL_COMPLETION_V2_INSTALLED"):
        return
    runtime_cls = router["CognitiveRuntime"]
    original_init = runtime_cls.__init__
    original_gather = runtime_cls.gather_initial
    original_repair = runtime_cls.repair
    original_render = runtime_cls.render
    original_process = runtime_cls.process
    original_health = runtime_cls.health
    original_extract = router["extract_query_atoms"]

    def extract_query_atoms_v2(query: str) -> Any:
        atoms = original_extract(query)
        low = str(query or "").lower()
        if any(phrase in low for phrase in ("nomenclature", "part name", "component name")):
            if "nomenclature" not in atoms.requested_claims:
                atoms.requested_claims.append("nomenclature")
        if atoms.ocr_requested and "ocr" not in atoms.requested_claims:
            atoms.requested_claims.append("ocr")
        material_claims = set(atoms.requested_claims)
        # OCR requests commonly contain visual wording such as "read the image".
        # OCR and visual_identity are overlapping retrieval clues here, not two
        # independent user claims. Preserve the dedicated OCR route.
        if atoms.ocr_requested:
            material_claims.discard("visual_identity")
        atoms.multi_question = len(material_claims) >= 2 and any(
            connector in low for connector in (" and ", ";", " also ", " then ", " plus ")
        )
        return atoms

    router["extract_query_atoms"] = extract_query_atoms_v2

    def init_v2(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        self._h30_local_artifact_resolver = LocalArtifactResolver.from_environment()

    def complete(self: Any, plan: Any, atoms: Any, envelope: Any) -> None:
        route = plan.primary_route
        if not getattr(atoms, "exact_part_numbers", None) and route not in {
            "document_page_navigation", "ocr_scan_recovery",
            "high_degree_entity_aggregation", "multi_question_research",
        }:
            return
        resolution = self._h30_local_artifact_resolver.resolve(
            query=atoms.latest_query,
            route=route,
            requested_parts=atoms.exact_part_numbers,
            seed_pages=_seed_pages(
                envelope,
                getattr(atoms, "exact_part_numbers", ()) or (),
            ),
            limit=250,
        )
        merge_local_resolution(envelope, resolution, router)
        envelope.direct_evidence[:] = router["unique_dicts"](
            envelope.direct_evidence,
            ("page_id", "field_name", "normalized_value", "value"),
        )
        envelope.visual_guidance[:] = router["unique_dicts"](
            envelope.visual_guidance,
            ("page_id", "subject", "figure_refs", "part_numbers", "snippet"),
        )
        router["apply_exact_entity_gate"](envelope, atoms)
        envelope.coverage["claim_results"] = build_claim_results(atoms, envelope)
        envelope.coverage.update({
            "direct_evidence_count": len(envelope.direct_evidence),
            "candidate_evidence_count": len(envelope.candidate_evidence),
            "visual_guidance_count": len(envelope.visual_guidance),
            "semantic_guidance_count": len(envelope.semantic_guidance),
            "authority_evidence_count": len(envelope.authority_evidence),
            "ocr_evidence_count": len(envelope.coverage.get("ocr_evidence", [])),
            "aggregate_record_count": len(envelope.coverage.get("aggregate_records", [])),
            "navigation_lead_count": len(envelope.coverage.get("navigation_leads", [])),
            "claim_bucket_count": len(envelope.coverage.get("claim_results", {})),
        })

    def gather_v2(self: Any, plan: Any, atoms: Any) -> Any:
        envelope = original_gather(self, plan, atoms)
        route = plan.primary_route
        if route == "document_page_navigation" and atoms.exact_part_numbers:
            for part in atoms.exact_part_numbers[:2]:
                self.add_unified(
                    envelope,
                    f"Find the strongest source page, figure, and document location for exact part {part}",
                    "navigation_exact_source_fallback",
                )
                self.add_unified(
                    envelope,
                    f"Find diagram for part {part}",
                    "navigation_visual_fallback",
                )
                self.add_guided(
                    envelope,
                    f"The P/N contains {part}.",
                    atoms,
                    "navigation_candidate_page_fallback",
                )
        if atoms.exact_part_numbers and route in {
            "document_page_navigation", "ocr_scan_recovery",
            "high_degree_entity_aggregation", "multi_question_research",
            "exact_identifier_lookup", "exact_table_ipl_lookup",
        }:
            for part in atoms.exact_part_numbers[:1]:
                self.add_unified(
                    envelope,
                    f"Resolve exact citation-ready source fields, page, document, OCR, table, and figure evidence for part {part}",
                    "direct_source_resolution_v2",
                )
        complete(self, plan, atoms, envelope)
        return envelope

    def repair_v2(self: Any, plan: Any, atoms: Any, envelope: Any, critic: Mapping[str, Any]) -> None:
        original_repair(self, plan, atoms, envelope, critic)
        complete(self, plan, atoms, envelope)

    def render_v2(self: Any, plan: Any, atoms: Any, envelope: Any, critic: Mapping[str, Any]) -> str:
        route = plan.primary_route
        if route == "document_page_navigation":
            return render_navigation_answer(atoms, envelope, critic)
        if route == "ocr_scan_recovery":
            return render_ocr_answer(atoms, envelope, critic)
        if route == "high_degree_entity_aggregation":
            return render_aggregation_answer(atoms, envelope, critic)
        if route == "multi_question_research":
            return render_claim_results(atoms, envelope, critic)
        return original_render(self, plan, atoms, envelope, critic)

    def process_v2(self: Any, payload: Mapping[str, Any]) -> Dict[str, Any]:
        result = original_process(self, payload)
        envelope = result.get("evidence_envelope") if isinstance(result.get("evidence_envelope"), Mapping) else {}
        coverage = envelope.get("coverage") if isinstance(envelope.get("coverage"), Mapping) else {}
        result["retrieval_completion"] = coverage.get("retrieval_completion", {})
        result["claim_results"] = coverage.get("claim_results", {})
        result["navigation_leads"] = coverage.get("navigation_leads", [])
        result["ocr_evidence"] = coverage.get("ocr_evidence", [])
        result["aggregate_records"] = coverage.get("aggregate_records", [])
        return result

    def health_v2(self: Any) -> Dict[str, Any]:
        result = original_health(self)
        result.update({
            "retrieval_completion_v2": True,
            "local_artifact_resolver_root": str(self._h30_local_artifact_resolver.root),
            "navigation_fallback_connected": True,
            "ocr_artifact_resolution_connected": True,
            "aggregation_coverage_connected": True,
            "claim_level_rendering_connected": True,
            "route_specific_clue_rendering_expected": True,
        })
        return result

    runtime_cls.__init__ = init_v2
    runtime_cls.gather_initial = gather_v2
    runtime_cls.repair = repair_v2
    runtime_cls.render = render_v2
    runtime_cls.process = process_v2
    runtime_cls.health = health_v2
    router["_H30_RETRIEVAL_COMPLETION_V2_INSTALLED"] = True
