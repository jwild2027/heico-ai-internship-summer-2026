"""TRACE-Net table tile text classifier/refiner v1.

This module refines the output of the TRACE-Net table tile text extractor.
It is intentionally deterministic and dependency-light. It reads tile-level
text records, classifies extracted tokens, separates true part-number evidence
from ATA/index/page/date/noise tokens, validates against the part catalog when
available, and writes a refined table-tile evidence layer.

The goal is not final row reconstruction. The goal is to make tile text safer
and cleaner before it is fed back into Evidence Consensus and the graph.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import webbrowser
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_EXPORT_DIR = Path("local_data/organization/export")
DEFAULT_TABLE_TILE_TEXT_DIR = Path("local_data/organization/table_extraction/table_tile_text")
DEFAULT_OUTPUT_DIR = Path("local_data/organization/table_extraction/table_tile_text_refined")

INPUT_RECORDS_FILE = "table_tile_text_records.jsonl"
REFINED_RECORDS_FILE = "table_tile_text_refined_records.jsonl"
SUMMARY_FILE = "table_tile_text_refined_summary.json"
CORPUS_MD_FILE = "table_tile_text_refined_corpus.md"
GRAPH_NODES_FILE = "table_tile_text_refined_graph_nodes.json"
GRAPH_EDGES_FILE = "table_tile_text_refined_graph_edges.json"
REVIEW_MD_FILE = "table_tile_text_refined_review.md"
REVIEW_HTML_FILE = "table_tile_text_refined_review.html"
QUALITY_FILE = "table_tile_text_refined_quality.json"

ATA_CODE_RE = re.compile(r"^\d{2}-\d{2}-\d{2}$")
ATA_CODE_SCAN_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
DATE_RE = re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}/\d{2}\b", re.I)
PAGE_REF_RE = re.compile(r"^(?:page\s*)?\d{1,4}(?:/\d{1,4})?$", re.I)
STRONG_DASH_PART_RE = re.compile(r"^\d{3}-\d{4,6}-[A-Z0-9]{2,4}$", re.I)
STRONG_TP_PART_RE = re.compile(r"^\d{2,4}TP\d{4,8}[A-Z0-9.\-]*$", re.I)
ALPHA_PART_RE = re.compile(r"^[A-Z]{1,4}\d{2,6}[A-Z0-9.\-]{1,}$", re.I)
SHORT_SECTION_LABEL_RE = re.compile(r"^\d{2}-[A-Z0-9]{2,12}$", re.I)
NUMERIC_DASH_RE = re.compile(r"^\d+(?:-\d+)+$")

INDEX_WORDS = {
    "INDEX",
    "NUMERICAL",
    "VENDOR",
    "VENDORS",
    "APPLICABILITY",
    "EFFECTIVITY",
    "IPL",
    "IFL",
    "PARTS",
    "LIST",
    "REVISION",
    "REVISIONS",
    "EFFECTIVE",
}

# Extra token scan catches obvious part-number-like strings that may be present
# in text even if the upstream part_numbers array was noisy or incomplete.
PART_SCAN_RE = re.compile(
    r"\b(?:\d{3}-\d{4,6}-[A-Z0-9]{2,4}|\d{2,4}TP\d{4,8}[A-Z0-9.\-]*|[A-Z]{1,4}\d{2,6}[A-Z0-9.\-]{1,})\b",
    re.I,
)


@dataclass(frozen=True)
class TableTileTextRefinerPaths:
    export_dir: Path = DEFAULT_EXPORT_DIR
    input_dir: Path = DEFAULT_TABLE_TILE_TEXT_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    input_records_path: Path | None = None
    part_tree_path: Path | None = None
    refined_records_path: Path | None = None
    summary_path: Path | None = None
    corpus_md_path: Path | None = None
    graph_nodes_path: Path | None = None
    graph_edges_path: Path | None = None
    review_md_path: Path | None = None
    review_html_path: Path | None = None
    quality_path: Path | None = None

    @property
    def input_records(self) -> Path:
        return self.input_records_path or (self.input_dir / INPUT_RECORDS_FILE)

    @property
    def part_tree(self) -> Path:
        return self.part_tree_path or (self.export_dir / "part_tree.json")

    @property
    def refined_records(self) -> Path:
        return self.refined_records_path or (self.output_dir / REFINED_RECORDS_FILE)

    @property
    def summary(self) -> Path:
        return self.summary_path or (self.output_dir / SUMMARY_FILE)

    @property
    def corpus_md(self) -> Path:
        return self.corpus_md_path or (self.output_dir / CORPUS_MD_FILE)

    @property
    def graph_nodes(self) -> Path:
        return self.graph_nodes_path or (self.output_dir / GRAPH_NODES_FILE)

    @property
    def graph_edges(self) -> Path:
        return self.graph_edges_path or (self.output_dir / GRAPH_EDGES_FILE)

    @property
    def review_md(self) -> Path:
        return self.review_md_path or (self.output_dir / REVIEW_MD_FILE)

    @property
    def review_html(self) -> Path:
        return self.review_html_path or (self.output_dir / REVIEW_HTML_FILE)

    @property
    def quality(self) -> Path:
        return self.quality_path or (self.output_dir / QUALITY_FILE)


@dataclass
class TableTileTextRefinerOptions:
    max_records: int | None = None
    page_id: str | None = None
    open_review: bool = False
    include_text_scan_tokens: bool = True


@dataclass
class ClassifiedToken:
    token: str
    normalized: str
    token_type: str
    catalog_supported: bool = False
    confidence: str = "low"
    reasons: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RefinedTileTextRecord:
    page_id: str
    tile_id: str
    tile_index: int
    status: str
    provider: str
    model: str
    source_record_status: str
    text: str
    text_chars: int
    tile_path: str = ""
    source_url: str = ""
    tiff_path: str = ""
    ocr_path: str = ""
    classified_tokens: list[dict[str, Any]] = field(default_factory=list)
    canonical_part_numbers: list[str] = field(default_factory=list)
    catalog_supported_part_numbers: list[str] = field(default_factory=list)
    probable_part_numbers: list[str] = field(default_factory=list)
    unsupported_part_candidates: list[str] = field(default_factory=list)
    ata_codes: list[str] = field(default_factory=list)
    index_labels: list[str] = field(default_factory=list)
    page_references: list[str] = field(default_factory=list)
    date_tokens: list[str] = field(default_factory=list)
    noise_tokens: list[str] = field(default_factory=list)
    filtered_non_part_tokens: list[str] = field(default_factory=list)
    part_number_source: str = ""
    classification_trust_tier: str = "C"
    rag_action: str = "exclude_from_rag"
    repair_action: str = "review_table_tile_text"
    review_action: str = "human_review"
    refinement_reasons: list[str] = field(default_factory=list)
    source_record: dict[str, Any] = field(default_factory=dict)
    trace_net_table_tile_text_refiner_version: str = "trace_net_table_tile_text_refiner_v1"

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, Mapping):
                rows.append(dict(value))
    return rows


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _norm_part(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _slug(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", _text(value).lower()).strip("_")
    return text or "unknown"


def _iter_values(value: Any) -> Iterable[Any]:
    if isinstance(value, Mapping):
        for k, v in value.items():
            yield k
            yield from _iter_values(v)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_values(item)
    else:
        yield value


def _catalog_part_set(part_tree: Any) -> set[str]:
    parts: set[str] = set()
    for value in _iter_values(part_tree):
        text = _text(value)
        if not text:
            continue
        for match in PART_SCAN_RE.finditer(text):
            parts.add(_norm_part(match.group(0)))
    return parts


def _unique_keep_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _text(value).strip(".,;:()[]{}\"'")
        if not text:
            continue
        key = text.upper()
        if key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _candidate_tokens_from_record(record: Mapping[str, Any], include_text_scan_tokens: bool = True) -> list[str]:
    tokens: list[str] = []
    for key in ("part_like_strings", "part_numbers", "catalog_supported_part_numbers", "unsupported_part_numbers"):
        for item in _as_list(record.get(key)):
            tokens.append(_text(item))
    if include_text_scan_tokens:
        for match in PART_SCAN_RE.finditer(_text(record.get("text"))):
            tokens.append(match.group(0))
        # Add common labels that should be filtered, even if upstream considered them parts.
        for match in re.finditer(r"\b\d{2}-(?:Numerical|Vendors?|Applicability|IPL|IFL|Parts|List)\b", _text(record.get("text")), re.I):
            tokens.append(match.group(0))
        for match in ATA_CODE_SCAN_RE.finditer(_text(record.get("text"))):
            tokens.append(match.group(0))
    return _unique_keep_order(tokens)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_token(token: str, catalog_parts: set[str]) -> ClassifiedToken:
    raw = _text(token).strip(".,;:()[]{}\"'")
    upper = raw.upper()
    normalized = _norm_part(raw)
    reasons: list[str] = []

    if not raw:
        return ClassifiedToken(token=raw, normalized="", token_type="noise", confidence="low", reasons=["empty_token"])

    if ATA_CODE_RE.match(upper):
        return ClassifiedToken(token=raw, normalized=normalized, token_type="ata_code", confidence="high", reasons=["matches_ata_code_pattern"])

    if DATE_RE.search(raw):
        return ClassifiedToken(token=raw, normalized=normalized, token_type="date", confidence="high", reasons=["matches_date_pattern"])

    words = set(re.split(r"[^A-Z0-9]+", upper))
    if words & INDEX_WORDS:
        return ClassifiedToken(token=raw, normalized=normalized, token_type="index_label", confidence="high", reasons=["contains_index_or_section_word"])

    if SHORT_SECTION_LABEL_RE.match(upper) and not STRONG_DASH_PART_RE.match(upper):
        # 20-IFL, 25-NUMERICAL, 25-VENDORS, etc. are page/index labels, not part numbers.
        suffix = upper.split("-", 1)[1]
        if suffix.isalpha() or len(suffix) <= 12:
            return ClassifiedToken(token=raw, normalized=normalized, token_type="index_label", confidence="medium", reasons=["short_section_label_pattern"])

    if PAGE_REF_RE.match(upper):
        return ClassifiedToken(token=raw, normalized=normalized, token_type="page_reference", confidence="medium", reasons=["page_reference_pattern"])

    if NUMERIC_DASH_RE.match(upper) and len(upper) <= 8:
        return ClassifiedToken(token=raw, normalized=normalized, token_type="noise", confidence="medium", reasons=["short_numeric_dash_marker"])

    catalog_supported = normalized in catalog_parts if normalized else False
    strong_part = bool(STRONG_DASH_PART_RE.match(upper) or STRONG_TP_PART_RE.match(upper) or ALPHA_PART_RE.match(upper))

    if catalog_supported:
        reasons.append("normalized_token_found_in_part_tree")
        if strong_part:
            reasons.append("strong_part_number_pattern")
        return ClassifiedToken(
            token=raw,
            normalized=normalized,
            token_type="catalog_supported_part_number",
            catalog_supported=True,
            confidence="high",
            reasons=reasons,
        )

    if strong_part:
        return ClassifiedToken(
            token=raw,
            normalized=normalized,
            token_type="unsupported_part_candidate",
            catalog_supported=False,
            confidence="medium",
            reasons=["strong_part_number_pattern_not_found_in_catalog"],
        )

    return ClassifiedToken(token=raw, normalized=normalized, token_type="noise", confidence="low", reasons=["no_part_or_index_pattern_match"])


def classify_record(record: Mapping[str, Any], catalog_parts: set[str], include_text_scan_tokens: bool = True) -> RefinedTileTextRecord:
    classified = [classify_token(token, catalog_parts) for token in _candidate_tokens_from_record(record, include_text_scan_tokens)]
    by_type: dict[str, list[ClassifiedToken]] = {}
    for item in classified:
        by_type.setdefault(item.token_type, []).append(item)

    catalog_supported = _unique_keep_order(item.token for item in by_type.get("catalog_supported_part_number", []))
    unsupported_candidates = _unique_keep_order(item.token for item in by_type.get("unsupported_part_candidate", []))
    canonical_parts = _unique_keep_order([*catalog_supported, *unsupported_candidates])
    probable_parts = unsupported_candidates[:]
    ata_codes = _unique_keep_order(item.token for item in by_type.get("ata_code", []))
    index_labels = _unique_keep_order(item.token for item in by_type.get("index_label", []))
    page_refs = _unique_keep_order(item.token for item in by_type.get("page_reference", []))
    date_tokens = _unique_keep_order(item.token for item in by_type.get("date", []))
    noise = _unique_keep_order(item.token for item in by_type.get("noise", []))
    filtered_non_parts = _unique_keep_order([*ata_codes, *index_labels, *page_refs, *date_tokens, *noise])

    source_status = _text(record.get("status"), "unknown").lower()
    text = _text(record.get("text"))
    reasons: list[str] = []

    if catalog_supported:
        tier = "B"
        rag = "include_as_derived_context"
        repair = "reconstruct_table_rows"
        review = "optional_review"
        reasons.append("catalog_supported_part_numbers_found")
    elif unsupported_candidates:
        tier = "C"
        rag = "exclude_from_rag"
        repair = "ocr_catalog_validation"
        review = "human_review"
        reasons.append("only_unsupported_part_candidates_found")
    elif text.strip():
        tier = "C"
        rag = "exclude_from_rag"
        repair = "review_table_tile_text"
        review = "human_review"
        reasons.append("text_found_without_catalog_supported_parts")
    elif source_status in {"error"}:
        tier = "D"
        rag = "exclude_from_rag"
        repair = "retry_or_review_tile_ocr"
        review = "human_review"
        reasons.append("source_record_error")
    else:
        tier = "C"
        rag = "exclude_until_table_text_exists"
        repair = "run_table_tile_ocr"
        review = "human_review"
        reasons.append("no_useful_tile_text")

    if filtered_non_parts:
        reasons.append("filtered_non_part_tokens")
    if index_labels:
        reasons.append("index_labels_detected")
    if ata_codes:
        reasons.append("ata_codes_detected")

    return RefinedTileTextRecord(
        page_id=_text(record.get("page_id")),
        tile_id=_text(record.get("tile_id")),
        tile_index=int(record.get("tile_index", 0) or 0),
        status="ok" if source_status in {"ok", "planned", "empty"} else source_status,
        provider=_text(record.get("provider")),
        model=_text(record.get("model")),
        source_record_status=source_status,
        text=text,
        text_chars=len(text),
        tile_path=_text(record.get("tile_path")),
        source_url=_text(record.get("source_url")),
        tiff_path=_text(record.get("tiff_path")),
        ocr_path=_text(record.get("ocr_path")),
        classified_tokens=[item.to_json() for item in classified],
        canonical_part_numbers=canonical_parts,
        catalog_supported_part_numbers=catalog_supported,
        probable_part_numbers=probable_parts,
        unsupported_part_candidates=unsupported_candidates,
        ata_codes=ata_codes,
        index_labels=index_labels,
        page_references=page_refs,
        date_tokens=date_tokens,
        noise_tokens=noise,
        filtered_non_part_tokens=filtered_non_parts,
        part_number_source="tile_text_refined",
        classification_trust_tier=tier,
        rag_action=rag,
        repair_action=repair,
        review_action=review,
        refinement_reasons=reasons,
        source_record=dict(record),
    )


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


def build_refined_graph(records: Sequence[RefinedTileTextRecord]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = [
        {"id": "trace_net_table_tile_text_refiner_run", "type": "table_tile_text_refiner_run", "label": "TRACE-Net table tile text refiner"}
    ]
    edges: list[dict[str, Any]] = []
    for record in records:
        page_node = f"page:{record.page_id}"
        tile_text_node = f"table_tile_text:{record.tile_id}"
        refined_node = f"table_tile_text_refined:{record.tile_id}"
        nodes.append({"id": page_node, "type": "page", "page_id": record.page_id})
        nodes.append({"id": tile_text_node, "type": "table_tile_text", "tile_id": record.tile_id, "page_id": record.page_id})
        nodes.append(
            {
                "id": refined_node,
                "type": "table_tile_text_refined",
                "tile_id": record.tile_id,
                "page_id": record.page_id,
                "trust_tier": record.classification_trust_tier,
                "rag_action": record.rag_action,
                "canonical_part_numbers": record.canonical_part_numbers,
                "catalog_supported_part_numbers": record.catalog_supported_part_numbers,
                "index_labels": record.index_labels,
                "ata_codes": record.ata_codes,
            }
        )
        edges.append({"source": page_node, "target": refined_node, "type": "HAS_REFINED_TABLE_TILE_TEXT"})
        edges.append({"source": tile_text_node, "target": refined_node, "type": "REFINED_AS"})
        edges.append({"source": refined_node, "target": "trace_net_table_tile_text_refiner_run", "type": "DERIVED_FROM"})
        for part in record.catalog_supported_part_numbers[:30]:
            part_node = f"part:{_slug(part)}"
            nodes.append({"id": part_node, "type": "part", "label": part, "normalized_part": _norm_part(part)})
            edges.append({"source": refined_node, "target": part_node, "type": "CATALOG_SUPPORTED_PART"})
        for part in record.unsupported_part_candidates[:30]:
            part_node = f"part_candidate:{_slug(part)}"
            nodes.append({"id": part_node, "type": "part_candidate", "label": part, "normalized_part": _norm_part(part)})
            edges.append({"source": refined_node, "target": part_node, "type": "UNSUPPORTED_PART_CANDIDATE"})
        for label in record.index_labels[:20]:
            label_node = f"index_label:{_slug(label)}"
            nodes.append({"id": label_node, "type": "index_label", "label": label})
            edges.append({"source": refined_node, "target": label_node, "type": "HAS_INDEX_LABEL"})
    dedup: dict[str, dict[str, Any]] = {}
    for node in nodes:
        node_id = _text(node.get("id"))
        if node_id:
            dedup[node_id] = node
    return list(dedup.values()), edges


def build_refined_summary(records: Sequence[RefinedTileTextRecord], nodes: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(r.status for r in records)
    trust_counts = Counter(r.classification_trust_tier for r in records)
    rag_counts = Counter(r.rag_action for r in records)
    token_type_counts: Counter[str] = Counter()
    for record in records:
        for token in record.classified_tokens:
            token_type_counts[_text(token.get("token_type"), "unknown")] += 1
    pages = {r.page_id for r in records if r.page_id}
    error_records = status_counts.get("error", 0)
    ok_records = len(records) - error_records
    status = "OK" if records and error_records == 0 else ("PARTIAL" if records and ok_records else "FAIL")
    return {
        "status": status,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "trace_net_table_tile_text_refiner_version": "trace_net_table_tile_text_refiner_v1",
        "records": len(records),
        "pages": len(pages),
        "ok_records": ok_records,
        "error_records": error_records,
        "records_with_canonical_parts": sum(1 for r in records if r.canonical_part_numbers),
        "records_with_catalog_supported_parts": sum(1 for r in records if r.catalog_supported_part_numbers),
        "records_with_probable_parts": sum(1 for r in records if r.probable_part_numbers),
        "records_with_index_labels": sum(1 for r in records if r.index_labels),
        "records_with_ata_codes": sum(1 for r in records if r.ata_codes),
        "records_with_filtered_non_part_tokens": sum(1 for r in records if r.filtered_non_part_tokens),
        "canonical_part_numbers_total": sum(len(r.canonical_part_numbers) for r in records),
        "catalog_supported_part_numbers_total": sum(len(r.catalog_supported_part_numbers) for r in records),
        "unsupported_part_candidates_total": sum(len(r.unsupported_part_candidates) for r in records),
        "index_labels_total": sum(len(r.index_labels) for r in records),
        "ata_codes_total": sum(len(r.ata_codes) for r in records),
        "filtered_non_part_tokens_total": sum(len(r.filtered_non_part_tokens) for r in records),
        "trust_tier_counts": dict(sorted(trust_counts.items())),
        "rag_action_counts": dict(sorted(rag_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "token_type_counts": dict(sorted(token_type_counts.items())),
        "graph_nodes": len(nodes),
        "graph_edges": len(edges),
    }


def build_refined_corpus(records: Sequence[RefinedTileTextRecord], summary: Mapping[str, Any]) -> str:
    lines = [
        "# TRACE-Net table tile text refined corpus",
        "",
        f"Status: {summary.get('status')}",
        f"Records: {summary.get('records')}",
        f"Catalog-supported record count: {summary.get('records_with_catalog_supported_parts')}",
        "",
    ]
    for record in records:
        lines.extend(
            [
                f"## {record.page_id} / tile {record.tile_index}",
                "",
                f"Trust: `{record.classification_trust_tier}` | RAG: `{record.rag_action}`",
                "",
            ]
        )
        if record.catalog_supported_part_numbers:
            lines.append("Catalog-supported parts: " + ", ".join(record.catalog_supported_part_numbers))
        if record.unsupported_part_candidates:
            lines.append("Unsupported part candidates: " + ", ".join(record.unsupported_part_candidates))
        if record.index_labels:
            lines.append("Index/section labels: " + ", ".join(record.index_labels))
        if record.ata_codes:
            lines.append("ATA codes: " + ", ".join(record.ata_codes))
        lines.extend(["", "```text", record.text[:4000], "```", ""])
    return "\n".join(lines)


def _review_rows(records: Sequence[RefinedTileTextRecord]) -> str:
    rows: list[str] = []
    for record in records:
        rows.append(
            "<tr>"
            f"<td>{html.escape(record.page_id)}</td>"
            f"<td>{record.tile_index}</td>"
            f"<td>{html.escape(record.classification_trust_tier)}</td>"
            f"<td>{html.escape(record.rag_action)}</td>"
            f"<td>{html.escape(', '.join(record.catalog_supported_part_numbers[:12]))}</td>"
            f"<td>{html.escape(', '.join(record.unsupported_part_candidates[:12]))}</td>"
            f"<td>{html.escape(', '.join(record.index_labels[:12]))}</td>"
            f"<td>{html.escape(', '.join(record.refinement_reasons))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def build_refined_review_html(records: Sequence[RefinedTileTextRecord], summary: Mapping[str, Any]) -> str:
    return f"""<!doctype html>
<html>
<head>
<meta charset='utf-8'/>
<title>TRACE-Net table tile text refined review</title>
<style>
body {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 24px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ border: 1px solid #ddd; padding: 6px; vertical-align: top; }}
th {{ background: #f4f4f4; position: sticky; top: 0; }}
pre {{ white-space: pre-wrap; background: #fafafa; padding: 8px; border: 1px solid #ddd; }}
.badge {{ display: inline-block; padding: 2px 6px; border-radius: 8px; background: #eee; }}
</style>
</head>
<body>
<h1>TRACE-Net table tile text refined review</h1>
<p>Status: <b>{html.escape(str(summary.get('status')))}</b></p>
<ul>
  <li>Records: {summary.get('records')}</li>
  <li>Pages: {summary.get('pages')}</li>
  <li>Records with catalog-supported parts: {summary.get('records_with_catalog_supported_parts')}</li>
  <li>Records with filtered non-part tokens: {summary.get('records_with_filtered_non_part_tokens')}</li>
  <li>Trust tiers: {html.escape(str(summary.get('trust_tier_counts')))}</li>
</ul>
<table>
<thead><tr><th>Page</th><th>Tile</th><th>Trust</th><th>RAG</th><th>Catalog parts</th><th>Unsupported candidates</th><th>Index labels</th><th>Reasons</th></tr></thead>
<tbody>
{_review_rows(records)}
</tbody>
</table>
</body>
</html>
"""


def build_refined_review_md(records: Sequence[RefinedTileTextRecord], summary: Mapping[str, Any]) -> str:
    lines = [
        "# TRACE-Net table tile text refined review",
        "",
        f"status: {summary.get('status')}",
        f"records: {summary.get('records')}",
        f"records_with_catalog_supported_parts: {summary.get('records_with_catalog_supported_parts')}",
        f"trust_tier_counts: {summary.get('trust_tier_counts')}",
        "",
    ]
    for record in records[:250]:
        lines.extend(
            [
                f"## {record.page_id} / tile {record.tile_index}",
                f"trust: {record.classification_trust_tier} | rag: {record.rag_action}",
                f"catalog parts: {', '.join(record.catalog_supported_part_numbers) or 'none'}",
                f"unsupported candidates: {', '.join(record.unsupported_part_candidates) or 'none'}",
                f"index labels: {', '.join(record.index_labels) or 'none'}",
                f"reasons: {', '.join(record.refinement_reasons)}",
                "",
            ]
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def refine_table_tile_text_records(paths: TableTileTextRefinerPaths, options: TableTileTextRefinerOptions) -> dict[str, Any]:
    source_rows = read_jsonl(paths.input_records)
    if options.page_id:
        source_rows = [row for row in source_rows if _text(row.get("page_id")) == options.page_id]
    if options.max_records is not None:
        source_rows = source_rows[: max(0, int(options.max_records))]
    catalog_parts = _catalog_part_set(_read_json(paths.part_tree, {}))
    records = [classify_record(row, catalog_parts, include_text_scan_tokens=options.include_text_scan_tokens) for row in source_rows]
    nodes, edges = build_refined_graph(records)
    summary = build_refined_summary(records, nodes, edges)

    paths.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(paths.refined_records, [record.to_json() for record in records])
    _write_json(paths.summary, summary)
    paths.corpus_md.write_text(build_refined_corpus(records, summary), encoding="utf-8")
    _write_json(paths.graph_nodes, nodes)
    _write_json(paths.graph_edges, edges)
    paths.review_md.write_text(build_refined_review_md(records, summary), encoding="utf-8")
    paths.review_html.write_text(build_refined_review_html(records, summary), encoding="utf-8")

    result = {
        "summary": summary,
        "records_path": paths.refined_records.as_posix(),
        "summary_path": paths.summary.as_posix(),
        "review_html_path": paths.review_html.as_posix(),
    }
    if options.open_review:
        try:
            webbrowser.open(paths.review_html.resolve().as_uri())
        except Exception:
            pass
    return result


def _print_summary(result: Mapping[str, Any], paths: TableTileTextRefinerPaths) -> None:
    summary = dict(result.get("summary") or {})
    print("TRACE-Net table tile text classifier/refiner")
    print(f"  Status: {summary.get('status')}")
    print(f"  Output dir: {paths.output_dir}")
    print("  Summary:")
    for key in (
        "records",
        "pages",
        "ok_records",
        "error_records",
        "records_with_canonical_parts",
        "records_with_catalog_supported_parts",
        "records_with_probable_parts",
        "records_with_index_labels",
        "records_with_ata_codes",
        "records_with_filtered_non_part_tokens",
        "canonical_part_numbers_total",
        "catalog_supported_part_numbers_total",
        "unsupported_part_candidates_total",
        "index_labels_total",
        "ata_codes_total",
        "filtered_non_part_tokens_total",
        "trust_tier_counts",
        "rag_action_counts",
        "graph_nodes",
        "graph_edges",
    ):
        print(f"    {key}: {summary.get(key)}")
    print("Files written:")
    print(f"  records: {paths.refined_records}")
    print(f"  summary: {paths.summary}")
    print(f"  corpus_md: {paths.corpus_md}")
    print(f"  review_html: {paths.review_html}")
    print(f"  graph_nodes: {paths.graph_nodes}")
    print(f"  graph_edges: {paths.graph_edges}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Classify/refine TRACE-Net table tile text records.")
    parser.add_argument("--input-records", type=Path, default=None)
    parser.add_argument("--part-tree", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-records", type=int, default=None)
    parser.add_argument("--page-id", default=None)
    parser.add_argument("--no-text-scan", action="store_true", help="Use only upstream token arrays; do not rescan text for extra tokens.")
    parser.add_argument("--open", action="store_true", dest="open_review")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    paths = TableTileTextRefinerPaths(
        input_records_path=args.input_records,
        part_tree_path=args.part_tree,
        output_dir=args.output_dir,
    )
    options = TableTileTextRefinerOptions(
        max_records=args.max_records,
        page_id=args.page_id,
        open_review=args.open_review,
        include_text_scan_tokens=not args.no_text_scan,
    )
    result = refine_table_tile_text_records(paths, options)
    _print_summary(result, paths)
    return 0 if result.get("summary", {}).get("status") in {"OK", "PARTIAL"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
