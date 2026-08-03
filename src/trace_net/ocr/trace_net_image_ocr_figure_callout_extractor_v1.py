"""TRACE-Net image OCR figure/callout extractor v1.

Patch B3 module for the image/visual route. It reads Patch B LLaVA visual
summary records plus the OCR route scan pack and builds a source-traced label
map for visual pages. The goal is to let OCR read exact manual labels (FIGURE,
FIG., ITEM, CALLOUT, INDEX NO.) while LLaVA remains a visual observer only.

This module is artifact-only: it performs no database/vector/search writes, no
source-truth mutation, and never grants answer permission.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

MODULE_NAME = "trace_net_image_ocr_figure_callout_extractor_v1"
STATUS_BUILT = "TRACE_NET_IMAGE_OCR_FIGURE_CALLOUT_EXTRACTOR_BUILT"
DEFAULT_OUTPUT_DIR = "local_data/organization/trace_net/image_ocr_figure_callout_extractor_v1"

FIGURE_PATTERN = re.compile(r"\b(?:FIG(?:URE)?\.?|ILLUS(?:TRATION)?\.?)\s*[-:#]?\s*([A-Z0-9]+(?:[-–][A-Z0-9]+)?)\b", re.IGNORECASE)
FIGURE_TITLE_PATTERN = re.compile(r"\b(?:FIG(?:URE)?\.?)\s*[-:#]?\s*([A-Z0-9]+(?:[-–][A-Z0-9]+)?)([^\n\r]{0,160})", re.IGNORECASE)
ITEM_PATTERN = re.compile(r"\b(?:ITEM|CALLOUT|INDEX\s+NO\.?|KEY\s+NO\.?|REF\.?\s+NO\.?|FIG(?:URE)?\.?\s+ITEM)\s*[-:#]?\s*([0-9A-Z]{1,5})\b", re.IGNORECASE)
PART_PATTERN = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
SIMPLE_TOKEN_PATTERN = re.compile(r"^[A-Z0-9]{1,5}(?:[-–][A-Z0-9]{1,5})?$")
DIMENSION_PATTERN = re.compile(r"(?:/|\bIN(?:CH|CHES)?\b|\bFT\b|\bMM\b|\bCM\b|\bDEG\b|°)", re.IGNORECASE)
PROMPT_ECHO_PHRASES = (
    "TRACE-NET",
    "LOCAL VISUAL",
    "INSPECT ONLY",
    "RETURN STRUCTURED JSON",
    "SUPPLIED PAGE IMAGE",
    "DO NOT CLAIM PART IDENTITY",
)
PAGE_ID_KEYS = ("page_id", "trace_page_id", "source_page_id", "page_key", "id")
PAGE_NUMBER_KEYS = ("page_number", "page_num", "page", "source_page_number", "physical_page_number")
OCR_TEXT_KEYS = (
    "ocr_text",
    "text",
    "raw_text",
    "page_text",
    "content",
    "extracted_text",
    "ocr_preview",
    "text_preview",
    "preview",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True) + "\n")


def normalize_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def compact_text(value: Any, max_chars: int = 1000) -> str:
    text = re.sub(r"\s+", " ", normalize_string(value)).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def safe_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = normalize_string(value)
    match = re.search(r"\d+", text)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def iter_dicts(value: Any) -> Iterator[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from iter_dicts(child)
    elif isinstance(value, list):
        for item in value:
            yield from iter_dicts(item)


def lower_key_map(record: Mapping[str, Any]) -> Dict[str, Any]:
    return {str(k).lower(): v for k, v in record.items()}


def first_from_keys(lower: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in lower and lower[key] not in (None, ""):
            return lower[key]
    return None


def extract_page_id(record: Mapping[str, Any]) -> str:
    lower = lower_key_map(record)
    return normalize_string(first_from_keys(lower, PAGE_ID_KEYS))


def extract_page_number(record: Mapping[str, Any]) -> Optional[int]:
    lower = lower_key_map(record)
    page = safe_int(first_from_keys(lower, PAGE_NUMBER_KEYS))
    if page is not None:
        return page
    page_id = extract_page_id(record)
    match = re.search(r"p0*([0-9]{1,6})\b", page_id)
    return int(match.group(1)) if match else None


def looks_like_path_or_filename(text: str) -> bool:
    lower = text.lower()
    return any(lower.endswith(ext) for ext in (".tif", ".tiff", ".png", ".jpg", ".jpeg", ".json", ".zip")) or "/" in text or "\\" in text


def text_from_record(record: Mapping[str, Any]) -> str:
    lower = lower_key_map(record)
    values: List[str] = []
    for key in OCR_TEXT_KEYS:
        value = lower.get(key)
        if isinstance(value, str) and value.strip() and not looks_like_path_or_filename(value.strip()):
            values.append(value)
    for key, value in lower.items():
        if not isinstance(value, str) or not value.strip():
            continue
        key_l = str(key).lower()
        if looks_like_path_or_filename(value.strip()):
            continue
        if any(hint in key_l for hint in ("ocr", "text", "content", "preview", "caption")):
            values.append(value)
    return compact_text("\n".join(values), 6000)


def norm_token(value: Any) -> str:
    return normalize_string(value).upper().replace(" ", "").replace(".", "").replace(":", "").replace("#", "")


def is_prompt_echo(text: str) -> bool:
    upper = text.upper()
    return any(phrase in upper for phrase in PROMPT_ECHO_PHRASES)


def is_dimension_like(text: str) -> bool:
    return bool(DIMENSION_PATTERN.search(text or ""))


def is_simple_candidate_token(text: str) -> bool:
    token = normalize_string(text).strip().strip("[]'\"")
    if not token or len(token) > 12:
        return False
    if is_prompt_echo(token) or is_dimension_like(token):
        return False
    return bool(SIMPLE_TOKEN_PATTERN.match(token.upper()))


def unique_norm_values(values: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = normalize_string(value).strip().strip("[]'\"")
        if not text or is_prompt_echo(text):
            continue
        if not is_simple_candidate_token(text):
            continue
        key = norm_token(text)
        if key and key not in seen:
            seen.add(key)
            out.append(text.upper() if text.isalnum() else text)
    return out[:80]


def flatten_text_candidates(value: Any) -> List[str]:
    out: List[str] = []
    if isinstance(value, list):
        for item in value:
            out.extend(flatten_text_candidates(item))
    elif isinstance(value, Mapping):
        for key in ("text", "value", "candidate", "description", "label", "number", "figure_id"):
            if key in value:
                out.extend(flatten_text_candidates(value[key]))
    else:
        text = normalize_string(value)
        if text and not is_prompt_echo(text):
            out.append(text)
    return out[:100]


def extract_figures_from_text(text: str) -> List[str]:
    return unique_norm_values(match.group(1).upper() for match in FIGURE_PATTERN.finditer(text or ""))


def extract_callouts_from_text(text: str) -> List[str]:
    return unique_norm_values(match.group(1).upper() for match in ITEM_PATTERN.finditer(text or ""))


def extract_titles_from_text(text: str) -> List[str]:
    titles: List[str] = []
    seen: set[str] = set()
    for match in FIGURE_TITLE_PATTERN.finditer(text or ""):
        fig = match.group(1).upper()
        rest = compact_text(match.group(2) or "", 140).strip(" :-–—\t")
        title = f"FIGURE {fig}" + (f" {rest}" if rest else "")
        key = title.upper()
        if key not in seen:
            seen.add(key)
            titles.append(title)
    return titles[:30]


def load_visual_records(path_text: str) -> List[Dict[str, Any]]:
    if not path_text:
        return []
    path = Path(path_text)
    if not path.exists():
        return []
    payload = read_json(path)
    if isinstance(payload, Mapping):
        records = payload.get("records") or payload.get("visual_summary_records") or payload.get("summaries") or []
    elif isinstance(payload, list):
        records = payload
    else:
        records = []
    return [dict(r) for r in records if isinstance(r, Mapping)]


def load_ocr_page_text_map(path_text: str) -> Dict[str, Dict[str, Any]]:
    """Return best OCR text by page id and page number keys."""
    if not path_text:
        return {}
    path = Path(path_text)
    if not path.exists():
        return {}
    payload = read_json(path)
    best: Dict[str, Dict[str, Any]] = {}
    for record in iter_dicts(payload):
        page_id = extract_page_id(record)
        page_number = extract_page_number(record)
        text = text_from_record(record)
        if not text:
            continue
        keys = []
        if page_id:
            keys.append(f"id:{page_id}")
        if page_number is not None:
            keys.append(f"num:{page_number}")
        for key in keys:
            current = best.get(key)
            if current is None or len(text) > len(current.get("text", "")):
                best[key] = {"page_id": page_id, "page_number": page_number, "text": text}
    return best


def page_text_for(record: Mapping[str, Any], page_text_map: Mapping[str, Mapping[str, Any]]) -> str:
    page_id = extract_page_id(record)
    page_number = extract_page_number(record)
    for key in (f"id:{page_id}" if page_id else "", f"num:{page_number}" if page_number is not None else ""):
        if key and key in page_text_map:
            return normalize_string(page_text_map[key].get("text"))
    return ""


def build_extractor_records(visual_records: Sequence[Mapping[str, Any]], page_text_map: Mapping[str, Mapping[str, Any]]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for idx, visual in enumerate(visual_records, start=1):
        page_id = extract_page_id(visual)
        page_number = extract_page_number(visual)
        source_member = normalize_string(visual.get("source_member") or visual.get("tiff_member") or visual.get("source_image_member"))
        ocr_text = page_text_for(visual, page_text_map)
        llava_text = "\n".join(flatten_text_candidates(visual.get("visible_text_candidates")) + flatten_text_candidates(visual.get("visual_summary")))
        combined_text = "\n".join(t for t in (ocr_text, llava_text) if t)

        ocr_figures = extract_figures_from_text(ocr_text)
        llava_figures = extract_figures_from_text(llava_text)
        ocr_callouts = extract_callouts_from_text(ocr_text)
        llava_callouts = extract_callouts_from_text(llava_text)
        title_candidates = extract_titles_from_text(ocr_text) or extract_titles_from_text(combined_text)
        visible_part_numbers = unique_norm_values(PART_PATTERN.findall(combined_text))

        label_confidence = "NONE"
        if ocr_figures and ocr_callouts:
            label_confidence = "HIGH"
        elif ocr_figures or ocr_callouts:
            label_confidence = "MEDIUM"
        elif llava_figures or llava_callouts:
            label_confidence = "LOW"

        source_trace_ready = bool(page_id or page_number or source_member)
        records.append({
            "extractor_record_id": f"image_ocr_figure_callout_{idx:05d}",
            "page_id": page_id,
            "page_number": page_number,
            "source_member": source_member,
            "ocr_figure_candidates": ocr_figures,
            "ocr_callout_candidates": ocr_callouts,
            "llava_figure_candidates": llava_figures,
            "llava_callout_candidates": llava_callouts,
            "figure_candidates": unique_norm_values(list(ocr_figures) + list(llava_figures)),
            "callout_candidates": unique_norm_values(list(ocr_callouts) + list(llava_callouts)),
            "title_candidates": title_candidates,
            "visible_part_number_candidates": visible_part_numbers,
            "ocr_preview": compact_text(ocr_text, 900),
            "llava_text_preview": compact_text(llava_text, 500),
            "ocr_label_confidence": label_confidence,
            "ocr_text_available": bool(ocr_text),
            "source_trace_ready": source_trace_ready,
            "citation_ready": source_trace_ready,
            "requires_human_review": label_confidence in {"NONE", "LOW"},
            "unsafe": False,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "opensearch_upload_attempt": False,
            "write_attempt_count": 0,
        })
    return records


def bool_count(records: Sequence[Mapping[str, Any]], key: str) -> int:
    return sum(1 for r in records if bool(r.get(key)))


def evaluate_quality(records: Sequence[Mapping[str, Any]], args: argparse.Namespace) -> Tuple[str, List[Dict[str, Any]]]:
    summary = {
        "extractor_record_count": len(records),
        "ocr_text_available_count": bool_count(records, "ocr_text_available"),
        "figure_candidate_record_count": sum(1 for r in records if r.get("figure_candidates")),
        "callout_candidate_record_count": sum(1 for r in records if r.get("callout_candidates")),
        "source_trace_ready_count": bool_count(records, "source_trace_ready"),
        "unsafe_record_count": bool_count(records, "unsafe"),
        "answer_permission_count": bool_count(records, "answer_permission"),
        "source_truth_mutation_allowed_count": bool_count(records, "source_truth_mutation_allowed"),
        "write_attempt_count": sum(int(r.get("write_attempt_count") or 0) for r in records),
    }
    checks: List[Dict[str, Any]] = []

    def add(name: str, passed: bool, observed: Any, expected: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "observed": observed, "expected": expected})

    add("min_extractor_records", summary["extractor_record_count"] >= args.min_extractor_records, summary["extractor_record_count"], f">= {args.min_extractor_records}")
    add("min_ocr_text_available", summary["ocr_text_available_count"] >= args.min_ocr_text_available, summary["ocr_text_available_count"], f">= {args.min_ocr_text_available}")
    add("min_figure_candidate_records", summary["figure_candidate_record_count"] >= args.min_figure_candidate_records, summary["figure_candidate_record_count"], f">= {args.min_figure_candidate_records}")
    add("min_source_trace_ready", summary["source_trace_ready_count"] >= args.min_source_trace_ready, summary["source_trace_ready_count"], f">= {args.min_source_trace_ready}")
    add("max_unsafe", summary["unsafe_record_count"] <= args.max_unsafe, summary["unsafe_record_count"], f"<= {args.max_unsafe}")
    add("max_answer_permission", summary["answer_permission_count"] <= args.max_answer_permission, summary["answer_permission_count"], f"<= {args.max_answer_permission}")
    add("max_source_truth_mutation_allowed", summary["source_truth_mutation_allowed_count"] <= args.max_source_truth_mutation_allowed, summary["source_truth_mutation_allowed_count"], f"<= {args.max_source_truth_mutation_allowed}")
    add("max_write_attempts", summary["write_attempt_count"] <= args.max_write_attempts, summary["write_attempt_count"], f"<= {args.max_write_attempts}")
    return ("PASS" if all(c["passed"] for c in checks) else "FAIL"), checks


def write_records_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "extractor_record_id", "page_id", "page_number", "source_member", "figure_candidates", "callout_candidates", "title_candidates", "ocr_label_confidence", "ocr_text_available", "source_trace_ready", "answer_permission", "source_truth_mutation_allowed",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({field: json.dumps(record.get(field)) if isinstance(record.get(field), list) else record.get(field, "") for field in fields})


def build_extractor(args: argparse.Namespace) -> Dict[str, Any]:
    visual_records = load_visual_records(args.llava_visual_summary_batch)
    page_text_map = load_ocr_page_text_map(args.ocr_route_scan_pack)
    records = build_extractor_records(visual_records, page_text_map)
    quality_status, checks = evaluate_quality(records, args)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = output_dir / f"{MODULE_NAME}.json"
    qc_path = output_dir / f"{MODULE_NAME}_quality_check.json"
    jsonl_path = output_dir / f"{MODULE_NAME}_records.jsonl"
    csv_path = output_dir / f"{MODULE_NAME}_records.csv"
    readme_path = output_dir / "README_trace_net_image_ocr_figure_callout_extractor_v1.md"

    summary = {
        "visual_summary_record_count": len(visual_records),
        "ocr_page_text_record_count": len(page_text_map),
        "extractor_record_count": len(records),
        "ocr_text_available_count": bool_count(records, "ocr_text_available"),
        "figure_candidate_record_count": sum(1 for r in records if r.get("figure_candidates")),
        "callout_candidate_record_count": sum(1 for r in records if r.get("callout_candidates")),
        "ocr_medium_or_high_label_record_count": sum(1 for r in records if r.get("ocr_label_confidence") in {"MEDIUM", "HIGH"}),
        "source_trace_ready_count": bool_count(records, "source_trace_ready"),
        "citation_ready_count": bool_count(records, "citation_ready"),
        "requires_human_review_count": bool_count(records, "requires_human_review"),
        "unsafe_record_count": bool_count(records, "unsafe"),
        "answer_permission_count": bool_count(records, "answer_permission"),
        "source_truth_mutation_allowed_count": bool_count(records, "source_truth_mutation_allowed"),
        "postgres_write_attempt_count": bool_count(records, "postgres_write_attempt"),
        "qdrant_write_attempt_count": bool_count(records, "qdrant_write_attempt"),
        "opensearch_write_attempt_count": bool_count(records, "opensearch_write_attempt"),
        "opensearch_upload_attempt_count": bool_count(records, "opensearch_upload_attempt"),
        "write_attempt_count": sum(int(r.get("write_attempt_count") or 0) for r in records),
        "ready_for_visual_linker_v2": quality_status == "PASS",
    }
    paths = {
        "extractor": artifact_path.as_posix(),
        "quality_check": qc_path.as_posix(),
        "records_jsonl": jsonl_path.as_posix(),
        "records_csv": csv_path.as_posix(),
        "readme": readme_path.as_posix(),
    }
    payload = {
        "module_name": MODULE_NAME,
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "created_at_utc": utc_now(),
        "inputs": {
            "llava_visual_summary_batch": args.llava_visual_summary_batch,
            "ocr_route_scan_pack": args.ocr_route_scan_pack,
        },
        "authority_model": {
            "ocr_role": "read exact visible manual labels such as FIGURE and ITEM",
            "llava_role": "visual observation only",
            "proof_role": "downstream linker must still verify part identity with trusted table/OCR/figure-item evidence",
        },
        "safety_contract": {
            "postgres_writes": False,
            "qdrant_writes": False,
            "opensearch_writes": False,
            "opensearch_uploads": False,
            "source_truth_mutation": False,
            "answer_permission": False,
        },
        "summary": summary,
        "quality_checks": checks,
        "artifact_paths": paths,
        "records": records,
    }
    qc = {
        "module_name": MODULE_NAME,
        "status": f"{STATUS_BUILT}_QUALITY_CHECKED",
        "quality_status": quality_status,
        "created_at_utc": payload["created_at_utc"],
        "summary": summary,
        "checks": checks,
        "artifact_paths": paths,
    }
    write_json(artifact_path, payload)
    write_json(qc_path, qc)
    write_jsonl(jsonl_path, records)
    write_records_csv(csv_path, records)
    readme_path.write_text(
        "# TRACE-Net Image OCR Figure/Callout Extractor v1\n\n"
        "Reads exact figure/callout labels from OCR for image-route pages. OCR labels are still not final answer proof; they are used by the visual linker to connect LLaVA observations to trusted table/figure evidence.\n\n"
        f"Artifact: `{artifact_path.as_posix()}`\n",
        encoding="utf-8",
    )
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build TRACE-Net image OCR figure/callout extractor v1.")
    p.add_argument("--llava-visual-summary-batch", required=True)
    p.add_argument("--ocr-route-scan-pack", required=True)
    p.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--min-extractor-records", type=int, default=1)
    p.add_argument("--min-ocr-text-available", type=int, default=1)
    p.add_argument("--min-figure-candidate-records", type=int, default=0)
    p.add_argument("--min-source-trace-ready", type=int, default=1)
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-answer-permission", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        artifact = build_extractor(args)
    except Exception as exc:
        print(f"ERROR {MODULE_NAME}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    summary = artifact.get("summary", {})
    print(f"status={artifact.get('status')}")
    print(f"quality_status={artifact.get('quality_status')}")
    for key in (
        "visual_summary_record_count",
        "ocr_page_text_record_count",
        "extractor_record_count",
        "ocr_text_available_count",
        "figure_candidate_record_count",
        "callout_candidate_record_count",
        "ocr_medium_or_high_label_record_count",
        "source_trace_ready_count",
        "ready_for_visual_linker_v2",
        "unsafe_record_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
        "write_attempt_count",
    ):
        print(f"{key}={summary.get(key)}")
    print(f"extractor={artifact.get('artifact_paths', {}).get('extractor')}")
    return 0 if artifact.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
