"""Postprocess and score visual-text extraction records.

This module is the v2.3.1 cleanup layer for the visual-text pipeline.  It does
not call a model.  It reads visual_text_extraction.jsonl, repairs common model
formatting problems, scores the cleaned output, assigns a trust tier, and writes
separate clean artifacts for review/RAG gating.

The cleanup layer is intentionally conservative: it never promotes visual model
text into canonical facts.  It only prepares derived visual context and review
signals.
"""
from __future__ import annotations

import argparse
import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

try:  # Reuse the active visual-text parser/scorer when available.
    from tiff.visual_text_extraction import (  # type: ignore
        VISUAL_TEXT_V2_SECTION_DEFAULTS,
        VISUAL_TEXT_V2_SECTIONS,
        normalize_visual_text_markdown,
        parse_visual_text_sections,
        score_visual_text_markdown,
    )
except Exception:  # pragma: no cover - fallback for isolated unit tests.
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
            m = re.match(r"^([A-Za-z][A-Za-z/ ]{1,50})\s*:\s*(.*)$", stripped)
            if m and m.group(1).strip() in VISUAL_TEXT_V2_SECTIONS:
                current = m.group(1).strip()
                sections.setdefault(current, [])
                if m.group(2).strip():
                    sections[current].append(m.group(2).strip())
                continue
            if current:
                sections.setdefault(current, []).append(line)
        return {key: "\n".join(value).strip() for key, value in sections.items()}

    def normalize_visual_text_markdown(markdown: str, *, prompt_version: str = "visual_text_v2_2") -> str:
        sections = parse_visual_text_sections(markdown)
        lines = ["# Page visual text", ""]
        for title in VISUAL_TEXT_V2_SECTIONS:
            value = str(sections.get(title) or VISUAL_TEXT_V2_SECTION_DEFAULTS[title]).strip()
            lines.extend([f"## {title}", value, ""])
        return "\n".join(lines).rstrip() + "\n"

    def score_visual_text_markdown(markdown: str, *, prompt_version: str = "visual_text_v2_2") -> dict[str, Any]:
        sections = parse_visual_text_sections(normalize_visual_text_markdown(markdown, prompt_version=prompt_version))
        text = markdown.lower()
        return {
            "prompt_version": "visual_text_v2_2",
            "required_sections_present": all(str(sections.get(t) or "").strip() for t in VISUAL_TEXT_V2_SECTIONS),
            "has_transcribed_visible_text": "no additional readable" not in sections.get("Transcribed visible text", "").lower(),
            "has_table_rows": "|" in sections.get("Tables", ""),
            "has_figure_description": "no readable figure" not in sections.get("Figures/diagrams", "").lower(),
            "has_labels_or_callouts": "no readable labels" not in sections.get("Labels/callouts/part numbers", "").lower(),
            "has_part_numbers": bool(re.search(r"\b[A-Z0-9]{1,4}[-/][A-Z0-9][A-Z0-9\-/\.]{2,}\b", markdown, re.I)),
            "has_ocr_context_notes": "no ocr/context" not in sections.get("OCR/context assist notes", "").lower(),
            "metadata_leakage_risk": bool(re.search(r"localhost|local_data|page[_ -]?id|current page role|image classification", markdown, re.I)),
            "metadata_leakage_marker_count": 0,
            "too_summary_heavy": False,
            "hallucination_risk": bool(re.search(r"likely|probably|could be|may be", text)),
            "refusal_like": bool(re.search(r"unable to transcribe text from images|cannot read images", text)),
        }


DEFAULT_VISUAL_TEXT_DIR = Path("local_data/organization/visual_text")
DEFAULT_INPUT_RECORDS = "visual_text_extraction.jsonl"
DEFAULT_CLEAN_RECORDS = "visual_text_extraction_clean.jsonl"
DEFAULT_CLEAN_SUMMARY = "visual_text_clean_summary.json"
DEFAULT_REVIEW_FLAGS = "visual_text_review_flags.json"
DEFAULT_CLEAN_CORPUS = "visual_text_clean_corpus.md"
DEFAULT_CLEAN_REVIEW_MD = "visual_text_clean_review.md"
DEFAULT_CLEAN_REVIEW_HTML = "visual_text_clean_review.html"
DEFAULT_CLEAN_QUALITY = "visual_text_clean_quality.json"

PROMPT_TEMPLATE_PATTERNS: tuple[tuple[str, str], ...] = (
    # Keep this intentionally narrow.  Earlier v2.3 scoring treated normal
    # phrases such as "No visible warnings..." or "fields that need source
    # review" as hard prompt-template leaks, which incorrectly rejected useful
    # records after cleanup.  v2.3.1 only counts the literal instruction text
    # that should never survive in cleaned output.
    ("bullet_list_instruction", r"\bbullet list of exact visible\b|\bbullet list of unreadable\b"),
    ("if_none_visible_instruction", r"\bif none visible, say so\b"),
    ("no_bullet_list_instruction", r"\bno bullet list of exact visible\b|\bno bullet list of unreadable\b"),
)

# Phrases that are suspicious when unsupported by OCR/catalog and therefore
# should trigger human review.  This list is intentionally small and project
# specific; it can be expanded from review findings.
SUSPICIOUS_HALLUCINATION_PATTERNS: tuple[tuple[str, str], ...] = (
    ("generic_aeronautical_standard", r"\baeronautical standard manuals\b"),
    ("martini_mauritzio", r"\bmartini mauritzio\b"),
    ("everything_you_need", r"\beverything you need to know\b"),
    ("electrical_equipment_generic", r"\belectrical equipment installation indicator\b|\belectrical circuit breaker\b"),
)

SECTION_LABELS = tuple(str(title) for title in VISUAL_TEXT_V2_SECTIONS)
SECTION_LABEL_PATTERN = re.compile(
    r"(?i)(?<![A-Za-z0-9])(" + "|".join(re.escape(title) for title in SECTION_LABELS) + r")\s*:\s*"
)

PART_NUMBER_PATTERN = re.compile(r"\b[A-Z0-9]{1,4}[-/][A-Z0-9][A-Z0-9\-/\.]{2,}\b", re.I)


@dataclass(frozen=True)
class VisualTextCleanupPaths:
    output_dir: Path = DEFAULT_VISUAL_TEXT_DIR
    input_records_path: Path | None = None
    clean_records_path: Path | None = None
    clean_summary_path: Path | None = None
    review_flags_path: Path | None = None
    clean_corpus_md_path: Path | None = None
    clean_review_md_path: Path | None = None
    clean_review_html_path: Path | None = None
    clean_quality_path: Path | None = None

    @property
    def records(self) -> Path:
        return self.input_records_path or (self.output_dir / DEFAULT_INPUT_RECORDS)

    @property
    def clean_records(self) -> Path:
        return self.clean_records_path or (self.output_dir / DEFAULT_CLEAN_RECORDS)

    @property
    def clean_summary(self) -> Path:
        return self.clean_summary_path or (self.output_dir / DEFAULT_CLEAN_SUMMARY)

    @property
    def review_flags(self) -> Path:
        return self.review_flags_path or (self.output_dir / DEFAULT_REVIEW_FLAGS)

    @property
    def clean_corpus_md(self) -> Path:
        return self.clean_corpus_md_path or (self.output_dir / DEFAULT_CLEAN_CORPUS)

    @property
    def clean_review_md(self) -> Path:
        return self.clean_review_md_path or (self.output_dir / DEFAULT_CLEAN_REVIEW_MD)

    @property
    def clean_review_html(self) -> Path:
        return self.clean_review_html_path or (self.output_dir / DEFAULT_CLEAN_REVIEW_HTML)

    @property
    def clean_quality(self) -> Path:
        return self.clean_quality_path or (self.output_dir / DEFAULT_CLEAN_QUALITY)


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


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


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


def _plain_text_from_markdown(markdown: str) -> str:
    text = re.sub(r"^#+\s*", "", str(markdown or ""), flags=re.M)
    text = re.sub(r"[`*_]+", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _build_markdown_from_sections(sections: Mapping[str, str]) -> str:
    lines = ["# Page visual text", ""]
    for title in VISUAL_TEXT_V2_SECTIONS:
        value = _text(sections.get(title)) or _text(VISUAL_TEXT_V2_SECTION_DEFAULTS.get(title))
        lines.extend([f"## {title}", value, ""])
    return "\n".join(lines).rstrip() + "\n"


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


def _inline_section_labels(value: str, *, current: str) -> list[str]:
    labels: list[str] = []
    for match in SECTION_LABEL_PATTERN.finditer(str(value or "")):
        title = _canonical_section_title(match.group(1))
        if title and title != current:
            labels.append(title)
    return sorted(set(labels))


def _canonical_section_title(value: str) -> str | None:
    normalized = re.sub(r"\s+", " ", str(value or "").strip().strip("#:")).lower()
    for title in SECTION_LABELS:
        if normalized == title.lower():
            return title
    aliases = {
        "figure/diagrams": "Figures/diagrams",
        "figures": "Figures/diagrams",
        "diagrams": "Figures/diagrams",
        "labels": "Labels/callouts/part numbers",
        "callouts": "Labels/callouts/part numbers",
        "part numbers": "Labels/callouts/part numbers",
        "warnings": "Warnings/notes",
        "notes": "Warnings/notes",
        "uncertain": "Uncertain/unreadable",
        "unreadable": "Uncertain/unreadable",
    }
    return aliases.get(normalized)


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


def _split_inline_sections(sections: Mapping[str, str]) -> tuple[dict[str, str], list[str]]:
    """Move embedded ``Section: value`` text to the right v2 section.

    LLaVA occasionally emits one section whose value contains several inline
    section labels.  This function separates those labels so the review UI and
    quality checks can reason about each section separately.
    """

    cleaned: dict[str, str] = {title: _text(sections.get(title)) for title in VISUAL_TEXT_V2_SECTIONS}
    bleed_markers: list[str] = []
    for current in VISUAL_TEXT_V2_SECTIONS:
        value = _text(cleaned.get(current))
        if not value:
            continue
        matches = list(SECTION_LABEL_PATTERN.finditer(value))
        # Ignore a label at the very beginning if it is the current section.
        useful = [match for match in matches if _canonical_section_title(match.group(1)) != current or match.start() > 3]
        if not useful:
            continue
        bleed_markers.extend(_inline_section_labels(value, current=current))
        prefix = value[: useful[0].start()].strip(" -\n")
        if prefix:
            cleaned[current] = prefix
        else:
            cleaned[current] = _text(VISUAL_TEXT_V2_SECTION_DEFAULTS.get(current))
        for index, match in enumerate(useful):
            target = _canonical_section_title(match.group(1))
            if not target:
                continue
            end = useful[index + 1].start() if index + 1 < len(useful) else len(value)
            content = value[match.end() : end].strip(" -\n")
            _append_or_replace_section(cleaned, target, content)
    return cleaned, sorted(set(bleed_markers))


def _remove_prompt_template_lines(sections: Mapping[str, str]) -> tuple[dict[str, str], list[str]]:
    cleaned = dict(sections)
    markers: list[str] = []
    for title, value in list(cleaned.items()):
        title_markers = _prompt_template_markers(value)
        if title_markers:
            markers.extend(title_markers)
        if not value:
            continue
        kept: list[str] = []
        removed_any = False
        for line in str(value).splitlines():
            if _prompt_template_markers(line):
                removed_any = True
                continue
            kept.append(line)
        if removed_any:
            replacement = "\n".join(kept).strip()
            if not replacement:
                if title == "Labels/callouts/part numbers":
                    replacement = "No reliable labels/callouts extracted after prompt-template cleanup. Source review required."
                elif title == "Warnings/notes":
                    replacement = "No reliable warnings/notes extracted after prompt-template cleanup. Source review required."
                elif title == "Uncertain/unreadable":
                    replacement = "Prompt-template text was removed; source review recommended."
                else:
                    replacement = _text(VISUAL_TEXT_V2_SECTION_DEFAULTS.get(title))
            cleaned[title] = replacement
    return cleaned, sorted(set(markers))


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
    unsupported = sorted([number for number in numbers if number not in set(supported_by_ocr) and number not in set(supported_by_known_parts)])
    return {
        "visual_part_numbers": numbers,
        "visual_part_number_count": len(numbers),
        "supported_by_ocr": supported_by_ocr,
        "supported_by_known_parts": supported_by_known_parts,
        "unsupported_part_numbers": unsupported,
        "unsupported_part_number_count": len(unsupported),
    }


def _table_expected(record: Mapping[str, Any]) -> bool:
    role = _norm(record.get("page_role"))
    image_class = _norm(record.get("image_classification"))
    return role in {"table", "parts_list"} or image_class in {"likely_table_or_grid", "likely_text_or_parts_list"}


def _trust_tier(record: Mapping[str, Any], clean_scores: Mapping[str, Any], extra_flags: Mapping[str, Any]) -> tuple[str, list[str]]:
    status = _norm(record.get("status"))
    reasons: list[str] = []
    if status not in {"ok", "planned"}:
        return "D", ["record_status_not_accepted"]
    hard_flags = {
        "metadata_leakage_risk": clean_scores.get("metadata_leakage_risk"),
        "refusal_like": clean_scores.get("refusal_like"),
        "prompt_template_leakage_risk": extra_flags.get("prompt_template_leakage_risk"),
    }
    for key, enabled in hard_flags.items():
        if enabled:
            reasons.append(key)
    if reasons:
        return "D", reasons
    review_flags = {
        "section_bleed_risk": extra_flags.get("section_bleed_risk"),
        "hallucination_risk": clean_scores.get("hallucination_risk"),
        "suspicious_phrase_risk": extra_flags.get("suspicious_phrase_risk"),
        # Table misses remain visible review signals, but v2.3.1 does not let
        # them demote otherwise clean visual-context records.  Dense tables need
        # a separate crop/tile extraction route; the visual-context layer should
        # not be rejected only because it did not reconstruct table rows.
        "too_summary_heavy": clean_scores.get("too_summary_heavy"),
    }
    for key, enabled in review_flags.items():
        if enabled:
            reasons.append(key)
    if reasons:
        return "C", reasons
    useful_flags = (
        clean_scores.get("has_transcribed_visible_text"),
        clean_scores.get("has_figure_description"),
        clean_scores.get("has_labels_or_callouts"),
        clean_scores.get("has_part_numbers"),
        clean_scores.get("has_table_rows"),
    )
    if all((clean_scores.get("required_sections_present"), any(useful_flags))):
        return "A", ["clean_useful_visual_context"]
    return "B", ["clean_but_low_detail"]


def cleanup_visual_text_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of one record with cleaned markdown and v2.3 scores."""

    output = dict(record)
    prompt_version = _text(record.get("prompt_version") or "visual_text_v2_2") or "visual_text_v2_2"
    original_markdown = _text(record.get("visual_text_markdown"))
    normalized = normalize_visual_text_markdown(original_markdown, prompt_version=prompt_version)
    initial_sections = parse_visual_text_sections(normalized)
    split_sections, repaired_bleed_markers = _split_inline_sections(initial_sections)
    cleaned_sections, repaired_template_markers = _remove_prompt_template_lines(split_sections)
    cleaned_markdown = _build_markdown_from_sections(cleaned_sections)

    # v2.3.1 separates "repaired during cleanup" from "still leaking after
    # cleanup".  The quality gate should fail only on unresolved leaks in the
    # cleaned artifact.  The repaired marker counts remain available for review
    # and prompt improvement.
    unresolved_template_markers = _prompt_template_markers(cleaned_markdown)
    unresolved_bleed_markers: list[str] = []
    for section_title, section_value in parse_visual_text_sections(cleaned_markdown).items():
        unresolved_bleed_markers.extend(_inline_section_labels(section_value, current=section_title))
    unresolved_bleed_markers = sorted(set(unresolved_bleed_markers))

    clean_scores = score_visual_text_markdown(cleaned_markdown, prompt_version=prompt_version)
    support = _support_part_numbers(record, cleaned_markdown)
    suspicious_markers = _suspicious_hallucination_markers(cleaned_markdown)
    table_expected = _table_expected(record)
    table_missing = bool(table_expected and not clean_scores.get("has_table_rows"))
    extra_flags: dict[str, Any] = {
        "cleanup_version": "visual_text_v2_3_1_cleanup",
        "prompt_template_repaired": bool(repaired_template_markers),
        "prompt_template_repaired_markers": repaired_template_markers,
        "prompt_template_repaired_marker_count": len(repaired_template_markers),
        "prompt_template_leakage_risk": bool(unresolved_template_markers),
        "prompt_template_leakage_markers": unresolved_template_markers,
        "prompt_template_leakage_marker_count": len(unresolved_template_markers),
        "section_bleed_repaired": bool(repaired_bleed_markers),
        "section_bleed_repaired_markers": repaired_bleed_markers,
        "section_bleed_repaired_marker_count": len(repaired_bleed_markers),
        "section_bleed_risk": bool(unresolved_bleed_markers),
        "section_bleed_markers": unresolved_bleed_markers,
        "section_bleed_marker_count": len(unresolved_bleed_markers),
        "suspicious_phrase_risk": bool(suspicious_markers),
        "suspicious_phrase_markers": suspicious_markers,
        "table_expected": table_expected,
        "table_expected_but_not_extracted": table_missing,
        "clean_char_count": len(cleaned_markdown.strip()),
        "original_char_count": len(original_markdown.strip()),
    }
    extra_flags.update(support)
    tier, reasons = _trust_tier(record, clean_scores, extra_flags)
    extra_flags["trust_tier"] = tier
    extra_flags["trust_reasons"] = reasons
    extra_flags["usable_for_rag"] = tier in {"A", "B"}
    extra_flags["requires_human_review"] = tier in {"C", "D"}

    output["visual_text_markdown_original"] = original_markdown
    output["visual_text_markdown_clean"] = cleaned_markdown.strip()
    output["visual_text_plain_clean"] = _plain_text_from_markdown(cleaned_markdown)
    output["visual_text_scores_original"] = _as_dict(record.get("visual_text_scores"))
    output["visual_text_scores_clean"] = clean_scores
    output["visual_text_cleanup_scores"] = extra_flags
    output["char_count_clean"] = len(cleaned_markdown.strip())
    output["cleanup_version"] = "visual_text_v2_3_1_cleanup"
    output["cleaned_at"] = utc_now_iso()
    return output


def cleanup_visual_text_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [cleanup_visual_text_record(record) for record in records]


def build_clean_summary(clean_records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    tier_counts: dict[str, int] = {}
    counters = {
        "records": len(clean_records),
        "ok_records": 0,
        "accepted_records": 0,
        "error_records": 0,
        "clean_records": 0,
        "required_section_records": 0,
        "metadata_leakage_records": 0,
        "refusal_like_records": 0,
        "prompt_template_leakage_records": 0,
        "prompt_template_leakage_marker_total": 0,
        "prompt_template_repaired_records": 0,
        "prompt_template_repaired_marker_total": 0,
        "section_bleed_records": 0,
        "section_bleed_marker_total": 0,
        "section_bleed_repaired_records": 0,
        "section_bleed_repaired_marker_total": 0,
        "summary_heavy_records": 0,
        "hallucination_risk_records": 0,
        "suspicious_phrase_records": 0,
        "table_expected_records": 0,
        "table_expected_missing_records": 0,
        "table_row_records": 0,
        "visual_part_number_records": 0,
        "unsupported_part_number_records": 0,
        "usable_for_rag_records": 0,
        "requires_human_review_records": 0,
    }
    flag_records: list[dict[str, Any]] = []
    for record in clean_records:
        status = _norm(record.get("status") or "unknown") or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == "ok":
            counters["ok_records"] += 1
        if status in {"ok", "planned"}:
            counters["accepted_records"] += 1
        if status == "error":
            counters["error_records"] += 1
        scores = _as_dict(record.get("visual_text_scores_clean"))
        cleanup = _as_dict(record.get("visual_text_cleanup_scores"))
        if record.get("visual_text_markdown_clean"):
            counters["clean_records"] += 1
        if scores.get("required_sections_present"):
            counters["required_section_records"] += 1
        bool_counter_map = {
            "metadata_leakage_risk": "metadata_leakage_records",
            "refusal_like": "refusal_like_records",
            "too_summary_heavy": "summary_heavy_records",
            "hallucination_risk": "hallucination_risk_records",
            "has_table_rows": "table_row_records",
        }
        for score_key, counter_key in bool_counter_map.items():
            if bool(scores.get(score_key)):
                counters[counter_key] += 1
        cleanup_counter_map = {
            "prompt_template_leakage_risk": "prompt_template_leakage_records",
            "prompt_template_repaired": "prompt_template_repaired_records",
            "section_bleed_risk": "section_bleed_records",
            "section_bleed_repaired": "section_bleed_repaired_records",
            "suspicious_phrase_risk": "suspicious_phrase_records",
            "table_expected": "table_expected_records",
            "table_expected_but_not_extracted": "table_expected_missing_records",
            "usable_for_rag": "usable_for_rag_records",
            "requires_human_review": "requires_human_review_records",
        }
        for score_key, counter_key in cleanup_counter_map.items():
            if bool(cleanup.get(score_key)):
                counters[counter_key] += 1
        counters["prompt_template_leakage_marker_total"] += int(cleanup.get("prompt_template_leakage_marker_count") or 0)
        counters["prompt_template_repaired_marker_total"] += int(cleanup.get("prompt_template_repaired_marker_count") or 0)
        counters["section_bleed_marker_total"] += int(cleanup.get("section_bleed_marker_count") or 0)
        counters["section_bleed_repaired_marker_total"] += int(cleanup.get("section_bleed_repaired_marker_count") or 0)
        if int(cleanup.get("visual_part_number_count") or 0) > 0:
            counters["visual_part_number_records"] += 1
        if int(cleanup.get("unsupported_part_number_count") or 0) > 0:
            counters["unsupported_part_number_records"] += 1
        tier = _text(cleanup.get("trust_tier") or "unknown") or "unknown"
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        if cleanup.get("requires_human_review") or cleanup.get("prompt_template_leakage_risk") or cleanup.get("section_bleed_risk"):
            flag_records.append(
                {
                    "page_id": record.get("page_id"),
                    "trust_tier": tier,
                    "trust_reasons": cleanup.get("trust_reasons", []),
                    "prompt_template_leakage_markers": cleanup.get("prompt_template_leakage_markers", []),
                    "prompt_template_repaired_markers": cleanup.get("prompt_template_repaired_markers", []),
                    "section_bleed_markers": cleanup.get("section_bleed_markers", []),
                    "section_bleed_repaired_markers": cleanup.get("section_bleed_repaired_markers", []),
                    "suspicious_phrase_markers": cleanup.get("suspicious_phrase_markers", []),
                    "table_expected_but_not_extracted": bool(cleanup.get("table_expected_but_not_extracted")),
                    "unsupported_part_numbers": cleanup.get("unsupported_part_numbers", []),
                }
            )
    status = "OK" if counters["error_records"] == 0 and counters["records"] > 0 else "FAIL"
    return {
        "status": status,
        "created_at": utc_now_iso(),
        "cleanup_version": "visual_text_v2_3_1_cleanup",
        **counters,
        "status_counts": dict(sorted(status_counts.items())),
        "trust_tier_counts": dict(sorted(tier_counts.items())),
        "flagged_records": flag_records,
    }


def _build_clean_corpus(clean_records: Sequence[Mapping[str, Any]]) -> str:
    lines = ["# Clean visual text corpus", ""]
    for record in clean_records:
        if _norm(record.get("status")) not in {"ok", "planned"}:
            continue
        cleanup = _as_dict(record.get("visual_text_cleanup_scores"))
        lines.extend(
            [
                f"## {record.get('page_id', 'unknown')}",
                "",
                f"- status: {record.get('status', 'unknown')}",
                f"- trust_tier: {cleanup.get('trust_tier', 'unknown')}",
                f"- use_in_rag: {bool(cleanup.get('usable_for_rag'))}",
                f"- review_reasons: {', '.join(cleanup.get('trust_reasons', [])) if isinstance(cleanup.get('trust_reasons'), list) else cleanup.get('trust_reasons', '')}",
                "",
                _text(record.get("visual_text_markdown_clean")),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _build_clean_review_md(clean_records: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]) -> str:
    lines = ["# Visual text v2.3.1 cleanup review", ""]
    lines.extend(
        [
            f"Status: **{summary.get('status', 'unknown')}**",
            "",
            f"Records: {summary.get('records', 0)}",
            f"Usable for RAG: {summary.get('usable_for_rag_records', 0)}",
            f"Requires review: {summary.get('requires_human_review_records', 0)}",
            f"Prompt-template leakage records: {summary.get('prompt_template_leakage_records', 0)}",
            f"Section-bleed records: {summary.get('section_bleed_records', 0)}",
            f"Metadata-leakage records: {summary.get('metadata_leakage_records', 0)}",
            "",
        ]
    )
    for record in clean_records:
        cleanup = _as_dict(record.get("visual_text_cleanup_scores"))
        scores = _as_dict(record.get("visual_text_scores_clean"))
        lines.extend(
            [
                f"## {record.get('page_id', 'unknown')}",
                "",
                f"- status: {record.get('status', 'unknown')}",
                f"- trust_tier: {cleanup.get('trust_tier', 'unknown')}",
                f"- reasons: {', '.join(cleanup.get('trust_reasons', [])) if isinstance(cleanup.get('trust_reasons'), list) else cleanup.get('trust_reasons', '')}",
                f"- prompt_template_leakage: {bool(cleanup.get('prompt_template_leakage_risk'))}",
                f"- section_bleed: {bool(cleanup.get('section_bleed_risk'))}",
                f"- table_expected_missing: {bool(cleanup.get('table_expected_but_not_extracted'))}",
                f"- hallucination_risk: {bool(scores.get('hallucination_risk'))}",
                f"- metadata_leakage: {bool(scores.get('metadata_leakage_risk'))}",
                f"- refusal_like: {bool(scores.get('refusal_like'))}",
                "",
                _text(record.get("visual_text_markdown_clean")),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _build_clean_review_html(clean_records: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]) -> str:
    cards: list[str] = []
    for record in clean_records:
        cleanup = _as_dict(record.get("visual_text_cleanup_scores"))
        scores = _as_dict(record.get("visual_text_scores_clean"))
        tier = html.escape(_text(cleanup.get("trust_tier") or "unknown"))
        reasons = cleanup.get("trust_reasons", [])
        if isinstance(reasons, list):
            reasons_text = ", ".join(_text(reason) for reason in reasons)
        else:
            reasons_text = _text(reasons)
        flags = [
            f"prompt_template={bool(cleanup.get('prompt_template_leakage_risk'))}",
            f"section_bleed={bool(cleanup.get('section_bleed_risk'))}",
            f"table_missing={bool(cleanup.get('table_expected_but_not_extracted'))}",
            f"hallucination={bool(scores.get('hallucination_risk'))}",
            f"metadata={bool(scores.get('metadata_leakage_risk'))}",
            f"refusal={bool(scores.get('refusal_like'))}",
        ]
        cards.append(
            "\n".join(
                [
                    f'<section class="card tier-{tier}">',
                    f"<h2>{html.escape(_text(record.get('page_id') or 'unknown'))}</h2>",
                    f"<p><b>Trust tier:</b> {tier} &nbsp; <b>Reasons:</b> {html.escape(reasons_text)}</p>",
                    f"<p><b>Flags:</b> {html.escape('; '.join(flags))}</p>",
                    f"<pre>{html.escape(_text(record.get('visual_text_markdown_clean')))}</pre>",
                    "</section>",
                ]
            )
        )
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Visual text v2.3.1 cleanup review</title>
<style>
body { font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 24px; background: #fbf7f1; color: #172033; }
.summary, .card { background: white; border: 1px solid #e2d4c4; border-radius: 14px; padding: 16px; margin: 16px 0; box-shadow: 0 1px 4px rgba(0,0,0,.04); }
.card { border-left-width: 8px; }
.tier-A { border-left-color: #56a764; }
.tier-B { border-left-color: #8bb8dd; }
.tier-C { border-left-color: #e0a83b; }
.tier-D { border-left-color: #cf5b5b; }
pre { white-space: pre-wrap; background: #f8f8f8; border: 1px solid #eee; padding: 12px; border-radius: 10px; }
code { background: #f4eee6; padding: 2px 4px; border-radius: 4px; }
</style>
</head>
<body>
<h1>Visual text v2.3.1 cleanup review</h1>
<section class="summary">
<h2>Summary</h2>
<ul>
""" + "\n".join(
        f"<li><code>{html.escape(str(key))}</code>: {html.escape(str(value))}</li>"
        for key, value in summary.items()
        if key != "flagged_records"
    ) + """
</ul>
</section>
""" + "\n".join(cards) + """
</body>
</html>
"""


def run_visual_text_cleanup(paths: VisualTextCleanupPaths = VisualTextCleanupPaths()) -> dict[str, Any]:
    records = read_jsonl(paths.records)
    clean_records = cleanup_visual_text_records(records)
    summary = build_clean_summary(clean_records)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(paths.clean_records, clean_records)
    _write_json(paths.clean_summary, summary)
    _write_json(paths.review_flags, summary.get("flagged_records", []))
    paths.clean_corpus_md.write_text(_build_clean_corpus(clean_records), encoding="utf-8")
    paths.clean_review_md.write_text(_build_clean_review_md(clean_records, summary), encoding="utf-8")
    paths.clean_review_html.write_text(_build_clean_review_html(clean_records, summary), encoding="utf-8")
    return {"summary": summary, "records": clean_records}


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_visual_text_clean_quality(
    paths: VisualTextCleanupPaths = VisualTextCleanupPaths(),
    *,
    min_records: int = 1,
    min_usable_for_rag_records: int = 0,
    max_metadata_leakage_records: int = 0,
    max_refusal_like_records: int = 0,
    max_prompt_template_leakage_records: int | None = None,
    max_section_bleed_records: int | None = None,
    max_trust_d_records: int | None = 0,
    max_error_records: int = 0,
) -> dict[str, Any]:
    summary_present = paths.clean_summary.exists()
    records_present = paths.clean_records.exists()
    summary = _read_json(paths.clean_summary) if summary_present else {}
    records = read_jsonl(paths.clean_records) if records_present else []
    tier_counts = _as_dict(summary.get("trust_tier_counts"))
    checks: list[dict[str, Any]] = []

    def add_check(name: str, ok: bool, message: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "message": message})

    record_count = _to_int(summary.get("records"), len(records))
    add_check(
        "visual_text_clean_artifacts_present",
        summary_present and records_present,
        f"clean_summary={summary_present}; clean_records={records_present}.",
    )
    add_check("visual_text_clean_records", record_count >= min_records and len(records) >= min_records, f"records summary={record_count}, jsonl={len(records)}; minimum={min_records}.")
    add_check(
        "visual_text_clean_status",
        str(summary.get("status", "")).lower() == "ok",
        f"Clean summary status is {summary.get('status', 'missing')!r}.",
    )
    errors = _to_int(summary.get("error_records"))
    add_check("visual_text_clean_errors", errors <= max_error_records, f"error_records={errors}; max={max_error_records}.")
    metadata = _to_int(summary.get("metadata_leakage_records"))
    add_check("visual_text_clean_metadata_leakage", metadata <= max_metadata_leakage_records, f"metadata_leakage_records={metadata}; max={max_metadata_leakage_records}.")
    refusals = _to_int(summary.get("refusal_like_records"))
    add_check("visual_text_clean_refusal_like", refusals <= max_refusal_like_records, f"refusal_like_records={refusals}; max={max_refusal_like_records}.")
    prompt_leaks = _to_int(summary.get("prompt_template_leakage_records"))
    if max_prompt_template_leakage_records is not None:
        add_check("visual_text_clean_prompt_template_leakage", prompt_leaks <= max_prompt_template_leakage_records, f"prompt_template_leakage_records={prompt_leaks}; max={max_prompt_template_leakage_records}.")
    else:
        add_check("visual_text_clean_prompt_template_leakage", True, f"prompt_template_leakage_records={prompt_leaks}; max=None.")
    section_bleed = _to_int(summary.get("section_bleed_records"))
    if max_section_bleed_records is not None:
        add_check("visual_text_clean_section_bleed", section_bleed <= max_section_bleed_records, f"section_bleed_records={section_bleed}; max={max_section_bleed_records}.")
    else:
        add_check("visual_text_clean_section_bleed", True, f"section_bleed_records={section_bleed}; max=None.")
    trust_d = _to_int(tier_counts.get("D"))
    if max_trust_d_records is not None:
        add_check("visual_text_clean_trust_d", trust_d <= max_trust_d_records, f"trust_tier_D={trust_d}; max={max_trust_d_records}.")
    usable = _to_int(summary.get("usable_for_rag_records"))
    add_check("visual_text_clean_usable_for_rag", usable >= min_usable_for_rag_records, f"usable_for_rag_records={usable}; minimum={min_usable_for_rag_records}.")

    status = "OK" if checks and all(check["ok"] for check in checks) else "FAIL"
    report = {
        "status": status,
        "created_at": utc_now_iso(),
        "summary_present": summary_present,
        "records_present": records_present,
        "summary_path": str(paths.clean_summary),
        "records_path": str(paths.clean_records),
        "summary": summary,
        "checks": checks,
    }
    return report


def print_cleanup_result(result: Mapping[str, Any], paths: VisualTextCleanupPaths) -> None:
    summary = _as_dict(result.get("summary"))
    print("Visual text v2.3.1 cleanup/scoring")
    print(f"  Status: {summary.get('status', 'UNKNOWN')}")
    print("  Summary:")
    for key in (
        "records",
        "ok_records",
        "error_records",
        "usable_for_rag_records",
        "requires_human_review_records",
        "prompt_template_leakage_records",
        "prompt_template_repaired_records",
        "section_bleed_records",
        "section_bleed_repaired_records",
        "metadata_leakage_records",
        "refusal_like_records",
        "summary_heavy_records",
        "hallucination_risk_records",
        "suspicious_phrase_records",
        "table_expected_missing_records",
    ):
        print(f"    {key}: {summary.get(key)}")
    print(f"  Trust tiers: {summary.get('trust_tier_counts', {})}")
    print("Files written:")
    print(f"  clean_records: {paths.clean_records}")
    print(f"  clean_summary: {paths.clean_summary}")
    print(f"  review_flags: {paths.review_flags}")
    print(f"  clean_corpus_md: {paths.clean_corpus_md}")
    print(f"  clean_review_md: {paths.clean_review_md}")
    print(f"  clean_review_html: {paths.clean_review_html}")


def print_quality_report(report: Mapping[str, Any], paths: VisualTextCleanupPaths) -> None:
    print("Visual text clean quality gate")
    print(f"  Status: {report.get('status', 'UNKNOWN')}")
    summary = _as_dict(report.get("summary"))
    print("  Summary:")
    for key in (
        "records",
        "ok_records",
        "error_records",
        "usable_for_rag_records",
        "requires_human_review_records",
        "prompt_template_leakage_records",
        "prompt_template_repaired_records",
        "section_bleed_records",
        "section_bleed_repaired_records",
        "metadata_leakage_records",
        "refusal_like_records",
        "trust_tier_counts",
    ):
        print(f"    {key}: {summary.get(key)}")
    print("  Checks:")
    for check in report.get("checks", []):
        if isinstance(check, Mapping):
            prefix = "OK" if check.get("ok") else "FAIL"
            print(f"    {prefix} {check.get('name')}: {check.get('message')}")
    print(f"\nJSON: {paths.clean_quality}")


def parse_cleanup_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean and score visual-text extraction records without calling a model.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_VISUAL_TEXT_DIR)
    parser.add_argument("--records", type=Path, default=None, help="Input visual_text_extraction.jsonl path")
    parser.add_argument("--open", action="store_true", help="Open the clean HTML review after writing it")
    return parser.parse_args(argv)


def cleanup_main(argv: Sequence[str] | None = None) -> int:
    args = parse_cleanup_args(argv)
    paths = VisualTextCleanupPaths(output_dir=args.output_dir, input_records_path=args.records)
    result = run_visual_text_cleanup(paths)
    print_cleanup_result(result, paths)
    if args.open:
        import os
        import subprocess
        import sys

        html_path = paths.clean_review_html.resolve()
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(html_path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", str(html_path)], check=False)
            else:
                subprocess.run(["xdg-open", str(html_path)], check=False)
        except Exception:
            print(f"Open this file in your browser: {html_path}")
    return 0


def parse_quality_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check visual-text v2.3 clean quality artifacts.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_VISUAL_TEXT_DIR)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-usable-for-rag-records", type=int, default=0)
    parser.add_argument("--max-error-records", type=int, default=0)
    parser.add_argument("--max-metadata-leakage-records", type=int, default=0)
    parser.add_argument("--max-refusal-like-records", type=int, default=0)
    parser.add_argument("--max-prompt-template-leakage-records", type=int, default=None)
    parser.add_argument("--max-section-bleed-records", type=int, default=None)
    parser.add_argument("--max-trust-d-records", type=int, default=0)
    return parser.parse_args(argv)


def quality_main(argv: Sequence[str] | None = None) -> int:
    args = parse_quality_args(argv)
    paths = VisualTextCleanupPaths(output_dir=args.output_dir)
    report = build_visual_text_clean_quality(
        paths,
        min_records=args.min_records,
        min_usable_for_rag_records=args.min_usable_for_rag_records,
        max_metadata_leakage_records=args.max_metadata_leakage_records,
        max_refusal_like_records=args.max_refusal_like_records,
        max_prompt_template_leakage_records=args.max_prompt_template_leakage_records,
        max_section_bleed_records=args.max_section_bleed_records,
        max_trust_d_records=args.max_trust_d_records,
        max_error_records=args.max_error_records,
    )
    if args.write_json:
        _write_json(paths.clean_quality, report)
    print_quality_report(report, paths)
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cleanup_main())
