"""TRACE-Net Vision Model Pilot v1.

This module selects a small, safe set of visual pages for optional local vision-model
inspection. It is intentionally advisory: vision output is never source truth and
never answer-authoritative. The module can run in plan-only mode or call Ollama for
local vision descriptions when image paths are available.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "trace_net_vision_model_pilot_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/vision_model_pilot")
DEFAULT_QUALITY_NAME = "trace_net_vision_model_pilot_v1_quality.json"
DEFAULT_REPORT_NAME = "trace_net_vision_model_pilot_v1.json"
DEFAULT_RECORDS_NAME = "trace_net_vision_model_pilot_v1_records.jsonl"
DEFAULT_PROMPTS_NAME = "trace_net_vision_model_pilot_v1_prompts.jsonl"
DEFAULT_MODEL_OUTPUTS_NAME = "trace_net_vision_model_pilot_v1_model_outputs.jsonl"
DEFAULT_BLOCKED_NAME = "trace_net_vision_model_pilot_v1_blocked.jsonl"
DEFAULT_SUMMARY_NAME = "trace_net_vision_model_pilot_v1_summary.json"
DEFAULT_MANIFEST_NAME = "trace_net_vision_model_pilot_v1_manifest.json"
DEFAULT_MD_NAME = "trace_net_vision_model_pilot_v1.md"
DEFAULT_HTML_NAME = "trace_net_vision_model_pilot_v1.html"

ALLOWED_VISION_MODES = {"plan-only", "ollama"}
ADVISORY_AUTHORITY = "visual_model_advisory_only"
ADVISORY_BUCKET = "vision_model_retrieval_helper"

FORBIDDEN_TEXT_MARKERS = (
    "local_data\\",
    "local_data/",
    "rescarta_exports",
    "C:\\Users\\",
    "TIFF path:",
    "OCR path:",
    "Source URL:",
    "OCR text: [b",
    "Source text evidence for page",
    "This chunk is source-backed",
    "ignore previous instructions",
    "system prompt",
)

VISUAL_LAYOUT_CLASSES = {
    "figure_or_diagram",
    "chart_or_plot",
    "mixed_table_and_diagram",
    "parts_list_or_illustrated_parts",
    "parts_list_table",
    "unknown_visual_layout",
}

LOW_PRIORITY_LAYOUT_CLASSES = {
    "blank",
    "text_heavy",
    "sparse_ink_text_or_source_trace",
}

TABLE_ONLY_LAYOUT_CLASSES = {
    "table_or_grid",
}

VISION_ROUTE_HINTS = {
    "visual_model_route",
    "visual_region_route",
    "callout_candidate_route",
    "catalog_graph_visual_compare_route",
    "figure_chart_understanding_route",
}


def read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), sort_keys=True) + "\n")


def stable_id(prefix: str, *parts: Any, length: int = 16) -> str:
    text = "||".join(str(part) for part in parts)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def normalize_page_id(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if text.startswith("t_p_120_1176_p"):
        return text
    digits = re.sub(r"\D", "", text)
    if digits:
        return f"t_p_120_1176_p{int(digits):06d}"
    return text


def page_number_from_id(page_id: str) -> int | None:
    match = re.search(r"p(\d{6})$", page_id or "")
    if not match:
        return None
    return int(match.group(1))


def safe_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return [value]


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "ok", "pass"}


def contains_forbidden_marker(text: str) -> bool:
    low = text.lower()
    return any(marker.lower() in low for marker in FORBIDDEN_TEXT_MARKERS)


def sanitize_model_text(text: str, max_chars: int = 1200) -> str:
    if not text:
        return ""
    text = str(text).replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    # Remove common local path fragments if a model echoes a prompt or file path.
    text = re.sub(r"[A-Za-z]:\\[^\s]+", "[redacted_path]", text)
    text = re.sub(r"local_data[\\/][^\s]+", "[redacted_path]", text)
    text = re.sub(r"rescarta_exports[\\/][^\s]+", "[redacted_path]", text)
    if len(text) > max_chars:
        text = text[: max_chars - 3].rstrip() + "..."
    return text


def first_existing_path(record: Mapping[str, Any]) -> str:
    keys = (
        "image_path",
        "page_image_path",
        "tiff_path",
        "source_tiff_path",
        "local_image_path",
        "path",
        "page_path",
    )
    for key in keys:
        value = record.get(key)
        if value:
            return str(value)
    # Some audit records nest source paths.
    for key in ("source", "source_record", "paths", "metadata"):
        nested = record.get(key)
        if isinstance(nested, Mapping):
            found = first_existing_path(nested)
            if found:
                return found
    return ""


def load_audit_by_page(path: str | Path | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    if p.suffix.lower() == ".jsonl":
        rows = read_jsonl(p)
    else:
        payload = read_json(p)
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, Mapping):
            rows = safe_list(payload.get("records") or payload.get("pages") or payload.get("items") or payload.get("audit_records") or [])
        else:
            rows = []
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        page_id = normalize_page_id(row.get("page_id") or row.get("id") or row.get("page") or row.get("page_label"))
        if page_id:
            out[page_id] = dict(row)
    return out


def load_records_by_page(path: str | Path) -> dict[str, dict[str, Any]]:
    payload = read_json(path)
    rows = payload.get("records", [])
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        page_id = normalize_page_id(row.get("page_id"))
        if page_id:
            out[page_id] = dict(row)
    return out


def load_visual_text_by_page(path: str | Path | None) -> dict[str, list[dict[str, Any]]]:
    if not path:
        return {}
    p = Path(path)
    rows: list[dict[str, Any]]
    if not p.exists():
        return {}
    if p.suffix.lower() == ".jsonl":
        rows = read_jsonl(p)
    else:
        payload = read_json(p)
        rows = safe_list(payload.get("records") or payload.get("visual_text_records") or payload.get("items"))
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        page_id = normalize_page_id(row.get("page_id") or row.get("page"))
        if page_id:
            out.setdefault(page_id, []).append(dict(row))
    return out



def figure_record_has_strong_visual_reason(figure_record: Mapping[str, Any] | None) -> bool:
    if not figure_record:
        return False
    if boolish(figure_record.get("needs_human_review")):
        return True
    if boolish(figure_record.get("requires_catalog_compare")):
        return True
    if safe_list(figure_record.get("callout_labels")):
        return True
    if safe_list(figure_record.get("linked_part_candidates")):
        return True
    return False


def should_select_for_vision_pilot(
    calibrated: Mapping[str, Any],
    figure_record: Mapping[str, Any] | None = None,
    *,
    explicit_include: bool = False,
) -> tuple[bool, str]:
    """Return whether a page should enter the vision pilot and the reason.

    The calibrated ink/layout class is the front gate. Older broad figure/chart
    classifications are advisory and should not re-promote blank or text-heavy
    pages into the vision pilot unless the user explicitly includes them.
    """
    if explicit_include:
        return True, "explicit_include_page"

    layout = str(calibrated.get("calibrated_layout_class") or "")
    if boolish(calibrated.get("source_confirmed_blank")) or layout == "blank":
        return False, "excluded_source_confirmed_blank"
    if layout in LOW_PRIORITY_LAYOUT_CLASSES:
        return False, f"excluded_low_priority_layout:{layout}"

    if boolish(calibrated.get("needs_vision_model")):
        return True, "calibrator_needs_vision_model"
    if layout in {"figure_or_diagram", "mixed_table_and_diagram", "parts_list_or_illustrated_parts", "unknown_visual_layout"}:
        return True, f"calibrated_visual_layout:{layout}"
    if layout == "chart_or_plot":
        return True, "calibrated_chart_or_plot"
    if layout == "parts_list_table" and figure_record_has_strong_visual_reason(figure_record):
        return True, "parts_list_table_with_catalog_or_callout_reason"
    if layout in TABLE_ONLY_LAYOUT_CLASSES:
        return False, f"excluded_table_only_layout:{layout}"

    return False, "not_selected_by_calibrated_layout_gate"


def pilot_selection_priority(record: Mapping[str, Any]) -> tuple[int, int]:
    """Higher priority pages should be sent to the pilot before low-value pages."""
    layout = str(record.get("calibrated_layout_class") or "")
    score = 0
    if boolish(record.get("needs_human_review")):
        score += 80
    if boolish(record.get("requires_catalog_compare")):
        score += 70
    if safe_list(record.get("linked_part_candidates")):
        score += 55
    if safe_list(record.get("callout_labels")):
        score += 45
    if layout == "mixed_table_and_diagram":
        score += 40
    elif layout == "figure_or_diagram":
        score += 35
    elif layout == "parts_list_or_illustrated_parts":
        score += 30
    elif layout == "parts_list_table":
        score += 20
    elif layout == "chart_or_plot":
        score += 15
    elif layout == "unknown_visual_layout":
        score += 10
    page_number = page_number_from_id(str(record.get("page_id") or "")) or 999999
    return score, -page_number

def infer_needs_vision_model(calibrated: Mapping[str, Any], figure_record: Mapping[str, Any] | None = None) -> bool:
    if boolish(calibrated.get("needs_vision_model")):
        return True
    layout = str(calibrated.get("calibrated_layout_class") or calibrated.get("calibrated_visual_type") or "")
    if layout in {"figure_or_diagram", "chart_or_plot", "mixed_table_and_diagram", "unknown_visual_layout"}:
        return True
    routes = set(str(r) for r in safe_list(calibrated.get("recommended_extraction_routes")))
    if routes & VISION_ROUTE_HINTS:
        return True
    scores = calibrated.get("calibrated_scores") or {}
    if isinstance(scores, Mapping):
        diagram = float(scores.get("diagram_score") or 0.0)
        chart = float(scores.get("chart_score") or 0.0)
        mixed = float(scores.get("mixed_layout_score") or 0.0)
        if max(diagram, chart, mixed) >= 0.65:
            return True
    if figure_record:
        if boolish(figure_record.get("needs_human_review")):
            return True
        if boolish(figure_record.get("requires_catalog_compare")):
            return True
        if str(figure_record.get("visual_type") or "") in {"parts_diagram_or_illustrated_parts_list", "chart_or_plot_candidate"}:
            return True
    return False


def classify_visual_task(calibrated: Mapping[str, Any], figure_record: Mapping[str, Any] | None = None) -> list[str]:
    layout = str(calibrated.get("calibrated_layout_class") or "")
    visual_type = str(calibrated.get("calibrated_visual_type") or "")
    prev = str((figure_record or {}).get("visual_type") or calibrated.get("previous_visual_type") or "")
    tasks: list[str] = []
    text = " ".join([layout, visual_type, prev]).lower()
    if "chart" in text or "plot" in text:
        tasks.append("classify_chart_axes_legend_and_labels")
    if "diagram" in text or "figure" in text or "illustrated" in text:
        tasks.append("describe_figure_regions_and_callouts")
    if "part" in text or boolish((figure_record or {}).get("requires_catalog_compare")):
        tasks.append("extract_visual_part_callout_candidates")
    if "table" in text or "mixed" in text:
        tasks.append("separate_table_from_visual_regions")
    if not tasks:
        tasks.append("visual_route_review")
    return tasks


def build_prompt(record: Mapping[str, Any]) -> str:
    page_id = record.get("page_id", "")
    layout = record.get("calibrated_layout_class", "")
    visual_type = record.get("calibrated_visual_type", "")
    tasks = ", ".join(record.get("vision_tasks", []))
    callouts = ", ".join(record.get("callout_labels", [])[:30]) if isinstance(record.get("callout_labels"), list) else ""
    linked_parts = ", ".join(record.get("linked_part_candidates", [])[:20]) if isinstance(record.get("linked_part_candidates"), list) else ""
    return (
        "You are assisting TRACE-Net with visual routing only. "
        "Do not claim source truth. Do not answer the user. "
        "Describe only visible layout elements, possible labels/callouts, and uncertainty. "
        "Mark any visual statement as requiring OCR/catalog/graph/citation verification.\n\n"
        f"Page ID: {page_id}\n"
        f"Calibrated layout class: {layout}\n"
        f"Calibrated visual type: {visual_type}\n"
        f"Vision tasks: {tasks}\n"
        f"Existing callout candidates: {callouts}\n"
        f"Existing linked part candidates: {linked_parts}\n\n"
        "Return a short JSON-like summary with keys: visual_summary, possible_callouts, possible_parts, uncertainty, required_comparisons."
    )


def encode_image_b64(path_text: str) -> str:
    if not path_text:
        return ""
    p = Path(path_text)
    if not p.exists():
        return ""
    try:
        return base64.b64encode(p.read_bytes()).decode("ascii")
    except OSError:
        return ""


def call_ollama_vision(
    *,
    prompt: str,
    image_path: str,
    model: str,
    ollama_url: str,
    endpoint: str = "/api/generate",
    timeout: int = 180,
) -> tuple[str, str]:
    """Return (status, response_text)."""
    image_b64 = encode_image_b64(image_path)
    if not image_b64:
        return "skipped_missing_image", ""
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
        "options": {"temperature": 0},
    }
    url = ollama_url.rstrip("/") + endpoint
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            parsed = json.loads(response.read().decode("utf-8"))
            return "model_completed", sanitize_model_text(str(parsed.get("response") or parsed.get("message") or ""))
    except urllib.error.HTTPError as exc:
        return "model_error", f"HTTP {exc.code}: {exc.reason}"
    except Exception as exc:  # noqa: BLE001 - CLI artifact should report model issues, not crash by default.
        return "model_error", str(exc)


@dataclass(frozen=True)
class QualityThresholds:
    require_page_count: int | None = None
    min_pilot_records: int = 1
    min_selected_pages: int = 1
    min_prompt_records: int = 1
    min_retrieval_only_records: int = 1
    max_model_error_count: int | None = None


def collect_candidate_records(
    calibrator_payload: Mapping[str, Any],
    figure_payload: Mapping[str, Any] | None,
    audit_by_page: Mapping[str, Mapping[str, Any]] | None,
    visual_text_by_page: Mapping[str, list[Mapping[str, Any]]] | None,
    max_pilot_pages: int,
    include_pages: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    figure_by_page: dict[str, dict[str, Any]] = {}
    if figure_payload:
        for row in safe_list(figure_payload.get("records")):
            if isinstance(row, Mapping):
                page_id = normalize_page_id(row.get("page_id"))
                if page_id:
                    figure_by_page[page_id] = dict(row)
    include_set = {normalize_page_id(page) for page in include_pages or [] if page}
    records: list[dict[str, Any]] = []
    for calibrated in safe_list(calibrator_payload.get("records")):
        if not isinstance(calibrated, Mapping):
            continue
        page_id = normalize_page_id(calibrated.get("page_id"))
        if not page_id:
            continue
        figure = figure_by_page.get(page_id, {})
        layout = str(calibrated.get("calibrated_layout_class") or "")
        selected, selection_reason = should_select_for_vision_pilot(
            calibrated,
            figure,
            explicit_include=page_id in include_set,
        )
        if not selected:
            continue
        audit = dict((audit_by_page or {}).get(page_id, {}))
        visual_text = [dict(v) for v in (visual_text_by_page or {}).get(page_id, [])]
        image_path = first_existing_path(audit) or first_existing_path(figure) or first_existing_path(calibrated)
        vision_tasks = classify_visual_task(calibrated, figure)
        callout_labels = safe_list(figure.get("callout_labels") or calibrated.get("callout_labels"))
        linked_parts = safe_list(figure.get("linked_part_candidates") or calibrated.get("linked_part_candidates"))
        record = {
            "pilot_record_id": stable_id("visionpilot", page_id, layout, ",".join(vision_tasks)),
            "schema_version": SCHEMA_VERSION,
            "page_id": page_id,
            "page_number": page_number_from_id(page_id),
            "forced_include": page_id in include_set,
            "record_type": "vision_model_pilot_record",
            "rag_bucket": ADVISORY_BUCKET,
            "authority": ADVISORY_AUTHORITY,
            "answer_use_policy": "visual_routing_advisory_requires_ocr_catalog_graph_citation",
            "calibrated_layout_class": layout,
            "calibrated_visual_type": calibrated.get("calibrated_visual_type"),
            "source_page_role": calibrated.get("source_page_role"),
            "previous_visual_type": calibrated.get("previous_visual_type"),
            "calibrated_scores": calibrated.get("calibrated_scores") or {},
            "figure_understanding_visual_type": figure.get("visual_type"),
            "figure_understanding_trust_tier": figure.get("trust_tier"),
            "callout_labels": [str(v) for v in callout_labels if str(v).strip()],
            "linked_part_candidates": [str(v) for v in linked_parts if str(v).strip()],
            "visual_text_record_count": len(visual_text),
            "image_path_available": bool(image_path),
            "image_path": image_path,
            "vision_tasks": vision_tasks,
            "requires_ocr_compare": True,
            "requires_catalog_compare": boolish(figure.get("requires_catalog_compare")) or "extract_visual_part_callout_candidates" in vision_tasks,
            "requires_graph_compare": True,
            "requires_source_resolution": True,
            "requires_citation": True,
            "requires_authority_gate": True,
            "needs_human_review": boolish(figure.get("needs_human_review")) or not bool(image_path),
            "needs_vision_model": True,
            "pilot_selection_reason": selection_reason,
            "pilot_selection_priority": 0,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "can_prove_source_truth": False,
            "canonical_source_truth": False,
            "can_mutate_source_truth": False,
            "final_answer_allowed": False,
            "visual_answer_allowed": False,
            "unverified_visual_claim": False,
            "prompt_text": "",
            "model_status": "not_run",
            "model_output_text": "",
            "model_output_allowed_for_final": False,
            "model_output_requires_validation": True,
            "blocked_reasons": [],
        }
        record["pilot_selection_priority"] = pilot_selection_priority(record)[0]
        record["prompt_text"] = build_prompt(record)
        records.append(record)
    records.sort(key=pilot_selection_priority, reverse=True)
    if max_pilot_pages:
        records = records[:max_pilot_pages]
    return records


def run_vision_model_for_records(
    records: list[dict[str, Any]],
    *,
    vision_mode: str,
    model: str,
    ollama_url: str,
    ollama_endpoint: str,
    ollama_timeout: int,
    progress: bool = False,
) -> None:
    if vision_mode == "plan-only":
        for record in records:
            record["model_status"] = "planned_not_run"
            record["model_output_text"] = ""
            record["model_output_allowed_for_final"] = False
        return
    if vision_mode != "ollama":
        raise ValueError(f"Unsupported vision mode: {vision_mode}")
    for index, record in enumerate(records, start=1):
        if progress:
            print(f"TRACE-Net vision pilot progress: model page {index}/{len(records)} {record['page_id']}")
        status, output = call_ollama_vision(
            prompt=record.get("prompt_text", ""),
            image_path=record.get("image_path", ""),
            model=model,
            ollama_url=ollama_url,
            endpoint=ollama_endpoint,
            timeout=ollama_timeout,
        )
        record["model_status"] = status
        record["model_output_text"] = output
        record["model_output_allowed_for_final"] = False
        if status == "model_error":
            record.setdefault("blocked_reasons", []).append("vision_model_error")
        if status == "skipped_missing_image":
            record.setdefault("blocked_reasons", []).append("missing_image_for_vision_model")
        if output and contains_forbidden_marker(output):
            record.setdefault("blocked_reasons", []).append("model_output_forbidden_marker")
            record["model_status"] = "model_output_blocked"


def summarize(records: Sequence[Mapping[str, Any]], source_summary: Mapping[str, Any] | None = None) -> dict[str, Any]:
    def count_if(pred: Any) -> int:
        return sum(1 for row in records if pred(row))

    visual_type_counts: dict[str, int] = {}
    layout_counts: dict[str, int] = {}
    task_counts: dict[str, int] = {}
    model_status_counts: dict[str, int] = {}
    selection_reason_counts: dict[str, int] = {}
    for row in records:
        layout = str(row.get("calibrated_layout_class") or "unknown")
        visual = str(row.get("figure_understanding_visual_type") or row.get("calibrated_visual_type") or "unknown")
        layout_counts[layout] = layout_counts.get(layout, 0) + 1
        visual_type_counts[visual] = visual_type_counts.get(visual, 0) + 1
        model_status = str(row.get("model_status") or "unknown")
        model_status_counts[model_status] = model_status_counts.get(model_status, 0) + 1
        reason = str(row.get("pilot_selection_reason") or "unknown")
        selection_reason_counts[reason] = selection_reason_counts.get(reason, 0) + 1
        for task in safe_list(row.get("vision_tasks")):
            task_counts[str(task)] = task_counts.get(str(task), 0) + 1
    summary = {
        "schema_version": SCHEMA_VERSION,
        "vision_pilot_record_count": len(records),
        "selected_page_count": len({row.get("page_id") for row in records}),
        "prompt_record_count": count_if(lambda r: bool(r.get("prompt_text"))),
        "retrieval_only_record_count": count_if(lambda r: r.get("rag_bucket") == ADVISORY_BUCKET),
        "image_path_available_count": count_if(lambda r: bool(r.get("image_path_available"))),
        "model_completed_count": count_if(lambda r: r.get("model_status") == "model_completed"),
        "model_error_count": count_if(lambda r: r.get("model_status") == "model_error"),
        "model_output_blocked_count": count_if(lambda r: r.get("model_status") == "model_output_blocked"),
        "planned_not_run_count": count_if(lambda r: r.get("model_status") == "planned_not_run"),
        "visual_answer_allowed_count": count_if(lambda r: boolish(r.get("visual_answer_allowed"))),
        "direct_answer_allowed_count": count_if(lambda r: boolish(r.get("can_answer_directly"))),
        "claim_proof_allowed_count": count_if(lambda r: boolish(r.get("can_prove_claims"))),
        "unverified_visual_claim_count": count_if(lambda r: boolish(r.get("unverified_visual_claim"))),
        "source_truth_mutation_allowed_count": count_if(lambda r: boolish(r.get("can_mutate_source_truth"))),
        "final_answer_allowed_count": count_if(lambda r: boolish(r.get("final_answer_allowed"))),
        "model_output_allowed_for_final_count": count_if(lambda r: boolish(r.get("model_output_allowed_for_final"))),
        "unsafe_vision_pilot_record_count": count_if(record_is_unsafe),
        "layout_counts": dict(sorted(layout_counts.items())),
        "visual_type_counts": dict(sorted(visual_type_counts.items())),
        "vision_task_counts": dict(sorted(task_counts.items())),
        "model_status_counts": dict(sorted(model_status_counts.items())),
        "pilot_selection_reason_counts": dict(sorted(selection_reason_counts.items())),
    }
    if source_summary:
        summary["source_calibrator_summary"] = dict(source_summary)
    return summary


def record_is_unsafe(record: Mapping[str, Any]) -> bool:
    if boolish(record.get("visual_answer_allowed")):
        return True
    if boolish(record.get("can_answer_directly")):
        return True
    if boolish(record.get("can_prove_claims")):
        return True
    if boolish(record.get("can_mutate_source_truth")):
        return True
    if boolish(record.get("final_answer_allowed")):
        return True
    if boolish(record.get("model_output_allowed_for_final")):
        return True
    if record.get("rag_bucket") != ADVISORY_BUCKET:
        return True
    if record.get("authority") != ADVISORY_AUTHORITY:
        return True
    prompt = str(record.get("prompt_text") or "")
    output = str(record.get("model_output_text") or "")
    if contains_forbidden_marker(output):
        return True
    # The prompt may contain policy text, but should not contain local paths.
    if any(marker.lower() in prompt.lower() for marker in ("local_data\\", "local_data/", "rescarta_exports", "C:\\Users\\")):
        return True
    return False


def build_quality(
    report: Mapping[str, Any],
    thresholds: QualityThresholds,
) -> dict[str, Any]:
    summary = dict(report.get("summary") or {})
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, observed: Any, expected: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "observed": observed, "expected": expected})

    if thresholds.require_page_count is not None:
        source_count = (report.get("source_calibrator_summary") or {}).get("calibrated_page_count")
        if source_count is None:
            source_count = (summary.get("source_calibrator_summary") or {}).get("calibrated_page_count")
        add("require_page_count", source_count == thresholds.require_page_count, source_count, thresholds.require_page_count)

    add("min_pilot_records", summary.get("vision_pilot_record_count", 0) >= thresholds.min_pilot_records, summary.get("vision_pilot_record_count", 0), thresholds.min_pilot_records)
    add("min_selected_pages", summary.get("selected_page_count", 0) >= thresholds.min_selected_pages, summary.get("selected_page_count", 0), thresholds.min_selected_pages)
    add("min_prompt_records", summary.get("prompt_record_count", 0) >= thresholds.min_prompt_records, summary.get("prompt_record_count", 0), thresholds.min_prompt_records)
    add("min_retrieval_only_records", summary.get("retrieval_only_record_count", 0) >= thresholds.min_retrieval_only_records, summary.get("retrieval_only_record_count", 0), thresholds.min_retrieval_only_records)
    if thresholds.max_model_error_count is not None:
        add("max_model_error_count", summary.get("model_error_count", 0) <= thresholds.max_model_error_count, summary.get("model_error_count", 0), thresholds.max_model_error_count)

    add("visual_answer_allowed_zero", summary.get("visual_answer_allowed_count", 0) == 0, summary.get("visual_answer_allowed_count", 0), 0)
    add("direct_answer_allowed_zero", summary.get("direct_answer_allowed_count", 0) == 0, summary.get("direct_answer_allowed_count", 0), 0)
    add("claim_proof_allowed_zero", summary.get("claim_proof_allowed_count", 0) == 0, summary.get("claim_proof_allowed_count", 0), 0)
    add("unverified_visual_claim_zero", summary.get("unverified_visual_claim_count", 0) == 0, summary.get("unverified_visual_claim_count", 0), 0)
    add("source_truth_mutation_allowed_zero", summary.get("source_truth_mutation_allowed_count", 0) == 0, summary.get("source_truth_mutation_allowed_count", 0), 0)
    add("final_answer_allowed_zero", summary.get("final_answer_allowed_count", 0) == 0, summary.get("final_answer_allowed_count", 0), 0)
    add("model_output_allowed_for_final_zero", summary.get("model_output_allowed_for_final_count", 0) == 0, summary.get("model_output_allowed_for_final_count", 0), 0)
    add("unsafe_vision_pilot_record_zero", summary.get("unsafe_vision_pilot_record_count", 0) == 0, summary.get("unsafe_vision_pilot_record_count", 0), 0)

    status = "PASS" if all(check["passed"] for check in checks) else "FAIL"
    return {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": status,
        "checks": checks,
        "summary": summary,
        "created_at_unix": int(time.time()),
    }


def build_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    lines = [
        "# TRACE-Net Vision Model Pilot v1",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        "",
        "## Summary",
        "",
    ]
    for key in (
        "vision_mode",
        "vision_model_name",
        "vision_pilot_record_count",
        "selected_page_count",
        "prompt_record_count",
        "retrieval_only_record_count",
        "model_completed_count",
        "model_error_count",
        "visual_answer_allowed_count",
        "unsafe_vision_pilot_record_count",
    ):
        value = report.get(key, summary.get(key))
        if value is not None:
            lines.append(f"- {key}: {value}")
    lines.extend([
        "",
        "## Safety rule",
        "",
        "Vision model outputs are advisory only. They cannot prove claims, answer directly, or mutate source truth.",
    ])
    return "\n".join(lines) + "\n"


def build_html(markdown_text: str) -> str:
    body = "\n".join(f"<p>{html.escape(line)}</p>" if line else "" for line in markdown_text.splitlines())
    return f"<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Vision Model Pilot v1</title></head><body>{body}</body></html>\n"


def build_vision_model_pilot(
    *,
    visual_ink_layout_calibrator_path: str | Path,
    figure_chart_understanding_path: str | Path | None = None,
    image_recognition_audit_path: str | Path | None = None,
    visual_text_records_path: str | Path | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    vision_mode: str = "plan-only",
    vision_model: str = "llava:latest",
    ollama_url: str = "http://localhost:11434",
    ollama_endpoint: str = "/api/generate",
    ollama_timeout: int = 180,
    max_pilot_pages: int = 25,
    include_pages: Sequence[str] | None = None,
    progress: bool = False,
    thresholds: QualityThresholds | None = None,
    write_quality: bool = True,
) -> dict[str, Any]:
    if vision_mode not in ALLOWED_VISION_MODES:
        raise ValueError(f"vision_mode must be one of {sorted(ALLOWED_VISION_MODES)}")
    calibrator = read_json(visual_ink_layout_calibrator_path)
    figure_payload = read_json(figure_chart_understanding_path) if figure_chart_understanding_path and Path(figure_chart_understanding_path).exists() else None
    audit_by_page = load_audit_by_page(image_recognition_audit_path) if image_recognition_audit_path else {}
    visual_text_by_page = load_visual_text_by_page(visual_text_records_path) if visual_text_records_path else {}
    records = collect_candidate_records(
        calibrator,
        figure_payload,
        audit_by_page,
        visual_text_by_page,
        max_pilot_pages=max_pilot_pages,
        include_pages=include_pages,
    )
    run_vision_model_for_records(
        records,
        vision_mode=vision_mode,
        model=vision_model,
        ollama_url=ollama_url,
        ollama_endpoint=ollama_endpoint,
        ollama_timeout=ollama_timeout,
        progress=progress,
    )
    source_summary = dict(calibrator.get("summary") or {})
    summary = summarize(records, source_summary=source_summary)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / DEFAULT_REPORT_NAME
    records_path = output / DEFAULT_RECORDS_NAME
    prompts_path = output / DEFAULT_PROMPTS_NAME
    outputs_path = output / DEFAULT_MODEL_OUTPUTS_NAME
    blocked_path = output / DEFAULT_BLOCKED_NAME
    summary_path = output / DEFAULT_SUMMARY_NAME
    manifest_path = output / DEFAULT_MANIFEST_NAME
    quality_path = output / DEFAULT_QUALITY_NAME
    md_path = output / DEFAULT_MD_NAME
    html_path = output / DEFAULT_HTML_NAME
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "VISION_MODEL_PILOT_BUILT",
        "quality_status": "UNKNOWN",
        "answer_status": "VISION_MODEL_PILOT_ONLY",
        "final_answer_allowed": False,
        "vision_mode": vision_mode,
        "vision_model_name": vision_model,
        "ollama_url": ollama_url if vision_mode == "ollama" else "",
        "ollama_endpoint": ollama_endpoint if vision_mode == "ollama" else "",
        "source_calibrator_path": str(visual_ink_layout_calibrator_path),
        "source_figure_chart_understanding_path": str(figure_chart_understanding_path or ""),
        "source_image_recognition_audit_path": str(image_recognition_audit_path or ""),
        "source_visual_text_records_path": str(visual_text_records_path or ""),
        "source_calibrator_summary": source_summary,
        "records": records,
        "summary": summary,
        "report_path": str(report_path),
        "records_path": str(records_path),
        "prompts_path": str(prompts_path),
        "model_outputs_path": str(outputs_path),
        "blocked_path": str(blocked_path),
        "summary_path": str(summary_path),
        "manifest_path": str(manifest_path),
        "quality_path": str(quality_path),
        "markdown_path": str(md_path),
        "html_path": str(html_path),
        "created_at_unix": int(time.time()),
    }
    thresholds = thresholds or QualityThresholds()
    quality = build_quality(report, thresholds)
    report["quality_status"] = quality["status"]
    write_json(report_path, report)
    write_jsonl(records_path, records)
    write_jsonl(prompts_path, ({"page_id": r["page_id"], "pilot_record_id": r["pilot_record_id"], "prompt_text": r["prompt_text"]} for r in records))
    write_jsonl(outputs_path, ({"page_id": r["page_id"], "pilot_record_id": r["pilot_record_id"], "model_status": r["model_status"], "model_output_text": r["model_output_text"]} for r in records if r.get("model_status") not in {"planned_not_run", "not_run"} or r.get("model_output_text")))
    write_jsonl(blocked_path, (r for r in records if r.get("blocked_reasons")))
    write_json(summary_path, summary)
    manifest = {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "report_path": str(report_path),
        "records_path": str(records_path),
        "prompts_path": str(prompts_path),
        "model_outputs_path": str(outputs_path),
        "blocked_path": str(blocked_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "vision_mode": vision_mode,
        "vision_model_name": vision_model,
        "record_count": len(records),
        "quality_status": quality["status"],
    }
    write_json(manifest_path, manifest)
    if write_quality:
        write_json(quality_path, quality)
    md = build_markdown(report)
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(build_html(md), encoding="utf-8")
    return report


def check_vision_model_pilot_quality(
    *,
    report_path: str | Path,
    thresholds: QualityThresholds | None = None,
    write_json_quality: bool = False,
) -> dict[str, Any]:
    report = read_json(report_path)
    quality = build_quality(report, thresholds or QualityThresholds())
    if write_json_quality:
        output_path = Path(report_path).with_name(DEFAULT_QUALITY_NAME)
        write_json(output_path, quality)
    return quality


def parse_include_pages(text: str | None) -> list[str]:
    if not text:
        return []
    pages: list[str] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part and not part.startswith("t_p_"):
            left, right = part.split("-", 1)
            if left.strip().isdigit() and right.strip().isdigit():
                for n in range(int(left), int(right) + 1):
                    pages.append(f"t_p_120_1176_p{n:06d}")
                continue
        pages.append(normalize_page_id(part))
    return pages


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Vision Model Pilot v1 artifacts.")
    parser.add_argument("--visual-ink-layout-calibrator", required=True)
    parser.add_argument("--figure-chart-understanding")
    parser.add_argument("--image-recognition-audit")
    parser.add_argument("--visual-text-records")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--vision-mode", choices=sorted(ALLOWED_VISION_MODES), default="plan-only")
    parser.add_argument("--vision-model", default="llava:latest")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--ollama-endpoint", default="/api/generate")
    parser.add_argument("--ollama-timeout", type=int, default=180)
    parser.add_argument("--max-pilot-pages", type=int, default=25)
    parser.add_argument("--include-pages", help="Comma-separated page IDs or page-number ranges, e.g. 3,5,10-12")
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-pilot-records", type=int, default=1)
    parser.add_argument("--min-selected-pages", type=int, default=1)
    parser.add_argument("--min-prompt-records", type=int, default=1)
    parser.add_argument("--min-retrieval-only-records", type=int, default=1)
    parser.add_argument("--max-model-error-count", type=int)
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    thresholds = QualityThresholds(
        require_page_count=args.require_page_count,
        min_pilot_records=args.min_pilot_records,
        min_selected_pages=args.min_selected_pages,
        min_prompt_records=args.min_prompt_records,
        min_retrieval_only_records=args.min_retrieval_only_records,
        max_model_error_count=args.max_model_error_count,
    )
    report = build_vision_model_pilot(
        visual_ink_layout_calibrator_path=args.visual_ink_layout_calibrator,
        figure_chart_understanding_path=args.figure_chart_understanding,
        image_recognition_audit_path=args.image_recognition_audit,
        visual_text_records_path=args.visual_text_records,
        output_dir=args.output_dir,
        vision_mode=args.vision_mode,
        vision_model=args.vision_model,
        ollama_url=args.ollama_url,
        ollama_endpoint=args.ollama_endpoint,
        ollama_timeout=args.ollama_timeout,
        max_pilot_pages=args.max_pilot_pages,
        include_pages=parse_include_pages(args.include_pages),
        progress=args.progress,
        thresholds=thresholds,
        write_quality=args.quality,
    )
    summary = report.get("summary", {})
    print("TRACE-Net vision model pilot v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    print(f" vision_mode: {report.get('vision_mode')}")
    print(f" vision_model_name: {report.get('vision_model_name')}")
    for key in (
        "vision_pilot_record_count",
        "selected_page_count",
        "prompt_record_count",
        "retrieval_only_record_count",
        "image_path_available_count",
        "model_completed_count",
        "model_error_count",
        "visual_answer_allowed_count",
        "unverified_visual_claim_count",
        "unsafe_vision_pilot_record_count",
        "source_truth_mutation_allowed_count",
    ):
        print(f" {key}: {summary.get(key, 0)}")
    print(f" report_path: {report.get('report_path')}")
    print(f" quality_path: {report.get('quality_path')}")
    return 0 if report.get("quality_status") == "PASS" else 1


def quality_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Vision Model Pilot v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-pilot-records", type=int, default=1)
    parser.add_argument("--min-selected-pages", type=int, default=1)
    parser.add_argument("--min-prompt-records", type=int, default=1)
    parser.add_argument("--min-retrieval-only-records", type=int, default=1)
    parser.add_argument("--max-model-error-count", type=int)
    parser.add_argument("--write-json", action="store_true")
    return parser


def quality_main(argv: Sequence[str] | None = None) -> int:
    parser = quality_arg_parser()
    args = parser.parse_args(argv)
    thresholds = QualityThresholds(
        require_page_count=args.require_page_count,
        min_pilot_records=args.min_pilot_records,
        min_selected_pages=args.min_selected_pages,
        min_prompt_records=args.min_prompt_records,
        min_retrieval_only_records=args.min_retrieval_only_records,
        max_model_error_count=args.max_model_error_count,
    )
    quality = check_vision_model_pilot_quality(
        report_path=args.report_path,
        thresholds=thresholds,
        write_json_quality=args.write_json,
    )
    summary = quality.get("summary", {})
    print("TRACE-Net vision model pilot v1 quality")
    print(f" Status: {quality.get('status')}")
    for key in (
        "vision_pilot_record_count",
        "selected_page_count",
        "prompt_record_count",
        "retrieval_only_record_count",
        "image_path_available_count",
        "model_completed_count",
        "model_error_count",
        "visual_answer_allowed_count",
        "unverified_visual_claim_count",
        "unsafe_vision_pilot_record_count",
        "source_truth_mutation_allowed_count",
    ):
        print(f" {key}: {summary.get(key, 0)}")
    return 0 if quality.get("status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
