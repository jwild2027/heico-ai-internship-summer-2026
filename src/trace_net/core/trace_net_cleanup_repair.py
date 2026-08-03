"""TRACE-Net cleanup repair executor.

This module executes the first TRACE-Net repair route:

    prompt_cleanup_repair_route -> rerun_cleanup_salvage

It does not call Ollama, OCR, or a table model.  It reads the current cleaned
visual-text records plus the TRACE-Net repair plan, deterministically repairs
prompt-template leakage and section bleed, rescans the repaired markdown, and
optionally applies the repaired records back to the visual-text clean artifact.

The intent is to turn graph trust traits into a concrete repair action:

    bad visual-text traits -> cleanup repair -> rebuilt trust traits -> new plan

Visual text remains derived context; this executor never promotes it to
canonical OCR/part-catalog evidence.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

try:
    from tiff.visual_text_cleanup import (  # type: ignore
        VISUAL_TEXT_V2_SECTION_DEFAULTS,
        VISUAL_TEXT_V2_SECTIONS,
        build_clean_summary,
        parse_visual_text_sections,
        score_visual_text_markdown,
    )
except Exception:  # pragma: no cover - isolated test fallback
    VISUAL_TEXT_V2_SECTIONS = (
        "Page type",
        "Visible title/header",
        "Transcribed visible text",
        "Visual summary",
        "OCR/context assist notes",
        "Tables",
        "Figures/diagrams",
        "Charts/graphs",
        "Labels/callouts/part numbers",
        "Warnings/notes",
        "Uncertain/unreadable",
        "Model caution",
    )
    VISUAL_TEXT_V2_SECTION_DEFAULTS = {
        "Page type": "unknown",
        "Visible title/header": "No readable title or header detected.",
        "Transcribed visible text": "No additional readable text transcribed from the image.",
        "Visual summary": "No additional visual summary available.",
        "OCR/context assist notes": "No OCR/context-only notes reported.",
        "Tables": "No readable table detected.",
        "Figures/diagrams": "No readable figure or diagram detected.",
        "Charts/graphs": "No readable chart or graph detected.",
        "Labels/callouts/part numbers": "No readable labels, callouts, item numbers, part numbers, or references detected.",
        "Warnings/notes": "No visible warnings, cautions, notes, revision notes, or procedural notes detected.",
        "Uncertain/unreadable": "No uncertain or unreadable visual regions reported.",
        "Model caution": "Use this visual extraction as derived context. Verify critical facts against source TIFF/OCR evidence.",
    }

    def parse_visual_text_sections(markdown: str) -> dict[str, str]:
        sections: dict[str, list[str]] = {}
        current: str | None = None
        for raw in str(markdown or "").splitlines():
            line = raw.rstrip()
            stripped = line.strip().lstrip("#").strip()
            if stripped in VISUAL_TEXT_V2_SECTIONS:
                current = stripped
                sections.setdefault(current, [])
                continue
            m = re.match(r"^([A-Za-z][A-Za-z0-9/ ()-]{1,80})\s*:\s*(.*)$", stripped)
            if m and m.group(1).strip() in VISUAL_TEXT_V2_SECTIONS:
                current = m.group(1).strip()
                sections.setdefault(current, [])
                if m.group(2).strip():
                    sections[current].append(m.group(2).strip())
                continue
            if current:
                sections.setdefault(current, []).append(line)
        return {key: "\n".join(value).strip() for key, value in sections.items()}

    def score_visual_text_markdown(markdown: str, *, prompt_version: str = "visual_text_v2_2") -> dict[str, Any]:
        sections = parse_visual_text_sections(markdown)
        text = str(markdown or "").lower()
        return {
            "prompt_version": prompt_version,
            "required_sections_present": all(str(sections.get(t) or "").strip() for t in VISUAL_TEXT_V2_SECTIONS),
            "has_transcribed_visible_text": "no additional readable" not in str(sections.get("Transcribed visible text", "")).lower(),
            "has_table_rows": "|" in str(sections.get("Tables", "")),
            "has_figure_description": "no readable figure" not in str(sections.get("Figures/diagrams", "")).lower(),
            "has_labels_or_callouts": "no readable labels" not in str(sections.get("Labels/callouts/part numbers", "")).lower(),
            "has_part_numbers": bool(re.search(r"\b[A-Z0-9]{1,4}[-/][A-Z0-9][A-Z0-9\-/\.]{2,}\b", markdown, re.I)),
            "has_ocr_context_notes": "no ocr/context" not in str(sections.get("OCR/context assist notes", "")).lower(),
            "metadata_leakage_risk": bool(re.search(r"localhost|local_data|page[_ -]?id|current page role|image classification", markdown, re.I)),
            "metadata_leakage_marker_count": 0,
            "too_summary_heavy": False,
            "hallucination_risk": bool(re.search(r"likely|probably|could be|may be", text)),
            "refusal_like": bool(re.search(r"unable to transcribe text from images|cannot read images", text)),
        }

    def build_clean_summary(clean_records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        tier_counts: Counter[str] = Counter()
        records = list(clean_records)
        counters = Counter()
        for record in records:
            scores = _as_dict(record.get("visual_text_scores_clean"))
            cleanup = _as_dict(record.get("visual_text_cleanup_scores"))
            tier_counts[str(cleanup.get("trust_tier") or "unknown")] += 1
            if str(record.get("status") or "").lower() == "ok":
                counters["ok_records"] += 1
            if scores.get("metadata_leakage_risk"):
                counters["metadata_leakage_records"] += 1
            if scores.get("refusal_like"):
                counters["refusal_like_records"] += 1
            if cleanup.get("prompt_template_leakage_risk"):
                counters["prompt_template_leakage_records"] += 1
            if cleanup.get("section_bleed_risk"):
                counters["section_bleed_records"] += 1
            if cleanup.get("usable_for_rag"):
                counters["usable_for_rag_records"] += 1
            if cleanup.get("requires_human_review"):
                counters["requires_human_review_records"] += 1
        return {
            "status": "OK" if records else "FAIL",
            "created_at": utc_now_iso(),
            "cleanup_version": "trace_net_cleanup_repair_applied",
            "records": len(records),
            **counters,
            "trust_tier_counts": dict(sorted(tier_counts.items())),
        }

DEFAULT_VISUAL_TEXT_DIR = Path("local_data/organization/visual_text")
DEFAULT_TRACE_NET_DIR = Path("local_data/organization/trace_net")
DEFAULT_OUTPUT_DIR = DEFAULT_TRACE_NET_DIR / "cleanup_repair"

DEFAULT_CLEAN_RECORDS = DEFAULT_VISUAL_TEXT_DIR / "visual_text_extraction_clean.jsonl"
DEFAULT_CLEAN_SUMMARY = DEFAULT_VISUAL_TEXT_DIR / "visual_text_clean_summary.json"
DEFAULT_CLEAN_CORPUS = DEFAULT_VISUAL_TEXT_DIR / "visual_text_clean_corpus.md"
DEFAULT_CLEAN_REVIEW_MD = DEFAULT_VISUAL_TEXT_DIR / "visual_text_clean_review.md"
DEFAULT_CLEAN_REVIEW_HTML = DEFAULT_VISUAL_TEXT_DIR / "visual_text_clean_review.html"
DEFAULT_REPAIR_PLAN_JSONL = DEFAULT_TRACE_NET_DIR / "trace_net_repair_plan.jsonl"

REPAIRED_RECORDS_FILE = "trace_net_cleanup_repaired_records.jsonl"
REPAIR_SUMMARY_FILE = "trace_net_cleanup_repair_summary.json"
REPAIR_REVIEW_MD_FILE = "trace_net_cleanup_repair_review.md"
REPAIR_REVIEW_HTML_FILE = "trace_net_cleanup_repair_review.html"
REPAIR_QUALITY_FILE = "trace_net_cleanup_repair_quality.json"

SECTION_LABELS = tuple(str(title) for title in VISUAL_TEXT_V2_SECTIONS)
SECTION_LABEL_PATTERN = re.compile(
    r"(?i)(?<![A-Za-z0-9])(" + "|".join(re.escape(title) for title in SECTION_LABELS) + r")\s*:\s*"
)
PART_NUMBER_PATTERN = re.compile(r"\b[A-Z0-9]{1,4}[-/][A-Z0-9][A-Z0-9\-/\.]{2,}\b", re.I)

PROMPT_TEMPLATE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("bullet_list_instruction", r"\bbullet list\b.*\b(exact|visible|labels|callouts|part numbers|quantities|references|unreadable)\b"),
    ("if_none_visible_instruction", r"\bif none visible\b|\bif none are visible\b"),
    ("no_bullet_list_instruction", r"\bno bullet list\b"),
    ("visible_warning_instruction", r"^\s*visible warnings, cautions, notes\b"),
    ("unreadable_region_instruction", r"^\s*(bullet list of )?unreadable regions, blurry fields\b"),
    ("fields_need_review_instruction", r"\bfields that need source review\b"),
)

SUSPICIOUS_HALLUCINATION_PATTERNS: tuple[tuple[str, str], ...] = (
    ("generic_aeronautical_standard", r"\baeronautical standard manuals\b"),
    ("martini_mauritzio", r"\bmartini mauritzio\b"),
    ("everything_you_need", r"\beverything you need to know\b"),
    ("electrical_equipment_generic", r"\belectrical equipment installation indicator\b|\belectrical circuit breaker\b"),
)

DEFAULT_NONE_VALUES = {
    "Labels/callouts/part numbers": "No reliable labels/callouts extracted after cleanup repair. Source review recommended.",
    "Warnings/notes": "No reliable warnings/notes extracted after cleanup repair. Source review recommended.",
    "Uncertain/unreadable": "Cleanup repair removed leaked template text; source review recommended.",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, Mapping):
                records.append(dict(value))
    return records


def write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(dict(record), sort_keys=True, ensure_ascii=False) + "\n")


def _canonical_section_title(value: str) -> str | None:
    normalized = re.sub(r"\s+", " ", str(value or "").strip().strip("#:")).lower()
    for title in SECTION_LABELS:
        if normalized == title.lower():
            return title
    aliases = {
        "labels": "Labels/callouts/part numbers",
        "callouts": "Labels/callouts/part numbers",
        "part numbers": "Labels/callouts/part numbers",
        "warnings": "Warnings/notes",
        "notes": "Warnings/notes",
        "figures": "Figures/diagrams",
        "diagrams": "Figures/diagrams",
        "unreadable": "Uncertain/unreadable",
        "uncertain": "Uncertain/unreadable",
    }
    return aliases.get(normalized)


def _build_markdown_from_sections(sections: Mapping[str, str]) -> str:
    lines = ["# Page visual text", ""]
    for title in VISUAL_TEXT_V2_SECTIONS:
        value = _text(sections.get(title)) or _text(VISUAL_TEXT_V2_SECTION_DEFAULTS.get(title))
        lines.extend([f"## {title}", value, ""])
    return "\n".join(lines).rstrip() + "\n"


def _ensure_sections(markdown: str) -> dict[str, str]:
    sections = parse_visual_text_sections(str(markdown or ""))
    out: dict[str, str] = {}
    for title in VISUAL_TEXT_V2_SECTIONS:
        out[title] = _text(sections.get(title)) or _text(VISUAL_TEXT_V2_SECTION_DEFAULTS.get(title))
    return out


def _append_or_replace_section(sections: MutableMapping[str, str], title: str, value: str) -> None:
    value = _text(value)
    if not value:
        return
    old = _text(sections.get(title))
    default = _text(VISUAL_TEXT_V2_SECTION_DEFAULTS.get(title))
    if not old or old == default:
        sections[title] = value
    elif value not in old:
        sections[title] = old.rstrip() + "\n" + value


def _inline_section_labels(value: str, *, current: str) -> list[str]:
    labels: list[str] = []
    for match in SECTION_LABEL_PATTERN.finditer(str(value or "")):
        title = _canonical_section_title(match.group(1))
        if title and title != current:
            labels.append(title)
    return sorted(set(labels))


def split_inline_sections(sections: Mapping[str, str]) -> tuple[dict[str, str], list[str]]:
    cleaned: dict[str, str] = {title: _text(sections.get(title)) for title in VISUAL_TEXT_V2_SECTIONS}
    repaired_markers: list[str] = []
    for current in VISUAL_TEXT_V2_SECTIONS:
        value = _text(cleaned.get(current))
        if not value:
            continue
        matches = list(SECTION_LABEL_PATTERN.finditer(value))
        useful = [match for match in matches if _canonical_section_title(match.group(1)) != current or match.start() > 3]
        if not useful:
            continue
        repaired_markers.extend(_inline_section_labels(value, current=current))
        prefix = value[: useful[0].start()].strip(" -\n")
        cleaned[current] = prefix or _text(VISUAL_TEXT_V2_SECTION_DEFAULTS.get(current))
        for index, match in enumerate(useful):
            target = _canonical_section_title(match.group(1))
            if not target:
                continue
            end = useful[index + 1].start() if index + 1 < len(useful) else len(value)
            content = value[match.end() : end].strip(" -\n")
            _append_or_replace_section(cleaned, target, content)
    return cleaned, sorted(set(repaired_markers))


def _prompt_template_markers(value: Any) -> list[str]:
    text = str(value or "")
    markers: list[str] = []
    for name, pattern in PROMPT_TEMPLATE_PATTERNS:
        if re.search(pattern, text, flags=re.I):
            markers.append(name)
    return sorted(set(markers))


def _suspicious_hallucination_markers(value: Any) -> list[str]:
    text = str(value or "")
    markers: list[str] = []
    for name, pattern in SUSPICIOUS_HALLUCINATION_PATTERNS:
        if re.search(pattern, text, flags=re.I):
            markers.append(name)
    return sorted(set(markers))


def remove_prompt_template_lines(sections: Mapping[str, str]) -> tuple[dict[str, str], list[str]]:
    cleaned: dict[str, str] = dict(sections)
    removed_markers: list[str] = []
    for title, value in list(cleaned.items()):
        if not value:
            continue
        kept: list[str] = []
        removed_any = False
        for raw in str(value).splitlines():
            line = raw.strip()
            markers = _prompt_template_markers(line)
            if markers:
                removed_markers.extend(markers)
                removed_any = True
                continue
            kept.append(raw)
        if removed_any:
            replacement = "\n".join(kept).strip()
            if not replacement:
                replacement = DEFAULT_NONE_VALUES.get(title) or _text(VISUAL_TEXT_V2_SECTION_DEFAULTS.get(title))
            cleaned[title] = replacement
    return cleaned, sorted(set(removed_markers))


def _extract_part_numbers(value: Any) -> list[str]:
    return sorted({match.group(0).upper().strip(".,;:") for match in PART_NUMBER_PATTERN.finditer(str(value or ""))})


def _known_part_numbers(record: Mapping[str, Any]) -> set[str]:
    known: set[str] = set()
    for part in _as_list(record.get("known_parts")):
        if isinstance(part, Mapping):
            for key in ("part_number", "part_number_display", "part_number_normalized", "part"):
                value = _text(part.get(key))
                if value:
                    known.add(value.upper())
        else:
            value = _text(part)
            if value:
                known.add(value.upper())
    return known


def _support_part_numbers(record: Mapping[str, Any], markdown: str) -> dict[str, Any]:
    numbers = _extract_part_numbers(markdown)
    ocr_text = _text(record.get("ocr_assist_preview")).upper()
    known = _known_part_numbers(record)
    supported_by_ocr = sorted([number for number in numbers if number in ocr_text])
    supported_by_known_parts = sorted([number for number in numbers if number in known])
    supported = set(supported_by_ocr) | set(supported_by_known_parts)
    unsupported = sorted([number for number in numbers if number not in supported])
    return {
        "visual_part_numbers": numbers,
        "visual_part_number_count": len(numbers),
        "supported_by_ocr": supported_by_ocr,
        "supported_by_known_parts": supported_by_known_parts,
        "unsupported_part_numbers": unsupported,
        "unsupported_part_number_count": len(unsupported),
    }


def _table_expected(record: Mapping[str, Any]) -> bool:
    cleanup = _as_dict(record.get("visual_text_cleanup_scores"))
    if cleanup.get("table_expected") or cleanup.get("table_expected_but_not_extracted"):
        return True
    role = _norm(record.get("page_role"))
    image_class = _norm(record.get("image_classification"))
    return role in {"table", "parts_list"} or image_class in {"likely_table_or_grid", "likely_text_or_parts_list"}


def _trust_tier(record: Mapping[str, Any], clean_scores: Mapping[str, Any], extra_flags: Mapping[str, Any]) -> tuple[str, list[str]]:
    status = _norm(record.get("status"))
    if status not in {"ok", "planned"}:
        return "D", ["record_status_not_accepted"]
    hard_flags = {
        "metadata_leakage_risk": clean_scores.get("metadata_leakage_risk"),
        "refusal_like": clean_scores.get("refusal_like"),
        "prompt_template_leakage_risk": extra_flags.get("prompt_template_leakage_risk"),
    }
    reasons = [key for key, enabled in hard_flags.items() if enabled]
    if reasons:
        return "D", reasons
    review_flags = {
        "section_bleed_risk": extra_flags.get("section_bleed_risk"),
        "hallucination_risk": clean_scores.get("hallucination_risk"),
        "suspicious_phrase_risk": extra_flags.get("suspicious_phrase_risk"),
        "too_summary_heavy": clean_scores.get("too_summary_heavy"),
        "unsupported_part_numbers": int(extra_flags.get("unsupported_part_number_count") or 0) > 0,
    }
    reasons = [key for key, enabled in review_flags.items() if enabled]
    if reasons:
        return "C", reasons
    useful_flags = (
        clean_scores.get("has_transcribed_visible_text"),
        clean_scores.get("has_figure_description"),
        clean_scores.get("has_labels_or_callouts"),
        clean_scores.get("has_part_numbers"),
        clean_scores.get("has_table_rows"),
    )
    if clean_scores.get("required_sections_present") and any(useful_flags):
        return "A", ["clean_useful_visual_context"]
    return "B", ["clean_but_low_detail"]


def _record_markdown(record: Mapping[str, Any]) -> str:
    for key in ("visual_text_markdown_clean", "visual_text_markdown", "visual_text_markdown_original", "markdown", "visual_text"):
        value = _text(record.get(key))
        if value:
            return value
    return ""


def repair_cleanup_record(record: Mapping[str, Any], plan: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Repair one visual-text record without calling any model."""

    output = dict(record)
    source_markdown = _record_markdown(record)
    prompt_version = _text(record.get("prompt_version") or "visual_text_v2_2") or "visual_text_v2_2"
    original_cleanup = _as_dict(record.get("visual_text_cleanup_scores"))
    original_tier = _text(original_cleanup.get("trust_tier") or "unknown") or "unknown"

    sections = _ensure_sections(source_markdown)
    split_sections, repaired_bleed_markers = split_inline_sections(sections)
    cleaned_sections, removed_template_markers = remove_prompt_template_lines(split_sections)
    repaired_markdown = _build_markdown_from_sections(cleaned_sections)

    unresolved_template_markers = _prompt_template_markers(repaired_markdown)
    unresolved_bleed_markers: list[str] = []
    for title, value in parse_visual_text_sections(repaired_markdown).items():
        unresolved_bleed_markers.extend(_inline_section_labels(value, current=title))
    unresolved_bleed_markers = sorted(set(unresolved_bleed_markers))

    scores = dict(score_visual_text_markdown(repaired_markdown, prompt_version=prompt_version))
    support = _support_part_numbers(record, repaired_markdown)
    suspicious = _suspicious_hallucination_markers(repaired_markdown)
    table_expected = _table_expected(record)
    table_missing = bool(table_expected and not scores.get("has_table_rows"))
    extra_flags: dict[str, Any] = {
        "cleanup_version": "trace_net_cleanup_repair_v1",
        "prompt_template_repaired": bool(removed_template_markers) or bool(original_cleanup.get("prompt_template_leakage_risk")),
        "prompt_template_repaired_markers": removed_template_markers,
        "prompt_template_repaired_marker_count": len(removed_template_markers),
        "prompt_template_leakage_risk": bool(unresolved_template_markers),
        "prompt_template_leakage_markers": unresolved_template_markers,
        "prompt_template_leakage_marker_count": len(unresolved_template_markers),
        "section_bleed_repaired": bool(repaired_bleed_markers) or bool(original_cleanup.get("section_bleed_risk")),
        "section_bleed_repaired_markers": repaired_bleed_markers,
        "section_bleed_repaired_marker_count": len(repaired_bleed_markers),
        "section_bleed_risk": bool(unresolved_bleed_markers),
        "section_bleed_markers": unresolved_bleed_markers,
        "section_bleed_marker_count": len(unresolved_bleed_markers),
        "suspicious_phrase_risk": bool(suspicious),
        "suspicious_phrase_markers": suspicious,
        "table_expected": table_expected,
        "table_expected_but_not_extracted": table_missing,
        "clean_char_count": len(repaired_markdown.strip()),
        "original_char_count": len(source_markdown.strip()),
    }
    extra_flags.update(support)
    tier, reasons = _trust_tier(record, scores, extra_flags)
    extra_flags["trust_tier"] = tier
    extra_flags["trust_reasons"] = reasons
    extra_flags["usable_for_rag"] = tier in {"A", "B"}
    extra_flags["requires_human_review"] = tier in {"C", "D"}

    output["visual_text_markdown_before_cleanup_repair"] = source_markdown
    output["visual_text_markdown_clean"] = repaired_markdown.strip()
    output["visual_text_plain_clean"] = re.sub(r"^#+\s*", "", repaired_markdown, flags=re.M).strip()
    output["visual_text_scores_clean"] = scores
    output["visual_text_cleanup_scores"] = extra_flags
    output["char_count_clean"] = len(repaired_markdown.strip())
    output["cleanup_version"] = "trace_net_cleanup_repair_v1"
    output["trace_net_cleanup_repair"] = {
        "route": _text((plan or {}).get("primary_repair_route")) or "prompt_cleanup_repair_route",
        "action": _text((plan or {}).get("primary_repair_action")) or "rerun_cleanup_salvage",
        "applied": True,
        "changed": repaired_markdown.strip() != source_markdown.strip(),
        "original_trust_tier": original_tier,
        "repaired_trust_tier": tier,
        "prompt_template_removed_markers": removed_template_markers,
        "section_bleed_repaired_markers": repaired_bleed_markers,
        "remaining_prompt_template_markers": unresolved_template_markers,
        "remaining_section_bleed_markers": unresolved_bleed_markers,
        "repaired_at": utc_now_iso(),
    }
    output["cleaned_at"] = utc_now_iso()
    return output


def _page_id(record: Mapping[str, Any]) -> str:
    return _text(record.get("page_id") or record.get("id") or record.get("entity_id"))


def _plan_page_id(record: Mapping[str, Any]) -> str:
    return _text(record.get("page_id") or record.get("entity_id") or record.get("page"))


@dataclass(frozen=True)
class TraceNetCleanupRepairPaths:
    visual_text_dir: Path = DEFAULT_VISUAL_TEXT_DIR
    trace_net_dir: Path = DEFAULT_TRACE_NET_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    clean_records_path: Path | None = None
    repair_plan_jsonl_path: Path | None = None

    @property
    def clean_records(self) -> Path:
        return self.clean_records_path or (self.visual_text_dir / "visual_text_extraction_clean.jsonl")

    @property
    def clean_summary(self) -> Path:
        return self.visual_text_dir / "visual_text_clean_summary.json"

    @property
    def clean_corpus_md(self) -> Path:
        return self.visual_text_dir / "visual_text_clean_corpus.md"

    @property
    def clean_review_md(self) -> Path:
        return self.visual_text_dir / "visual_text_clean_review.md"

    @property
    def clean_review_html(self) -> Path:
        return self.visual_text_dir / "visual_text_clean_review.html"

    @property
    def repair_plan_jsonl(self) -> Path:
        return self.repair_plan_jsonl_path or (self.trace_net_dir / "trace_net_repair_plan.jsonl")

    @property
    def repaired_records(self) -> Path:
        return self.output_dir / REPAIRED_RECORDS_FILE

    @property
    def repair_summary(self) -> Path:
        return self.output_dir / REPAIR_SUMMARY_FILE

    @property
    def repair_review_md(self) -> Path:
        return self.output_dir / REPAIR_REVIEW_MD_FILE

    @property
    def repair_review_html(self) -> Path:
        return self.output_dir / REPAIR_REVIEW_HTML_FILE

    @property
    def repair_quality(self) -> Path:
        return self.output_dir / REPAIR_QUALITY_FILE


@dataclass(frozen=True)
class TraceNetCleanupRepairOptions:
    route: str = "prompt_cleanup_repair_route"
    apply: bool = False
    backup: bool = True
    max_records: int | None = None
    page_id: str | None = None


def _build_clean_corpus(records: Sequence[Mapping[str, Any]]) -> str:
    lines = ["# Clean visual text corpus", ""]
    for record in records:
        cleanup = _as_dict(record.get("visual_text_cleanup_scores"))
        lines.extend([
            f"## {_page_id(record) or 'unknown'}",
            "",
            f"- status: {record.get('status', 'unknown')}",
            f"- trust_tier: {cleanup.get('trust_tier', 'unknown')}",
            f"- use_in_rag: {bool(cleanup.get('usable_for_rag'))}",
            f"- repair_version: {record.get('cleanup_version', '')}",
            "",
            _text(record.get("visual_text_markdown_clean")),
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def _build_review_md(records: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]) -> str:
    lines = ["# TRACE-Net cleanup repair review", ""]
    for key in (
        "status",
        "records",
        "selected_records",
        "repaired_records",
        "applied_to_clean_records",
        "remaining_prompt_template_leakage_records",
        "remaining_section_bleed_records",
        "usable_for_rag_records_after",
    ):
        lines.append(f"- {key}: {summary.get(key)}")
    lines.append("")
    for record in records:
        repair = _as_dict(record.get("trace_net_cleanup_repair"))
        cleanup = _as_dict(record.get("visual_text_cleanup_scores"))
        lines.extend([
            f"## {_page_id(record) or 'unknown'}",
            "",
            f"- original_tier: {repair.get('original_trust_tier')}",
            f"- repaired_tier: {repair.get('repaired_trust_tier')}",
            f"- changed: {repair.get('changed')}",
            f"- remaining_prompt_template_markers: {repair.get('remaining_prompt_template_markers', [])}",
            f"- remaining_section_bleed_markers: {repair.get('remaining_section_bleed_markers', [])}",
            f"- trust_reasons: {cleanup.get('trust_reasons', [])}",
            "",
            _text(record.get("visual_text_markdown_clean")),
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def _build_review_html(records: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]) -> str:
    cards: list[str] = []
    for record in records:
        repair = _as_dict(record.get("trace_net_cleanup_repair"))
        cleanup = _as_dict(record.get("visual_text_cleanup_scores"))
        tier = html.escape(_text(cleanup.get("trust_tier") or "unknown"))
        cards.append("\n".join([
            f'<section class="card tier-{tier}">',
            f"<h2>{html.escape(_page_id(record) or 'unknown')}</h2>",
            f"<p><b>Original tier:</b> {html.escape(_text(repair.get('original_trust_tier')))} &nbsp; <b>Repaired tier:</b> {html.escape(_text(repair.get('repaired_trust_tier')))}</p>",
            f"<p><b>Changed:</b> {html.escape(str(repair.get('changed')))} &nbsp; <b>RAG usable:</b> {html.escape(str(cleanup.get('usable_for_rag')))}</p>",
            f"<p><b>Remaining prompt markers:</b> {html.escape(str(repair.get('remaining_prompt_template_markers', [])))}</p>",
            f"<p><b>Remaining section bleed:</b> {html.escape(str(repair.get('remaining_section_bleed_markers', [])))}</p>",
            f"<pre>{html.escape(_text(record.get('visual_text_markdown_clean')))}</pre>",
            "</section>",
        ]))
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>TRACE-Net cleanup repair review</title>
<style>
body { font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 24px; background: #fbf7f1; color: #172033; }
.summary, .card { background: white; border: 1px solid #e2d4c4; border-radius: 14px; padding: 16px; margin: 16px 0; box-shadow: 0 1px 4px rgba(0,0,0,.04); }
.card { border-left-width: 8px; }
.tier-A { border-left-color: #56a764; } .tier-B { border-left-color: #8bb8dd; } .tier-C { border-left-color: #e0a83b; } .tier-D { border-left-color: #cf5b5b; }
pre { white-space: pre-wrap; background: #f8f8f8; border: 1px solid #eee; padding: 12px; border-radius: 10px; }
code { background: #f4eee6; padding: 2px 4px; border-radius: 4px; }
</style></head><body>
<h1>TRACE-Net cleanup repair review</h1>
<section class="summary"><h2>Summary</h2><ul>
""" + "\n".join(f"<li><code>{html.escape(str(k))}</code>: {html.escape(str(v))}</li>" for k, v in summary.items()) + """
</ul></section>
""" + "\n".join(cards) + "\n</body></html>\n"


def _copy_with_backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    backup = path.with_suffix(path.suffix + f".{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.bak")
    shutil.copy2(path, backup)
    return backup


def _write_visual_clean_artifacts(paths: TraceNetCleanupRepairPaths, records: Sequence[Mapping[str, Any]], *, backup: bool = True) -> list[str]:
    backups: list[str] = []
    if backup:
        for path in (paths.clean_records, paths.clean_summary, paths.clean_corpus_md, paths.clean_review_md, paths.clean_review_html):
            created = _copy_with_backup(path)
            if created:
                backups.append(str(created))
    write_jsonl(paths.clean_records, records)
    summary = build_clean_summary(records)
    write_json(paths.clean_summary, summary)
    paths.clean_corpus_md.write_text(_build_clean_corpus(records), encoding="utf-8")
    paths.clean_review_md.write_text(_build_review_md(records, summary), encoding="utf-8")
    paths.clean_review_html.write_text(_build_review_html(records, summary), encoding="utf-8")
    return backups


def run_trace_net_cleanup_repairs(
    paths: TraceNetCleanupRepairPaths = TraceNetCleanupRepairPaths(),
    options: TraceNetCleanupRepairOptions = TraceNetCleanupRepairOptions(),
) -> dict[str, Any]:
    clean_records = read_jsonl(paths.clean_records)
    plan_records = read_jsonl(paths.repair_plan_jsonl)
    plan_by_page = {_plan_page_id(plan): plan for plan in plan_records if _plan_page_id(plan)}

    selected_pages: set[str] = set()
    for page_id, plan in plan_by_page.items():
        if _text(plan.get("primary_repair_route")) == options.route:
            selected_pages.add(page_id)
    if options.page_id:
        selected_pages = {options.page_id}

    repaired_all: list[dict[str, Any]] = []
    repaired_selected: list[dict[str, Any]] = []
    selected_count = 0
    for record in clean_records:
        page_id = _page_id(record)
        should_repair = bool(page_id and page_id in selected_pages)
        if options.max_records is not None and selected_count >= options.max_records:
            should_repair = False
        if should_repair:
            selected_count += 1
            repaired = repair_cleanup_record(record, plan_by_page.get(page_id))
            repaired_selected.append(repaired)
            repaired_all.append(repaired)
        else:
            repaired_all.append(dict(record))

    paths.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(paths.repaired_records, repaired_all)

    before_tiers = Counter(_text(_as_dict(rec.get("visual_text_cleanup_scores")).get("trust_tier") or "unknown") for rec in clean_records)
    after_tiers = Counter(_text(_as_dict(rec.get("visual_text_cleanup_scores")).get("trust_tier") or "unknown") for rec in repaired_all)
    selected_before_tiers = Counter(_text(_as_dict(rec.get("visual_text_cleanup_scores")).get("trust_tier") or "unknown") for rec in clean_records if _page_id(rec) in selected_pages)
    selected_after_tiers = Counter(_text(_as_dict(rec.get("visual_text_cleanup_scores")).get("trust_tier") or "unknown") for rec in repaired_selected)

    remaining_prompt = 0
    remaining_bleed = 0
    usable_after = 0
    improved = 0
    changed = 0
    for record in repaired_all:
        cleanup = _as_dict(record.get("visual_text_cleanup_scores"))
        if cleanup.get("prompt_template_leakage_risk"):
            remaining_prompt += 1
        if cleanup.get("section_bleed_risk"):
            remaining_bleed += 1
        if cleanup.get("usable_for_rag"):
            usable_after += 1
    order = {"A": 4, "B": 3, "C": 2, "D": 1, "unknown": 0, "": 0}
    for record in repaired_selected:
        repair = _as_dict(record.get("trace_net_cleanup_repair"))
        if repair.get("changed"):
            changed += 1
        if order.get(_text(repair.get("repaired_trust_tier")), 0) > order.get(_text(repair.get("original_trust_tier")), 0):
            improved += 1

    backups: list[str] = []
    if options.apply:
        backups = _write_visual_clean_artifacts(paths, repaired_all, backup=options.backup)

    summary = {
        "status": "OK" if clean_records else "FAIL",
        "created_at": utc_now_iso(),
        "repair_version": "trace_net_cleanup_repair_v1",
        "records": len(clean_records),
        "selected_records": len(repaired_selected),
        "repaired_records": len(repaired_selected),
        "changed_records": changed,
        "improved_trust_tier_records": improved,
        "applied_to_clean_records": bool(options.apply),
        "route": options.route,
        "remaining_prompt_template_leakage_records": remaining_prompt,
        "remaining_section_bleed_records": remaining_bleed,
        "usable_for_rag_records_after": usable_after,
        "trust_tier_counts_before": dict(sorted(before_tiers.items())),
        "trust_tier_counts_after": dict(sorted(after_tiers.items())),
        "selected_trust_tier_counts_before": dict(sorted(selected_before_tiers.items())),
        "selected_trust_tier_counts_after": dict(sorted(selected_after_tiers.items())),
        "backups": backups,
        "records_path": str(paths.repaired_records),
        "clean_records_path": str(paths.clean_records),
        "repair_plan_path": str(paths.repair_plan_jsonl),
    }
    write_json(paths.repair_summary, summary)
    paths.repair_review_md.write_text(_build_review_md(repaired_selected, summary), encoding="utf-8")
    paths.repair_review_html.write_text(_build_review_html(repaired_selected, summary), encoding="utf-8")
    return {"summary": summary, "records": repaired_all, "selected_records": repaired_selected}


def build_trace_net_cleanup_repair_quality(
    paths: TraceNetCleanupRepairPaths = TraceNetCleanupRepairPaths(),
    *,
    min_input_records: int = 1,
    min_repaired_records: int = 1,
    max_remaining_prompt_template_leakage_records: int | None = None,
    max_remaining_section_bleed_records: int | None = None,
    min_improved_trust_tier_records: int | None = None,
    require_applied: bool = False,
) -> dict[str, Any]:
    summary_present = paths.repair_summary.exists()
    records_present = paths.repaired_records.exists()
    summary = _as_dict(read_json(paths.repair_summary, {}))
    records = read_jsonl(paths.repaired_records)
    checks: list[dict[str, Any]] = []

    def add_check(name: str, ok: bool, message: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "message": message})

    input_records = _to_int(summary.get("records"), len(records))
    repaired_records = _to_int(summary.get("repaired_records"), 0)
    add_check("trace_net_cleanup_repair_artifacts_present", summary_present and records_present, f"summary={summary_present}; records={records_present}.")
    add_check("trace_net_cleanup_repair_status", _norm(summary.get("status")) == "ok", f"repair summary status is {summary.get('status', 'missing')!r}.")
    add_check("trace_net_cleanup_repair_input_records", input_records >= min_input_records, f"input records={input_records}; minimum={min_input_records}.")
    add_check("trace_net_cleanup_repair_repaired_records", repaired_records >= min_repaired_records, f"repaired records={repaired_records}; minimum={min_repaired_records}.")
    remaining_prompt = _to_int(summary.get("remaining_prompt_template_leakage_records"))
    if max_remaining_prompt_template_leakage_records is not None:
        add_check("trace_net_cleanup_repair_remaining_prompt_template", remaining_prompt <= max_remaining_prompt_template_leakage_records, f"remaining prompt-template leakage records={remaining_prompt}; max={max_remaining_prompt_template_leakage_records}.")
    else:
        add_check("trace_net_cleanup_repair_remaining_prompt_template", True, f"remaining prompt-template leakage records={remaining_prompt}; max=None.")
    remaining_bleed = _to_int(summary.get("remaining_section_bleed_records"))
    if max_remaining_section_bleed_records is not None:
        add_check("trace_net_cleanup_repair_remaining_section_bleed", remaining_bleed <= max_remaining_section_bleed_records, f"remaining section-bleed records={remaining_bleed}; max={max_remaining_section_bleed_records}.")
    else:
        add_check("trace_net_cleanup_repair_remaining_section_bleed", True, f"remaining section-bleed records={remaining_bleed}; max=None.")
    improved = _to_int(summary.get("improved_trust_tier_records"))
    if min_improved_trust_tier_records is not None:
        add_check("trace_net_cleanup_repair_improved_tiers", improved >= min_improved_trust_tier_records, f"improved trust-tier records={improved}; minimum={min_improved_trust_tier_records}.")
    else:
        add_check("trace_net_cleanup_repair_improved_tiers", True, f"improved trust-tier records={improved}; minimum=None.")
    if require_applied:
        add_check("trace_net_cleanup_repair_applied", bool(summary.get("applied_to_clean_records")), f"applied_to_clean_records={summary.get('applied_to_clean_records')}.")
    else:
        add_check("trace_net_cleanup_repair_applied", True, f"applied_to_clean_records={summary.get('applied_to_clean_records')}.")

    status = "OK" if checks and all(check["ok"] for check in checks) else "FAIL"
    return {"status": status, "created_at": utc_now_iso(), "summary": summary, "checks": checks}


def write_trace_net_cleanup_repair_quality(report: Mapping[str, Any], paths: TraceNetCleanupRepairPaths) -> Path:
    write_json(paths.repair_quality, report)
    return paths.repair_quality


def print_cleanup_repair_result(result: Mapping[str, Any], paths: TraceNetCleanupRepairPaths) -> None:
    summary = _as_dict(result.get("summary"))
    print("TRACE-Net cleanup repair executor")
    print(f"  Status: {summary.get('status', 'UNKNOWN')}")
    print(f"  Output dir: {paths.output_dir}")
    print("  Summary:")
    for key in (
        "records",
        "selected_records",
        "repaired_records",
        "changed_records",
        "improved_trust_tier_records",
        "applied_to_clean_records",
        "remaining_prompt_template_leakage_records",
        "remaining_section_bleed_records",
        "usable_for_rag_records_after",
        "trust_tier_counts_before",
        "trust_tier_counts_after",
        "selected_trust_tier_counts_before",
        "selected_trust_tier_counts_after",
    ):
        print(f"    {key}: {summary.get(key)}")
    print("Files written:")
    print(f"  repaired_records: {paths.repaired_records}")
    print(f"  summary: {paths.repair_summary}")
    print(f"  review_md: {paths.repair_review_md}")
    print(f"  review_html: {paths.repair_review_html}")


def print_cleanup_repair_quality(report: Mapping[str, Any]) -> None:
    print("TRACE-Net cleanup repair quality gate")
    print(f"  Status: {report.get('status', 'UNKNOWN')}")
    print("  Summary:")
    for key, value in _as_dict(report.get("summary")).items():
        print(f"    {key}: {value}")
    print("  Checks:")
    for check in _as_list(report.get("checks")):
        status = "OK" if check.get("ok") else "FAIL"
        print(f"    {status} {check.get('name')}: {check.get('message')}")


def _open_path(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["cmd", "/c", "start", "", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run TRACE-Net deterministic cleanup repairs.")
    parser.add_argument("--visual-text-dir", default=str(DEFAULT_VISUAL_TEXT_DIR))
    parser.add_argument("--trace-net-dir", default=str(DEFAULT_TRACE_NET_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--clean-records", default=None)
    parser.add_argument("--repair-plan-jsonl", default=None)
    parser.add_argument("--route", default="prompt_cleanup_repair_route")
    parser.add_argument("--page-id", default=None)
    parser.add_argument("--max-records", type=int, default=None)
    parser.add_argument("--apply", action="store_true", help="Apply repaired records back to visual_text_extraction_clean.jsonl.")
    parser.add_argument("--no-backup", action="store_true", help="Do not create backups when using --apply.")
    parser.add_argument("--open", action="store_true", help="Open the repair review HTML after writing it.")
    args = parser.parse_args(argv)

    paths = TraceNetCleanupRepairPaths(
        visual_text_dir=Path(args.visual_text_dir),
        trace_net_dir=Path(args.trace_net_dir),
        output_dir=Path(args.output_dir),
        clean_records_path=Path(args.clean_records) if args.clean_records else None,
        repair_plan_jsonl_path=Path(args.repair_plan_jsonl) if args.repair_plan_jsonl else None,
    )
    result = run_trace_net_cleanup_repairs(
        paths,
        TraceNetCleanupRepairOptions(
            route=args.route,
            apply=bool(args.apply),
            backup=not bool(args.no_backup),
            max_records=args.max_records,
            page_id=args.page_id,
        ),
    )
    print_cleanup_repair_result(result, paths)
    if args.open:
        _open_path(paths.repair_review_html)
    return 0 if _as_dict(result.get("summary")).get("status") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
