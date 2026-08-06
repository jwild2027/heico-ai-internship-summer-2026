"""TRACE-Net page-route planner.

TRACE-Net = Traceable Routed Adaptive Context Extraction Network.

This module does not call OCR, Ollama, or a table model. It is a planning and
quality layer that reads the page/card/visual-text artifacts already produced by
this project and decides which extraction route each page should use next.

The planner is deliberately conservative:
- The core page/source graph remains the evidence backbone.
- Vision text is treated as derived context.
- Table-heavy pages are routed away from full-page vision extraction and toward
  a future crop/tile/table route.
- Failed or risky visual outputs become review signals, not trusted facts.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_EXPORT_DIR = Path("local_data/organization/export")
DEFAULT_TRAIT_DIR = Path("local_data/organization/entity_traits")
DEFAULT_VISUAL_TEXT_DIR = Path("local_data/organization/visual_text")
DEFAULT_TRACE_NET_DIR = Path("local_data/organization/trace_net")

_PAGE_ID_KEYS = (
    "page_id",
    "id",
    "node_id",
    "entity_id",
)

PART_RE = re.compile(r"\b[A-Z0-9]{1,4}[-/]?[A-Z0-9]{0,4}[-/]?\d{2,6}(?:[-.][A-Z0-9]{1,6}){0,3}\b")


@dataclass(frozen=True)
class TraceNetPaths:
    """Artifact locations used by the planner."""

    export_dir: Path = DEFAULT_EXPORT_DIR
    trait_dir: Path = DEFAULT_TRAIT_DIR
    visual_text_dir: Path = DEFAULT_VISUAL_TEXT_DIR
    output_dir: Path = DEFAULT_TRACE_NET_DIR

    @property
    def page_index_path(self) -> Path:
        return self.export_dir / "page_index.json"

    @property
    def organization_summary_path(self) -> Path:
        return self.export_dir / "organization_summary.json"

    @property
    def page_cards_path(self) -> Path:
        return self.trait_dir / "page_character_cards.json"

    @property
    def clean_records_path(self) -> Path:
        return self.visual_text_dir / "visual_text_extraction_clean.jsonl"

    @property
    def raw_records_path(self) -> Path:
        return self.visual_text_dir / "visual_text_extraction.jsonl"

    @property
    def clean_summary_path(self) -> Path:
        return self.visual_text_dir / "visual_text_clean_summary.json"

    @property
    def review_flags_path(self) -> Path:
        return self.visual_text_dir / "visual_text_review_flags.json"

    @property
    def plan_path(self) -> Path:
        return self.output_dir / "trace_net_plan.json"

    @property
    def plan_jsonl_path(self) -> Path:
        return self.output_dir / "trace_net_plan.jsonl"

    @property
    def summary_path(self) -> Path:
        return self.output_dir / "trace_net_plan_summary.json"

    @property
    def graph_nodes_path(self) -> Path:
        return self.output_dir / "trace_net_graph_nodes.json"

    @property
    def graph_edges_path(self) -> Path:
        return self.output_dir / "trace_net_graph_edges.json"

    @property
    def review_md_path(self) -> Path:
        return self.output_dir / "trace_net_plan_review.md"


@dataclass
class TraceNetOptions:
    expected_pages: int | None = None
    include_review_only: bool = True
    high_value_only: bool = False
    write_review_md: bool = True


@dataclass
class TraceNetRoute:
    page_id: str
    route: str
    priority: str
    recommended_extractor: str
    recommended_prompt_version: str | None = None
    recommended_max_image_edge: int | None = None
    recommended_timeout_seconds: int | None = None
    fishnet_enabled: bool = False
    skip_model: bool = False
    needs_human_review: bool = False
    usable_for_rag: bool = False
    trust_tier: str = "C"
    reasons: list[str] = field(default_factory=list)
    source_signals: dict[str, Any] = field(default_factory=dict)
    safety_layers: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Low-level IO helpers
# ---------------------------------------------------------------------------


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except Exception:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(dict(row), ensure_ascii=False) + "\n")


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        return list(value.values())
    return [value]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def _first_present(row: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _page_id(row: Mapping[str, Any]) -> str | None:
    raw = _first_present(row, _PAGE_ID_KEYS)
    if raw is None:
        return None
    value = str(raw)
    if value.startswith("page:"):
        value = value.split(":", 1)[1]
    return value


def _normalize_role(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "_")
    aliases = {
        "frontmatter": "front_matter",
        "front-matter": "front_matter",
        "partslist": "parts_list",
        "parts-list": "parts_list",
        "diagram": "figure",
    }
    return aliases.get(text, text or "unknown")


def _flatten_strings(value: Any) -> list[str]:
    out: list[str] = []
    if value is None:
        return out
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, Mapping):
        for item in value.values():
            out.extend(_flatten_strings(item))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            out.extend(_flatten_strings(item))
    else:
        out.append(str(value))
    return out


def _find_in_strings(strings: Iterable[str], needles: Sequence[str]) -> bool:
    haystack = "\n".join(strings).lower()
    return any(n.lower() in haystack for n in needles)


# ---------------------------------------------------------------------------
# Artifact normalization
# ---------------------------------------------------------------------------


def load_page_index(paths: TraceNetPaths) -> dict[str, dict[str, Any]]:
    raw = _read_json(paths.page_index_path, {})
    pages: dict[str, dict[str, Any]] = {}

    if isinstance(raw, Mapping):
        candidates: list[Any] = []
        if isinstance(raw.get("pages"), list):
            candidates = list(raw.get("pages") or [])
        elif isinstance(raw.get("page_index"), list):
            candidates = list(raw.get("page_index") or [])
        elif all(isinstance(v, Mapping) for v in raw.values()):
            candidates = list(raw.values())
        for key, value in raw.items():
            if isinstance(value, Mapping):
                row = dict(value)
                row.setdefault("page_id", key)
                pid = _page_id(row)
                if pid:
                    pages[pid] = row
        for item in candidates:
            if isinstance(item, Mapping):
                pid = _page_id(item)
                if pid:
                    pages.setdefault(pid, dict(item))
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, Mapping):
                pid = _page_id(item)
                if pid:
                    pages[pid] = dict(item)
    return pages


def load_page_cards(paths: TraceNetPaths) -> dict[str, dict[str, Any]]:
    raw = _read_json(paths.page_cards_path, {})
    cards: dict[str, dict[str, Any]] = {}
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, Mapping):
        values = list(raw.values()) if all(isinstance(v, Mapping) for v in raw.values()) else _as_list(raw.get("pages"))
    else:
        values = []
    for item in values:
        if not isinstance(item, Mapping):
            continue
        row = dict(item)
        pid = _page_id(row)
        if pid:
            cards[pid] = row
    return cards


def load_visual_records(paths: TraceNetPaths) -> dict[str, dict[str, Any]]:
    rows = _read_jsonl(paths.clean_records_path)
    if not rows:
        rows = _read_jsonl(paths.raw_records_path)
    records: dict[str, dict[str, Any]] = {}
    for row in rows:
        pid = _page_id(row)
        if pid:
            records[pid] = row
    return records


def load_review_flags(paths: TraceNetPaths) -> dict[str, dict[str, Any]]:
    raw = _read_json(paths.review_flags_path, {})
    flags: dict[str, dict[str, Any]] = {}
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, Mapping):
        if isinstance(raw.get("records"), list):
            rows = raw["records"]
        elif isinstance(raw.get("flags"), list):
            rows = raw["flags"]
        else:
            rows = []
            for key, value in raw.items():
                if isinstance(value, Mapping):
                    row = dict(value)
                    row.setdefault("page_id", key)
                    rows.append(row)
    else:
        rows = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        pid = _page_id(row)
        if pid:
            flags[pid] = dict(row)
    return flags


# ---------------------------------------------------------------------------
# Signal extraction
# ---------------------------------------------------------------------------


def _traits_from_card(card: Mapping[str, Any]) -> list[str]:
    traits: list[str] = []
    for key in ("traits", "direct_traits", "derived_traits", "trait_keys", "trait_values"):
        traits.extend(_flatten_strings(card.get(key)))
    for key in ("roles", "signals", "image", "visual", "source", "quality"):
        traits.extend(_flatten_strings(card.get(key)))
    return traits


def _page_role(page: Mapping[str, Any], card: Mapping[str, Any], visual: Mapping[str, Any]) -> str:
    for source in (page, card, visual):
        for key in ("page_role", "role", "context_role", "current_page_role"):
            value = source.get(key)
            if value:
                return _normalize_role(value)
        nested = _as_dict(source.get("roles"))
        for key in ("page_role", "context_role", "role"):
            value = nested.get(key)
            if value:
                return _normalize_role(value)
    traits = _traits_from_card(card)
    for role in ("blank", "front_matter", "figure", "table", "parts_list", "procedure"):
        if _find_in_strings(traits, [f"page_role:{role}", f"page_role={role}", role]):
            return role
    return "unknown"


def _image_classes(page: Mapping[str, Any], card: Mapping[str, Any], visual: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for source in (page, card, visual):
        for key in ("image_class", "image_classes", "visual_class", "visual_classes", "classification", "class"):
            values.extend(_flatten_strings(source.get(key)))
        nested = _as_dict(source.get("image"))
        values.extend(_flatten_strings(nested.get("classes")))
        values.extend(_flatten_strings(nested.get("classification")))
    values.extend(_traits_from_card(card))
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip().lower().replace(" ", "_")
        if "likely_table" in text or "table_or_grid" in text:
            token = "likely_table_or_grid"
        elif "likely_figure" in text or "figure_or_diagram" in text or "diagram" in text:
            token = "likely_figure_or_diagram"
        elif "likely_blank" in text or "blank" == text:
            token = "likely_blank"
        elif "likely_text" in text or "parts_list" in text:
            token = "likely_text_or_parts_list"
        else:
            continue
        if token not in seen:
            seen.add(token)
            normalized.append(token)
    return normalized


def _bool_from_sources(key: str, sources: Sequence[Mapping[str, Any]]) -> bool:
    for source in sources:
        value = source.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            if value.strip().lower() in {"true", "yes", "1", "y"}:
                return True
    return False


def _visual_scores(visual: Mapping[str, Any], flags: Mapping[str, Any]) -> dict[str, Any]:
    scores = _as_dict(visual.get("scores"))
    merged: dict[str, Any] = {}
    for key in (
        "required_sections_present",
        "metadata_leakage_risk",
        "prompt_template_leakage",
        "prompt_template_leakage_risk",
        "section_bleed",
        "section_bleed_risk",
        "refusal_like",
        "too_summary_heavy",
        "hallucination_risk",
        "has_table_rows",
        "has_figure_description",
        "has_labels_or_callouts",
        "has_part_numbers",
        "has_ocr_context_notes",
        "usable_for_rag",
        "requires_human_review",
        "table_expected_missing",
    ):
        merged[key] = _bool_from_sources(key, [scores, visual, flags])
    for key in ("trust_tier", "clean_trust_tier", "tier"):
        value = flags.get(key) or visual.get(key) or scores.get(key)
        if value:
            merged["trust_tier"] = str(value).upper()[:1]
            break
    return merged


def build_page_signals(
    page_id: str,
    page: Mapping[str, Any],
    card: Mapping[str, Any],
    visual: Mapping[str, Any],
    flags: Mapping[str, Any],
) -> dict[str, Any]:
    role = _page_role(page, card, visual)
    image_classes = _image_classes(page, card, visual)
    scores = _visual_scores(visual, flags)
    traits = _traits_from_card(card)
    text_blob = "\n".join(_flatten_strings(visual))
    part_numbers = sorted(set(PART_RE.findall(text_blob)))

    source_url = page.get("source_url") or card.get("source_url") or visual.get("source_url")
    tiff_path = page.get("tiff_path") or page.get("source_tiff_path") or card.get("tiff_path") or visual.get("tiff_path")
    ocr_path = page.get("ocr_path") or page.get("source_ocr_path") or card.get("ocr_path") or visual.get("ocr_path")

    return {
        "page_id": page_id,
        "role": role,
        "image_classes": image_classes,
        "traits": traits,
        "has_source_url": bool(source_url),
        "has_tiff_path": bool(tiff_path),
        "has_ocr_path": bool(ocr_path),
        "visual_status": str(visual.get("status") or flags.get("status") or "unknown").lower(),
        "visual_prompt_version": visual.get("prompt_version") or flags.get("prompt_version"),
        "visual_scores": scores,
        "visual_part_numbers": part_numbers,
        "part_number_count": len(part_numbers),
    }


# ---------------------------------------------------------------------------
# Routing logic
# ---------------------------------------------------------------------------


def _priority_from_reasons(reasons: Sequence[str]) -> str:
    high = {
        "visual_error_or_missing",
        "trust_tier_d",
        "prompt_template_leakage",
        "metadata_leakage",
        "refusal_like",
        "table_expected_missing",
        "table_page_needs_table_route",
    }
    medium = {
        "hallucination_risk",
        "section_bleed",
        "summary_heavy",
        "trust_tier_c",
        "no_visual_record",
    }
    if any(reason in high for reason in reasons):
        return "high"
    if any(reason in medium for reason in reasons):
        return "medium"
    return "normal"


def _base_route(role: str, image_classes: Sequence[str], traits: Sequence[str]) -> str:
    trait_text = "\n".join(traits).lower()
    classes = set(image_classes)
    if role == "blank" or "likely_blank" in classes or "verified_blank_page" in trait_text:
        return "blank"
    if role in {"front_matter"}:
        return "front_matter"
    if role == "figure" or "likely_figure_or_diagram" in classes:
        return "figure_diagram"
    if role == "table" or "likely_table_or_grid" in classes:
        return "table_grid"
    if role == "parts_list":
        return "parts_list"
    if role == "procedure":
        return "procedure_text"
    return "general_text"


def _extractor_for_route(route: str) -> tuple[str, str | None, int | None, int | None, bool, bool, list[dict[str, Any]]]:
    if route == "blank":
        return ("skip_blank", None, None, None, True, False, [])
    if route == "table_grid":
        return (
            "grit_table_crop_tile_route",
            "table_text_v1_planned",
            1024,
            600,
            False,
            True,
            [
                {"name": "table_tile_768", "max_image_edge": 768, "timeout_seconds": 1200},
                {"name": "table_tile_512", "max_image_edge": 512, "timeout_seconds": 1200},
            ],
        )
    if route == "figure_diagram":
        return (
            "vision_figure_callout_route",
            "visual_text_v2_2",
            1024,
            600,
            False,
            True,
            [
                {"name": "rescue_768", "max_image_edge": 768, "timeout_seconds": 1200},
                {"name": "rescue_512", "max_image_edge": 512, "timeout_seconds": 1200},
            ],
        )
    if route == "parts_list":
        return (
            "ocr_part_catalog_validation_route",
            "visual_text_v2_2",
            1024,
            600,
            False,
            True,
            [
                {"name": "rescue_768", "max_image_edge": 768, "timeout_seconds": 1200},
                {"name": "rescue_512", "max_image_edge": 512, "timeout_seconds": 1200},
            ],
        )
    if route == "front_matter":
        return (
            "title_header_context_route",
            "visual_text_v2_2",
            1024,
            600,
            False,
            True,
            [{"name": "rescue_768", "max_image_edge": 768, "timeout_seconds": 1200}],
        )
    if route == "procedure_text":
        return (
            "ocr_context_warning_note_route",
            "visual_text_v2_2",
            1024,
            600,
            False,
            True,
            [{"name": "rescue_768", "max_image_edge": 768, "timeout_seconds": 1200}],
        )
    return (
        "ocr_context_general_route",
        "visual_text_v2_2",
        1024,
        600,
        False,
        True,
        [{"name": "rescue_768", "max_image_edge": 768, "timeout_seconds": 1200}],
    )


def plan_page_route(signals: Mapping[str, Any]) -> TraceNetRoute:
    role = str(signals.get("role") or "unknown")
    image_classes = list(signals.get("image_classes") or [])
    traits = list(signals.get("traits") or [])
    scores = _as_dict(signals.get("visual_scores"))
    visual_status = str(signals.get("visual_status") or "unknown").lower()
    route = _base_route(role, image_classes, traits)

    reasons: list[str] = []
    if visual_status in {"error", "fail", "failed", "partial"}:
        reasons.append("visual_error_or_missing")
    if not signals.get("visual_prompt_version"):
        reasons.append("no_visual_record")
    if scores.get("metadata_leakage_risk"):
        reasons.append("metadata_leakage")
    if scores.get("refusal_like"):
        reasons.append("refusal_like")
    if scores.get("prompt_template_leakage") or scores.get("prompt_template_leakage_risk"):
        reasons.append("prompt_template_leakage")
    if scores.get("section_bleed") or scores.get("section_bleed_risk"):
        reasons.append("section_bleed")
    if scores.get("too_summary_heavy"):
        reasons.append("summary_heavy")
    if scores.get("hallucination_risk"):
        reasons.append("hallucination_risk")

    trust_tier = str(scores.get("trust_tier") or "C").upper()[:1]
    if trust_tier == "D":
        reasons.append("trust_tier_d")
    elif trust_tier == "C":
        reasons.append("trust_tier_c")

    tableish = route == "table_grid" or "likely_table_or_grid" in image_classes
    if tableish and not scores.get("has_table_rows"):
        reasons.append("table_expected_missing")
        if route == "table_grid":
            reasons.append("table_page_needs_table_route")

    if route == "blank":
        reasons.append("blank_or_low_value")

    recommended_extractor, prompt_version, edge, timeout, skip_model, fishnet, layers = _extractor_for_route(route)
    priority = _priority_from_reasons(reasons)

    needs_review = bool(
        trust_tier in {"C", "D"}
        or any(
            reason in reasons
            for reason in (
                "metadata_leakage",
                "refusal_like",
                "prompt_template_leakage",
                "section_bleed",
                "hallucination_risk",
                "table_expected_missing",
                "visual_error_or_missing",
            )
        )
    )
    usable_for_rag = bool(
        route != "blank"
        and trust_tier in {"A", "B"}
        and not any(
            reason in reasons
            for reason in (
                "metadata_leakage",
                "refusal_like",
                "prompt_template_leakage",
                "visual_error_or_missing",
                "trust_tier_d",
            )
        )
    )

    return TraceNetRoute(
        page_id=str(signals["page_id"]),
        route=route,
        priority=priority,
        recommended_extractor=recommended_extractor,
        recommended_prompt_version=prompt_version,
        recommended_max_image_edge=edge,
        recommended_timeout_seconds=timeout,
        fishnet_enabled=fishnet,
        skip_model=skip_model,
        needs_human_review=needs_review,
        usable_for_rag=usable_for_rag,
        trust_tier=trust_tier,
        reasons=sorted(set(reasons)),
        source_signals={
            "role": role,
            "image_classes": image_classes,
            "visual_status": visual_status,
            "visual_prompt_version": signals.get("visual_prompt_version"),
            "has_source_url": signals.get("has_source_url"),
            "has_tiff_path": signals.get("has_tiff_path"),
            "has_ocr_path": signals.get("has_ocr_path"),
            "part_number_count": signals.get("part_number_count", 0),
            "visual_scores": scores,
        },
        safety_layers=layers,
    )


# ---------------------------------------------------------------------------
# Plan build + outputs
# ---------------------------------------------------------------------------


def build_trace_net_plan(paths: TraceNetPaths, options: TraceNetOptions | None = None) -> dict[str, Any]:
    options = options or TraceNetOptions()
    page_index = load_page_index(paths)
    page_cards = load_page_cards(paths)
    visual_records = load_visual_records(paths)
    review_flags = load_review_flags(paths)

    all_page_ids = sorted(set(page_index) | set(page_cards) | set(visual_records) | set(review_flags))
    routes: list[TraceNetRoute] = []
    for pid in all_page_ids:
        signals = build_page_signals(
            pid,
            page_index.get(pid, {}),
            page_cards.get(pid, {}),
            visual_records.get(pid, {}),
            review_flags.get(pid, {}),
        )
        route = plan_page_route(signals)
        if options.high_value_only and route.route in {"blank", "front_matter"}:
            continue
        routes.append(route)

    summary = summarize_trace_net_plan(routes, paths, options, page_index, page_cards, visual_records, review_flags)
    plan = {
        "status": summary["status"],
        "summary": summary,
        "routes": [route.to_json() for route in routes],
    }
    return plan


def summarize_trace_net_plan(
    routes: Sequence[TraceNetRoute],
    paths: TraceNetPaths,
    options: TraceNetOptions,
    page_index: Mapping[str, Any] | None = None,
    page_cards: Mapping[str, Any] | None = None,
    visual_records: Mapping[str, Any] | None = None,
    review_flags: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    page_index = page_index or {}
    page_cards = page_cards or {}
    visual_records = visual_records or {}
    review_flags = review_flags or {}
    route_counts = Counter(route.route for route in routes)
    priority_counts = Counter(route.priority for route in routes)
    extractor_counts = Counter(route.recommended_extractor for route in routes)
    trust_counts = Counter(route.trust_tier for route in routes)
    reason_counts: Counter[str] = Counter()
    for route in routes:
        reason_counts.update(route.reasons)

    total = len(routes)
    ok = total > 0
    if options.expected_pages is not None and total != options.expected_pages:
        ok = False

    return {
        "status": "OK" if ok else "FAIL",
        "records": total,
        "expected_pages": options.expected_pages,
        "page_index_records": len(page_index),
        "page_card_records": len(page_cards),
        "visual_text_records": len(visual_records),
        "review_flag_records": len(review_flags),
        "route_counts": dict(sorted(route_counts.items())),
        "priority_counts": dict(sorted(priority_counts.items())),
        "extractor_counts": dict(sorted(extractor_counts.items())),
        "trust_tier_counts": dict(sorted(trust_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "usable_for_rag_records": sum(1 for route in routes if route.usable_for_rag),
        "needs_human_review_records": sum(1 for route in routes if route.needs_human_review),
        "fishnet_enabled_records": sum(1 for route in routes if route.fishnet_enabled),
        "skip_model_records": sum(1 for route in routes if route.skip_model),
        "table_route_records": route_counts.get("table_grid", 0),
        "figure_route_records": route_counts.get("figure_diagram", 0),
        "parts_list_route_records": route_counts.get("parts_list", 0),
        "front_matter_route_records": route_counts.get("front_matter", 0),
        "blank_route_records": route_counts.get("blank", 0),
        "trace_net_version": "trace_net_v0_1_planner",
        "paths": {
            "page_index": str(paths.page_index_path),
            "page_cards": str(paths.page_cards_path),
            "visual_records_clean": str(paths.clean_records_path),
            "visual_records_raw": str(paths.raw_records_path),
            "output_dir": str(paths.output_dir),
        },
    }


def build_trace_net_graph(plan: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    route_nodes: set[str] = set()
    extractor_nodes: set[str] = set()
    reason_nodes: set[str] = set()

    nodes.append({"id": "trace_net:planner", "type": "trace_net_planner", "label": "TRACE-Net planner"})
    for row in _as_list(plan.get("routes")):
        if not isinstance(row, Mapping):
            continue
        pid = str(row.get("page_id"))
        route = str(row.get("route"))
        extractor = str(row.get("recommended_extractor"))
        page_node = f"page:{pid}"
        route_node = f"trace_route:{route}"
        extractor_node = f"trace_extractor:{extractor}"
        nodes.append({"id": f"trace_plan:{pid}", "type": "trace_net_page_plan", "page_id": pid, "label": f"TRACE plan {pid}", **dict(row)})
        if route_node not in route_nodes:
            route_nodes.add(route_node)
            nodes.append({"id": route_node, "type": "trace_net_route", "route": route, "label": route})
        if extractor_node not in extractor_nodes:
            extractor_nodes.add(extractor_node)
            nodes.append({"id": extractor_node, "type": "trace_net_extractor", "extractor": extractor, "label": extractor})
        edges.append({"source": page_node, "target": f"trace_plan:{pid}", "type": "HAS_TRACE_NET_PLAN"})
        edges.append({"source": f"trace_plan:{pid}", "target": route_node, "type": "USES_ROUTE"})
        edges.append({"source": f"trace_plan:{pid}", "target": extractor_node, "type": "RECOMMENDS_EXTRACTOR"})
        for reason in row.get("reasons") or []:
            reason_node = f"trace_reason:{reason}"
            if reason_node not in reason_nodes:
                reason_nodes.add(reason_node)
                nodes.append({"id": reason_node, "type": "trace_net_reason", "reason": reason, "label": reason})
            edges.append({"source": f"trace_plan:{pid}", "target": reason_node, "type": "HAS_REASON"})
    return nodes, edges


def write_trace_net_plan(plan: Mapping[str, Any], paths: TraceNetPaths) -> None:
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    routes = _as_list(plan.get("routes"))
    _write_json(paths.plan_path, plan)
    _write_jsonl(paths.plan_jsonl_path, [r for r in routes if isinstance(r, Mapping)])
    _write_json(paths.summary_path, plan.get("summary", {}))
    nodes, edges = build_trace_net_graph(plan)
    _write_json(paths.graph_nodes_path, nodes)
    _write_json(paths.graph_edges_path, edges)
    summary = _as_dict(plan.get("summary"))
    review_md = format_trace_net_review(plan)
    paths.review_md_path.write_text(review_md, encoding="utf-8")


def format_trace_net_review(plan: Mapping[str, Any], limit: int = 80) -> str:
    summary = _as_dict(plan.get("summary"))
    routes = [r for r in _as_list(plan.get("routes")) if isinstance(r, Mapping)]
    lines: list[str] = []
    lines.append("# TRACE-Net route plan")
    lines.append("")
    lines.append(f"Status: **{summary.get('status', plan.get('status', 'unknown'))}**")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    for key in (
        "records",
        "usable_for_rag_records",
        "needs_human_review_records",
        "fishnet_enabled_records",
        "table_route_records",
        "figure_route_records",
        "parts_list_route_records",
        "front_matter_route_records",
        "blank_route_records",
    ):
        lines.append(f"- {key}: {summary.get(key)}")
    lines.append("")
    for key in ("route_counts", "priority_counts", "trust_tier_counts", "extractor_counts", "reason_counts"):
        lines.append(f"## {key}")
        lines.append("")
        value = _as_dict(summary.get(key))
        if not value:
            lines.append("- none")
        else:
            for k, v in sorted(value.items(), key=lambda kv: str(kv[0])):
                lines.append(f"- {k}: {v}")
        lines.append("")
    lines.append("## Sample page plans")
    lines.append("")
    for row in routes[:limit]:
        lines.append(f"### {row.get('page_id')}")
        lines.append("")
        lines.append(f"- route: `{row.get('route')}`")
        lines.append(f"- priority: `{row.get('priority')}`")
        lines.append(f"- extractor: `{row.get('recommended_extractor')}`")
        lines.append(f"- trust tier: `{row.get('trust_tier')}`")
        lines.append(f"- usable_for_rag: `{row.get('usable_for_rag')}`")
        lines.append(f"- needs_human_review: `{row.get('needs_human_review')}`")
        reasons = row.get("reasons") or []
        lines.append(f"- reasons: {', '.join(reasons) if reasons else 'none'}")
        layers = row.get("safety_layers") or []
        if layers:
            layer_text = ", ".join(f"{l.get('name')}({l.get('max_image_edge')}/{l.get('timeout_seconds')})" for l in layers)
            lines.append(f"- safety layers: {layer_text}")
        lines.append("")
    return "\n".join(lines)


def build_and_write_trace_net_plan(paths: TraceNetPaths, options: TraceNetOptions | None = None) -> dict[str, Any]:
    plan = build_trace_net_plan(paths, options)
    write_trace_net_plan(plan, paths)
    return plan


# ---------------------------------------------------------------------------
# Quality gate
# ---------------------------------------------------------------------------


def build_trace_net_quality(paths: TraceNetPaths, min_records: int = 1, expected_pages: int | None = None) -> dict[str, Any]:
    summary = _read_json(paths.summary_path, {})
    plan = _read_json(paths.plan_path, {})
    routes = _read_jsonl(paths.plan_jsonl_path)
    graph_nodes = _read_json(paths.graph_nodes_path, [])
    graph_edges = _read_json(paths.graph_edges_path, [])

    summary_present = bool(summary)
    plan_present = bool(plan)
    routes_present = bool(routes)
    graph_nodes_present = isinstance(graph_nodes, list) and len(graph_nodes) > 0
    graph_edges_present = isinstance(graph_edges, list) and len(graph_edges) > 0
    records = int(summary.get("records") or len(routes) or 0)
    status = str(summary.get("status") or plan.get("status") or "missing").lower()

    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, message: str) -> None:
        checks.append({"name": name, "status": "OK" if ok else "FAIL", "message": message})

    add("trace_net_artifacts_present", summary_present and plan_present and routes_present, f"summary={summary_present}; plan={plan_present}; routes={routes_present}.")
    add("trace_net_status", status == "ok", f"TRACE-Net plan status is {status!r}.")
    add("trace_net_records", records >= min_records, f"records={records}; minimum={min_records}.")
    if expected_pages is not None:
        add("trace_net_expected_pages", records == expected_pages, f"records={records}; expected={expected_pages}.")
    add("trace_net_graph_overlay_nodes", graph_nodes_present, f"graph nodes present={graph_nodes_present}; count={len(graph_nodes) if isinstance(graph_nodes, list) else 0}.")
    add("trace_net_graph_overlay_edges", graph_edges_present, f"graph edges present={graph_edges_present}; count={len(graph_edges) if isinstance(graph_edges, list) else 0}.")
    add("trace_net_route_counts", bool(summary.get("route_counts")), f"route_counts={summary.get('route_counts', {})}.")
    add("trace_net_extractor_counts", bool(summary.get("extractor_counts")), f"extractor_counts={summary.get('extractor_counts', {})}.")

    ok = all(check["status"] == "OK" for check in checks)
    quality = {
        "status": "OK" if ok else "FAIL",
        "summary": {
            "trace_net_summary_present": summary_present,
            "trace_net_plan_present": plan_present,
            "trace_net_routes_present": routes_present,
            "trace_net_status": status,
            "trace_net_records": records,
            "trace_net_expected_pages": expected_pages,
            "trace_net_route_counts": summary.get("route_counts", {}),
            "trace_net_priority_counts": summary.get("priority_counts", {}),
            "trace_net_trust_tier_counts": summary.get("trust_tier_counts", {}),
            "trace_net_extractor_counts": summary.get("extractor_counts", {}),
            "trace_net_usable_for_rag_records": summary.get("usable_for_rag_records", 0),
            "trace_net_needs_human_review_records": summary.get("needs_human_review_records", 0),
            "trace_net_fishnet_enabled_records": summary.get("fishnet_enabled_records", 0),
            "trace_net_graph_nodes_present": graph_nodes_present,
            "trace_net_graph_edges_present": graph_edges_present,
            "trace_net_graph_nodes": len(graph_nodes) if isinstance(graph_nodes, list) else 0,
            "trace_net_graph_edges": len(graph_edges) if isinstance(graph_edges, list) else 0,
            "trace_net_summary_path": str(paths.summary_path),
            "trace_net_plan_path": str(paths.plan_path),
            "trace_net_plan_jsonl_path": str(paths.plan_jsonl_path),
        },
        "checks": checks,
    }
    return quality


def write_trace_net_quality(quality: Mapping[str, Any], paths: TraceNetPaths) -> Path:
    out = paths.output_dir / "trace_net_quality.json"
    _write_json(out, quality)
    return out


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


def print_trace_net_plan(plan: Mapping[str, Any], paths: TraceNetPaths, samples: int = 10) -> None:
    summary = _as_dict(plan.get("summary"))
    print("TRACE-Net route planner")
    print(f"  Status: {summary.get('status', plan.get('status', 'unknown'))}")
    print(f"  Output dir: {paths.output_dir}")
    print("  Summary:")
    for key in (
        "records",
        "usable_for_rag_records",
        "needs_human_review_records",
        "fishnet_enabled_records",
        "skip_model_records",
        "table_route_records",
        "figure_route_records",
        "parts_list_route_records",
        "front_matter_route_records",
        "blank_route_records",
    ):
        print(f"    {key}: {summary.get(key)}")
    print("  Route counts:")
    for key, value in _as_dict(summary.get("route_counts")).items():
        print(f"    {key}: {value}")
    print("  Extractor counts:")
    for key, value in _as_dict(summary.get("extractor_counts")).items():
        print(f"    {key}: {value}")
    print("  Reason counts:")
    for key, value in list(_as_dict(summary.get("reason_counts")).items())[:20]:
        print(f"    {key}: {value}")

    routes = [r for r in _as_list(plan.get("routes")) if isinstance(r, Mapping)]
    if routes:
        print("  Sample routes:")
        for row in routes[:samples]:
            reasons = ",".join(row.get("reasons") or []) or "none"
            layer = ""
            if row.get("fishnet_enabled"):
                layer = " fishnet=yes"
            print(
                f"    {row.get('page_id')} | route={row.get('route')} | "
                f"priority={row.get('priority')} | extractor={row.get('recommended_extractor')} | "
                f"tier={row.get('trust_tier')} | reasons={reasons}{layer}"
            )
    print("Files written:")
    print(f"  plan: {paths.plan_path}")
    print(f"  plan_jsonl: {paths.plan_jsonl_path}")
    print(f"  summary: {paths.summary_path}")
    print(f"  graph_nodes: {paths.graph_nodes_path}")
    print(f"  graph_edges: {paths.graph_edges_path}")
    print(f"  review_md: {paths.review_md_path}")


def print_trace_net_quality(quality: Mapping[str, Any]) -> None:
    summary = _as_dict(quality.get("summary"))
    print("TRACE-Net plan quality gate")
    print(f"  Status: {quality.get('status')}")
    print("  Summary:")
    for key, value in summary.items():
        print(f"    {key}: {value}")
    print("  Checks:")
    for check in quality.get("checks") or []:
        print(f"    {check.get('status')} {check.get('name')}: {check.get('message')}")


def _paths_from_args(args: argparse.Namespace) -> TraceNetPaths:
    return TraceNetPaths(
        export_dir=Path(args.export_dir),
        trait_dir=Path(args.trait_dir),
        visual_text_dir=Path(args.visual_text_dir),
        output_dir=Path(args.output_dir),
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net page extraction route plan.")
    parser.add_argument("--export-dir", default=str(DEFAULT_EXPORT_DIR))
    parser.add_argument("--trait-dir", default=str(DEFAULT_TRAIT_DIR))
    parser.add_argument("--visual-text-dir", default=str(DEFAULT_VISUAL_TEXT_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_TRACE_NET_DIR))
    parser.add_argument("--expect-pages", type=int, default=None)
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--high-value-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    paths = _paths_from_args(args)
    options = TraceNetOptions(expected_pages=args.expect_pages, high_value_only=args.high_value_only)
    plan = build_and_write_trace_net_plan(paths, options)
    print_trace_net_plan(plan, paths, samples=args.samples)
    return 0 if plan.get("status") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
