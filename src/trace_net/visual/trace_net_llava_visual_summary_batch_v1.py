"""TRACE-Net LLaVA visual summary batch v1.

Patch B module for the image/visual route. It consumes the Patch A LLaVA job
manifest, optionally calls local Ollama/LLaVA for each page image, forces a
structured visual-observation JSON card, and writes artifact-only outputs. LLaVA
observations are explicitly guidance-only and never grant answer permission.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, MutableMapping, Optional, Sequence, Tuple

MODULE_NAME = "trace_net_llava_visual_summary_batch_v1"
STATUS_BUILT = "TRACE_NET_LLAVA_VISUAL_SUMMARY_BATCH_BUILT"
DEFAULT_OUTPUT_DIR = "local_data/organization/trace_net/llava_visual_summary_batch_v1"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "llava:13b"

FIGURE_PATTERN = re.compile(r"\b(?:FIG(?:URE)?\.?|ILLUS(?:TRATION)?\.?)\s*[-:#]?\s*([A-Z0-9]+(?:[-–][A-Z0-9]+)?)\b", re.IGNORECASE)
CALLOUT_PATTERN = re.compile(r"\b(?:ITEM|CALLOUT|INDEX\s+NO\.?|KEY\s+NO\.?|REF\.?\s+NO\.?)\s*[-:#]?\s*([0-9A-Z]+)\b", re.IGNORECASE)
JSON_OBJECT_PATTERN = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True)
class SourceImage:
    member: str
    exists: bool
    bytes_payload: bytes
    media_type: str
    note: str


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


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
            if isinstance(value, Mapping):
                records.append(dict(value))
    return records


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


def normalize_candidate_list(value: Any, max_items: int = 50) -> List[str]:
    items: List[str] = []
    seen: set[str] = set()

    def add(item: Any) -> None:
        text = normalize_string(item)
        if not text:
            return
        if len(text) > 200:
            text = text[:200].rstrip()
        key = text.upper()
        if key not in seen:
            seen.add(key)
            items.append(text)

    if isinstance(value, list):
        for item in value:
            if isinstance(item, Mapping):
                add(item.get("value") or item.get("candidate") or item.get("text") or item.get("number") or item)
            else:
                add(item)
    elif isinstance(value, Mapping):
        for item in value.values():
            add(item)
    else:
        add(value)
    return items[:max_items]


def compact_preview(text: str, max_chars: int = 600) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "…"


def safe_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = normalize_string(value)
    if not text:
        return None
    match = re.search(r"\d+", text)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def image_member_candidates(job: Mapping[str, Any]) -> List[str]:
    values = [
        job.get("source_member"),
        job.get("tiff_member"),
        ((job.get("source_trace_fields") or {}) if isinstance(job.get("source_trace_fields"), Mapping) else {}).get("source_member"),
    ]
    out: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = normalize_string(value).replace("\\", "/")
        if not text:
            continue
        basename = Path(text).name
        for candidate in (text, basename):
            if candidate and candidate not in seen:
                seen.add(candidate)
                out.append(candidate)
    page_number = safe_int(job.get("page_number"))
    if page_number is not None:
        for ext in (".tif", ".tiff", ".png", ".jpg", ".jpeg"):
            candidate = f"{page_number:08d}{ext}"
            if candidate not in seen:
                seen.add(candidate)
                out.append(candidate)
    return out


def guess_media_type(member: str) -> str:
    ext = Path(member).suffix.lower()
    if ext in {".png"}:
        return "image/png"
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext in {".tif", ".tiff"}:
        return "image/tiff"
    return "application/octet-stream"


def maybe_convert_to_png(member: str, payload: bytes) -> Tuple[bytes, str, str]:
    """Convert TIFF-ish payloads to PNG when Pillow exists; otherwise return raw bytes."""
    ext = Path(member).suffix.lower()
    if ext not in {".tif", ".tiff"}:
        return payload, guess_media_type(member), "original_image_bytes"
    try:
        from PIL import Image  # type: ignore
        import io

        with Image.open(io.BytesIO(payload)) as img:
            if getattr(img, "is_animated", False):
                img.seek(0)
            if img.mode not in {"RGB", "RGBA", "L"}:
                img = img.convert("RGB")
            out = io.BytesIO()
            img.save(out, format="PNG")
            return out.getvalue(), "image/png", "converted_tiff_to_png_with_pillow"
    except Exception as exc:  # pragma: no cover - depends on local Pillow/TIFF support
        return payload, guess_media_type(member), f"pillow_tiff_conversion_unavailable:{type(exc).__name__}"


def load_source_image(job: Mapping[str, Any], source_package: Optional[str]) -> SourceImage:
    if not source_package:
        return SourceImage(member="", exists=False, bytes_payload=b"", media_type="", note="source_package_not_provided")
    source_path = Path(source_package)
    candidates = image_member_candidates(job)
    if not source_path.exists():
        return SourceImage(member="", exists=False, bytes_payload=b"", media_type="", note=f"source_package_missing:{source_path}")

    if source_path.is_dir():
        for candidate in candidates:
            direct = source_path / candidate
            if direct.exists() and direct.is_file():
                payload, media_type, note = maybe_convert_to_png(candidate, direct.read_bytes())
                return SourceImage(member=candidate, exists=True, bytes_payload=payload, media_type=media_type, note=note)
            matches = [p for p in source_path.rglob(Path(candidate).name) if p.is_file()]
            if matches:
                payload, media_type, note = maybe_convert_to_png(matches[0].name, matches[0].read_bytes())
                return SourceImage(member=str(matches[0].relative_to(source_path)).replace("\\", "/"), exists=True, bytes_payload=payload, media_type=media_type, note=note)
        return SourceImage(member="", exists=False, bytes_payload=b"", media_type="", note="image_member_not_found_in_directory")

    if source_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(source_path, "r") as zf:
            names = zf.namelist()
            by_basename = {Path(name).name: name for name in names}
            for candidate in candidates:
                selected = candidate if candidate in names else by_basename.get(Path(candidate).name)
                if selected:
                    raw = zf.read(selected)
                    payload, media_type, note = maybe_convert_to_png(selected, raw)
                    return SourceImage(member=selected, exists=True, bytes_payload=payload, media_type=media_type, note=note)
        return SourceImage(member="", exists=False, bytes_payload=b"", media_type="", note="image_member_not_found_in_zip")

    return SourceImage(member="", exists=False, bytes_payload=b"", media_type="", note="unsupported_source_package_type")


def strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    return cleaned


def parse_json_object(text: str) -> Tuple[Dict[str, Any], str]:
    cleaned = strip_code_fences(text)
    try:
        value = json.loads(cleaned)
        if isinstance(value, Mapping):
            return dict(value), "json_direct"
    except json.JSONDecodeError:
        pass
    match = JSON_OBJECT_PATTERN.search(cleaned)
    if match:
        try:
            value = json.loads(match.group(0))
            if isinstance(value, Mapping):
                return dict(value), "json_extracted_from_text"
        except json.JSONDecodeError:
            pass
    return {}, "json_parse_failed"


def infer_candidates_from_text(text: str) -> Tuple[List[str], List[str], List[str]]:
    figures: List[str] = []
    callouts: List[str] = []
    visible: List[str] = []
    seen_fig: set[str] = set()
    seen_call: set[str] = set()
    for match in FIGURE_PATTERN.finditer(text or ""):
        value = match.group(1).upper()
        if value not in seen_fig:
            seen_fig.add(value)
            figures.append(value)
            visible.append(match.group(0).strip())
    for match in CALLOUT_PATTERN.finditer(text or ""):
        value = match.group(1).upper()
        if value not in seen_call:
            seen_call.add(value)
            callouts.append(value)
            visible.append(match.group(0).strip())
    return figures[:30], callouts[:60], visible[:80]


def build_dry_run_visual_payload(job: Mapping[str, Any]) -> Dict[str, Any]:
    ocr_preview = normalize_string(job.get("ocr_excerpt_preview"))
    route_figures = [c.get("value") for c in job.get("figure_candidates") or [] if isinstance(c, Mapping) and c.get("candidate_type") == "figure"]
    route_callouts = [c.get("value") for c in job.get("figure_candidates") or [] if isinstance(c, Mapping) and c.get("candidate_type") in {"item", "callout"}]
    inferred_figures, inferred_callouts, visible = infer_candidates_from_text(ocr_preview)
    figures = normalize_candidate_list(route_figures + inferred_figures)
    callouts = normalize_candidate_list(route_callouts + inferred_callouts)
    visible_text = normalize_candidate_list(visible or ([ocr_preview[:120]] if ocr_preview else []))
    return {
        "page_id": job.get("page_id"),
        "page_number": safe_int(job.get("page_number")),
        "figure_candidates": figures,
        "callout_candidates": callouts,
        "visible_text_candidates": visible_text,
        "diagram_type": "image_or_diagram_page",
        "visual_summary": compact_preview(f"Dry-run structured visual card for image-route page {job.get('page_number') or job.get('page_id')}. OCR preview was used only to seed figure/callout candidates.", 500),
        "uncertainties": ["dry_run_mode_no_model_image_inspection"],
        "visual_confidence": "low",
    }


def call_ollama_llava(job: Mapping[str, Any], source_image: SourceImage, base_url: str, model: str, timeout: int) -> Tuple[str, Dict[str, Any]]:
    if not source_image.exists or not source_image.bytes_payload:
        raise FileNotFoundError(source_image.note)
    prompt = normalize_string(job.get("recommended_llava_prompt")) or (
        "Return structured JSON only with page_id, page_number, figure_candidates, callout_candidates, "
        "visible_text_candidates, diagram_type, visual_summary, uncertainties, visual_confidence. "
        "Do not claim part identity as proof."
    )
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [base64.b64encode(source_image.bytes_payload).decode("ascii")],
        "stream": False,
        "options": {"temperature": 0},
    }
    url = base_url.rstrip("/") + "/api/generate"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec - localhost user-supplied endpoint for local model
        body = resp.read().decode("utf-8")
    parsed = json.loads(body)
    return normalize_string(parsed.get("response")), parsed


def canonicalize_visual_payload(raw_payload: Mapping[str, Any], job: Mapping[str, Any], parse_status: str) -> Dict[str, Any]:
    ocr_figures, ocr_callouts, ocr_visible = infer_candidates_from_text(normalize_string(job.get("ocr_excerpt_preview")))
    page_id = normalize_string(raw_payload.get("page_id")) or normalize_string(job.get("page_id"))
    page_number = safe_int(raw_payload.get("page_number"))
    if page_number is None:
        page_number = safe_int(job.get("page_number"))

    figures = normalize_candidate_list(raw_payload.get("figure_candidates")) or ocr_figures
    callouts = normalize_candidate_list(raw_payload.get("callout_candidates")) or ocr_callouts
    visible = normalize_candidate_list(raw_payload.get("visible_text_candidates")) or ocr_visible
    uncertainties = normalize_candidate_list(raw_payload.get("uncertainties"), max_items=25)
    confidence = normalize_string(raw_payload.get("visual_confidence")).lower()
    if confidence not in {"high", "medium", "low", "unknown"}:
        confidence = "unknown" if parse_status == "json_parse_failed" else "medium"
    summary = compact_preview(normalize_string(raw_payload.get("visual_summary")), 1500)
    if not summary:
        summary = "Structured visual observation card created, but no visual_summary text was returned."
        uncertainties.append("missing_visual_summary_text")
    diagram_type = normalize_string(raw_payload.get("diagram_type")) or "unknown"

    return {
        "page_id": page_id,
        "page_number": page_number,
        "figure_candidates": figures,
        "callout_candidates": callouts,
        "visible_text_candidates": visible,
        "diagram_type": diagram_type,
        "visual_summary": summary,
        "uncertainties": uncertainties[:25],
        "visual_confidence": confidence,
    }


def bool_count(records: Iterable[Mapping[str, Any]], key: str) -> int:
    return sum(1 for record in records if bool(record.get(key)))


def write_records_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "record_id",
        "page_id",
        "page_number",
        "source_member",
        "llava_mode",
        "llava_summary_status",
        "structured_json_ready",
        "figure_candidate_count",
        "callout_candidate_count",
        "visible_text_candidate_count",
        "visual_confidence",
        "source_trace_ready",
        "answer_permission",
        "source_truth_mutation_allowed",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in fields})


def evaluate_quality(records: Sequence[Mapping[str, Any]], args: argparse.Namespace) -> Tuple[str, List[Dict[str, Any]]]:
    checks: List[Dict[str, Any]] = []

    def add(name: str, passed: bool, observed: Any, expected: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "observed": observed, "expected": expected})

    summary_count = len(records)
    structured_count = bool_count(records, "structured_json_ready")
    visual_summary_count = sum(1 for r in records if bool(normalize_string(r.get("visual_summary"))))
    ready_for_visual_linking = summary_count >= args.min_llava_summaries and structured_count >= args.min_structured_json
    add("llava_summary_count", summary_count >= args.min_llava_summaries, summary_count, f">= {args.min_llava_summaries}")
    add("structured_json_count", structured_count >= args.min_structured_json, structured_count, f">= {args.min_structured_json}")
    add("visual_summary_text_count", visual_summary_count >= args.min_visual_summary_text, visual_summary_count, f">= {args.min_visual_summary_text}")
    add("source_trace_ready_count", bool_count(records, "source_trace_ready") >= args.min_source_trace_ready, bool_count(records, "source_trace_ready"), f">= {args.min_source_trace_ready}")
    add("unsafe_record_count", bool_count(records, "unsafe") <= args.max_unsafe, bool_count(records, "unsafe"), f"<= {args.max_unsafe}")
    add("answer_permission_count", bool_count(records, "answer_permission") <= args.max_answer_permission, bool_count(records, "answer_permission"), f"<= {args.max_answer_permission}")
    add("source_truth_mutation_allowed_count", bool_count(records, "source_truth_mutation_allowed") <= args.max_source_truth_mutation_allowed, bool_count(records, "source_truth_mutation_allowed"), f"<= {args.max_source_truth_mutation_allowed}")
    add("write_attempt_count", sum(int(r.get("write_attempt_count") or 0) for r in records) <= args.max_write_attempts, sum(int(r.get("write_attempt_count") or 0) for r in records), f"<= {args.max_write_attempts}")
    add("ready_for_visual_linking", ready_for_visual_linking, ready_for_visual_linking, "true")
    return ("PASS" if all(c["passed"] for c in checks) else "FAIL"), checks


def build_batch(args: argparse.Namespace) -> Dict[str, Any]:
    jobs = read_jsonl(Path(args.jobs_jsonl))
    if args.max_jobs and args.max_jobs > 0:
        jobs = jobs[: args.max_jobs]
    output_dir = Path(args.output_dir)
    summary_dir = output_dir / "summaries"
    records: List[Dict[str, Any]] = []
    raw_model_responses: List[Dict[str, Any]] = []

    for idx, job in enumerate(jobs, start=1):
        page_id = normalize_string(job.get("page_id")) or f"llava_page_{idx:04d}"
        source_image = load_source_image(job, args.source_package_metadata_zip)
        model_text = ""
        model_payload: Dict[str, Any] = {}
        parse_status = "not_run"
        llava_summary_status = "created"
        error_text = ""
        llava_mode = args.llm_mode

        if args.llm_mode == "dry_run":
            raw_visual = build_dry_run_visual_payload(job)
            parse_status = "dry_run_structured_json"
        elif args.llm_mode == "ollama":
            try:
                model_text, model_payload = call_ollama_llava(job, source_image, args.ollama_base_url, args.ollama_model, args.request_timeout)
                raw_visual, parse_status = parse_json_object(model_text)
                if not raw_visual:
                    llava_summary_status = "parse_failed"
            except Exception as exc:  # pragma: no cover - depends on local Ollama runtime
                raw_visual = build_dry_run_visual_payload(job) if args.fallback_to_dry_run else {}
                parse_status = "ollama_call_failed_fallback" if args.fallback_to_dry_run else "ollama_call_failed"
                llava_summary_status = "fallback_created" if args.fallback_to_dry_run else "failed"
                error_text = f"{type(exc).__name__}: {exc}"
        else:
            raise ValueError(f"Unsupported llm mode: {args.llm_mode}")

        visual_payload = canonicalize_visual_payload(raw_visual, job, parse_status)
        output_target = summary_dir / f"{page_id}_llava_visual_summary_v1.json"
        record = {
            "record_id": f"llava_visual_summary_{idx:04d}",
            "job_id": job.get("job_id") or f"llava_visual_summary_job_{idx:04d}",
            "page_id": visual_payload["page_id"],
            "page_number": visual_payload["page_number"],
            "source_member": source_image.member or normalize_string(job.get("source_member")),
            "source_image_exists": source_image.exists,
            "source_image_note": source_image.note,
            "source_image_media_type": source_image.media_type,
            "route_label": job.get("route_label"),
            "llava_mode": llava_mode,
            "llava_model": args.ollama_model if args.llm_mode == "ollama" else "dry_run_fixture",
            "llava_summary_status": llava_summary_status,
            "structured_json_ready": bool(visual_payload.get("visual_summary")) and llava_summary_status not in {"failed", "parse_failed"},
            "parse_status": parse_status,
            "figure_candidates": visual_payload["figure_candidates"],
            "callout_candidates": visual_payload["callout_candidates"],
            "visible_text_candidates": visual_payload["visible_text_candidates"],
            "diagram_type": visual_payload["diagram_type"],
            "visual_summary": visual_payload["visual_summary"],
            "uncertainties": visual_payload["uncertainties"],
            "visual_confidence": visual_payload["visual_confidence"],
            "figure_candidate_count": len(visual_payload["figure_candidates"]),
            "callout_candidate_count": len(visual_payload["callout_candidates"]),
            "visible_text_candidate_count": len(visual_payload["visible_text_candidates"]),
            "source_trace_ready": bool(job.get("source_trace_ready")) and bool(visual_payload["page_id"]),
            "source_trace_fields": job.get("source_trace_fields") or {},
            "llava_output_path": str(output_target.as_posix()),
            "unsafe": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "opensearch_upload_attempt": False,
            "write_attempt_count": 0,
            "authority_note": "LLaVA sees/describes visual content only; OCR/table/figure-item evidence must prove final part facts.",
            "error_text": error_text,
        }
        write_json(output_target, record)
        records.append(record)
        if args.keep_raw_model_responses:
            raw_model_responses.append({
                "record_id": record["record_id"],
                "page_id": record["page_id"],
                "parse_status": parse_status,
                "model_text_preview": compact_preview(model_text, 1500),
                "model_payload_keys": sorted(model_payload.keys()),
            })

    quality_status, checks = evaluate_quality(records, args)
    output_dir.mkdir(parents=True, exist_ok=True)
    batch_path = output_dir / f"{MODULE_NAME}.json"
    qc_path = output_dir / f"{MODULE_NAME}_quality_check.json"
    jsonl_path = output_dir / f"{MODULE_NAME}_summaries.jsonl"
    csv_path = output_dir / f"{MODULE_NAME}_records.csv"
    raw_path = output_dir / f"{MODULE_NAME}_raw_model_responses.jsonl"
    readme_path = output_dir / "README_trace_net_llava_visual_summary_batch_v1.md"

    summary = {
        "llava_summary_count": len(records),
        "structured_json_count": bool_count(records, "structured_json_ready"),
        "source_trace_ready_count": bool_count(records, "source_trace_ready"),
        "figure_candidate_count": sum(int(r.get("figure_candidate_count") or 0) for r in records),
        "figure_candidate_record_count": sum(1 for r in records if int(r.get("figure_candidate_count") or 0) > 0),
        "callout_candidate_count": sum(int(r.get("callout_candidate_count") or 0) for r in records),
        "callout_candidate_record_count": sum(1 for r in records if int(r.get("callout_candidate_count") or 0) > 0),
        "visible_text_candidate_count": sum(int(r.get("visible_text_candidate_count") or 0) for r in records),
        "failed_llava_summary_count": sum(1 for r in records if r.get("llava_summary_status") == "failed"),
        "parse_failed_count": sum(1 for r in records if r.get("parse_status") == "json_parse_failed"),
        "dry_run_summary_count": sum(1 for r in records if r.get("llava_mode") == "dry_run"),
        "ollama_summary_count": sum(1 for r in records if r.get("llava_mode") == "ollama"),
        "unsafe_record_count": bool_count(records, "unsafe"),
        "answer_permission_count": bool_count(records, "answer_permission"),
        "source_truth_mutation_allowed_count": bool_count(records, "source_truth_mutation_allowed"),
        "postgres_write_attempt_count": bool_count(records, "postgres_write_attempt"),
        "qdrant_write_attempt_count": bool_count(records, "qdrant_write_attempt"),
        "opensearch_write_attempt_count": bool_count(records, "opensearch_write_attempt"),
        "opensearch_upload_attempt_count": bool_count(records, "opensearch_upload_attempt"),
        "write_attempt_count": sum(int(r.get("write_attempt_count") or 0) for r in records),
        "ready_for_visual_linking": quality_status == "PASS",
    }

    artifact_paths = {
        "batch": str(batch_path.as_posix()),
        "quality_check": str(qc_path.as_posix()),
        "summaries_jsonl": str(jsonl_path.as_posix()),
        "records_csv": str(csv_path.as_posix()),
        "summary_dir": str(summary_dir.as_posix()),
        "raw_model_responses_jsonl": str(raw_path.as_posix()) if args.keep_raw_model_responses else "",
        "readme": str(readme_path.as_posix()),
    }
    batch = {
        "module_name": MODULE_NAME,
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "created_at_utc": utc_now(),
        "inputs": {
            "jobs_jsonl": args.jobs_jsonl,
            "source_package_metadata_zip": args.source_package_metadata_zip,
            "llm_mode": args.llm_mode,
            "ollama_base_url": args.ollama_base_url if args.llm_mode == "ollama" else "",
            "ollama_model": args.ollama_model if args.llm_mode == "ollama" else "",
        },
        "authority_model": {
            "llava_role": "visual observation and page understanding guidance only",
            "proof_role": "OCR/table/figure-item/source-truth evidence must prove part identity and final factual claims",
            "linking_rule": "visual candidates are promoted only when matched to trusted OCR/table/figure-item evidence",
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
        "artifact_paths": artifact_paths,
        "records": records,
    }
    qc = {
        "module_name": MODULE_NAME,
        "status": f"{STATUS_BUILT}_QUALITY_CHECKED",
        "quality_status": quality_status,
        "created_at_utc": batch["created_at_utc"],
        "summary": summary,
        "checks": checks,
        "artifact_paths": artifact_paths,
    }
    write_json(batch_path, batch)
    write_json(qc_path, qc)
    write_jsonl(jsonl_path, records)
    write_records_csv(csv_path, records)
    if args.keep_raw_model_responses:
        write_jsonl(raw_path, raw_model_responses)
    readme_path.write_text(
        "# TRACE-Net LLaVA Visual Summary Batch v1\n\n"
        "Consumes Patch A image-route LLaVA jobs and writes structured visual observation cards. "
        "LLaVA output is guidance only; OCR/table/figure-item evidence proves final claims.\n\n"
        f"Batch: `{batch_path.as_posix()}`\n\n"
        f"Summaries JSONL: `{jsonl_path.as_posix()}`\n",
        encoding="utf-8",
    )
    return batch


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net LLaVA visual summary batch v1.")
    parser.add_argument("--jobs-jsonl", required=True, help="Patch A jobs JSONL path.")
    parser.add_argument("--source-package-metadata-zip", default="", help="metadata.zip or directory containing page images.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--llm-mode", choices=["dry_run", "ollama"], default="dry_run")
    parser.add_argument("--ollama-base-url", default=DEFAULT_OLLAMA_BASE_URL)
    parser.add_argument("--ollama-model", default=DEFAULT_OLLAMA_MODEL)
    parser.add_argument("--request-timeout", type=int, default=120)
    parser.add_argument("--max-jobs", type=int, default=0, help="Optional cap for smoke runs; 0 means all jobs.")
    parser.add_argument("--fallback-to-dry-run", action="store_true", help="If Ollama fails, create low-confidence fallback cards instead of failing the whole batch.")
    parser.add_argument("--keep-raw-model-responses", action="store_true")
    parser.add_argument("--min-llava-summaries", type=int, default=1)
    parser.add_argument("--min-structured-json", type=int, default=1)
    parser.add_argument("--min-visual-summary-text", type=int, default=1)
    parser.add_argument("--min-source-trace-ready", type=int, default=1)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--max-answer-permission", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--max-write-attempts", type=int, default=0)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        batch = build_batch(args)
    except Exception as exc:
        print(f"ERROR {MODULE_NAME}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    summary = batch.get("summary", {})
    print(f"status={batch.get('status')}")
    print(f"quality_status={batch.get('quality_status')}")
    for key in (
        "llava_summary_count",
        "structured_json_count",
        "figure_candidate_count",
        "callout_candidate_count",
        "source_trace_ready_count",
        "ready_for_visual_linking",
        "unsafe_record_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
        "write_attempt_count",
    ):
        print(f"{key}={summary.get(key)}")
    print(f"batch={batch.get('artifact_paths', {}).get('batch')}")
    return 0 if batch.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
