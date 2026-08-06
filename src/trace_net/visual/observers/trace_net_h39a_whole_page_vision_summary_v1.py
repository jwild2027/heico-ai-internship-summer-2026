from __future__ import annotations

import argparse
import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


MODULE = "trace_net_h39a_whole_page_vision_summary_v1"
VERSION = "v1"

IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"]
BAD_PAGE_PREFIXES = ("metadata_page_", "source_p")
BAD_PATH_PARTS = (
    "table_full_region_recovery/previews",
    "contact_sheet",
    "overlay",
    "debug",
    "__pycache__",
)


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _norm(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()


def iter_dicts(obj: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from iter_dicts(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_dicts(item)


def looks_like_bad_page_id(page_id: str) -> bool:
    low = page_id.lower()
    return low.startswith(BAD_PAGE_PREFIXES) or "metadata" in low


def extract_page_id(record: Mapping[str, Any]) -> str:
    for key in [
        "page_id",
        "source_page_id",
        "source_trace_page_id",
        "image_page_id",
        "manual_page_id",
        "trace_page_id",
    ]:
        value = _norm(record.get(key))
        if value and not looks_like_bad_page_id(value):
            return value

    blob = json.dumps(record, ensure_ascii=False)
    match = re.search(r"\bt_p_[A-Za-z0-9_]+_p\d{6}\b", blob)
    if match:
        return match.group(0)
    match = re.search(r"\bp\d{6}\b", blob)
    if match:
        return match.group(0)
    return ""


def extract_page_number(page_id: str, record: Mapping[str, Any]) -> str:
    for key in ["page_number", "page", "source_page", "manual_page"]:
        value = _norm(record.get(key))
        if re.fullmatch(r"\d{1,6}", value):
            return str(int(value))
    match = re.search(r"p0*([0-9]{1,6})\b", page_id)
    if match:
        return str(int(match.group(1)))
    return ""


def infer_image_visual_record(record: Mapping[str, Any], source_hint_is_visual_pack: bool = False) -> bool:
    if source_hint_is_visual_pack:
        return bool(extract_page_id(record))

    blob = json.dumps(record, ensure_ascii=False).lower()
    route = _norm(
        record.get("route")
        or record.get("primary_route")
        or record.get("selected_route")
        or record.get("route_name")
        or record.get("page_route")
    ).lower()
    return route == "image_visual" or "image_visual" in route or '"image_visual"' in blob


def discover_image_visual_pages(
    image_visual_evidence_pack: str | Path,
    trace_dir: str | Path = "local_data/organization/trace_net",
    skip_first_n_pages: int = 0,
) -> List[Dict[str, Any]]:
    """Discover real image_visual pages from the visual pack and route artifacts.

    This intentionally rejects metadata/source alias page IDs so the vision model
    receives actual source page images, not table previews or synthetic cards.
    """

    trace_dir = Path(trace_dir)
    image_visual_evidence_pack = Path(image_visual_evidence_pack)
    candidates: Dict[str, Dict[str, Any]] = {}

    sources: List[Tuple[Path, bool]] = []
    if image_visual_evidence_pack.exists():
        sources.append((image_visual_evidence_pack, True))

    if trace_dir.exists():
        for path in trace_dir.rglob("*.json"):
            normalized = str(path).replace("\\", "/").lower()
            if path == image_visual_evidence_pack:
                continue
            if any(skip in normalized for skip in ["/llm_", "/h38", "/h37", "/h36", "/h35", "vision_image_route_summary"]):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if "image_visual" in text or "visual" in normalized:
                sources.append((path, False))

    for path, is_visual_pack in sources:
        try:
            data = _read_json(path)
        except Exception:
            continue

        for record in iter_dicts(data):
            if not infer_image_visual_record(record, source_hint_is_visual_pack=is_visual_pack):
                continue

            page_id = extract_page_id(record)
            if not page_id or looks_like_bad_page_id(page_id):
                continue

            page_number = extract_page_number(page_id, record)
            if skip_first_n_pages and page_number.isdigit() and int(page_number) <= skip_first_n_pages:
                continue

            rec = candidates.setdefault(page_id, {
                "page_id": page_id,
                "page_number": page_number,
                "route": "image_visual",
                "source_route_artifacts": [],
                "source_record_count": 0,
                "candidate_image_paths": [],
            })
            if page_number and not rec.get("page_number"):
                rec["page_number"] = page_number
            rec["source_route_artifacts"].append(str(path))
            rec["source_record_count"] += 1

            for value in record.values():
                if isinstance(value, str) and any(value.lower().endswith(ext) for ext in IMAGE_EXTS):
                    rec["candidate_image_paths"].append(value)

    out = list(candidates.values())
    out.sort(key=lambda item: (int(item.get("page_number") or 999999), item.get("page_id") or ""))
    return out


def _path_is_allowed_image(path: Path, allow_previews: bool = False) -> bool:
    if not path.exists() or not path.is_file():
        return False
    if path.suffix.lower() not in IMAGE_EXTS:
        return False
    normalized = str(path).replace("\\", "/").lower()
    if not allow_previews and any(part in normalized for part in BAD_PATH_PARTS):
        return False
    return True


def _exact_page_tokens(page_id: str, page_number: str) -> List[str]:
    tokens: List[str] = []
    if page_id:
        tokens.append(page_id)
        match = re.search(r"(p\d{6})\b", page_id)
        if match:
            tokens.append(match.group(1))
    if page_number and str(page_number).isdigit():
        tokens.append("p" + str(int(page_number)).zfill(6))

    out: List[str] = []
    seen = set()
    for token in tokens:
        token = token.strip()
        if len(token) < 5:
            continue
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out


def _score_image_candidate(path: Path, page_id: str) -> tuple:
    normalized = str(path).replace("\\", "/").lower()
    preview_penalty = 20 if "preview" in normalized else 0
    overlay_penalty = 20 if "overlay" in normalized or "contact_sheet" in normalized else 0
    source_bonus = -10 if "source" in normalized or "page_images" in normalized or "tiff" in normalized else 0
    exact_bonus = -20 if page_id.lower() and page_id.lower() in path.name.lower() else 0
    size_score = -min(path.stat().st_size if path.exists() else 0, 20_000_000)
    return (preview_penalty + overlay_penalty + source_bonus + exact_bonus, size_score, len(normalized))


def find_image_for_page(
    page: Mapping[str, Any],
    image_roots: List[str | Path],
    allow_previews: bool = False,
) -> Optional[Path]:
    page_id = _norm(page.get("page_id"))
    page_number = _norm(page.get("page_number"))

    direct: List[Path] = []
    for raw in page.get("candidate_image_paths") or []:
        path = Path(raw)
        if _path_is_allowed_image(path, allow_previews=allow_previews):
            direct.append(path)
    if direct:
        return sorted(direct, key=lambda item: _score_image_candidate(item, page_id))[0]

    candidates: List[Path] = []
    for root in [Path(p) for p in image_roots]:
        if not root.exists():
            continue
        for token in _exact_page_tokens(page_id, page_number):
            for ext in IMAGE_EXTS:
                candidates.extend(root.rglob(f"*{token}*{ext}"))

    candidates = [p for p in set(candidates) if _path_is_allowed_image(p, allow_previews=allow_previews)]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: _score_image_candidate(item, page_id))[0]


def convert_for_vision(
    source_image: str | Path,
    output_dir: str | Path,
    max_side: int = 1600,
    jpeg_quality: int = 85,
) -> Tuple[Path, Dict[str, Any]]:
    """Convert any source page image to a model-friendly RGB JPEG."""

    try:
        from PIL import Image, ImageOps
    except Exception as exc:
        raise RuntimeError("Image conversion requires Pillow. Run: python -m pip install pillow") from exc

    source_image = Path(source_image)
    output_dir = Path(output_dir)
    jpeg_dir = output_dir / "vision_input_jpeg"
    jpeg_dir.mkdir(parents=True, exist_ok=True)
    output_path = jpeg_dir / f"{source_image.stem}_max{max_side}.jpg"

    with Image.open(source_image) as image:
        image = ImageOps.exif_transpose(image)
        original_mode = image.mode
        original_size = image.size
        image = image.convert("RGB")
        image.thumbnail((max_side, max_side))
        converted_size = image.size
        image.save(output_path, format="JPEG", quality=jpeg_quality, optimize=True)

    return output_path, {
        "source_image_path": str(source_image),
        "converted_image_path": str(output_path),
        "source_suffix": source_image.suffix.lower(),
        "original_mode": original_mode,
        "original_size": list(original_size),
        "converted_size": list(converted_size),
        "converted_bytes": output_path.stat().st_size,
        "vision_max_side": max_side,
        "jpeg_quality": jpeg_quality,
    }


def _load_engram_guidance(
    trace_dir: str | Path = "local_data/organization/trace_net",
    max_rules: int = 12,
) -> str:
    trace_dir = Path(trace_dir)
    seed = [
        "- Vision summaries are guidance only; they are not proof.",
        "- Act like a cautious engineer: observations, confidence, uncertainty, limits.",
        "- Do not claim interchangeability, effectivity, fit, replacement approval, or installation safety.",
        "- If text is hard to read, say uncertain instead of inventing.",
        "- OCR/table/exact/graph routes must verify factual source claims.",
    ]

    paths = [
        trace_dir / "engineering_engram_memory_layers_v1/trace_net_engineering_engram_memory_layers_v1.json",
        trace_dir / "engineering_engram_core_v1/trace_net_engineering_engram_core_v1.json",
    ]

    rules: List[str] = []
    for path in paths:
        if not path.exists():
            continue
        try:
            data = _read_json(path)
        except Exception:
            continue
        for record in iter_dicts(data):
            rule = _norm(record.get("rule") or record.get("text") or record.get("content") or record.get("guidance"))
            layer = _norm(record.get("memory_layer") or record.get("layer"))
            if rule and len(rule) > 20:
                rules.append(f"- {layer + ': ' if layer else ''}{rule}")

    out: List[str] = []
    seen = set()
    for item in seed + rules:
        key = item.lower()
        if key not in seen:
            out.append(item)
            seen.add(key)
        if len(out) >= max_rules:
            break
    return "\n".join(out)


def build_prompt(page: Mapping[str, Any], engram_guidance: str) -> str:
    page_id = _norm(page.get("page_id"))
    page_number = _norm(page.get("page_number"))
    return f"""
TRACE-NET H39A WHOLE-PAGE IMAGE_VISUAL ENGINEERING SUMMARY

Act like a cautious aircraft-manual engineer. You are a visual scout, not the proof source.

ENGRAM GUIDANCE:
{engram_guidance}

PAGE:
page_id: {page_id}
page_number: {page_number}
route: image_visual

Return compact JSON only:
{{
  "page_id": "{page_id}",
  "page_number": "{page_number}",
  "image_type": "diagram | figure | table | mixed | blank | unknown",
  "engineering_summary": "",
  "visible_figures": [],
  "visible_callouts": [],
  "visible_part_numbers": [],
  "visible_nomenclature": [],
  "layout_observations": [],
  "possible_relationships": [
    {{
      "relationship": "figure-to-part | callout-to-part | text-near-part | unknown",
      "subject": "",
      "object": "",
      "confidence": "low | medium | high",
      "why": ""
    }}
  ],
  "uncertainties": [],
  "limits": [
    "Vision summary is guidance only and is not source proof.",
    "Do not infer interchangeability, effectivity, fit, replacement approval, or installation safety."
  ],
  "recommended_followup_routes": ["ocr", "table", "exact_search", "graph"]
}}

Rules:
- Do not invent unreadable text.
- Use uncertainty when unsure.
- Do not make approval, effectivity, fit, replacement, or installation-safety claims.
- Output JSON only.
""".strip()


def _image_b64(path: str | Path) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode("ascii")


def _read_http_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")[:4000]
    except Exception:
        return ""


def call_ollama_vision(
    prompt: str,
    image_path: str | Path,
    model: str,
    ollama_url: str,
    timeout_seconds: int,
    num_ctx: int,
) -> Tuple[str, str]:
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [_image_b64(image_path)],
        "stream": False,
        "options": {"temperature": 0.05, "num_ctx": num_ctx},
    }
    request = urllib.request.Request(
        ollama_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
        return (data.get("response") or "").strip(), ""
    except urllib.error.HTTPError as exc:
        return "", f"HTTPError {exc.code}: {exc.reason}; body={_read_http_error_body(exc)}"
    except Exception as exc:
        return "", repr(exc)


def _maybe_json(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return None
    return None


def _artifact_response(page: Mapping[str, Any]) -> Dict[str, Any]:
    page_id = _norm(page.get("page_id"))
    page_number = _norm(page.get("page_number"))
    return {
        "page_id": page_id,
        "page_number": page_number,
        "image_type": "unknown",
        "engineering_summary": "Artifact-mode placeholder: page is selected for image_visual whole-page vision review.",
        "visible_figures": [],
        "visible_callouts": [],
        "visible_part_numbers": [],
        "visible_nomenclature": [],
        "layout_observations": ["Whole-page vision summary should be generated by a live vision model."],
        "possible_relationships": [],
        "uncertainties": ["No live vision model was called in artifact mode."],
        "limits": [
            "Vision summary is guidance only and is not source proof.",
            "Do not infer interchangeability, effectivity, fit, replacement approval, or installation safety.",
        ],
        "recommended_followup_routes": ["ocr", "table", "exact_search", "graph"],
    }


def build_whole_page_vision_summary(
    image_visual_evidence_pack: str | Path,
    output_dir: str | Path,
    image_roots: str = "local_data",
    trace_dir: str | Path = "local_data/organization/trace_net",
    model: str = "llama3.2-vision:11b",
    ollama_url: str = "http://127.0.0.1:11434/api/generate",
    llm_mode: str = "ollama",
    max_pages: int = 3,
    skip_first_n_pages: int = 0,
    allow_previews: bool = False,
    vision_max_side: int = 1600,
    jpeg_quality: int = 85,
    vision_num_ctx: int = 4096,
    timeout_seconds: int = 420,
    min_records: int = 1,
    min_pass: int = 1,
    require_no_answer_permission: bool = False,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
    progress: bool = True,
) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    response_dir = output_dir / "responses"
    response_dir.mkdir(parents=True, exist_ok=True)

    image_root_list = [item for item in image_roots.split(";") if item.strip()]
    pages = discover_image_visual_pages(
        image_visual_evidence_pack=image_visual_evidence_pack,
        trace_dir=trace_dir,
        skip_first_n_pages=skip_first_n_pages,
    )

    selected: List[Dict[str, Any]] = []
    missing_images: List[Dict[str, Any]] = []
    for page in pages:
        image = find_image_for_page(page, image_root_list, allow_previews=allow_previews)
        if image:
            page["image_path"] = str(image)
            selected.append(page)
        else:
            missing_images.append({
                "page_id": page.get("page_id", ""),
                "page_number": page.get("page_number", ""),
                "source_record_count": page.get("source_record_count", 0),
            })
        if len(selected) >= max_pages:
            break

    engram_guidance = _load_engram_guidance(trace_dir=trace_dir)
    records: List[Dict[str, Any]] = []
    start = time.time()

    for idx, page in enumerate(selected, 1):
        source_image = Path(page["image_path"])
        page_id = page.get("page_id") or f"page_{idx:04d}"
        safe_page = re.sub(r"[^A-Za-z0-9_.-]+", "_", page_id)[:100]

        record: Dict[str, Any] = {
            "page_id": page.get("page_id", ""),
            "page_number": page.get("page_number", ""),
            "route": "image_visual",
            "source_image_path": str(source_image),
            "model": model,
            "llm_mode": llm_mode,
            "summary_status": "PENDING",
            "error": "",
            "response_text_path": "",
            "parsed_json": None,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "vision_summary_guidance_only": True,
            "write_attempt_count": 0,
            "unsafe": False,
        }

        try:
            prompt = build_prompt(page, engram_guidance)
            if llm_mode == "artifact":
                parsed = _artifact_response(page)
                response_text = json.dumps(parsed, indent=2, ensure_ascii=False)
                record.update({
                    "summary_status": "PASS",
                    "parsed_json": parsed,
                    "response_preview": response_text[:1500],
                    "converted_image_path": "",
                })
            elif llm_mode == "ollama":
                converted_path, conversion_meta = convert_for_vision(
                    source_image=source_image,
                    output_dir=output_dir,
                    max_side=vision_max_side,
                    jpeg_quality=jpeg_quality,
                )
                response_text, error = call_ollama_vision(
                    prompt=prompt,
                    image_path=converted_path,
                    model=model,
                    ollama_url=ollama_url,
                    timeout_seconds=timeout_seconds,
                    num_ctx=vision_num_ctx,
                )
                record.update(conversion_meta)
                if error:
                    raise RuntimeError(error)
                if not response_text:
                    raise RuntimeError("empty Ollama response")
                parsed = _maybe_json(response_text)
                record.update({
                    "summary_status": "PASS",
                    "parsed_json": parsed,
                    "response_preview": response_text[:1500],
                })
            else:
                raise ValueError(f"unsupported llm_mode: {llm_mode}")

            response_path = response_dir / f"{idx:04d}_{safe_page}_response.txt"
            _write_text(response_path, response_text)
            record["response_text_path"] = str(response_path)

        except Exception as exc:
            record.update({
                "summary_status": "ERROR",
                "error": str(exc)[:4000],
            })

        records.append(record)

        if progress:
            elapsed = time.time() - start
            converted = f" converted={record.get('converted_image_path', '')}" if record.get("converted_image_path") else ""
            error_tail = f" error={record['error'][:220]}" if record["error"] else ""
            print(
                f"[H39A vision progress] {idx}/{len(selected)} "
                f"page_id={record['page_id']} status={record['summary_status']} "
                f"elapsed={elapsed:.1f}s source={source_image}{converted}{error_tail}",
                flush=True,
            )

    pass_count = sum(1 for record in records if record["summary_status"] == "PASS")
    error_count = sum(1 for record in records if record["summary_status"] == "ERROR")
    unsafe_count = sum(1 for record in records if record.get("unsafe"))
    write_attempt_count = sum(int(record.get("write_attempt_count") or 0) for record in records)
    answer_permission_count = sum(1 for record in records if record.get("answer_permission"))
    source_truth_mutation_count = sum(1 for record in records if record.get("source_truth_mutation_allowed"))

    summary = {
        "module": MODULE,
        "version": VERSION,
        "record_count": len(records),
        "pass_count": pass_count,
        "error_count": error_count,
        "discovered_image_visual_page_count": len(pages),
        "selected_page_count": len(selected),
        "missing_image_count_before_limit": len(missing_images),
        "model": model,
        "llm_mode": llm_mode,
        "vision_summary_guidance_only_count": len(records),
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_count,
        "unsafe_finding_count": unsafe_count,
        "write_attempt_count": write_attempt_count,
    }

    failures: List[str] = []
    if len(records) < min_records:
        failures.append("record_count_below_min")
    if pass_count < min_pass:
        failures.append("pass_count_below_min")
    if require_no_answer_permission and answer_permission_count:
        failures.append("answer_permission_nonzero")
    if unsafe_count > max_unsafe:
        failures.append("unsafe_finding_count_above_max")
    if write_attempt_count > max_write_attempts:
        failures.append("write_attempt_count_above_max")

    summary["quality_failures"] = failures
    quality_status = "PASS" if not failures else "FAIL"

    manifest = {
        "status": "TRACE_NET_H39A_WHOLE_PAGE_VISION_SUMMARY_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "vision_policy": {
            "mode": "whole_page_image_visual_summary",
            "proof_boundary": "Vision summaries are guidance only. Source claims still require OCR/table/exact/graph/source-trace proof.",
            "input_transform": "source TIFF/page image -> downscaled RGB JPEG -> vision model",
            "forbidden": [
                "answer_permission_from_vision_summary",
                "source_truth_mutation_from_vision_summary",
                "interchangeability_or_approval_claims_from_vision_only",
                "live_db_or_vector_writes",
            ],
        },
        "source_paths": {
            "image_visual_evidence_pack": str(image_visual_evidence_pack),
            "trace_dir": str(trace_dir),
            "image_roots": image_root_list,
        },
        "missing_image_examples": missing_images[:20],
        "engram_guidance": engram_guidance,
        "records": records,
    }

    _write_json(output_dir / f"{MODULE}.json", manifest)
    _write_json(output_dir / f"{MODULE}_quality_check.json", {
        "status": "TRACE_NET_H39A_WHOLE_PAGE_VISION_SUMMARY_CHECKED",
        "quality_status": quality_status,
        "summary": summary,
    })
    return manifest


def check_whole_page_vision_summary(
    vision_summary: str | Path,
    min_records: int = 1,
    min_pass: int = 1,
    require_quality_pass: bool = False,
    require_no_answer_permission: bool = False,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    data = _read_json(vision_summary)
    summary = data.get("summary", {})
    failures: List[str] = []
    if int(summary.get("record_count") or 0) < min_records:
        failures.append("record_count_below_min")
    if int(summary.get("pass_count") or 0) < min_pass:
        failures.append("pass_count_below_min")
    if require_quality_pass and data.get("quality_status") != "PASS":
        failures.append("quality_not_pass")
    if require_no_answer_permission and int(summary.get("answer_permission_count") or 0):
        failures.append("answer_permission_nonzero")
    if int(summary.get("unsafe_finding_count") or 0) > max_unsafe:
        failures.append("unsafe_finding_count_above_max")
    if int(summary.get("write_attempt_count") or 0) > max_write_attempts:
        failures.append("write_attempt_count_above_max")

    return {
        "status": "TRACE_NET_H39A_WHOLE_PAGE_VISION_SUMMARY_CHECKED",
        "quality_status": "PASS" if not failures else "FAIL",
        "record_count": int(summary.get("record_count") or 0),
        "pass_count": int(summary.get("pass_count") or 0),
        "error_count": int(summary.get("error_count") or 0),
        "answer_permission_count": int(summary.get("answer_permission_count") or 0),
        "source_truth_mutation_allowed_count": int(summary.get("source_truth_mutation_allowed_count") or 0),
        "unsafe_finding_count": int(summary.get("unsafe_finding_count") or 0),
        "write_attempt_count": int(summary.get("write_attempt_count") or 0),
        "quality_failures": failures,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net H39A whole-page vision summaries")
    parser.add_argument("--image-visual-evidence-pack", default="local_data/organization/trace_net/image_visual_evidence_nomenclature_merger_v1/trace_net_image_visual_evidence_pack_with_nomenclature_v1.json")
    parser.add_argument("--output-dir", default="local_data/organization/trace_net/h39a_whole_page_vision_summary_v1")
    parser.add_argument("--image-roots", default="local_data")
    parser.add_argument("--trace-dir", default="local_data/organization/trace_net")
    parser.add_argument("--model", default=os.environ.get("TRACE_NET_VISION_MODEL", "llama3.2-vision:11b"))
    parser.add_argument("--ollama-url", default=os.environ.get("TRACE_NET_OLLAMA_URL", "http://127.0.0.1:11434/api/generate"))
    parser.add_argument("--llm-mode", default="ollama", choices=["ollama", "artifact"])
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--skip-first-n-pages", type=int, default=0)
    parser.add_argument("--allow-previews", action="store_true")
    parser.add_argument("--vision-max-side", type=int, default=1600)
    parser.add_argument("--jpeg-quality", type=int, default=85)
    parser.add_argument("--vision-num-ctx", type=int, default=4096)
    parser.add_argument("--timeout-seconds", type=int, default=420)
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-pass", type=int, default=1)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--max-write-attempts", type=int, default=0)
    parser.add_argument("--no-progress", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    kwargs = vars(args).copy()
    no_progress = bool(kwargs.pop("no_progress", False))
    result = build_whole_page_vision_summary(progress=not no_progress, **kwargs)
    summary = result["summary"]
    print("status=TRACE_NET_H39A_WHOLE_PAGE_VISION_SUMMARY_BUILT")
    print(f"quality_status={result['quality_status']}")
    print(f"record_count={summary['record_count']}")
    print(f"pass_count={summary['pass_count']}")
    print(f"error_count={summary['error_count']}")
    print(f"discovered_image_visual_page_count={summary['discovered_image_visual_page_count']}")
    print(f"selected_page_count={summary['selected_page_count']}")
    print(f"answer_permission_count={summary['answer_permission_count']}")
    print(f"source_truth_mutation_allowed_count={summary['source_truth_mutation_allowed_count']}")
    print(f"unsafe_finding_count={summary['unsafe_finding_count']}")
    print(f"write_attempt_count={summary['write_attempt_count']}")
    print(f"output={Path(args.output_dir) / (MODULE + '.json')}")
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
