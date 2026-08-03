"""TRACE-Net Evidence Consensus Router v1.2.

The Evidence Consensus Router is the center judge in TRACE-Net. It does not
create facts. It takes source/graph/OCR/visual/table evidence that already
exists, checks whether each layer is source-backed and internally consistent,
and emits page/layer-level decisions:

- OCR support?
- Graph support?
- Part catalog support?
- Source traceable?
- Hallucination / leakage risk?
- Trust tier A/B/C/D
- RAG action
- Repair action

Version 1.2 is still mostly page/layer-level, but it also accepts refined
table-tile text records as tile-level derived evidence and adds TRACE-LC
(layer-confidence) scores. Stage 1 confidence scoring is non-breaking: it
computes support/risk/usable confidence and score-derived tiers, but it does
not yet override the existing rule-based trust tiers or routing actions.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import webbrowser
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_EXPORT_DIR = Path("local_data/organization/export")
DEFAULT_GRAPH_DIR = Path("local_data/organization/graph")
DEFAULT_VISUAL_TEXT_DIR = Path("local_data/organization/visual_text")
DEFAULT_TRUST_TRAIT_DIR = Path("local_data/organization/trust_traits")
DEFAULT_TRACE_NET_DIR = Path("local_data/organization/trace_net")
DEFAULT_TABLE_DIR = Path("local_data/organization/table_extraction")
DEFAULT_COMMUNITY_DIR = Path("local_data/organization/communities")
DEFAULT_OUTPUT_DIR = DEFAULT_TRACE_NET_DIR / "evidence_consensus"

RECORDS_FILE = "evidence_consensus_records.jsonl"
SUMMARY_FILE = "evidence_consensus_summary.json"
GRAPH_NODES_FILE = "evidence_consensus_graph_nodes.json"
GRAPH_EDGES_FILE = "evidence_consensus_graph_edges.json"
REVIEW_MD_FILE = "evidence_consensus_review.md"
REVIEW_HTML_FILE = "evidence_consensus_review.html"
QUALITY_FILE = "evidence_consensus_quality.json"

TRUST_TIERS = {"A", "B", "C", "D"}
SOURCE_OK = {"source_verified", "local_source_verified", "source_link_only"}
SOURCE_STRONG = {"source_verified", "local_source_verified"}

PART_NUMBER_RE = re.compile(r"\b[A-Z0-9]{1,5}[-.]?[A-Z0-9]{0,5}[-.]?[0-9A-Z]{2,6}(?:[-.][0-9A-Z]{1,6})?\b", re.I)

REVIEW_FLAG_KEYS = {
    "metadata_leakage",
    "metadata_leakage_risk",
    "refusal_like",
    "prompt_template_leakage",
    "prompt_template_leakage_risk",
    "prompt_template_repaired",
    "section_bleed",
    "section_bleed_risk",
    "section_bleed_repaired",
    "hallucination_risk",
    "suspicious_phrase",
    "suspicious_phrase_risk",
    "summary_heavy",
    "too_summary_heavy",
    "table_expected_but_not_extracted",
    "needs_human_review",
}
HARD_RISK_FLAGS = {
    "metadata_leakage",
    "metadata_leakage_risk",
    "refusal_like",
    "prompt_template_leakage",
    "prompt_template_leakage_risk",
    "section_bleed",
    "section_bleed_risk",
}
MEDIUM_RISK_FLAGS = {
    "hallucination_risk",
    "suspicious_phrase",
    "suspicious_phrase_risk",
    "summary_heavy",
    "too_summary_heavy",
    "table_expected_but_not_extracted",
}

TRACE_LC_VERSION = "trace_lc_v1"
TRACE_LC_WEIGHTS = {
    "source_trace": 0.30,
    "graph_support": 0.25,
    "ocr_support": 0.20,
    "part_catalog": 0.20,
    "extraction_layer": 0.05,
}
TRACE_LC_THRESHOLDS = {"A": 0.90, "B": 0.70, "C": 0.45}


@dataclass(frozen=True)
class EvidenceConsensusPaths:
    export_dir: Path = DEFAULT_EXPORT_DIR
    graph_dir: Path = DEFAULT_GRAPH_DIR
    visual_text_dir: Path = DEFAULT_VISUAL_TEXT_DIR
    trust_trait_dir: Path = DEFAULT_TRUST_TRAIT_DIR
    trace_net_dir: Path = DEFAULT_TRACE_NET_DIR
    table_dir: Path = DEFAULT_TABLE_DIR
    community_dir: Path = DEFAULT_COMMUNITY_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    page_index_path: Path | None = None
    part_tree_path: Path | None = None
    visual_clean_records_path: Path | None = None
    trust_assertions_path: Path | None = None
    table_candidate_plan_path: Path | None = None
    table_tile_plan_path: Path | None = None
    table_tile_text_refined_records_path: Path | None = None
    algorithm_policy_path: Path | None = None
    records_path: Path | None = None
    summary_path: Path | None = None
    graph_nodes_path: Path | None = None
    graph_edges_path: Path | None = None
    review_md_path: Path | None = None
    review_html_path: Path | None = None
    quality_path: Path | None = None

    @property
    def page_index(self) -> Path:
        return self.page_index_path or (self.export_dir / "page_index.json")

    @property
    def part_tree(self) -> Path:
        return self.part_tree_path or (self.export_dir / "part_tree.json")

    @property
    def visual_clean_records(self) -> Path:
        return self.visual_clean_records_path or (self.visual_text_dir / "visual_text_extraction_clean.jsonl")

    @property
    def trust_assertions(self) -> Path:
        return self.trust_assertions_path or (self.trust_trait_dir / "trust_trait_assertions.jsonl")

    @property
    def table_candidate_plan(self) -> Path:
        # Prefer the all-page scan. If absent, fall back to the repair plan.
        if self.table_candidate_plan_path:
            return self.table_candidate_plan_path
        all_page = self.table_dir / "all_page_scan" / "table_candidate_plan.jsonl"
        if all_page.exists():
            return all_page
        return self.trace_net_dir / "trace_net_repair_plan.jsonl"

    @property
    def table_tile_plan(self) -> Path:
        return self.table_tile_plan_path or (self.table_dir / "table_tile_plan.jsonl")

    @property
    def table_tile_text_refined_records(self) -> Path:
        return self.table_tile_text_refined_records_path or (self.table_dir / "table_tile_text_refined" / "table_tile_text_refined_records.jsonl")

    @property
    def algorithm_policy(self) -> Path:
        return self.algorithm_policy_path or (self.community_dir / "community_algorithm_policy.json")

    @property
    def records(self) -> Path:
        return self.records_path or (self.output_dir / RECORDS_FILE)

    @property
    def summary(self) -> Path:
        return self.summary_path or (self.output_dir / SUMMARY_FILE)

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
class EvidenceConsensusOptions:
    expected_pages: int | None = None
    include_source_trace: bool = True
    include_visual_text: bool = True
    include_table_candidates: bool = True
    include_table_tiles: bool = True
    include_table_tile_text_refined: bool = True
    include_part_catalog: bool = True
    max_review_records: int = 200


@dataclass
class EvidenceCheck:
    status: str
    score: float | None = None
    reasons: list[str] = field(default_factory=list)
    refs: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceConfidenceScores:
    """TRACE-LC Stage 1 confidence scores.

    These scores are advisory in v1.2. They are written for review, policy
    tuning, and future routing experiments, but they do not override the
    existing trust tier/rag action yet.
    """

    version: str = TRACE_LC_VERSION
    source_trace_score: float = 0.0
    graph_support_score: float = 0.0
    ocr_support_score: float = 0.0
    part_catalog_score: float = 0.0
    extraction_layer_score: float = 0.0
    support_score: float = 0.0
    risk_score: float = 0.0
    usable_confidence: float = 0.0
    confidence_tier: str = "D"
    max_allowed_tier: str = "A"
    hard_gate_blocked: bool = False
    hard_gate_reasons: list[str] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=lambda: dict(TRACE_LC_WEIGHTS))
    thresholds: dict[str, float] = field(default_factory=lambda: dict(TRACE_LC_THRESHOLDS))

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceConsensusRecord:
    page_id: str
    evidence_layer: str
    evidence_id: str
    source_trace: EvidenceCheck
    ocr_support: EvidenceCheck
    graph_support: EvidenceCheck
    part_catalog_support: EvidenceCheck
    hallucination_risk: EvidenceCheck
    confidence_scores: EvidenceConfidenceScores
    trust_tier: str
    rag_action: str
    repair_action: str
    review_action: str
    reasons: list[str] = field(default_factory=list)
    route: str = ""
    source_artifact: str = ""
    consensus_version: str = "trace_net_evidence_consensus_v1_2"
    properties: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["source_trace"] = self.source_trace.to_json()
        data["ocr_support"] = self.ocr_support.to_json()
        data["graph_support"] = self.graph_support.to_json()
        data["part_catalog_support"] = self.part_catalog_support.to_json()
        data["hallucination_risk"] = self.hallucination_risk.to_json()
        data["confidence_scores"] = self.confidence_scores.to_json()
        return data


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
    out: list[dict[str, Any]] = []
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
                out.append(dict(value))
    return out


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    out = str(value).strip()
    return out if out else default


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", _text(value)).strip().lower()


def _slug(value: Any) -> str:
    text = _norm(value)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "unknown"


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ok"}
    return bool(value)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _path_exists(path_text: Any) -> bool:
    text = _text(path_text)
    if not text:
        return False
    return Path(text).exists()


def _page_id_from_record(record: Mapping[str, Any]) -> str:
    for key in ("page_id", "id", "page", "node_id", "entity_id"):
        value = record.get(key)
        if value:
            text = _text(value)
            if text.startswith("page:"):
                return text.split(":", 1)[1]
            return text
    source = _as_dict(record.get("source"))
    value = source.get("page_id")
    if value:
        return _text(value)
    return ""


def _extract_part_numbers(text: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for match in PART_NUMBER_RE.finditer(text or ""):
        value = match.group(0).strip().upper()
        # Filter obvious route/ATA fragments that are not useful part claims.
        if re.fullmatch(r"\d{2}-\d{2}-\d{2}", value):
            continue
        if len(value) < 5:
            continue
        if value not in seen:
            seen.add(value)
            values.append(value)
    return values


def _record_text(record: Mapping[str, Any]) -> str:
    chunks: list[str] = []
    for key in (
        "visual_text",
        "visual_text_clean",
        "clean_text",
        "markdown",
        "text",
        "table_text",
        "tile_text",
        "refined_text",
        "clean_text",
    ):
        value = record.get(key)
        if isinstance(value, str):
            chunks.append(value)
    sections = record.get("sections") or record.get("clean_sections")
    if isinstance(sections, Mapping):
        for value in sections.values():
            if isinstance(value, str):
                chunks.append(value)
    return "\n".join(chunks)


# ---------------------------------------------------------------------------
# Loading page and signal indexes
# ---------------------------------------------------------------------------


def _extract_page_record(pid: str, raw: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(raw)
    data.setdefault("page_id", pid)
    source = _as_dict(data.get("source"))
    for key in ("source_url", "rescart_url", "url"):
        if not data.get("source_url") and data.get(key):
            data["source_url"] = data.get(key)
    if not data.get("source_url"):
        data["source_url"] = source.get("source_url") or source.get("url") or source.get("rescart_url")
    if not data.get("tiff_path"):
        data["tiff_path"] = source.get("tiff_path") or source.get("image_path") or data.get("image_path")
    if not data.get("ocr_path"):
        data["ocr_path"] = source.get("ocr_path") or data.get("ocr_text_path")
    if not data.get("page_role"):
        data["page_role"] = data.get("role") or source.get("page_role")
    if not data.get("ata_code"):
        data["ata_code"] = data.get("ata") or source.get("ata_code")
    return data


def load_page_index(path: Path) -> dict[str, dict[str, Any]]:
    raw = _read_json(path, {})
    pages: dict[str, dict[str, Any]] = {}
    if isinstance(raw, list):
        for row in raw:
            if isinstance(row, Mapping):
                pid = _page_id_from_record(row)
                if pid:
                    pages[pid] = _extract_page_record(pid, row)
        return pages
    if not isinstance(raw, Mapping):
        return pages

    candidates: Any = None
    for key in ("pages", "page_index", "records", "items"):
        if isinstance(raw.get(key), (list, dict)):
            candidates = raw.get(key)
            break
    if candidates is None:
        candidates = raw

    if isinstance(candidates, list):
        for row in candidates:
            if isinstance(row, Mapping):
                pid = _page_id_from_record(row)
                if pid:
                    pages[pid] = _extract_page_record(pid, row)
    elif isinstance(candidates, Mapping):
        for key, value in candidates.items():
            if isinstance(value, Mapping):
                pid = _page_id_from_record(value) or _text(key)
                pages[pid] = _extract_page_record(pid, value)
    return pages


def load_clean_visual_records(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        pid = _page_id_from_record(row)
        if pid:
            out[pid] = row
    return out


def _extract_trait_values(assertion: Mapping[str, Any]) -> tuple[str, str, str]:
    props = _as_dict(assertion.get("properties"))
    trait_type = _text(assertion.get("trait_type") or props.get("trait_type"))
    trait_key = _text(assertion.get("trait_key") or props.get("trait_key"))
    trait_value = _text(assertion.get("trait_value") or props.get("trait_value"))
    return trait_type, trait_key, trait_value


def _assertion_page_id(assertion: Mapping[str, Any]) -> str:
    value = _text(assertion.get("page_id"))
    if value:
        return value
    props = _as_dict(assertion.get("properties"))
    value = _text(props.get("page_id"))
    if value:
        return value
    entity_id = _text(assertion.get("entity_id") or props.get("entity_id"))
    if entity_id.startswith("page:"):
        return entity_id.split(":", 1)[1]
    return ""


def load_trust_signals(path: Path) -> dict[str, dict[str, Any]]:
    signals: dict[str, dict[str, Any]] = defaultdict(lambda: {"review_traits": set(), "rag_traits": set()})
    for row in read_jsonl(path):
        pid = _assertion_page_id(row)
        if not pid:
            continue
        trait_type, trait_key, trait_value = _extract_trait_values(row)
        ttype = _norm(trait_type)
        tkey = _norm(trait_key)
        tval = _norm(trait_value)
        bucket = signals[pid]
        if ttype == "trust" and tkey == "visual_text":
            tier = _text(trait_value).upper()[:1]
            if tier in TRUST_TIERS:
                bucket["visual_text_trust_tier"] = tier
        elif ttype == "rag" and tkey == "visual_text":
            bucket["rag_traits"].add(tval)
        elif ttype == "review" and tkey == "visual_text":
            bucket["review_traits"].add(tval)
    return {
        pid: {
            **{k: v for k, v in row.items() if not isinstance(v, set)},
            "review_traits": sorted(row.get("review_traits", set())),
            "rag_traits": sorted(row.get("rag_traits", set())),
        }
        for pid, row in signals.items()
    }


def load_table_records(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        pid = _page_id_from_record(row)
        if pid:
            out[pid] = row
    return out


def load_table_tile_text_refined_records(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in read_jsonl(path):
        pid = _page_id_from_record(row)
        if pid:
            item = dict(row)
            item["page_id"] = pid
            rows.append(item)
    return rows


def _tile_id_from_record(record: Mapping[str, Any], index: int = 0) -> str:
    for key in ("tile_id", "tile", "tile_index", "tile_number", "tile_label"):
        value = record.get(key)
        if value is not None and str(value).strip():
            text = str(value).strip()
            return text if text.startswith("tile") else f"tile_{text}"
    props = _as_dict(record.get("properties"))
    for key in ("tile_id", "tile", "tile_index", "tile_number", "tile_label"):
        value = props.get(key)
        if value is not None and str(value).strip():
            text = str(value).strip()
            return text if text.startswith("tile") else f"tile_{text}"
    return f"tile_{index + 1:03d}"


def _record_existing_tier(record: Mapping[str, Any]) -> str:
    for key in ("trust_tier", "table_tile_text_trust_tier", "refined_trust_tier"):
        value = _text(record.get(key))
        if value.upper()[:1] in TRUST_TIERS:
            return value.upper()[:1]
    scores = _as_dict(record.get("scores"))
    value = _text(scores.get("trust_tier"))
    if value.upper()[:1] in TRUST_TIERS:
        return value.upper()[:1]
    return ""


def load_part_index(path: Path, pages: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build a lightweight page -> part summary index.

    This is deliberately permissive because different artifact versions store
    parts under different keys.
    """
    index: dict[str, dict[str, Any]] = defaultdict(lambda: {"part_numbers": set(), "mention_count": 0})

    for pid, page in pages.items():
        for key in ("parts", "part_numbers", "part_mentions", "mentions"):
            value = page.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, Mapping):
                        pn = _text(item.get("part_number") or item.get("part_number_display") or item.get("id"))
                    else:
                        pn = _text(item)
                    if pn:
                        index[pid]["part_numbers"].add(pn.upper())
                        index[pid]["mention_count"] += 1
            elif isinstance(value, Mapping):
                for pn in value.keys():
                    index[pid]["part_numbers"].add(_text(pn).upper())
                    index[pid]["mention_count"] += 1

    raw = _read_json(path, None)
    # part_tree.json often maps part -> pages/mentions. Try to invert it.
    if isinstance(raw, Mapping):
        candidates = raw.get("parts") or raw.get("part_tree") or raw
        if isinstance(candidates, Mapping):
            for part_key, payload in candidates.items():
                pn = _text(part_key).upper()
                if not pn:
                    continue
                if isinstance(payload, Mapping):
                    pages_value = payload.get("pages") or payload.get("page_ids") or payload.get("mentions")
                else:
                    pages_value = None
                if isinstance(pages_value, list):
                    for item in pages_value:
                        if isinstance(item, Mapping):
                            pid = _page_id_from_record(item)
                        else:
                            pid = _text(item)
                        if pid:
                            index[pid]["part_numbers"].add(pn)
                            index[pid]["mention_count"] += 1
    final: dict[str, dict[str, Any]] = {}
    for pid, row in index.items():
        final[pid] = {
            "part_numbers": sorted(row.get("part_numbers", set())),
            "mention_count": int(row.get("mention_count", 0)),
        }
    return final


# ---------------------------------------------------------------------------
# Check modules
# ---------------------------------------------------------------------------


def check_source_trace(page: Mapping[str, Any] | None) -> EvidenceCheck:
    if not page:
        return EvidenceCheck("not_traceable", 0.0, ["page is missing from page_index"])
    source_url = _text(page.get("source_url") or page.get("url"))
    tiff_path = _text(page.get("tiff_path") or page.get("image_path"))
    ocr_path = _text(page.get("ocr_path") or page.get("ocr_text_path"))
    reasons: list[str] = []
    if source_url:
        reasons.append("source URL present")
    else:
        reasons.append("source URL missing")
    if tiff_path:
        if _path_exists(tiff_path):
            reasons.append("TIFF path present and file exists")
        else:
            reasons.append("TIFF path present but file was not found from current working directory")
    else:
        reasons.append("TIFF path missing")
    if ocr_path:
        if _path_exists(ocr_path):
            reasons.append("OCR path present and file exists")
        else:
            reasons.append("OCR path present but file was not found from current working directory")
    else:
        reasons.append("OCR path missing or not tracked on page record")

    refs = {"source_url": source_url, "tiff_path": tiff_path, "ocr_path": ocr_path}
    if source_url and tiff_path and _path_exists(tiff_path):
        return EvidenceCheck("source_verified", 1.0, reasons, refs)
    if source_url and tiff_path:
        return EvidenceCheck("local_source_link_only", 0.75, reasons, refs)
    if source_url:
        return EvidenceCheck("source_link_only", 0.55, reasons, refs)
    if tiff_path and _path_exists(tiff_path):
        return EvidenceCheck("local_tiff_only", 0.5, reasons, refs)
    return EvidenceCheck("not_traceable", 0.0, reasons, refs)


def check_ocr_support(page: Mapping[str, Any] | None, candidate_text: str = "") -> EvidenceCheck:
    if not page:
        return EvidenceCheck("not_evaluated", None, ["page missing"])
    ocr_text = _text(page.get("ocr_text"))
    ocr_path = _text(page.get("ocr_path") or page.get("ocr_text_path"))
    if not ocr_text and ocr_path and Path(ocr_path).exists():
        try:
            ocr_text = Path(ocr_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            ocr_text = ""
    if not ocr_text.strip():
        return EvidenceCheck("ocr_empty_or_unavailable", 0.2, ["no visible OCR text found for this page"], {"ocr_path": ocr_path})

    if not candidate_text.strip():
        return EvidenceCheck("ocr_available", 0.65, ["OCR text exists, but this layer has no claim text to compare"], {"ocr_path": ocr_path, "ocr_chars": len(ocr_text)})

    claim_parts = _extract_part_numbers(candidate_text)
    ocr_norm = re.sub(r"[^A-Z0-9]+", "", ocr_text.upper())
    matched_parts = []
    for part in claim_parts:
        part_norm = re.sub(r"[^A-Z0-9]+", "", part.upper())
        if part_norm and part_norm in ocr_norm:
            matched_parts.append(part)
    if matched_parts:
        return EvidenceCheck("part_number_supported_by_ocr", 0.9, [f"{len(matched_parts)} part-like values found in OCR"], {"matched_part_numbers": matched_parts[:20], "ocr_path": ocr_path})

    # Text comparison for short labels.
    cleaned_claim = _norm(candidate_text)
    if cleaned_claim and len(cleaned_claim) <= 80 and cleaned_claim in _norm(ocr_text):
        return EvidenceCheck("exact_text_supported_by_ocr", 0.85, ["claim text appears in OCR"], {"ocr_path": ocr_path})
    return EvidenceCheck("ocr_available_no_direct_match", 0.45, ["OCR exists but did not directly support this layer text"], {"ocr_path": ocr_path, "ocr_chars": len(ocr_text)})


def check_graph_support(
    page: Mapping[str, Any] | None,
    *,
    evidence_layer: str,
    table_candidate: Mapping[str, Any] | None = None,
    table_tile: Mapping[str, Any] | None = None,
) -> EvidenceCheck:
    if not page:
        return EvidenceCheck("unsupported", 0.0, ["page missing from page index"])
    reasons = ["page exists in page index"]
    if page.get("ata_code"):
        reasons.append("page has ATA code")
    if page.get("source_url"):
        reasons.append("page has source URL")
    role = _norm(page.get("page_role") or page.get("role"))
    image_class = _norm(page.get("image_class") or page.get("classification") or page.get("image_classification"))

    if evidence_layer == "table_candidate":
        route = _norm(_as_dict(table_candidate).get("route") or _as_dict(table_candidate).get("repair_route"))
        if "table_crop_tile" in route:
            reasons.append(f"table candidate route={route}")
            return EvidenceCheck("strong_support", 0.9, reasons)
        if "table_candidate_review" in route:
            reasons.append("weak table candidate route requires review")
            return EvidenceCheck("weak_support", 0.55, reasons)
        if "skip" in route:
            reasons.append("table candidate scan skipped this page")
            return EvidenceCheck("unsupported", 0.3, reasons)
    if evidence_layer == "table_tiles":
        row = _as_dict(table_tile)
        status = _norm(row.get("status"))
        tiles = _to_int(row.get("tile_count") or row.get("tiles") or len(_as_list(row.get("tiles"))))
        if status == "ok" and tiles > 0:
            reasons.append(f"table tiles were created: {tiles}")
            return EvidenceCheck("strong_support", 0.9, reasons)
        if status.startswith("skipped"):
            reasons.append(f"table tile status={status}")
            return EvidenceCheck("weak_support", 0.45, reasons)
    if evidence_layer == "table_tile_text_refined":
        row = _as_dict(table_tile)
        status = _norm(row.get("status"))
        catalog_parts = _as_list(row.get("catalog_supported_part_numbers")) or _as_list(row.get("catalog_supported_parts"))
        canonical_parts = _as_list(row.get("canonical_part_numbers")) or _as_list(row.get("canonical_parts"))
        if status == "ok" and catalog_parts:
            reasons.append(f"refined tile text has catalog-supported parts: {len(catalog_parts)}")
            return EvidenceCheck("strong_support", 0.9, reasons, {"catalog_supported_part_numbers": catalog_parts[:20]})
        if status == "ok" and canonical_parts:
            reasons.append(f"refined tile text has canonical/probable parts: {len(canonical_parts)}")
            return EvidenceCheck("weak_support", 0.65, reasons, {"canonical_part_numbers": canonical_parts[:20]})
        if status == "ok":
            reasons.append("refined tile text exists but has no catalog-supported part evidence")
            return EvidenceCheck("weak_support", 0.45, reasons)
        if status:
            reasons.append(f"refined tile text status={status}")
            return EvidenceCheck("unsupported", 0.25, reasons)
    if evidence_layer == "visual_text":
        if role:
            reasons.append(f"page_role={role}")
        if image_class:
            reasons.append(f"image_class={image_class}")
        return EvidenceCheck("strong_support", 0.8, reasons)
    if evidence_layer == "part_catalog":
        return EvidenceCheck("strong_support", 0.85, reasons)
    if evidence_layer == "source_trace":
        return EvidenceCheck("strong_support", 0.9, reasons)
    return EvidenceCheck("weak_support", 0.6, reasons)


def check_part_catalog_support(page_id: str, part_index: Mapping[str, Mapping[str, Any]], candidate_text: str = "") -> EvidenceCheck:
    page_parts = _as_dict(part_index.get(page_id))
    part_numbers = list(page_parts.get("part_numbers") or [])
    mention_count = _to_int(page_parts.get("mention_count"), len(part_numbers))
    claim_parts = _extract_part_numbers(candidate_text)
    if not part_numbers and not claim_parts:
        return EvidenceCheck("not_applicable", None, ["no part claim or page part catalog signal"])
    if part_numbers and not claim_parts:
        return EvidenceCheck("page_part_mentions_present", 0.75, [f"page has {mention_count} part catalog/mention signals"], {"part_numbers": part_numbers[:20]})
    supported = []
    unsupported = []
    page_norm = {re.sub(r"[^A-Z0-9]+", "", p.upper()): p for p in part_numbers}
    for part in claim_parts:
        pnorm = re.sub(r"[^A-Z0-9]+", "", part.upper())
        if pnorm in page_norm:
            supported.append(part)
        else:
            unsupported.append(part)
    if supported:
        return EvidenceCheck("catalog_or_page_mention_supported", 0.9, [f"{len(supported)} visual/table part values supported by page part signals"], {"supported_part_numbers": supported[:20], "unsupported_part_numbers": unsupported[:20]})
    if claim_parts:
        return EvidenceCheck("visual_or_table_part_only", 0.35, ["part-like values found in derived evidence but not in page part signals"], {"unsupported_part_numbers": unsupported[:20]})
    return EvidenceCheck("not_applicable", None, ["no part catalog comparison available"])


def _review_traits_from_record(record: Mapping[str, Any]) -> set[str]:
    traits: set[str] = set()
    for key in REVIEW_FLAG_KEYS:
        if _boolish(record.get(key)):
            traits.add(key)
    for section_key in ("visual_text_cleanup_scores", "visual_text_scores", "visual_text_scores_clean", "scores"):
        nested = _as_dict(record.get(section_key))
        for key in REVIEW_FLAG_KEYS:
            if _boolish(nested.get(key)):
                traits.add(key)
    for key in ("review_traits", "traits", "flags"):
        for value in _as_list(record.get(key)):
            if value:
                traits.add(_slug(value))
    return traits


def check_hallucination_risk(record: Mapping[str, Any] | None = None, trust_signals: Mapping[str, Any] | None = None) -> EvidenceCheck:
    record = record or {}
    trust_signals = trust_signals or {}
    traits = set(_review_traits_from_record(record))
    traits.update(_as_list(trust_signals.get("review_traits")))
    traits = {_slug(t) for t in traits if t}
    hard = sorted(t for t in traits if t in HARD_RISK_FLAGS)
    medium = sorted(t for t in traits if t in MEDIUM_RISK_FLAGS)
    if hard:
        return EvidenceCheck("blocked", 1.0, ["hard hallucination/leakage risk flags present", *hard], {"risk_traits": sorted(traits)})
    if medium:
        return EvidenceCheck("medium_risk", 0.65, ["review-risk flags present", *medium], {"risk_traits": sorted(traits)})
    return EvidenceCheck("low_risk", 0.1, ["no hallucination/leakage risk flags detected"], {"risk_traits": sorted(traits)})


# ---------------------------------------------------------------------------
# TRACE-LC Stage 1 confidence scoring
# ---------------------------------------------------------------------------


def _score_from_check(check: EvidenceCheck, neutral: float = 0.5) -> float:
    if check.score is None:
        return neutral
    return max(0.0, min(1.0, float(check.score)))


def _extraction_layer_score(evidence_layer: str, payload: Mapping[str, Any], existing_tier: str | None = None) -> float:
    status = _norm(payload.get("status"))
    if status in {"error", "fail", "failed"}:
        return 0.0
    tier = _text(existing_tier).upper()[:1]
    if tier == "A":
        return 0.95
    if tier == "B":
        return 0.80
    if tier == "C":
        return 0.55
    if tier == "D":
        return 0.20
    if evidence_layer == "source_trace":
        return 1.0
    if evidence_layer == "part_catalog":
        return 0.90
    if evidence_layer == "table_tile_text_refined":
        if _as_list(payload.get("catalog_supported_part_numbers")) or _as_list(payload.get("catalog_supported_parts")):
            return 0.85
        if _as_list(payload.get("canonical_part_numbers")) or _as_list(payload.get("canonical_parts")):
            return 0.65
        return 0.45
    if evidence_layer == "table_tiles":
        return 0.75 if status == "ok" else 0.45
    if evidence_layer == "table_candidate":
        route = _norm(payload.get("route") or payload.get("repair_route") or payload.get("primary_repair_route"))
        if "table_crop_tile" in route:
            return 0.70
        if "table_candidate_review" in route:
            return 0.45
        return 0.35
    if evidence_layer == "visual_text":
        return 0.65 if status in {"", "ok"} else 0.35
    return 0.50


def _risk_score_from_hallucination(check: EvidenceCheck) -> float:
    if check.status == "blocked":
        return 1.0
    if check.status == "high_risk":
        return 0.85
    if check.status == "medium_risk":
        return 0.50
    if check.status == "low_risk":
        return 0.05
    return _score_from_check(check, neutral=0.25)


def _confidence_tier(score: float) -> str:
    if score >= TRACE_LC_THRESHOLDS["A"]:
        return "A"
    if score >= TRACE_LC_THRESHOLDS["B"]:
        return "B"
    if score >= TRACE_LC_THRESHOLDS["C"]:
        return "C"
    return "D"


def _apply_max_tier(tier: str, max_tier: str) -> str:
    order = {"A": 3, "B": 2, "C": 1, "D": 0}
    if order.get(tier, 0) <= order.get(max_tier, 0):
        return tier
    return max_tier


def compute_confidence_scores(
    *,
    evidence_layer: str,
    source_trace: EvidenceCheck,
    ocr_support: EvidenceCheck,
    graph_support: EvidenceCheck,
    part_support: EvidenceCheck,
    hallucination: EvidenceCheck,
    payload: Mapping[str, Any] | None = None,
    existing_tier: str | None = None,
    status: str = "",
) -> EvidenceConfidenceScores:
    payload = payload or {}
    source_score = _score_from_check(source_trace, neutral=0.0)
    graph_score = _score_from_check(graph_support, neutral=0.5)
    ocr_score = _score_from_check(ocr_support, neutral=0.5)
    catalog_score = _score_from_check(part_support, neutral=0.5)
    layer_score = _extraction_layer_score(evidence_layer, payload, existing_tier)
    weights = TRACE_LC_WEIGHTS
    support = (
        weights["source_trace"] * source_score
        + weights["graph_support"] * graph_score
        + weights["ocr_support"] * ocr_score
        + weights["part_catalog"] * catalog_score
        + weights["extraction_layer"] * layer_score
    )
    risk = _risk_score_from_hallucination(hallucination)
    hard_reasons: list[str] = []
    max_tier = "A"
    hard_blocked = False
    if not _source_ok(source_trace):
        max_tier = "C"
        hard_reasons.append("source trace is not verified; max tier C")
    if hallucination.status == "blocked":
        max_tier = "D"
        hard_blocked = True
        hard_reasons.append("hard hallucination/leakage/refusal gate blocked evidence")
    if status and _norm(status) in {"error", "fail", "failed"}:
        max_tier = "D"
        hard_blocked = True
        hard_reasons.append(f"evidence status is {status}")
    usable = max(0.0, min(1.0, support * (1.0 - risk)))
    tier = _apply_max_tier(_confidence_tier(usable), max_tier)
    return EvidenceConfidenceScores(
        source_trace_score=round(source_score, 6),
        graph_support_score=round(graph_score, 6),
        ocr_support_score=round(ocr_score, 6),
        part_catalog_score=round(catalog_score, 6),
        extraction_layer_score=round(layer_score, 6),
        support_score=round(support, 6),
        risk_score=round(risk, 6),
        usable_confidence=round(usable, 6),
        confidence_tier=tier,
        max_allowed_tier=max_tier,
        hard_gate_blocked=hard_blocked,
        hard_gate_reasons=hard_reasons,
    )


# ---------------------------------------------------------------------------
# Consensus decisions
# ---------------------------------------------------------------------------


def _source_ok(check: EvidenceCheck) -> bool:
    return check.status in SOURCE_OK or check.status in SOURCE_STRONG


def _source_strong(check: EvidenceCheck) -> bool:
    return check.status in SOURCE_STRONG


def _combine_tier(
    *,
    evidence_layer: str,
    source_trace: EvidenceCheck,
    graph_support: EvidenceCheck,
    part_support: EvidenceCheck,
    hallucination: EvidenceCheck,
    existing_tier: str | None = None,
    status: str = "",
) -> str:
    if not _source_ok(source_trace):
        return "D"
    if hallucination.status == "blocked":
        return "D"
    if existing_tier and existing_tier.upper()[:1] in TRUST_TIERS:
        return existing_tier.upper()[:1]
    if status and _norm(status) in {"error", "fail", "failed"}:
        return "D"
    if evidence_layer == "source_trace":
        return "A" if _source_strong(source_trace) else "B"
    if evidence_layer == "part_catalog":
        if part_support.status in {"catalog_or_page_mention_supported", "page_part_mentions_present"}:
            return "A" if _source_strong(source_trace) else "B"
        return "C"
    if evidence_layer == "table_tile_text_refined":
        if part_support.status in {"catalog_or_page_mention_supported", "page_part_mentions_present"}:
            return "A" if _source_strong(source_trace) and hallucination.status == "low_risk" else "B"
        if graph_support.status == "strong_support" and hallucination.status == "low_risk":
            return "B"
        return "C"
    if evidence_layer == "table_tiles":
        # Tiles are useful structure but not yet text evidence.
        return "B" if graph_support.status == "strong_support" and hallucination.status == "low_risk" else "C"
    if evidence_layer == "table_candidate":
        return "C"
    if evidence_layer == "visual_text":
        if hallucination.status == "low_risk" and graph_support.status == "strong_support":
            return "B"
        return "C"
    return "C"


def _actions_for_record(evidence_layer: str, tier: str, source_trace: EvidenceCheck, hallucination: EvidenceCheck, *, route: str = "") -> tuple[str, str, str, list[str]]:
    reasons: list[str] = []
    if not _source_ok(source_trace):
        return "exclude_from_rag", "repair_source_trace", "human_review", ["source trace is not verified"]
    if tier == "D":
        if hallucination.status == "blocked":
            return "exclude_from_rag", "run_cleanup_or_rerun_extraction", "human_review", ["hard hallucination/leakage risk blocks RAG"]
        return "exclude_from_rag", "human_review", "human_review", ["trust tier D blocks RAG"]
    if evidence_layer == "source_trace" and tier in {"A", "B"}:
        return "include_as_source_evidence", "none", "none", ["source trace is usable as evidence"]
    if evidence_layer == "part_catalog" and tier == "A":
        return "include_as_verified_part_evidence", "none", "none", ["part catalog/page mention evidence is source-backed"]
    if evidence_layer == "table_tile_text_refined":
        if tier in {"A", "B"}:
            return "include_as_derived_context", "none", "optional_review", ["refined table tile text has source-backed derived evidence"]
        return "exclude_from_rag", "run_table_tile_ocr_or_human_review", "human_review", ["refined table tile text is not yet supported enough for RAG"]
    if evidence_layer == "table_tiles":
        return "exclude_until_table_text_exists", "run_table_tile_ocr", "not_required_yet", ["table tiles exist but tile text extraction has not run"]
    if evidence_layer == "table_candidate":
        if "table_crop_tile" in route:
            return "exclude_until_table_tiles_exist", "run_table_crop_tile", "not_required_yet", ["table candidate should be tiled before RAG use"]
        return "exclude_from_rag", "review_table_candidate", "human_review", ["weak table candidate needs review"]
    if evidence_layer == "visual_text":
        if tier in {"A", "B"}:
            return "include_as_derived_context", "none", "optional_review", ["visual text is usable only as derived context"]
        return "exclude_from_rag", "ocr_graph_validation_or_human_review", "human_review", ["visual text remains review-needed"]
    if tier in {"A", "B"}:
        return "include_as_derived_context", "none", "optional_review", reasons
    return "exclude_from_rag", "human_review", "human_review", reasons


def _make_record(
    *,
    page_id: str,
    evidence_layer: str,
    evidence_id: str,
    page: Mapping[str, Any] | None,
    part_index: Mapping[str, Mapping[str, Any]],
    source_artifact: str,
    candidate_text: str = "",
    payload: Mapping[str, Any] | None = None,
    trust_signals: Mapping[str, Any] | None = None,
    existing_tier: str | None = None,
    route: str = "",
) -> EvidenceConsensusRecord:
    payload = payload or {}
    trust_signals = trust_signals or {}
    source_trace = check_source_trace(page)
    ocr_support = check_ocr_support(page, candidate_text)
    graph_support = check_graph_support(page, evidence_layer=evidence_layer, table_candidate=payload if evidence_layer == "table_candidate" else None, table_tile=payload if evidence_layer in {"table_tiles", "table_tile_text_refined"} else None)
    part_support = check_part_catalog_support(page_id, part_index, candidate_text)
    hallucination = check_hallucination_risk(payload, trust_signals)
    status = _text(payload.get("status"))
    confidence_scores = compute_confidence_scores(
        evidence_layer=evidence_layer,
        source_trace=source_trace,
        ocr_support=ocr_support,
        graph_support=graph_support,
        part_support=part_support,
        hallucination=hallucination,
        payload=payload,
        existing_tier=existing_tier,
        status=status,
    )
    tier = _combine_tier(
        evidence_layer=evidence_layer,
        source_trace=source_trace,
        graph_support=graph_support,
        part_support=part_support,
        hallucination=hallucination,
        existing_tier=existing_tier,
        status=status,
    )
    rag_action, repair_action, review_action, action_reasons = _actions_for_record(evidence_layer, tier, source_trace, hallucination, route=route)
    reasons: list[str] = []
    for check in (source_trace, ocr_support, graph_support, part_support, hallucination):
        reasons.extend(check.reasons[:3])
    reasons.extend(action_reasons)
    # De-duplicate while preserving order.
    seen = set()
    unique_reasons = []
    for reason in reasons:
        if reason and reason not in seen:
            seen.add(reason)
            unique_reasons.append(reason)
    return EvidenceConsensusRecord(
        page_id=page_id,
        evidence_layer=evidence_layer,
        evidence_id=evidence_id,
        source_trace=source_trace,
        ocr_support=ocr_support,
        graph_support=graph_support,
        part_catalog_support=part_support,
        hallucination_risk=hallucination,
        confidence_scores=confidence_scores,
        trust_tier=tier,
        rag_action=rag_action,
        repair_action=repair_action,
        review_action=review_action,
        reasons=unique_reasons,
        route=route,
        source_artifact=source_artifact,
        properties={
            "status": status,
            "part_number_count": len(_extract_part_numbers(candidate_text)),
            "candidate_text_chars": len(candidate_text or ""),
            "trace_lc_usable_confidence": confidence_scores.usable_confidence,
            "trace_lc_confidence_tier": confidence_scores.confidence_tier,
        },
    )


def build_evidence_consensus_records(paths: EvidenceConsensusPaths, options: EvidenceConsensusOptions) -> tuple[list[EvidenceConsensusRecord], dict[str, Any]]:
    pages = load_page_index(paths.page_index)
    visual_records = load_clean_visual_records(paths.visual_clean_records)
    trust_signals = load_trust_signals(paths.trust_assertions)
    table_candidates = load_table_records(paths.table_candidate_plan)
    table_tiles = load_table_records(paths.table_tile_plan)
    table_tile_text_refined = load_table_tile_text_refined_records(paths.table_tile_text_refined_records)
    part_index = load_part_index(paths.part_tree, pages)
    policy = _as_dict(_read_json(paths.algorithm_policy, {}))

    records: list[EvidenceConsensusRecord] = []
    page_ids = sorted(pages.keys())

    if options.include_source_trace:
        for pid in page_ids:
            records.append(
                _make_record(
                    page_id=pid,
                    evidence_layer="source_trace",
                    evidence_id=f"source_trace:{pid}",
                    page=pages.get(pid),
                    part_index=part_index,
                    source_artifact=str(paths.page_index),
                    candidate_text="",
                )
            )

    if options.include_part_catalog:
        for pid in page_ids:
            part_info = _as_dict(part_index.get(pid))
            if not part_info:
                continue
            candidate_text = " ".join(_as_list(part_info.get("part_numbers")))
            records.append(
                _make_record(
                    page_id=pid,
                    evidence_layer="part_catalog",
                    evidence_id=f"part_catalog:{pid}",
                    page=pages.get(pid),
                    part_index=part_index,
                    source_artifact=str(paths.part_tree),
                    candidate_text=candidate_text,
                    payload=part_info,
                )
            )

    if options.include_visual_text:
        for pid, visual in sorted(visual_records.items()):
            scores = _as_dict(visual.get("visual_text_cleanup_scores"))
            existing_tier = _text(scores.get("trust_tier") or visual.get("trust_tier") or _as_dict(trust_signals.get(pid)).get("visual_text_trust_tier"))
            records.append(
                _make_record(
                    page_id=pid,
                    evidence_layer="visual_text",
                    evidence_id=f"visual_text:{pid}",
                    page=pages.get(pid),
                    part_index=part_index,
                    source_artifact=str(paths.visual_clean_records),
                    candidate_text=_record_text(visual),
                    payload=visual,
                    trust_signals=trust_signals.get(pid, {}),
                    existing_tier=existing_tier,
                )
            )

    if options.include_table_candidates:
        for pid, candidate in sorted(table_candidates.items()):
            route = _text(candidate.get("route") or candidate.get("primary_repair_route") or candidate.get("repair_route"))
            records.append(
                _make_record(
                    page_id=pid,
                    evidence_layer="table_candidate",
                    evidence_id=f"table_candidate:{pid}",
                    page=pages.get(pid),
                    part_index=part_index,
                    source_artifact=str(paths.table_candidate_plan),
                    candidate_text="",
                    payload=candidate,
                    route=route,
                )
            )

    if options.include_table_tiles:
        for pid, tile in sorted(table_tiles.items()):
            route = _text(tile.get("route") or tile.get("primary_repair_route") or tile.get("repair_route"))
            records.append(
                _make_record(
                    page_id=pid,
                    evidence_layer="table_tiles",
                    evidence_id=f"table_tiles:{pid}",
                    page=pages.get(pid),
                    part_index=part_index,
                    source_artifact=str(paths.table_tile_plan),
                    candidate_text="",
                    payload=tile,
                    route=route,
                )
            )

    if options.include_table_tile_text_refined:
        for idx, refined in enumerate(table_tile_text_refined):
            pid = _page_id_from_record(refined)
            tile_id = _tile_id_from_record(refined, idx)
            route = _text(refined.get("route") or refined.get("repair_route") or refined.get("source_route"))
            candidate_text = _record_text(refined)
            for key in (
                "catalog_supported_part_numbers",
                "catalog_supported_parts",
                "canonical_part_numbers",
                "canonical_parts",
                "probable_part_numbers",
                "unsupported_part_candidates",
            ):
                values = _as_list(refined.get(key))
                if values:
                    candidate_text += "\n" + " ".join(_text(v) for v in values)
            records.append(
                _make_record(
                    page_id=pid,
                    evidence_layer="table_tile_text_refined",
                    evidence_id=f"table_tile_text_refined:{pid}:{tile_id}",
                    page=pages.get(pid),
                    part_index=part_index,
                    source_artifact=str(paths.table_tile_text_refined_records),
                    candidate_text=candidate_text,
                    payload=refined,
                    route=route,
                    existing_tier=_record_existing_tier(refined),
                )
            )

    summary = summarize_records(records, pages=pages, policy=policy, paths=paths)
    return records, summary


def summarize_records(records: Sequence[EvidenceConsensusRecord], *, pages: Mapping[str, Any], policy: Mapping[str, Any], paths: EvidenceConsensusPaths) -> dict[str, Any]:
    layer_counts = Counter(r.evidence_layer for r in records)
    tier_counts = Counter(r.trust_tier for r in records)
    rag_counts = Counter(r.rag_action for r in records)
    repair_counts = Counter(r.repair_action for r in records)
    review_counts = Counter(r.review_action for r in records)
    source_counts = Counter(r.source_trace.status for r in records)
    graph_counts = Counter(r.graph_support.status for r in records)
    hallucination_counts = Counter(r.hallucination_risk.status for r in records)
    pages_covered = {r.page_id for r in records if r.page_id}
    rag_include_records = [r for r in records if r.rag_action.startswith("include")]
    unsafe_rag_include = [
        r for r in rag_include_records
        if r.trust_tier == "D" or not _source_ok(r.source_trace)
    ]
    confidence_records = [r for r in records if r.confidence_scores]
    confidence_tier_counts = Counter(r.confidence_scores.confidence_tier for r in confidence_records)
    confidence_disagreements = [r for r in confidence_records if r.confidence_scores.confidence_tier != r.trust_tier]
    avg_usable_confidence = (sum(r.confidence_scores.usable_confidence for r in confidence_records) / len(confidence_records)) if confidence_records else 0.0
    avg_support_score = (sum(r.confidence_scores.support_score for r in confidence_records) / len(confidence_records)) if confidence_records else 0.0
    avg_risk_score = (sum(r.confidence_scores.risk_score for r in confidence_records) / len(confidence_records)) if confidence_records else 0.0
    hard_gate_blocked = [r for r in confidence_records if r.confidence_scores.hard_gate_blocked]
    source_trace_records = layer_counts.get("source_trace", 0)
    visual_text_records = layer_counts.get("visual_text", 0)
    table_candidate_records = layer_counts.get("table_candidate", 0)
    table_tile_records = layer_counts.get("table_tiles", 0)
    table_tile_text_refined_records = layer_counts.get("table_tile_text_refined", 0)
    part_catalog_records = layer_counts.get("part_catalog", 0)
    policy_jobs = _as_dict(policy.get("jobs")) or _as_dict(policy.get("job_selections"))
    return {
        "status": "OK",
        "consensus_version": "trace_net_evidence_consensus_v1_2",
        "confidence_version": TRACE_LC_VERSION,
        "records": len(records),
        "pages_loaded": len(pages),
        "pages_covered": len(pages_covered),
        "source_trace_records": source_trace_records,
        "visual_text_records": visual_text_records,
        "table_candidate_records": table_candidate_records,
        "table_tile_records": table_tile_records,
        "table_tile_text_refined_records": table_tile_text_refined_records,
        "part_catalog_records": part_catalog_records,
        "trust_tier_counts": dict(sorted(tier_counts.items())),
        "confidence_tier_counts": dict(sorted(confidence_tier_counts.items())),
        "confidence_score_records": len(confidence_records),
        "confidence_avg_usable": round(avg_usable_confidence, 6),
        "confidence_avg_support": round(avg_support_score, 6),
        "confidence_avg_risk": round(avg_risk_score, 6),
        "confidence_tier_disagreement_records": len(confidence_disagreements),
        "confidence_hard_gate_blocked_records": len(hard_gate_blocked),
        "confidence_weights": dict(TRACE_LC_WEIGHTS),
        "confidence_thresholds": dict(TRACE_LC_THRESHOLDS),
        "layer_counts": dict(sorted(layer_counts.items())),
        "rag_action_counts": dict(sorted(rag_counts.items())),
        "repair_action_counts": dict(sorted(repair_counts.items())),
        "review_action_counts": dict(sorted(review_counts.items())),
        "source_trace_status_counts": dict(sorted(source_counts.items())),
        "graph_support_status_counts": dict(sorted(graph_counts.items())),
        "hallucination_status_counts": dict(sorted(hallucination_counts.items())),
        "rag_include_records": len(rag_include_records),
        "unsafe_rag_include_records": len(unsafe_rag_include),
        "source_untraceable_records": sum(1 for r in records if not _source_ok(r.source_trace)),
        "algorithm_policy_present": bool(policy),
        "algorithm_policy_jobs": len(policy_jobs) if isinstance(policy_jobs, Mapping) else 0,
        "algorithm_policy_path": str(paths.algorithm_policy),
        "records_path": str(paths.records),
        "summary_path": str(paths.summary),
        "graph_nodes_path": str(paths.graph_nodes),
        "graph_edges_path": str(paths.graph_edges),
        "review_html_path": str(paths.review_html),
    }


# ---------------------------------------------------------------------------
# Output builders
# ---------------------------------------------------------------------------


def build_graph_overlay(records: Sequence[EvidenceConsensusRecord]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def node(node_id: str, node_type: str, **props: Any) -> None:
        nodes.setdefault(node_id, {"id": node_id, "type": node_type, **props})

    for rec in records:
        page_node = f"page:{rec.page_id}"
        consensus_node = f"evidence_consensus:{rec.evidence_layer}:{rec.page_id}"
        trust_node = f"trait:trust:{rec.evidence_layer}:{rec.trust_tier}"
        rag_node = f"trait:rag:{rec.evidence_layer}:{_slug(rec.rag_action)}"
        repair_node = f"trace_net_repair_action:{_slug(rec.repair_action)}"
        node(page_node, "page", page_id=rec.page_id)
        node(
            consensus_node,
            "evidence_consensus",
            page_id=rec.page_id,
            evidence_layer=rec.evidence_layer,
            trust_tier=rec.trust_tier,
            rag_action=rec.rag_action,
            repair_action=rec.repair_action,
            source_trace=rec.source_trace.status,
            graph_support=rec.graph_support.status,
            trace_lc_usable_confidence=rec.confidence_scores.usable_confidence,
            trace_lc_confidence_tier=rec.confidence_scores.confidence_tier,
            trace_lc_support_score=rec.confidence_scores.support_score,
            trace_lc_risk_score=rec.confidence_scores.risk_score,
        )
        node(trust_node, "trait", trait_type="trust", trait_key=rec.evidence_layer, trait_value=rec.trust_tier)
        node(rag_node, "trait", trait_type="rag", trait_key=rec.evidence_layer, trait_value=rec.rag_action)
        node(repair_node, "trace_net_repair_action", repair_action=rec.repair_action)
        edges.append({"source": page_node, "target": consensus_node, "type": "HAS_EVIDENCE_CONSENSUS"})
        edges.append({"source": consensus_node, "target": trust_node, "type": "ASSERTS_TRUST_TIER"})
        edges.append({"source": consensus_node, "target": rag_node, "type": "ASSERTS_RAG_ACTION"})
        edges.append({"source": consensus_node, "target": repair_node, "type": "RECOMMENDS_REPAIR_ACTION"})
        if rec.evidence_layer != "source_trace":
            source_node = f"evidence_artifact:{_slug(rec.source_artifact)}"
            node(source_node, "evidence_artifact", path=rec.source_artifact)
            edges.append({"source": consensus_node, "target": source_node, "type": "DERIVED_FROM"})
    return list(nodes.values()), edges


def build_review_markdown(summary: Mapping[str, Any], records: Sequence[EvidenceConsensusRecord], max_records: int = 200) -> str:
    lines: list[str] = []
    lines.append("# TRACE-Net Evidence Consensus Router v1.2")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    for key in (
        "records",
        "pages_loaded",
        "pages_covered",
        "source_trace_records",
        "visual_text_records",
        "table_candidate_records",
        "table_tile_records",
        "table_tile_text_refined_records",
        "part_catalog_records",
        "rag_include_records",
        "unsafe_rag_include_records",
        "source_untraceable_records",
    ):
        lines.append(f"- **{key}**: {summary.get(key)}")
    lines.append("")
    lines.append("## Trust tiers")
    for key, value in _as_dict(summary.get("trust_tier_counts")).items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## TRACE-LC confidence")
    lines.append(f"- confidence version: {summary.get('confidence_version')}")
    lines.append(f"- scored records: {summary.get('confidence_score_records')}")
    lines.append(f"- average usable confidence: {summary.get('confidence_avg_usable')}")
    lines.append(f"- average support score: {summary.get('confidence_avg_support')}")
    lines.append(f"- average risk score: {summary.get('confidence_avg_risk')}")
    lines.append(f"- score/trust-tier disagreement records: {summary.get('confidence_tier_disagreement_records')}")
    for key, value in _as_dict(summary.get("confidence_tier_counts")).items():
        lines.append(f"- confidence tier {key}: {value}")
    lines.append("")
    lines.append("## RAG actions")
    for key, value in _as_dict(summary.get("rag_action_counts")).items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Sample records")
    lines.append("")
    for rec in list(records)[:max_records]:
        lines.append(f"### {rec.page_id} / {rec.evidence_layer}")
        lines.append("")
        lines.append(f"- Trust tier: **{rec.trust_tier}**")
        lines.append(f"- RAG action: `{rec.rag_action}`")
        lines.append(f"- Repair action: `{rec.repair_action}`")
        lines.append(f"- Source trace: `{rec.source_trace.status}`")
        lines.append(f"- OCR support: `{rec.ocr_support.status}`")
        lines.append(f"- Graph support: `{rec.graph_support.status}`")
        lines.append(f"- Part catalog support: `{rec.part_catalog_support.status}`")
        lines.append(f"- Hallucination risk: `{rec.hallucination_risk.status}`")
        lines.append(f"- TRACE-LC usable confidence: `{rec.confidence_scores.usable_confidence}`")
        lines.append(f"- TRACE-LC confidence tier: `{rec.confidence_scores.confidence_tier}`")
        lines.append(f"- TRACE-LC support/risk: `{rec.confidence_scores.support_score}` / `{rec.confidence_scores.risk_score}`")
        if rec.route:
            lines.append(f"- Route: `{rec.route}`")
        if rec.reasons:
            lines.append("- Reasons:")
            for reason in rec.reasons[:8]:
                lines.append(f"  - {reason}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_review_html(markdown_text: str) -> str:
    # Minimal markdown-ish HTML renderer to avoid optional dependencies.
    body_parts: list[str] = []
    in_list = False
    for raw in markdown_text.splitlines():
        line = raw.rstrip()
        if line.startswith("# "):
            if in_list:
                body_parts.append("</ul>"); in_list = False
            body_parts.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            if in_list:
                body_parts.append("</ul>"); in_list = False
            body_parts.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("### "):
            if in_list:
                body_parts.append("</ul>"); in_list = False
            body_parts.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("- "):
            if not in_list:
                body_parts.append("<ul>"); in_list = True
            body_parts.append(f"<li>{html.escape(line[2:])}</li>")
        elif line.startswith("  - "):
            if not in_list:
                body_parts.append("<ul>"); in_list = True
            body_parts.append(f"<li class='sub'>{html.escape(line[4:])}</li>")
        elif not line.strip():
            if in_list:
                body_parts.append("</ul>"); in_list = False
        else:
            if in_list:
                body_parts.append("</ul>"); in_list = False
            body_parts.append(f"<p>{html.escape(line)}</p>")
    if in_list:
        body_parts.append("</ul>")
    return """<!doctype html>
<html><head><meta charset=\"utf-8\"><title>TRACE-Net Evidence Consensus</title>
<style>
body{font-family:Segoe UI,Arial,sans-serif;margin:24px;background:#faf7f2;color:#172033;line-height:1.45}
h1,h2,h3{color:#172033}.card{background:#fff;border:1px solid #e0d2c1;border-radius:12px;padding:16px;margin:12px 0}
ul{background:#fff;border:1px solid #eadcca;border-radius:10px;padding:12px 24px}.sub{margin-left:20px;color:#46536b}
code{background:#f0ece6;padding:2px 5px;border-radius:4px}strong{font-weight:700}
</style></head><body>
""" + "\n".join(body_parts) + "\n</body></html>\n"


def write_evidence_consensus_outputs(paths: EvidenceConsensusPaths, records: Sequence[EvidenceConsensusRecord], summary: Mapping[str, Any], max_review_records: int = 200) -> dict[str, Path]:
    rows = [r.to_json() for r in records]
    write_jsonl(paths.records, rows)
    _write_json(paths.summary, dict(summary))
    nodes, edges = build_graph_overlay(records)
    _write_json(paths.graph_nodes, nodes)
    _write_json(paths.graph_edges, edges)
    md = build_review_markdown(summary, records, max_review_records)
    paths.review_md.parent.mkdir(parents=True, exist_ok=True)
    paths.review_md.write_text(md, encoding="utf-8")
    paths.review_html.write_text(build_review_html(md), encoding="utf-8")
    # Refresh graph counts in summary after building overlay.
    final_summary = dict(summary)
    final_summary["graph_nodes"] = len(nodes)
    final_summary["graph_edges"] = len(edges)
    _write_json(paths.summary, final_summary)
    return {
        "records": paths.records,
        "summary": paths.summary,
        "graph_nodes": paths.graph_nodes,
        "graph_edges": paths.graph_edges,
        "review_md": paths.review_md,
        "review_html": paths.review_html,
    }


def build_and_write_evidence_consensus(paths: EvidenceConsensusPaths, options: EvidenceConsensusOptions) -> dict[str, Any]:
    records, summary = build_evidence_consensus_records(paths, options)
    written = write_evidence_consensus_outputs(paths, records, summary, options.max_review_records)
    summary = _as_dict(_read_json(paths.summary, summary))
    return {"status": summary.get("status", "OK"), "summary": summary, "records": [r.to_json() for r in records], "paths": {k: str(v) for k, v in written.items()}}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_result(result: Mapping[str, Any]) -> None:
    summary = _as_dict(result.get("summary"))
    print("TRACE-Net evidence consensus router")
    print(f"  Status: {summary.get('status', result.get('status', 'OK'))}")
    print("  Summary:")
    for key in (
        "records",
        "pages_loaded",
        "pages_covered",
        "source_trace_records",
        "visual_text_records",
        "table_candidate_records",
        "table_tile_records",
        "table_tile_text_refined_records",
        "part_catalog_records",
        "rag_include_records",
        "unsafe_rag_include_records",
        "source_untraceable_records",
        "confidence_score_records",
        "confidence_avg_usable",
        "confidence_tier_disagreement_records",
    ):
        print(f"    {key}: {summary.get(key)}")
    print("  Trust tiers:")
    for key, value in _as_dict(summary.get("trust_tier_counts")).items():
        print(f"    {key}: {value}")
    print("  Confidence tiers:")
    for key, value in _as_dict(summary.get("confidence_tier_counts")).items():
        print(f"    {key}: {value}")
    print("  RAG actions:")
    for key, value in _as_dict(summary.get("rag_action_counts")).items():
        print(f"    {key}: {value}")
    print("Files written:")
    for label, path in _as_dict(result.get("paths")).items():
        print(f"  {label}: {path}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Evidence Consensus Router v1.2 records.")
    parser.add_argument("--export-dir", type=Path, default=DEFAULT_EXPORT_DIR)
    parser.add_argument("--visual-text-dir", type=Path, default=DEFAULT_VISUAL_TEXT_DIR)
    parser.add_argument("--trust-trait-dir", type=Path, default=DEFAULT_TRUST_TRAIT_DIR)
    parser.add_argument("--trace-net-dir", type=Path, default=DEFAULT_TRACE_NET_DIR)
    parser.add_argument("--table-dir", type=Path, default=DEFAULT_TABLE_DIR)
    parser.add_argument("--community-dir", type=Path, default=DEFAULT_COMMUNITY_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--expect-pages", type=int, default=None)
    parser.add_argument("--no-source-trace", action="store_true")
    parser.add_argument("--no-visual-text", action="store_true")
    parser.add_argument("--no-table-candidates", action="store_true")
    parser.add_argument("--no-table-tiles", action="store_true")
    parser.add_argument("--no-table-tile-text-refined", action="store_true")
    parser.add_argument("--no-part-catalog", action="store_true")
    parser.add_argument("--samples", type=int, default=200)
    parser.add_argument("--open", action="store_true", help="Open the review HTML after writing.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    paths = EvidenceConsensusPaths(
        export_dir=args.export_dir,
        visual_text_dir=args.visual_text_dir,
        trust_trait_dir=args.trust_trait_dir,
        trace_net_dir=args.trace_net_dir,
        table_dir=args.table_dir,
        community_dir=args.community_dir,
        output_dir=args.output_dir,
    )
    options = EvidenceConsensusOptions(
        expected_pages=args.expect_pages,
        include_source_trace=not args.no_source_trace,
        include_visual_text=not args.no_visual_text,
        include_table_candidates=not args.no_table_candidates,
        include_table_tiles=not args.no_table_tiles,
        include_table_tile_text_refined=not args.no_table_tile_text_refined,
        include_part_catalog=not args.no_part_catalog,
        max_review_records=args.samples,
    )
    result = build_and_write_evidence_consensus(paths, options)
    _print_result(result)
    if args.expect_pages is not None:
        pages_loaded = _to_int(_as_dict(result.get("summary")).get("pages_loaded"))
        if pages_loaded != args.expect_pages:
            print(f"WARNING: pages_loaded={pages_loaded}; expected={args.expect_pages}")
    if args.open:
        webbrowser.open(Path(result["paths"]["review_html"]).resolve().as_uri())
    return 0 if result.get("status", "OK") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
