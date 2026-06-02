"""TRACE-Net repair planner.

TRACE-Net = Traceable Routed Adaptive Context Extraction Network.

This module reads the visual-text clean records and trust-trait overlay, then
plans the next repair action for each page. It does not call Ollama, OCR, or a
table extractor. It is a decision layer that converts trust traits into an
operational queue:

- safe visual text can be included later in RAG;
- prompt/template or section-bleed issues go to cleanup/salvage;
- table/grid pages with no table rows are refined into high/medium/low table candidates before a future crop/tile table route;
- hallucination/suspicious phrases go to OCR/catalog/graph validation;
- unresolved C/D records remain human-review candidates.

The output is intentionally graph-shaped so the repair plan can be traversed in
the same page/trait style as the rest of the project.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_VISUAL_TEXT_DIR = Path("local_data/organization/visual_text")
DEFAULT_TRUST_TRAIT_DIR = Path("local_data/organization/trust_traits")
DEFAULT_TRACE_NET_DIR = Path("local_data/organization/trace_net")

TRUST_TIERS = {"A", "B", "C", "D"}
RAG_INCLUDE = "include_visual_text"
RAG_EXCLUDE = "exclude_visual_text"

TABLE_ROUTE_HIGH = "table_crop_tile_repair_route_high"
TABLE_ROUTE_MEDIUM = "table_crop_tile_repair_route_medium"
TABLE_ROUTE_LOW = "table_candidate_review_route"
TABLE_ROUTE_LEGACY = "table_crop_tile_repair_route"
TABLE_REPAIR_ROUTES = {TABLE_ROUTE_LEGACY, TABLE_ROUTE_HIGH, TABLE_ROUTE_MEDIUM}
TABLE_REVIEW_ROUTES = {TABLE_ROUTE_LOW}

HIGH_REVIEW_FLAGS = {
    "metadata_leakage",
    "refusal_like",
    "prompt_template_leakage",
    "section_bleed",
    "table_expected_but_not_extracted",
}
MEDIUM_REVIEW_FLAGS = {
    "hallucination_risk",
    "suspicious_phrase",
    "summary_heavy",
    "prompt_template_repaired",
    "section_bleed_repaired",
}

PROMPT_CLEANUP_FLAGS = {
    "prompt_template_leakage",
    "section_bleed",
}
VISION_RERUN_FLAGS = {
    "metadata_leakage",
    "refusal_like",
}
OCR_VALIDATE_FLAGS = {
    "hallucination_risk",
    "suspicious_phrase",
}
TABLE_FLAGS = {
    "table_expected_but_not_extracted",
}

# Page roles/classes used to avoid sending every weak visual-text record to the
# same table route. These are intentionally broad because records come from
# several artifact shapes: page cards, visual-text records, source metadata, and
# image-recognition outputs.
TABLE_HIGH_ROLES = {"table", "table_grid", "parts_table", "effective_pages_table"}
TABLE_MEDIUM_ROLES = {"parts_list", "numerical_index", "index", "vendor_list", "front_matter_table"}
TABLE_LOW_REVIEW_ROLES = {"front_matter", "procedure", "text", "general_text", "mixed", "unknown"}
TABLE_NON_TABLE_ROLES = {"blank", "figure", "diagram", "title", "cover", "title_page"}
TABLE_CLASS_HINTS = {"likely_table_or_grid", "table", "grid", "table_or_grid"}
FIGURE_CLASS_HINTS = {"likely_figure_or_diagram", "figure", "diagram", "image_heavy"}

SUMMARY_FLAGS = {
    "summary_heavy",
}

REPAIR_PLAN_FILE = "trace_net_repair_plan.json"
REPAIR_PLAN_JSONL_FILE = "trace_net_repair_plan.jsonl"
REPAIR_SUMMARY_FILE = "trace_net_repair_summary.json"
REPAIR_GRAPH_NODES_FILE = "trace_net_repair_graph_nodes.json"
REPAIR_GRAPH_EDGES_FILE = "trace_net_repair_graph_edges.json"
REPAIR_REVIEW_MD_FILE = "trace_net_repair_review.md"
REPAIR_QUALITY_FILE = "trace_net_repair_quality.json"

_PAGE_ID_KEYS = ("page_id", "id", "page", "node_id", "entity_id")


@dataclass(frozen=True)
class TraceNetRepairPaths:
    visual_text_dir: Path = DEFAULT_VISUAL_TEXT_DIR
    trust_trait_dir: Path = DEFAULT_TRUST_TRAIT_DIR
    output_dir: Path = DEFAULT_TRACE_NET_DIR
    clean_records_path: Path | None = None
    trust_assertions_path: Path | None = None
    trust_summary_path: Path | None = None
    plan_path: Path | None = None
    plan_jsonl_path: Path | None = None
    summary_path: Path | None = None
    graph_nodes_path: Path | None = None
    graph_edges_path: Path | None = None
    review_md_path: Path | None = None
    quality_path: Path | None = None

    @property
    def clean_records(self) -> Path:
        return self.clean_records_path or (self.visual_text_dir / "visual_text_extraction_clean.jsonl")

    @property
    def trust_assertions(self) -> Path:
        return self.trust_assertions_path or (self.trust_trait_dir / "trust_trait_assertions.jsonl")

    @property
    def trust_summary(self) -> Path:
        return self.trust_summary_path or (self.trust_trait_dir / "trust_trait_summary.json")

    @property
    def plan(self) -> Path:
        return self.plan_path or (self.output_dir / REPAIR_PLAN_FILE)

    @property
    def plan_jsonl(self) -> Path:
        return self.plan_jsonl_path or (self.output_dir / REPAIR_PLAN_JSONL_FILE)

    @property
    def summary(self) -> Path:
        return self.summary_path or (self.output_dir / REPAIR_SUMMARY_FILE)

    @property
    def graph_nodes(self) -> Path:
        return self.graph_nodes_path or (self.output_dir / REPAIR_GRAPH_NODES_FILE)

    @property
    def graph_edges(self) -> Path:
        return self.graph_edges_path or (self.output_dir / REPAIR_GRAPH_EDGES_FILE)

    @property
    def review_md(self) -> Path:
        return self.review_md_path or (self.output_dir / REPAIR_REVIEW_MD_FILE)

    @property
    def quality(self) -> Path:
        return self.quality_path or (self.output_dir / REPAIR_QUALITY_FILE)


@dataclass
class TraceNetRepairOptions:
    expected_pages: int | None = None
    include_trust_ab: bool = True
    max_review_sample: int = 100


@dataclass
class RepairAction:
    action: str
    route: str
    extractor: str
    reason: str
    priority: str
    settings: dict[str, Any] = field(default_factory=dict)
    blocking_for_rag: bool = True

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TraceNetRepairRecord:
    page_id: str
    current_trust_tier: str
    current_rag_trait: str
    current_usable_for_rag: bool
    requires_human_review: bool
    priority: str
    primary_repair_route: str
    primary_repair_action: str
    primary_extractor: str
    action_queue: list[RepairAction]
    review_traits: list[str] = field(default_factory=list)
    blocking_traits: list[str] = field(default_factory=list)
    nonblocking_traits: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    recommended_settings: dict[str, Any] = field(default_factory=dict)
    table_route_priority: str = "none"
    route_refinement_reason: str = ""
    route_metadata: dict[str, Any] = field(default_factory=dict)
    source: dict[str, Any] = field(default_factory=dict)
    trace_net_repair_version: str = "trace_net_repair_v0_2_table_refinement"

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["action_queue"] = [a.to_json() for a in self.action_queue]
        return data


# ---------------------------------------------------------------------------
# IO helpers
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
    text = str(value).strip()
    return text if text else default


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", _text(value)).strip().lower()


def _slug(value: Any) -> str:
    text = _norm(value)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "unknown"


def _page_id_from_record(record: Mapping[str, Any]) -> str:
    for key in _PAGE_ID_KEYS:
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


def _clean_scores(record: Mapping[str, Any]) -> dict[str, Any]:
    return _as_dict(record.get("visual_text_cleanup_scores"))


def _visual_scores(record: Mapping[str, Any]) -> dict[str, Any]:
    return _as_dict(record.get("visual_text_scores_clean") or record.get("visual_text_scores"))


def _nested_text(record: Mapping[str, Any], keys: Sequence[str]) -> str:
    """Return the first text value found across common nested metadata shapes."""
    candidates: list[Any] = []
    for key in keys:
        candidates.append(record.get(key))
    for parent_key in ("source", "metadata", "page", "page_card", "context", "image_recognition"):
        parent = _as_dict(record.get(parent_key))
        for key in keys:
            candidates.append(parent.get(key))
    for scores_key in ("visual_text_scores_clean", "visual_text_scores", "visual_text_cleanup_scores"):
        parent = _as_dict(record.get(scores_key))
        for key in keys:
            candidates.append(parent.get(key))
    for value in candidates:
        text = _text(value)
        if text:
            return text
    return ""


def _record_page_role(record: Mapping[str, Any]) -> str:
    return _slug(_nested_text(record, ("page_role", "role", "context_role", "document_role", "page_type")))


def _record_image_class(record: Mapping[str, Any]) -> str:
    return _slug(_nested_text(record, ("image_class", "image_classification", "visual_class", "classification", "page_image_class")))


def _record_visible_title(record: Mapping[str, Any]) -> str:
    title = _nested_text(record, ("visible_title", "visible_title_header", "title", "header"))
    if title:
        return title
    sections = _as_dict(record.get("sections") or record.get("visual_text_sections"))
    for key in ("Visible title/header", "visible_title_header", "visible_title", "title"):
        if key in sections:
            return _text(sections.get(key))
    return ""


def _has_table_image_hint(image_class: str) -> bool:
    image_class = _slug(image_class)
    return any(hint in image_class for hint in TABLE_CLASS_HINTS)


def _has_figure_image_hint(image_class: str) -> bool:
    image_class = _slug(image_class)
    return any(hint in image_class for hint in FIGURE_CLASS_HINTS)


def classify_table_route_for_record(record: Mapping[str, Any] | None, review_traits: set[str]) -> dict[str, Any]:
    """Classify a table-missing record into a safer table-route priority.

    The previous planner treated every `table_expected_but_not_extracted` flag as
    the same crop/tile task. This caused front matter and figure pages to be
    routed like true table pages. The refined policy keeps actual table/grid
    candidates in table routes and sends weak candidates to review/validation.
    """
    record = record or {}
    if not (review_traits & TABLE_FLAGS):
        return {
            "has_table_flag": False,
            "table_route_priority": "none",
            "table_route": "none",
            "table_action": "none",
            "table_reason": "no_table_missing_trait",
            "table_candidate": False,
        }

    page_role = _record_page_role(record)
    image_class = _record_image_class(record)
    title = _slug(_record_visible_title(record))
    table_image = _has_table_image_hint(image_class)
    figure_image = _has_figure_image_hint(image_class)

    # No metadata available: preserve old behavior for backward compatibility
    # and for unit fixtures that only contain the review trait.
    if not page_role and not image_class and not title:
        return {
            "has_table_flag": True,
            "table_route_priority": "generic",
            "table_route": "table_crop_tile_repair_route",
            "table_action": "send_to_table_crop_tile_route",
            "table_reason": "table_missing_without_page_metadata_fallback",
            "table_candidate": True,
            "page_role": page_role,
            "image_class": image_class,
        }

    if page_role in TABLE_HIGH_ROLES or (page_role == "table" and table_image):
        return {
            "has_table_flag": True,
            "table_route_priority": "high",
            "table_route": "table_crop_tile_repair_route_high",
            "table_action": "send_to_high_priority_table_crop_tile_route",
            "table_reason": "page_role_or_image_class_indicates_actual_table",
            "table_candidate": True,
            "page_role": page_role,
            "image_class": image_class,
        }

    if page_role in TABLE_MEDIUM_ROLES and table_image:
        return {
            "has_table_flag": True,
            "table_route_priority": "medium",
            "table_route": "table_crop_tile_repair_route_medium",
            "table_action": "send_to_medium_priority_table_crop_tile_route",
            "table_reason": "parts_or_index_page_with_table_grid_image_signal",
            "table_candidate": True,
            "page_role": page_role,
            "image_class": image_class,
        }

    if page_role in TABLE_MEDIUM_ROLES and not figure_image:
        return {
            "has_table_flag": True,
            "table_route_priority": "medium",
            "table_route": "table_crop_tile_repair_route_medium",
            "table_action": "send_to_medium_priority_table_crop_tile_route",
            "table_reason": "parts_or_index_page_with_table_missing_trait",
            "table_candidate": True,
            "page_role": page_role,
            "image_class": image_class,
        }

    if page_role in TABLE_NON_TABLE_ROLES or figure_image or title in {"numerical_index", "title", "cover"}:
        return {
            "has_table_flag": True,
            "table_route_priority": "not_table",
            "table_route": "ocr_graph_validation_review_route",
            "table_action": "run_ocr_graph_validation",
            "table_reason": "table_flag_conflicts_with_figure_blank_or_title_page",
            "table_candidate": False,
            "page_role": page_role,
            "image_class": image_class,
        }

    return {
        "has_table_flag": True,
        "table_route_priority": "low",
        "table_route": "table_candidate_review_route",
        "table_action": "review_table_route_candidate",
        "table_reason": "weak_table_flag_needs_route_review_before_crop_tile",
        "table_candidate": False,
        "page_role": page_role,
        "image_class": image_class,
    }


def _record_status(record: Mapping[str, Any]) -> str:
    return _norm(record.get("status") or "unknown") or "unknown"


def _record_trust_tier(record: Mapping[str, Any]) -> str:
    cleanup = _clean_scores(record)
    raw = _text(cleanup.get("trust_tier") or record.get("trust_tier"), "D").upper()
    tier = raw[:1]
    return tier if tier in TRUST_TIERS else "D"


def _record_review_traits(record: Mapping[str, Any]) -> set[str]:
    cleanup = _clean_scores(record)
    scores = _visual_scores(record)
    traits: set[str] = set()
    mapping = {
        "metadata_leakage_risk": "metadata_leakage",
        "refusal_like": "refusal_like",
        "prompt_template_leakage_risk": "prompt_template_leakage",
        "prompt_template_leakage": "prompt_template_leakage",
        "section_bleed_risk": "section_bleed",
        "section_bleed": "section_bleed",
        "hallucination_risk": "hallucination_risk",
        "suspicious_phrase_risk": "suspicious_phrase",
        "too_summary_heavy": "summary_heavy",
        "table_expected_but_not_extracted": "table_expected_but_not_extracted",
    }
    for source in (scores, cleanup, record):
        for key, trait in mapping.items():
            if bool(source.get(key)):
                traits.add(trait)
    if cleanup.get("prompt_template_repaired"):
        traits.add("prompt_template_repaired")
    if cleanup.get("section_bleed_repaired"):
        traits.add("section_bleed_repaired")
    return traits


def _record_usable_for_rag(record: Mapping[str, Any], tier: str) -> bool:
    cleanup = _clean_scores(record)
    if "usable_for_rag" in cleanup:
        return bool(cleanup.get("usable_for_rag"))
    return tier in {"A", "B"}


def _record_requires_review(record: Mapping[str, Any], tier: str, review_traits: set[str]) -> bool:
    cleanup = _clean_scores(record)
    if "requires_human_review" in cleanup:
        return bool(cleanup.get("requires_human_review"))
    return tier in {"C", "D"} or bool(review_traits)


def _extract_trait_value(assertion: Mapping[str, Any]) -> tuple[str, str, str]:
    trait_type = _text(assertion.get("trait_type"))
    trait_key = _text(assertion.get("trait_key"))
    trait_value = _text(assertion.get("trait_value"))
    # Some graph rows may keep the values under properties.
    props = _as_dict(assertion.get("properties"))
    trait_type = trait_type or _text(props.get("trait_type"))
    trait_key = trait_key or _text(props.get("trait_key"))
    trait_value = trait_value or _text(props.get("trait_value"))
    return trait_type, trait_key, trait_value


def _assertion_page_id(assertion: Mapping[str, Any]) -> str:
    value = _text(assertion.get("page_id"))
    if value:
        return value
    props = _as_dict(assertion.get("properties"))
    return _text(props.get("page_id"))


def load_clean_records(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for record in read_jsonl(path):
        pid = _page_id_from_record(record)
        if pid:
            out[pid] = record
    return out


def load_trust_assertion_signals(path: Path) -> dict[str, dict[str, Any]]:
    signals: dict[str, dict[str, Any]] = defaultdict(lambda: {"review_traits": set(), "rag_traits": set()})
    for row in read_jsonl(path):
        pid = _assertion_page_id(row)
        if not pid:
            continue
        trait_type, trait_key, trait_value = _extract_trait_value(row)
        trait_type_norm = _norm(trait_type)
        trait_key_norm = _norm(trait_key)
        trait_value_norm = _norm(trait_value)
        bucket = signals[pid]
        if trait_type_norm == "trust" and trait_key_norm == "visual_text" and trait_value.upper()[:1] in TRUST_TIERS:
            bucket["trust_tier"] = trait_value.upper()[:1]
        elif trait_type_norm == "rag" and trait_key_norm == "visual_text":
            bucket.setdefault("rag_traits", set()).add(trait_value_norm)
        elif trait_type_norm == "review" and trait_key_norm == "visual_text":
            bucket.setdefault("review_traits", set()).add(trait_value_norm)
    # Convert sets to sorted lists for easier downstream use.
    final: dict[str, dict[str, Any]] = {}
    for pid, sig in signals.items():
        final[pid] = {
            **{k: v for k, v in sig.items() if not isinstance(v, set)},
            "review_traits": sorted(sig.get("review_traits", set())),
            "rag_traits": sorted(sig.get("rag_traits", set())),
        }
    return final



# ---------------------------------------------------------------------------
# Page route/trait helpers
# ---------------------------------------------------------------------------

_ROLE_KEYS = (
    "page_role",
    "role",
    "context_role",
    "document_role",
    "visual_role",
)
_IMAGE_CLASS_KEYS = (
    "image_class",
    "image_classes",
    "image_classification",
    "visual_class",
    "visual_classes",
    "page_image_class",
    "page_image_classes",
)

_TABLE_STRONG_ROLES = {"table"}
_TABLE_MEDIUM_ROLES = {"parts_list", "numerical_index", "index", "list"}
_TABLE_LOW_ROLES = {"front_matter", "figure", "procedure", "text", "general_text", "blank", "unknown"}


def _iter_nested_dicts(record: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    """Yield common nested metadata dictionaries from a visual-text record."""
    yield record
    for key in (
        "source",
        "metadata",
        "page_metadata",
        "page_card",
        "page_context",
        "context",
        "visual_text_scores",
        "visual_text_scores_clean",
        "visual_text_cleanup_scores",
    ):
        value = record.get(key)
        if isinstance(value, Mapping):
            yield value


def _first_nested_text(record: Mapping[str, Any], keys: Sequence[str]) -> str:
    for source in _iter_nested_dicts(record):
        for key in keys:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return _slug(value)
    return ""


def _record_page_role(record: Mapping[str, Any]) -> str:
    role = _first_nested_text(record, _ROLE_KEYS)
    if role:
        return role
    # Try to infer a weak role from free text fields when explicit page-card
    # metadata is unavailable in unit fixtures or old artifacts.
    blob = " ".join(
        _text(record.get(k))
        for k in ("page_type", "visual_summary", "clean_markdown", "visual_text", "text")
        if record.get(k)
    ).lower()
    if "parts list" in blob or "part list" in blob:
        return "parts_list"
    if "effective page" in blob or "revision" in blob or "table" in blob:
        return "table"
    if "figure" in blob or "diagram" in blob:
        return "figure"
    return "unknown"


def _collect_text_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        out: list[str] = []
        for item in value:
            out.extend(_collect_text_values(item))
        return out
    if isinstance(value, Mapping):
        out: list[str] = []
        for item in value.values():
            out.extend(_collect_text_values(item))
        return out
    return [str(value)]


def _record_image_classes(record: Mapping[str, Any]) -> set[str]:
    classes: set[str] = set()
    for source in _iter_nested_dicts(record):
        for key in _IMAGE_CLASS_KEYS:
            if key in source:
                for value in _collect_text_values(source.get(key)):
                    slug = _slug(value)
                    if slug:
                        classes.add(slug)
    return classes


def _has_table_grid_signal(image_classes: set[str]) -> bool:
    return any("table" in c or "grid" in c for c in image_classes)


def _has_figure_signal(image_classes: set[str]) -> bool:
    return any("figure" in c or "diagram" in c or "image_heavy" in c for c in image_classes)


def classify_table_repair_route(
    record: Mapping[str, Any] | None,
    review_traits: set[str],
) -> tuple[str, str, str, dict[str, Any]]:
    """Return (route, action, priority, settings) for table-missing records.

    The original planner used one route for every
    ``table_expected_but_not_extracted`` record. TRACE-Net now separates real
    table candidates from weak table-review candidates:

    - high: explicit table role, or table/grid image signal on a table/parts page;
    - medium: parts-list/table-ish page where a table route may help;
    - low: front matter/figure/text pages where the table flag should be reviewed
      before spending table-extractor time.
    """
    if not (review_traits & TABLE_FLAGS):
        return "", "", "", {}
    record = record or {}
    role = _record_page_role(record)
    image_classes = _record_image_classes(record)
    has_table_signal = _has_table_grid_signal(image_classes)
    has_figure_signal = _has_figure_signal(image_classes)

    base = {
        "page_role": role,
        "image_classes": sorted(image_classes),
        "table_signal": has_table_signal,
        "figure_signal": has_figure_signal,
    }

    if role == "unknown" and not image_classes:
        # Preserve original behavior when no page-role/image-class metadata is
        # available. Older fixtures and some legacy artifacts only carry the
        # table-missing trait.
        return TABLE_ROUTE_LEGACY, "send_to_table_crop_tile_route", "high", {**_settings_for_route(TABLE_ROUTE_LEGACY), **base, "route_priority": "generic"}
    if role in _TABLE_STRONG_ROLES or (has_table_signal and role in _TABLE_STRONG_ROLES):
        return TABLE_ROUTE_HIGH, "send_to_table_crop_tile_route", "high", {**_settings_for_route(TABLE_ROUTE_HIGH), **base}
    if has_table_signal and role in _TABLE_MEDIUM_ROLES:
        return TABLE_ROUTE_MEDIUM, "send_to_table_crop_tile_route", "medium", {**_settings_for_route(TABLE_ROUTE_MEDIUM), **base}
    if role in _TABLE_MEDIUM_ROLES:
        return TABLE_ROUTE_MEDIUM, "send_to_table_crop_tile_route", "medium", {**_settings_for_route(TABLE_ROUTE_MEDIUM), **base}
    if has_figure_signal or role in {"figure", "diagram", "blank", "title", "cover", "title_page"}:
        return "ocr_graph_validation_review_route", "run_ocr_graph_validation", "medium", {**_settings_for_route("ocr_graph_validation_review_route"), **base, "table_route_priority": "not_table"}
    if role in _TABLE_LOW_ROLES:
        return TABLE_ROUTE_LOW, "review_table_candidate_before_extraction", "medium", {**_settings_for_route(TABLE_ROUTE_LOW), **base}
    if has_table_signal:
        return TABLE_ROUTE_MEDIUM, "send_to_table_crop_tile_route", "medium", {**_settings_for_route(TABLE_ROUTE_MEDIUM), **base}
    return TABLE_ROUTE_LOW, "review_table_candidate_before_extraction", "medium", {**_settings_for_route(TABLE_ROUTE_LOW), **base}

# ---------------------------------------------------------------------------
# Repair routing
# ---------------------------------------------------------------------------


def _priority_for_traits(tier: str, traits: set[str], current_usable: bool) -> str:
    if tier == "D" or traits & HIGH_REVIEW_FLAGS:
        return "high"
    if tier == "C" or traits & MEDIUM_REVIEW_FLAGS or not current_usable:
        return "medium"
    return "normal"


def _action(
    action: str,
    route: str,
    extractor: str,
    reason: str,
    priority: str,
    settings: Mapping[str, Any] | None = None,
    blocking_for_rag: bool = True,
) -> RepairAction:
    return RepairAction(
        action=action,
        route=route,
        extractor=extractor,
        reason=reason,
        priority=priority,
        settings=dict(settings or {}),
        blocking_for_rag=blocking_for_rag,
    )


def _settings_for_route(route: str) -> dict[str, Any]:
    if route in {TABLE_ROUTE_LEGACY, TABLE_ROUTE_HIGH, TABLE_ROUTE_MEDIUM}:
        priority = "high" if route in {TABLE_ROUTE_LEGACY, TABLE_ROUTE_HIGH} else "medium"
        return {
            "planned_prompt_version": "table_text_v1_planned",
            "route_priority": priority,
            "max_image_edge": 1024 if priority == "high" else 896,
            "timeout_seconds": 600,
            "fishnet": [
                {"name": "table_tile_768", "max_image_edge": 768, "timeout_seconds": 1200},
                {"name": "table_tile_512", "max_image_edge": 512, "timeout_seconds": 1200},
            ],
        }
    if route == TABLE_ROUTE_LOW:
        return {
            "route_priority": "low",
            "does_not_call_table_extractor": True,
            "goal": "review_table_signal_before_crop_tile_extraction",
        }
    if route == "vision_rerun_sanitized_route":
        return {
            "prompt_version": "visual_text_v2_2",
            "max_image_edge": 1024,
            "timeout_seconds": 600,
            "fishnet": [
                {"name": "rescue_768", "max_image_edge": 768, "timeout_seconds": 1200},
                {"name": "rescue_512", "max_image_edge": 512, "timeout_seconds": 1200},
            ],
        }
    if route == "prompt_cleanup_repair_route":
        return {
            "cleanup_version": "visual_text_v2_3_1_salvage_cleanup",
            "does_not_call_model": True,
        }
    if route == "ocr_graph_validation_review_route":
        return {
            "validators": ["same_page_ocr", "part_catalog", "graph_part_mentions", "source_trace"],
            "does_not_call_model": True,
        }
    if route == "summary_rewrite_repair_route":
        return {
            "prompt_version": "visual_text_v2_2",
            "max_image_edge": 768,
            "timeout_seconds": 1200,
            "goal": "short_fact_preserving_rewrite",
        }
    return {}


def build_action_queue(
    *,
    trust_tier: str,
    review_traits: set[str],
    current_usable_for_rag: bool,
    clean_record: Mapping[str, Any] | None = None,
) -> list[RepairAction]:
    priority = _priority_for_traits(trust_tier, review_traits, current_usable_for_rag)
    actions: list[RepairAction] = []

    if current_usable_for_rag and trust_tier in {"A", "B"} and not (review_traits & HIGH_REVIEW_FLAGS):
        actions.append(
            _action(
                "no_repair_needed",
                "rag_include_route",
                "none",
                "visual_text_currently_usable",
                "normal",
                {"allow_visual_text_rag": True},
                blocking_for_rag=False,
            )
        )
        return actions

    if review_traits & VISION_RERUN_FLAGS:
        actions.append(
            _action(
                "rerun_visual_text_sanitized",
                "vision_rerun_sanitized_route",
                "visual_text_ollama_fishnet",
                "metadata_or_refusal_requires_clean_rerun",
                "high",
                _settings_for_route("vision_rerun_sanitized_route"),
            )
        )
    if review_traits & PROMPT_CLEANUP_FLAGS:
        actions.append(
            _action(
                "rerun_cleanup_salvage",
                "prompt_cleanup_repair_route",
                "visual_text_cleanup_postprocessor",
                "prompt_template_or_section_bleed_can_be_salvaged",
                priority,
                _settings_for_route("prompt_cleanup_repair_route"),
            )
        )
    if review_traits & TABLE_FLAGS:
        table_route, table_action, table_priority, table_settings = classify_table_repair_route(clean_record, review_traits)
        if table_route:
            actions.append(
                _action(
                    table_action,
                    table_route,
                    (
                        "grit_table_crop_tile_extractor_planned"
                        if table_route in TABLE_REPAIR_ROUTES
                        else "ocr_catalog_graph_validator"
                        if table_route == "ocr_graph_validation_review_route"
                        else "table_candidate_review_queue"
                    ),
                    (
                        "table_expected_but_rows_missing"
                        if table_route in TABLE_REPAIR_ROUTES
                        else "table_flag_conflicts_with_page_role_or_image_class"
                        if table_route == "ocr_graph_validation_review_route"
                        else "weak_table_signal_needs_route_review"
                    ),
                    table_priority,
                    table_settings,
                )
            )
    if review_traits & OCR_VALIDATE_FLAGS:
        actions.append(
            _action(
                "run_ocr_graph_validation",
                "ocr_graph_validation_review_route",
                "ocr_catalog_graph_validator",
                "hallucination_or_suspicious_phrase_needs_grounding",
                "medium" if priority != "high" else "high",
                _settings_for_route("ocr_graph_validation_review_route"),
            )
        )
    if review_traits & SUMMARY_FLAGS:
        actions.append(
            _action(
                "rerun_or_rewrite_visual_summary",
                "summary_rewrite_repair_route",
                "visual_text_summary_rewriter",
                "summary_heavy_output_needs_tighter_context",
                "medium",
                _settings_for_route("summary_rewrite_repair_route"),
            )
        )

    if not actions and trust_tier in {"C", "D"}:
        actions.append(
            _action(
                "send_to_human_review",
                "human_review_route",
                "human_review_queue",
                f"trust_tier_{trust_tier.lower()}_without_specific_auto_repair",
                priority,
                {"allow_visual_text_rag": False},
            )
        )

    # Keep human review as a trailing action for unresolved C/D records. This is
    # not the primary repair if an automatic route exists, but it remains in the
    # queue so operators can see the safety state.
    if trust_tier in {"C", "D"} or review_traits:
        if not any(a.route == "human_review_route" for a in actions):
            actions.append(
                _action(
                    "keep_in_human_review_queue",
                    "human_review_route",
                    "human_review_queue",
                    "derived_visual_text_not_yet_rag_safe",
                    "medium" if priority != "high" else "high",
                    {"allow_visual_text_rag": False},
                )
            )
    return actions


def plan_repair_for_page(
    page_id: str,
    clean_record: Mapping[str, Any] | None,
    trust_signals: Mapping[str, Any] | None,
) -> TraceNetRepairRecord:
    clean_record = clean_record or {}
    trust_signals = trust_signals or {}
    record_tier = _record_trust_tier(clean_record) if clean_record else "D"
    trust_tier = _text(trust_signals.get("trust_tier") or record_tier, "D").upper()[:1]
    if trust_tier not in TRUST_TIERS:
        trust_tier = "D"

    record_traits = _record_review_traits(clean_record) if clean_record else {"missing_clean_record"}
    trust_traits = set(_as_list(trust_signals.get("review_traits")))
    review_traits = set(t for t in record_traits | trust_traits if t)
    rag_traits = set(_as_list(trust_signals.get("rag_traits")))
    current_usable = _record_usable_for_rag(clean_record, trust_tier) if clean_record else False
    if RAG_INCLUDE in rag_traits:
        current_usable = True
    if RAG_EXCLUDE in rag_traits:
        current_usable = False

    requires_review = _record_requires_review(clean_record, trust_tier, review_traits) if clean_record else True
    if "needs_human_review" in review_traits:
        requires_review = True

    blocking_traits = sorted(t for t in review_traits if t in HIGH_REVIEW_FLAGS or t in {"missing_clean_record"})
    nonblocking_traits = sorted(t for t in review_traits if t not in set(blocking_traits) and t != "needs_human_review")
    priority = _priority_for_traits(trust_tier, review_traits, current_usable)
    action_queue = build_action_queue(
        trust_tier=trust_tier,
        review_traits=review_traits,
        current_usable_for_rag=current_usable,
        clean_record=clean_record,
    )
    if not action_queue:
        action_queue = [
            _action(
                "no_repair_needed",
                "rag_include_route" if current_usable else "human_review_route",
                "none" if current_usable else "human_review_queue",
                "default_no_specific_repair",
                priority,
                {"allow_visual_text_rag": current_usable},
                blocking_for_rag=not current_usable,
            )
        ]

    primary = action_queue[0]
    refined_route, _refined_action, refined_priority, refined_settings = classify_table_repair_route(clean_record, review_traits)
    table_refinement = {
        "has_table_flag": bool(refined_route),
        "table_route": refined_route,
        "table_route_priority": _text(refined_settings.get("route_priority") or refined_settings.get("table_route_priority") or refined_priority or "none"),
        "table_reason": primary.reason if refined_route else "no_table_missing_trait",
        "page_role": refined_settings.get("page_role"),
        "image_class": ",".join(refined_settings.get("image_classes", [])) if isinstance(refined_settings.get("image_classes"), list) else refined_settings.get("image_class"),
        "table_candidate": refined_route in TABLE_REPAIR_ROUTES,
    }
    reasons = sorted({primary.reason, *blocking_traits, *nonblocking_traits})
    if table_refinement.get("has_table_flag"):
        reasons = sorted(set(reasons) | {_text(table_refinement.get("table_reason"), "table_route_refined")})
    current_rag_trait = RAG_INCLUDE if current_usable else RAG_EXCLUDE

    return TraceNetRepairRecord(
        page_id=page_id,
        current_trust_tier=trust_tier,
        current_rag_trait=current_rag_trait,
        current_usable_for_rag=current_usable,
        requires_human_review=requires_review,
        priority=priority,
        primary_repair_route=primary.route,
        primary_repair_action=primary.action,
        primary_extractor=primary.extractor,
        action_queue=action_queue,
        review_traits=sorted(review_traits),
        blocking_traits=blocking_traits,
        nonblocking_traits=nonblocking_traits,
        reasons=reasons,
        recommended_settings=primary.settings,
        table_route_priority=_text(table_refinement.get("table_route_priority"), "none"),
        route_refinement_reason=_text(table_refinement.get("table_reason")),
        route_metadata={k: v for k, v in table_refinement.items() if k in {"page_role", "image_class", "table_candidate", "has_table_flag"}},
        source={
            "status": _record_status(clean_record) if clean_record else "missing",
            "prompt_version": clean_record.get("prompt_version") if clean_record else None,
            "cleanup_version": _clean_scores(clean_record).get("cleanup_version") if clean_record else None,
            "char_count_clean": clean_record.get("char_count_clean") or clean_record.get("char_count") if clean_record else None,
        },
    )


# ---------------------------------------------------------------------------
# Plan build, summary, graph
# ---------------------------------------------------------------------------


def build_trace_net_repair_plan(
    paths: TraceNetRepairPaths,
    options: TraceNetRepairOptions | None = None,
) -> dict[str, Any]:
    options = options or TraceNetRepairOptions()
    clean_records = load_clean_records(paths.clean_records)
    trust_signals = load_trust_assertion_signals(paths.trust_assertions)
    all_page_ids = sorted(set(clean_records) | set(trust_signals))
    records: list[TraceNetRepairRecord] = []
    for pid in all_page_ids:
        record = plan_repair_for_page(pid, clean_records.get(pid), trust_signals.get(pid))
        if not options.include_trust_ab and record.current_trust_tier in {"A", "B"} and record.current_usable_for_rag:
            continue
        records.append(record)

    summary = summarize_trace_net_repair_plan(records, paths, options, clean_records, trust_signals)
    return {
        "status": summary["status"],
        "summary": summary,
        "repairs": [r.to_json() for r in records],
    }


def summarize_trace_net_repair_plan(
    records: Sequence[TraceNetRepairRecord],
    paths: TraceNetRepairPaths,
    options: TraceNetRepairOptions,
    clean_records: Mapping[str, Any],
    trust_signals: Mapping[str, Any],
) -> dict[str, Any]:
    tier_counts = Counter(r.current_trust_tier for r in records)
    priority_counts = Counter(r.priority for r in records)
    route_counts = Counter(r.primary_repair_route for r in records)
    action_counts = Counter(r.primary_repair_action for r in records)
    extractor_counts = Counter(r.primary_extractor for r in records)
    review_trait_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    for r in records:
        review_trait_counts.update(r.review_traits)
        reason_counts.update(r.reasons)

    total = len(records)
    unplanned_problem_records = sum(
        1
        for r in records
        if r.current_trust_tier in {"C", "D"}
        and r.primary_repair_route in {"rag_include_route"}
    )
    auto_repair_candidate_records = sum(
        1
        for r in records
        if r.primary_repair_route
        not in {"rag_include_route", "human_review_route"}
    )
    table_repair_records = sum(route_counts.get(route, 0) for route in TABLE_REPAIR_ROUTES)
    table_repair_high_records = route_counts.get(TABLE_ROUTE_HIGH, 0) + route_counts.get(TABLE_ROUTE_LEGACY, 0)
    table_repair_medium_records = route_counts.get(TABLE_ROUTE_MEDIUM, 0)
    table_candidate_review_records = sum(route_counts.get(route, 0) for route in TABLE_REVIEW_ROUTES)
    cleanup_repair_records = route_counts.get("prompt_cleanup_repair_route", 0)
    rerun_model_records = route_counts.get("vision_rerun_sanitized_route", 0) + route_counts.get("summary_rewrite_repair_route", 0)
    validation_records = route_counts.get("ocr_graph_validation_review_route", 0)
    human_review_records = sum(1 for r in records if r.requires_human_review)
    rag_excluded_records = sum(1 for r in records if r.current_rag_trait == RAG_EXCLUDE)
    rag_included_records = sum(1 for r in records if r.current_rag_trait == RAG_INCLUDE)

    ok = total > 0 and unplanned_problem_records == 0
    if options.expected_pages is not None and total != options.expected_pages:
        ok = False

    return {
        "status": "OK" if ok else "FAIL",
        "records": total,
        "expected_pages": options.expected_pages,
        "clean_record_count": len(clean_records),
        "trust_signal_page_count": len(trust_signals),
        "trust_tier_counts": dict(sorted(tier_counts.items())),
        "priority_counts": dict(sorted(priority_counts.items())),
        "repair_route_counts": dict(sorted(route_counts.items())),
        "repair_action_counts": dict(sorted(action_counts.items())),
        "extractor_counts": dict(sorted(extractor_counts.items())),
        "review_trait_counts": dict(sorted(review_trait_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "auto_repair_candidate_records": auto_repair_candidate_records,
        "human_review_records": human_review_records,
        "rag_excluded_records": rag_excluded_records,
        "rag_included_records": rag_included_records,
        "table_repair_records": table_repair_records,
        "table_repair_high_records": table_repair_high_records,
        "table_repair_medium_records": table_repair_medium_records,
        "table_candidate_review_records": table_candidate_review_records,
        "cleanup_repair_records": cleanup_repair_records,
        "rerun_model_records": rerun_model_records,
        "ocr_graph_validation_records": validation_records,
        "unplanned_problem_records": unplanned_problem_records,
        "trace_net_repair_version": "trace_net_repair_v0_2_table_refinement",
        "paths": {
            "clean_records": str(paths.clean_records),
            "trust_assertions": str(paths.trust_assertions),
            "trust_summary": str(paths.trust_summary),
            "output_dir": str(paths.output_dir),
        },
    }


def _node_id(prefix: str, raw: Any) -> str:
    text = _slug(raw)
    return f"{prefix}:{text}"


def build_trace_net_repair_graph(plan: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def add_node(node_id: str, node_type: str, label: str, **props: Any) -> None:
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, "type": node_type, "label": label, **{k: v for k, v in props.items() if v not in (None, "", [], {})}}
        else:
            nodes[node_id].update({k: v for k, v in props.items() if v not in (None, "", [], {})})

    def add_edge(source: str, target: str, edge_type: str, **props: Any) -> None:
        if source and target and source != target:
            edges.append({"source": source, "target": target, "type": edge_type, **{k: v for k, v in props.items() if v not in (None, "", [], {})}})

    add_node("trace_net:repair_planner", "trace_net_repair_planner", "TRACE-Net repair planner")
    for row in plan.get("repairs") or []:
        if not isinstance(row, Mapping):
            continue
        pid = _text(row.get("page_id"))
        repair_id = _node_id("trace_repair", pid)
        page_node = f"page:{pid}"
        visual_node = f"visual_text:{_slug(pid)}"
        route_node = _node_id("trace_repair_route", row.get("primary_repair_route"))
        action_node = _node_id("trace_repair_action", row.get("primary_repair_action"))
        tier_node = f"trait:trust:visual_text:{_slug(row.get('current_trust_tier'))}"
        add_node(page_node, "page", pid, page_id=pid)
        add_node(visual_node, "visual_text_context", f"Visual text for {pid}", page_id=pid)
        add_node(repair_id, "trace_net_repair_plan", f"Repair plan {pid}", **dict(row))
        add_node(route_node, "trace_net_repair_route", _text(row.get("primary_repair_route")), route=row.get("primary_repair_route"))
        add_node(action_node, "trace_net_repair_action", _text(row.get("primary_repair_action")), action=row.get("primary_repair_action"))
        add_node(tier_node, "trait", f"trust:visual_text={row.get('current_trust_tier')}", trait_type="trust", trait_key="visual_text", trait_value=row.get("current_trust_tier"))
        add_edge("trace_net:repair_planner", repair_id, "HAS_REPAIR_PLAN")
        add_edge(page_node, repair_id, "HAS_TRACE_NET_REPAIR_PLAN")
        add_edge(page_node, visual_node, "HAS_VISUAL_TEXT")
        add_edge(visual_node, repair_id, "HAS_REPAIR_PLAN")
        add_edge(repair_id, route_node, "USES_REPAIR_ROUTE")
        add_edge(repair_id, action_node, "RECOMMENDS_REPAIR_ACTION")
        add_edge(repair_id, tier_node, "CURRENT_TRUST_TIER")
        for trait in row.get("review_traits") or []:
            trait_node = f"trait:review:visual_text:{_slug(trait)}"
            add_node(trait_node, "trait", f"review:visual_text={trait}", trait_type="review", trait_key="visual_text", trait_value=trait)
            add_edge(repair_id, trait_node, "REPAIRS_REVIEW_TRAIT")
        for action in row.get("action_queue") or []:
            if not isinstance(action, Mapping):
                continue
            q_node = _node_id("trace_repair_action", action.get("action"))
            add_node(q_node, "trace_net_repair_action", _text(action.get("action")), action=action.get("action"), route=action.get("route"))
            add_edge(repair_id, q_node, "HAS_ACTION_QUEUE_ITEM", priority=action.get("priority"), reason=action.get("reason"))
    return list(nodes.values()), edges


def format_trace_net_repair_review(plan: Mapping[str, Any], limit: int = 100) -> str:
    summary = _as_dict(plan.get("summary"))
    rows = [r for r in plan.get("repairs") or [] if isinstance(r, Mapping)]
    lines: list[str] = []
    lines.append("# TRACE-Net repair plan")
    lines.append("")
    lines.append(f"Status: **{summary.get('status', plan.get('status', 'unknown'))}**")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    for key in (
        "records",
        "auto_repair_candidate_records",
        "human_review_records",
        "rag_excluded_records",
        "rag_included_records",
        "table_repair_records",
        "table_repair_high_records",
        "table_repair_medium_records",
        "table_candidate_review_records",
        "cleanup_repair_records",
        "ocr_graph_validation_records",
        "rerun_model_records",
        "unplanned_problem_records",
    ):
        lines.append(f"- {key}: {summary.get(key)}")
    lines.append("")
    for key in ("trust_tier_counts", "repair_route_counts", "repair_action_counts", "review_trait_counts", "priority_counts"):
        lines.append(f"## {key}")
        value = _as_dict(summary.get(key))
        if value:
            for k, v in sorted(value.items(), key=lambda kv: str(kv[0])):
                lines.append(f"- {k}: {v}")
        else:
            lines.append("- none")
        lines.append("")
    lines.append("## Sample repairs")
    lines.append("")
    for row in rows[:limit]:
        lines.append(f"### {row.get('page_id')}")
        lines.append("")
        lines.append(f"- trust tier: `{row.get('current_trust_tier')}`")
        lines.append(f"- current RAG trait: `{row.get('current_rag_trait')}`")
        lines.append(f"- priority: `{row.get('priority')}`")
        lines.append(f"- primary route: `{row.get('primary_repair_route')}`")
        lines.append(f"- primary action: `{row.get('primary_repair_action')}`")
        traits = row.get("review_traits") or []
        lines.append(f"- review traits: {', '.join(traits) if traits else 'none'}")
        queue = row.get("action_queue") or []
        if queue:
            lines.append("- action queue:")
            for action in queue:
                if isinstance(action, Mapping):
                    lines.append(f"  - `{action.get('action')}` via `{action.get('route')}`: {action.get('reason')}")
        lines.append("")
    return "\n".join(lines)


def write_trace_net_repair_plan(plan: Mapping[str, Any], paths: TraceNetRepairPaths) -> None:
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    repairs = [r for r in plan.get("repairs") or [] if isinstance(r, Mapping)]
    _write_json(paths.plan, plan)
    write_jsonl(paths.plan_jsonl, repairs)
    _write_json(paths.summary, plan.get("summary", {}))
    nodes, edges = build_trace_net_repair_graph(plan)
    _write_json(paths.graph_nodes, nodes)
    _write_json(paths.graph_edges, edges)
    paths.review_md.write_text(format_trace_net_repair_review(plan), encoding="utf-8")


def build_and_write_trace_net_repair_plan(
    paths: TraceNetRepairPaths,
    options: TraceNetRepairOptions | None = None,
) -> dict[str, Any]:
    plan = build_trace_net_repair_plan(paths, options)
    write_trace_net_repair_plan(plan, paths)
    return plan


# ---------------------------------------------------------------------------
# Quality gate
# ---------------------------------------------------------------------------


def build_trace_net_repair_quality(
    paths: TraceNetRepairPaths,
    *,
    min_records: int = 1,
    expected_pages: int | None = None,
    min_auto_repair_candidates: int = 0,
    max_unplanned_problem_records: int = 0,
) -> dict[str, Any]:
    summary = _read_json(paths.summary, {}) or {}
    plan = _read_json(paths.plan, {}) or {}
    repairs = read_jsonl(paths.plan_jsonl)
    nodes = _read_json(paths.graph_nodes, []) or []
    edges = _read_json(paths.graph_edges, []) or []
    summary_present = bool(summary)
    plan_present = bool(plan)
    repairs_present = bool(repairs)
    records = int(summary.get("records") or len(repairs) or 0)
    status = _norm(summary.get("status") or plan.get("status") or "missing")
    auto_repair_candidates = int(summary.get("auto_repair_candidate_records") or 0)
    unplanned = int(summary.get("unplanned_problem_records") or 0)

    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, message: str) -> None:
        checks.append({"name": name, "status": "OK" if ok else "FAIL", "message": message})

    add("trace_net_repair_artifacts_present", summary_present and plan_present and repairs_present, f"summary={summary_present}; plan={plan_present}; repairs={repairs_present}.")
    add("trace_net_repair_status", status == "ok", f"repair plan status is {status!r}.")
    add("trace_net_repair_records", records >= min_records, f"records={records}; minimum={min_records}.")
    if expected_pages is not None:
        add("trace_net_repair_expected_pages", records == expected_pages, f"records={records}; expected={expected_pages}.")
    add("trace_net_repair_auto_candidates", auto_repair_candidates >= min_auto_repair_candidates, f"auto_repair_candidate_records={auto_repair_candidates}; minimum={min_auto_repair_candidates}.")
    add("trace_net_repair_unplanned_problems", unplanned <= max_unplanned_problem_records, f"unplanned_problem_records={unplanned}; max={max_unplanned_problem_records}.")
    add("trace_net_repair_route_counts", bool(summary.get("repair_route_counts")), f"repair_route_counts={summary.get('repair_route_counts', {})}.")
    add("trace_net_repair_action_counts", bool(summary.get("repair_action_counts")), f"repair_action_counts={summary.get('repair_action_counts', {})}.")
    add("trace_net_repair_graph_nodes", isinstance(nodes, list) and len(nodes) > 0, f"graph nodes={len(nodes) if isinstance(nodes, list) else 0}.")
    add("trace_net_repair_graph_edges", isinstance(edges, list) and len(edges) > 0, f"graph edges={len(edges) if isinstance(edges, list) else 0}.")

    ok = all(c["status"] == "OK" for c in checks)
    quality = {
        "status": "OK" if ok else "FAIL",
        "summary": {
            "trace_net_repair_summary_present": summary_present,
            "trace_net_repair_plan_present": plan_present,
            "trace_net_repair_records_present": repairs_present,
            "trace_net_repair_status": status,
            "trace_net_repair_records": records,
            "trace_net_repair_expected_pages": expected_pages,
            "trace_net_repair_trust_tier_counts": summary.get("trust_tier_counts", {}),
            "trace_net_repair_route_counts": summary.get("repair_route_counts", {}),
            "trace_net_repair_action_counts": summary.get("repair_action_counts", {}),
            "trace_net_repair_review_trait_counts": summary.get("review_trait_counts", {}),
            "trace_net_repair_auto_repair_candidate_records": auto_repair_candidates,
            "trace_net_repair_human_review_records": summary.get("human_review_records", 0),
            "trace_net_repair_rag_excluded_records": summary.get("rag_excluded_records", 0),
            "trace_net_repair_table_repair_records": summary.get("table_repair_records", 0),
            "trace_net_repair_table_repair_high_records": summary.get("table_repair_high_records", 0),
            "trace_net_repair_table_repair_medium_records": summary.get("table_repair_medium_records", 0),
            "trace_net_repair_table_candidate_review_records": summary.get("table_candidate_review_records", 0),
            "trace_net_repair_cleanup_repair_records": summary.get("cleanup_repair_records", 0),
            "trace_net_repair_ocr_graph_validation_records": summary.get("ocr_graph_validation_records", 0),
            "trace_net_repair_unplanned_problem_records": unplanned,
            "trace_net_repair_graph_nodes": len(nodes) if isinstance(nodes, list) else 0,
            "trace_net_repair_graph_edges": len(edges) if isinstance(edges, list) else 0,
            "trace_net_repair_summary_path": str(paths.summary),
            "trace_net_repair_plan_path": str(paths.plan),
            "trace_net_repair_plan_jsonl_path": str(paths.plan_jsonl),
        },
        "checks": checks,
    }
    return quality


def write_trace_net_repair_quality(quality: Mapping[str, Any], paths: TraceNetRepairPaths) -> Path:
    _write_json(paths.quality, quality)
    return paths.quality


# ---------------------------------------------------------------------------
# CLI printing
# ---------------------------------------------------------------------------


def print_trace_net_repair_plan(plan: Mapping[str, Any], paths: TraceNetRepairPaths, samples: int = 12) -> None:
    summary = _as_dict(plan.get("summary"))
    print("TRACE-Net repair planner")
    print(f"  Status: {summary.get('status', plan.get('status', 'unknown'))}")
    print(f"  Output dir: {paths.output_dir}")
    print("  Summary:")
    for key in (
        "records",
        "auto_repair_candidate_records",
        "human_review_records",
        "rag_excluded_records",
        "rag_included_records",
        "table_repair_records",
        "table_repair_high_records",
        "table_repair_medium_records",
        "table_candidate_review_records",
        "cleanup_repair_records",
        "ocr_graph_validation_records",
        "rerun_model_records",
        "unplanned_problem_records",
    ):
        print(f"    {key}: {summary.get(key)}")
    print("  Trust tiers:")
    for key, value in _as_dict(summary.get("trust_tier_counts")).items():
        print(f"    {key}: {value}")
    print("  Repair routes:")
    for key, value in _as_dict(summary.get("repair_route_counts")).items():
        print(f"    {key}: {value}")
    print("  Review traits:")
    for key, value in list(_as_dict(summary.get("review_trait_counts")).items())[:20]:
        print(f"    {key}: {value}")
    repairs = [r for r in plan.get("repairs") or [] if isinstance(r, Mapping)]
    if repairs:
        print("  Sample repairs:")
        for row in repairs[:samples]:
            traits = ",".join(row.get("review_traits") or []) or "none"
            print(
                f"    {row.get('page_id')} | tier={row.get('current_trust_tier')} | "
                f"priority={row.get('priority')} | route={row.get('primary_repair_route')} | "
                f"action={row.get('primary_repair_action')} | traits={traits}"
            )
    print("Files written:")
    print(f"  plan: {paths.plan}")
    print(f"  plan_jsonl: {paths.plan_jsonl}")
    print(f"  summary: {paths.summary}")
    print(f"  graph_nodes: {paths.graph_nodes}")
    print(f"  graph_edges: {paths.graph_edges}")
    print(f"  review_md: {paths.review_md}")


def print_trace_net_repair_quality(quality: Mapping[str, Any]) -> None:
    print("TRACE-Net repair quality gate")
    print(f"  Status: {quality.get('status')}")
    print("  Summary:")
    for key, value in _as_dict(quality.get("summary")).items():
        print(f"    {key}: {value}")
    print("  Checks:")
    for check in quality.get("checks") or []:
        if isinstance(check, Mapping):
            print(f"    {check.get('status')} {check.get('name')}: {check.get('message')}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan TRACE-Net repairs from trust traits and clean visual-text records.")
    parser.add_argument("--visual-text-dir", default=str(DEFAULT_VISUAL_TEXT_DIR))
    parser.add_argument("--trust-trait-dir", default=str(DEFAULT_TRUST_TRAIT_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_TRACE_NET_DIR))
    parser.add_argument("--clean-records", default=None)
    parser.add_argument("--trust-assertions", default=None)
    parser.add_argument("--expect-pages", type=int, default=None)
    parser.add_argument("--samples", type=int, default=12)
    parser.add_argument("--exclude-trust-ab", action="store_true")
    return parser


def paths_from_args(args: argparse.Namespace) -> TraceNetRepairPaths:
    return TraceNetRepairPaths(
        visual_text_dir=Path(args.visual_text_dir),
        trust_trait_dir=Path(args.trust_trait_dir),
        output_dir=Path(args.output_dir),
        clean_records_path=Path(args.clean_records) if args.clean_records else None,
        trust_assertions_path=Path(args.trust_assertions) if args.trust_assertions else None,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    paths = paths_from_args(args)
    options = TraceNetRepairOptions(
        expected_pages=args.expect_pages,
        include_trust_ab=not args.exclude_trust_ab,
    )
    plan = build_and_write_trace_net_repair_plan(paths, options)
    print_trace_net_repair_plan(plan, paths, samples=args.samples)
    return 0 if plan.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
