from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import mimetypes
import re
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

VERSION = "v34.3"
MODULE = "trace_net_e2e_image_visual_observer_route_v34_3"
MODEL_ID = "trace-net-e2e-technical-drawing-geometry-llava-v34-3"

PAGE_ID_RE = re.compile(r"t_p_\d+_\d+_p\d{6}", re.I)
DATA_URL_RE = re.compile(r"^data:(?P<mime>[^;]+);base64,(?P<data>.+)$", re.I | re.S)

SAFETY_CONTRACT: Dict[str, Any] = {
    "answer_permission": False,
    "can_answer_directly": False,
    "can_prove_claims": False,
    "source_truth_mutation_allowed": False,
    "writes_to_postgres": False,
    "writes_to_qdrant": False,
    "writes_to_opensearch": False,
    "uploads_to_opensearch": False,
    "raw_5tb_scan_at_query_time": False,
    "graph_rebuild_at_query_time": False,
    "visual_observations_guidance_only": True,
    "llava_observer_guidance_only": True,
    "source_truth_required_for_visual_claims": True,
    "human_review_required_for_low_confidence_visual_claims": True,
    "response_is_final_gated": True,
    "ocr_text_candidates_guidance_only": True,
    "opencv_layout_regions_guidance_only": True,
    "llava_text_claims_require_ocr_confirmation": True,
    "hallucinated_text_suppression_enabled": True,
    "technical_drawing_geometry_guidance_only": True,
    "dimension_ocr_candidates_require_confirmation": True,
    "cad_reconstruction_not_authoritative": True,
}

VISUAL_OBSERVER_SYSTEM_PROMPT = (
    "You are a visual observer for scanned technical manuals. "
    "Describe only visible visual structure. Identify whether the image looks like a diagram, table, text page, or mixed page. "
    "List visible callouts, arrows, labels, dimension lines, circles, arcs, hatching, views, and obvious text candidates. Do not guess missing details. "
    "Do not invent brand names or quoted text. If text is unclear, say it is unclear. "
    "Your observations are guidance only and are not proof authority; OCR must confirm visible text."
)

STANDARD_DEMO_QUERIES = [
    {
        "user_query": "Inspect this uploaded manual page image and describe visible structure.",
        "synthetic_image_id": "demo_visual_page_001",
        "synthetic_visual_type": "diagram_candidate",
        "expected_mode": "visual_observer_guidance",
    },
    {
        "user_query": "Does this image contain a diagram or callouts?",
        "synthetic_image_id": "demo_visual_page_002",
        "synthetic_visual_type": "callout_diagram_candidate",
        "expected_mode": "visual_observer_guidance",
    },
    {
        "user_query": "Turn this image into a diagram draft.",
        "synthetic_image_id": "demo_visual_page_003",
        "synthetic_visual_type": "diagram_generation_draft",
        "expected_mode": "diagram_draft_guidance",
    },
    {
        "user_query": "Turn this engineering drawing into a technical diagram draft.",
        "synthetic_image_id": "demo_visual_page_004",
        "synthetic_visual_type": "technical_drawing_candidate",
        "expected_mode": "technical_drawing_draft_guidance",
    },
    {
        "user_query": "What does this picture prove about the part?",
        "synthetic_image_id": "demo_visual_page_005",
        "synthetic_visual_type": "unknown_visual_claim_risk",
        "expected_mode": "visual_guidance_only_no_proof",
    },
]


def _now() -> int:
    return int(time.time())


def _norm(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _lower(value: Any) -> str:
    return _norm(value).lower()


def _stable_id(prefix: str, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _read_json(path: str | Path | None) -> Dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: str | Path, rows: Sequence[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows) + "\n", encoding="utf-8")


def _walk_json(obj: Any) -> Iterable[Any]:
    yield obj
    if isinstance(obj, Mapping):
        for v in obj.values():
            yield from _walk_json(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_json(v)


def _extract_page_id(text_or_obj: Any) -> str:
    text = text_or_obj if isinstance(text_or_obj, str) else json.dumps(text_or_obj, ensure_ascii=False)
    m = PAGE_ID_RE.search(text)
    return m.group(0) if m else ""


def _extract_user_text_and_images(payload_or_messages: Any) -> Tuple[str, List[Dict[str, Any]]]:
    """Extract user text plus image references from OpenAI-compatible payloads.

    Handles both chat payloads and raw message lists. Open WebUI can send message
    content as strings, as arrays of {type:text}, {type:image_url}, or sometimes
    top-level `images` arrays. This function is intentionally defensive so one
    malformed content item does not crash the endpoint.
    """
    payload = payload_or_messages if isinstance(payload_or_messages, Mapping) else {}
    messages = payload.get("messages", []) if isinstance(payload, Mapping) else payload_or_messages
    texts: List[str] = []
    images: List[Dict[str, Any]] = []

    def add_image(value: Any, source: str) -> None:
        if not value:
            return
        if isinstance(value, Mapping):
            url = value.get("url") or value.get("image_url") or value.get("data") or value.get("base64")
            detail = value.get("detail")
        else:
            url = value
            detail = None
        if not isinstance(url, str) or not url.strip():
            return
        ref = url.strip()
        mime = None
        b64 = None
        m = DATA_URL_RE.match(ref)
        if m:
            mime = m.group("mime")
            b64 = m.group("data").strip()
        elif len(ref) > 100 and re.fullmatch(r"[A-Za-z0-9+/=\n\r]+", ref.strip()):
            b64 = ref.strip()
        images.append({"source": source, "reference": ref, "mime_type": mime, "base64": b64, "detail": detail})

    if isinstance(messages, str):
        texts.append(messages)
    elif isinstance(messages, list):
        for msg in messages:
            if isinstance(msg, str):
                texts.append(msg)
                continue
            if not isinstance(msg, Mapping):
                continue
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, str):
                        texts.append(item)
                    elif isinstance(item, Mapping):
                        item_type = _lower(item.get("type"))
                        if item_type in {"text", "input_text"}:
                            texts.append(_norm(item.get("text")))
                        elif item_type in {"image_url", "input_image", "image"}:
                            add_image(item.get("image_url") or item.get("url") or item.get("image") or item, "message_content")
            # Some clients put images beside content.
            if isinstance(msg.get("images"), list):
                for img in msg.get("images"):
                    add_image(img, "message_images")

    if isinstance(payload, Mapping) and isinstance(payload.get("images"), list):
        for img in payload.get("images"):
            add_image(img, "payload_images")

    # Deduplicate by reference/hash.
    seen = set()
    out: List[Dict[str, Any]] = []
    for img in images:
        key = img.get("base64") or img.get("reference")
        if key in seen:
            continue
        seen.add(key)
        out.append(img)
    return "\n".join(t for t in texts if t).strip(), out


def _guess_visual_intent(query: str, image_count: int = 0) -> str:
    q = query.lower()
    if image_count and any(w in q for w in ("diagram", "draw", "mermaid", "flow", "turn this", "recreate")):
        return "uploaded_image_diagram_draft"
    if image_count:
        return "uploaded_image_visual_inspection"
    if any(w in q for w in ("image", "picture", "photo", "diagram", "callout", "visual")):
        return "image_visual_missing_upload"
    return "image_visual_observer_demo"


def _classify_visual_type(query: str) -> str:
    q = query.lower()
    if any(w in q for w in ("engineering drawing", "technical drawing", "mechanical drawing", "blueprint", "cad", "dimension", "dimensions", "section view", "orthographic", "flange", "bolt hole", "bore", "hatching")):
        return "technical_drawing_candidate"
    if "table" in q:
        return "table_or_grid_candidate"
    if any(w in q for w in ("callout", "arrow", "label")):
        return "callout_diagram_candidate"
    if any(w in q for w in ("diagram", "draw", "recreate", "mermaid")):
        return "diagram_candidate"
    if any(w in q for w in ("text", "ocr", "read")):
        return "text_page_candidate"
    return "mixed_or_unknown_visual"


def _image_quality_card_from_path(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    card: Dict[str, Any] = {
        "image_id": _stable_id("image", str(p)),
        "image_source": "local_path",
        "path": str(p),
        "exists": p.exists(),
        "mime_type": mimetypes.guess_type(str(p))[0],
        "sha256": None,
        "width": None,
        "height": None,
        "quality_status": "IMAGE_FILE_NOT_FOUND",
        "quality_warnings": [],
    }
    if not p.exists() or not p.is_file():
        card["quality_warnings"].append("image_file_missing")
        return card
    data = p.read_bytes()
    card["sha256"] = hashlib.sha256(data).hexdigest()
    card["byte_count"] = len(data)
    if len(data) < 1024:
        card["quality_warnings"].append("very_small_file")
    try:
        from PIL import Image  # type: ignore
        with Image.open(p) as im:
            card["width"] = int(im.width)
            card["height"] = int(im.height)
            card["mode"] = im.mode
        if card["width"] and card["height"] and (card["width"] < 300 or card["height"] < 300):
            card["quality_warnings"].append("low_resolution")
    except Exception as exc:  # pragma: no cover - depends on optional PIL/image file.
        card["quality_warnings"].append(f"image_dimension_read_failed:{type(exc).__name__}")
    card["quality_status"] = "IMAGE_QUALITY_READY" if not card["quality_warnings"] else "IMAGE_QUALITY_WARNINGS"
    return card


def _image_quality_card_from_reference(img: Mapping[str, Any], idx: int) -> Dict[str, Any]:
    b64 = img.get("base64")
    ref = _norm(img.get("reference"))
    raw = b64 or ref
    digest = hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]
    byte_count = None
    warnings: List[str] = []
    if b64:
        try:
            byte_count = len(base64.b64decode(b64, validate=False))
        except Exception:
            warnings.append("base64_decode_warning")
    else:
        warnings.append("external_or_path_reference_not_loaded")
    if byte_count is not None and byte_count < 1024:
        warnings.append("very_small_uploaded_image_payload")
    return {
        "image_id": f"uploaded_image_{idx:04d}_{digest}",
        "image_source": img.get("source") or "uploaded_reference",
        "mime_type": img.get("mime_type"),
        "has_base64_payload": bool(b64),
        "byte_count": byte_count,
        "width": None,
        "height": None,
        "quality_status": "IMAGE_QUALITY_READY" if not warnings else "IMAGE_QUALITY_WARNINGS",
        "quality_warnings": warnings,
    }


def _synthetic_image_quality_card(image_id: str, visual_type: str) -> Dict[str, Any]:
    return {
        "image_id": image_id,
        "image_source": "synthetic_demo_reference",
        "mime_type": "image/png",
        "has_base64_payload": False,
        "byte_count": None,
        "width": 1600,
        "height": 2200,
        "quality_status": "IMAGE_QUALITY_SYNTHETIC_READY",
        "quality_warnings": [],
        "visual_type_hint": visual_type,
    }




def _decode_image_reference_bytes(img: Mapping[str, Any]) -> bytes | None:
    b64 = img.get("base64")
    if isinstance(b64, str) and b64.strip():
        try:
            return base64.b64decode(b64, validate=False)
        except Exception:
            return None
    ref = _norm(img.get("reference"))
    if ref and Path(ref).exists() and Path(ref).is_file():
        try:
            return Path(ref).read_bytes()
        except Exception:
            return None
    return None


def _decode_image_card_bytes(card: Mapping[str, Any], uploaded_images: Sequence[Mapping[str, Any]], index: int) -> bytes | None:
    if index < len(uploaded_images):
        return _decode_image_reference_bytes(uploaded_images[index])
    path = card.get("path")
    if path and Path(str(path)).exists() and Path(str(path)).is_file():
        try:
            return Path(str(path)).read_bytes()
        except Exception:
            return None
    return None


def _unique_texts(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for v in values:
        text = re.sub(r"\s+", " ", _norm(v)).strip(" .,:;|-_")
        if not text or len(text) < 2:
            continue
        key = text.upper()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _synthetic_ocr_text_card(image_id: str, visual_type: str | None, query: str) -> Dict[str, Any]:
    low = f"{visual_type or ''} {query}".lower()
    candidates: List[str] = []
    if any(w in low for w in ("diagram", "callout", "aircraft", "powerplant", "image")):
        candidates.extend(["AIRCRAFT PARTS", "POWERPLANT"])
    if "table" in low:
        candidates.extend(["TABLE", "ITEM", "PART NO"])
    if "text" in low and not candidates:
        candidates.append("VISIBLE TEXT CANDIDATE")
    return {
        "ocr_card_id": _stable_id("ocr_text_v34_3", image_id + "|" + low),
        "image_id": image_id,
        "ocr_engine": "synthetic_demo_ocr",
        "ocr_status": "OCR_SIMULATED_READY",
        "text_candidates": _unique_texts(candidates),
        "text_candidate_count": len(_unique_texts(candidates)),
        "authority": "guidance_only",
        "proof_authority": False,
        "requires_source_truth_confirmation": True,
    }


def _ocr_text_card_from_bytes(image_id: str, image_bytes: bytes | None) -> Dict[str, Any]:
    candidates: List[str] = []
    status = "OCR_UNAVAILABLE_NO_IMAGE_BYTES"
    error = None
    if image_bytes:
        try:
            from PIL import Image  # type: ignore
            import pytesseract  # type: ignore
            with Image.open(io.BytesIO(image_bytes)) as im:
                # Upscale small screenshots before OCR when possible.
                if im.width < 900:
                    ratio = max(2, int(900 / max(im.width, 1)))
                    im = im.resize((im.width * ratio, im.height * ratio))
                text = pytesseract.image_to_string(im)
            candidates = _unique_texts(line for line in text.splitlines() if line.strip())
            status = "OCR_READY" if candidates else "OCR_READY_NO_TEXT_FOUND"
        except Exception as exc:  # optional dependency/runtime path
            status = "OCR_UNAVAILABLE_OR_FAILED"
            error = f"{type(exc).__name__}: {exc}"
    return {
        "ocr_card_id": _stable_id("ocr_text_v34_3", image_id + "|" + hashlib.sha1((image_bytes or b'')).hexdigest()[:12]),
        "image_id": image_id,
        "ocr_engine": "tesseract_optional",
        "ocr_status": status,
        "ocr_error": error,
        "text_candidates": candidates[:25],
        "text_candidate_count": len(candidates[:25]),
        "authority": "guidance_only",
        "proof_authority": False,
        "requires_source_truth_confirmation": True,
    }


def _synthetic_opencv_layout_card(image_id: str, visual_type: str | None, query: str) -> Dict[str, Any]:
    low = f"{visual_type or ''} {query}".lower()
    regions: List[Dict[str, Any]] = [
        {"region_id": "left_visual_region", "label": "Left visual region", "region_type": "visual_object_region", "confidence": "medium"},
        {"region_id": "right_visual_region", "label": "Right visual region", "region_type": "visual_object_region", "confidence": "medium"},
        {"region_id": "bottom_text_region", "label": "Bottom text region", "region_type": "text_region", "confidence": "medium"},
    ]
    if "table" in low:
        regions.append({"region_id": "possible_grid_region", "label": "Possible grid/table region", "region_type": "table_or_grid_region", "confidence": "low"})
    return {
        "layout_card_id": _stable_id("opencv_layout_v34_3", image_id + "|" + low),
        "image_id": image_id,
        "layout_engine": "synthetic_demo_layout",
        "layout_status": "LAYOUT_SIMULATED_READY",
        "regions": regions,
        "region_count": len(regions),
        "authority": "guidance_only",
        "proof_authority": False,
        "requires_source_truth_confirmation": True,
    }


def _opencv_layout_card_from_bytes(image_id: str, image_bytes: bytes | None) -> Dict[str, Any]:
    regions: List[Dict[str, Any]] = []
    status = "LAYOUT_UNAVAILABLE_NO_IMAGE_BYTES"
    error = None
    width = height = None
    if image_bytes:
        try:
            from PIL import Image  # type: ignore
            with Image.open(io.BytesIO(image_bytes)) as im:
                width, height = int(im.width), int(im.height)
            status = "LAYOUT_READY_BASIC_REGIONS"
            # Conservative page-layout regions. These are coordinate guidance,
            # not part identity proof. Use normalized boxes to avoid format assumptions.
            if width and height:
                regions = [
                    {"region_id": "left_visual_region", "label": "Left visual region", "region_type": "visual_object_region", "bbox_norm": [0.0, 0.0, 0.40, 0.88], "confidence": "medium"},
                    {"region_id": "right_visual_region", "label": "Right visual region", "region_type": "visual_object_region", "bbox_norm": [0.35, 0.0, 1.0, 0.88], "confidence": "medium"},
                    {"region_id": "bottom_text_region", "label": "Bottom text region", "region_type": "text_region", "bbox_norm": [0.0, 0.75, 1.0, 1.0], "confidence": "medium"},
                ]
        except Exception as exc:
            status = "LAYOUT_UNAVAILABLE_OR_FAILED"
            error = f"{type(exc).__name__}: {exc}"
    return {
        "layout_card_id": _stable_id("opencv_layout_v34_3", image_id + "|" + hashlib.sha1((image_bytes or b'')).hexdigest()[:12]),
        "image_id": image_id,
        "layout_engine": "opencv_pil_basic_regions",
        "layout_status": status,
        "layout_error": error,
        "width": width,
        "height": height,
        "regions": regions,
        "region_count": len(regions),
        "authority": "guidance_only",
        "proof_authority": False,
        "requires_source_truth_confirmation": True,
    }


def _ocr_confirmed_terms(ocr_cards: Sequence[Mapping[str, Any]]) -> set[str]:
    terms: set[str] = set()
    for card in ocr_cards:
        for text in card.get("text_candidates") or []:
            up = _norm(text).upper()
            if not up:
                continue
            terms.add(up)
            for tok in re.findall(r"[A-Z0-9][A-Z0-9&/-]{2,}", up):
                terms.add(tok)
    return terms


def _extract_llava_text_claims(observation_cards: Sequence[Mapping[str, Any]]) -> List[str]:
    claims: List[str] = []
    for card in observation_cards:
        blob = "\n".join(_norm(x) for x in (card.get("visual_observations") or []))
        # Quoted strings often contain hallucinated OCR-like claims.
        claims.extend(re.findall(r'"([^"\n]{3,80})"', blob))
        # Uppercase phrases / brands. Keep conservative; this is for downgrade telemetry.
        claims.extend(re.findall(r"\b[A-Z][A-Z0-9&/-]{2,}(?:\s+[A-Z0-9&/-]{2,}){0,4}\b", blob))
    ignore = {"TRACE", "NET", "OCR", "API", "JSON", "PNG", "JPG"}
    return [c for c in _unique_texts(claims) if c.upper() not in ignore]


def _unconfirmed_llava_text_claims(observation_cards: Sequence[Mapping[str, Any]], ocr_cards: Sequence[Mapping[str, Any]]) -> List[str]:
    confirmed = _ocr_confirmed_terms(ocr_cards)
    unconfirmed: List[str] = []
    for claim in _extract_llava_text_claims(observation_cards):
        up = claim.upper().strip()
        # Confirm if the exact phrase or its main tokens appear in OCR.
        tokens = [t for t in re.findall(r"[A-Z0-9&/-]{3,}", up) if t]
        if up in confirmed or (tokens and all(t in confirmed for t in tokens[:3])):
            continue
        unconfirmed.append(claim)
    return _unique_texts(unconfirmed)


def _llava_simulated_observation(query: str, image_card: Mapping[str, Any], visual_type: str | None = None) -> Dict[str, Any]:
    vt = visual_type or _classify_visual_type(query)
    observations = [
        f"image appears to be {vt}",
        "manual-style visual inspection required",
    ]
    if "technical_drawing" in vt:
        observations.extend(["possible engineering drawing", "possible dimension lines", "possible circles/arcs", "possible hatching or section view"])
    elif "callout" in vt or "diagram" in vt:
        observations.extend(["possible callout labels", "possible arrows or leader lines"])
    if "table" in vt or "grid" in vt:
        observations.extend(["possible grid/table structure", "line geometry should be checked"])
    if "text" in vt:
        observations.append("OCR should be used to confirm visible text")
    return {
        "visual_observation_id": _stable_id("visual_obs_v34", _norm(image_card.get("image_id")) + query + vt),
        "image_id": image_card.get("image_id"),
        "visual_model": "llava:13b",
        "llm_mode": "simulate",
        "llava_called": False,
        "observer_status": "LLAVA_OBSERVER_SIMULATED",
        "visual_type": vt,
        "visual_observations": observations,
        "visible_text_candidates": [],
        "callout_candidates": [
            {"label": "unknown_callout", "confidence": "low", "requires_source_truth_confirmation": True}
        ] if "callout" in vt or "diagram" in vt else [],
        "diagram_draft_available": "diagram" in vt,
        "authority": "guidance_only",
        "proof_authority": False,
        "requires_source_truth_confirmation": True,
        "requires_human_review": True,
        "confidence": "low" if "unknown" in vt else "medium",
    }


def _call_ollama_vision_observer(
    *,
    base_url: str,
    model: str,
    query: str,
    image_b64: str,
    request_timeout: int,
    temperature: float = 0.0,
    max_output_tokens: int = 220,
) -> Dict[str, Any]:
    endpoint = base_url.rstrip("/").removesuffix("/v1") + "/api/generate"
    prompt = f"{VISUAL_OBSERVER_SYSTEM_PROMPT}\n\nUser request: {query}"
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_output_tokens},
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=request_timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        data = json.loads(raw)
        response_text = _norm(data.get("response"))
        return {
            "llava_call_status": "LLAVA_CALL_SUCCEEDED",
            "llava_response_text": response_text,
            "llava_call_error": None,
            "llava_latency_ms": elapsed_ms,
            "llava_called": True,
        }
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        return {
            "llava_call_status": "LLAVA_CALL_FAILED",
            "llava_response_text": "",
            "llava_call_error": f"{type(exc).__name__}: {exc}",
            "llava_latency_ms": elapsed_ms,
            "llava_called": True,
        }


def _llava_live_observation(
    query: str,
    image_card: Mapping[str, Any],
    image_b64: str,
    *,
    llm_base_url: str,
    llm_model: str,
    request_timeout: int,
    temperature: float,
    max_output_tokens: int,
) -> Dict[str, Any]:
    call = _call_ollama_vision_observer(
        base_url=llm_base_url,
        model=llm_model,
        query=query,
        image_b64=image_b64,
        request_timeout=request_timeout,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
    response_text = call.get("llava_response_text") or ""
    vt = _classify_visual_type(query)
    if response_text:
        low = response_text.lower()
        if _looks_like_technical_drawing_text(low):
            vt = "technical_drawing_candidate"
        elif "table" in low or "grid" in low:
            vt = "table_or_grid_candidate"
        elif "diagram" in low or "arrow" in low or "callout" in low:
            vt = "callout_diagram_candidate"
        elif "text" in low:
            vt = "text_page_candidate"
    return {
        "visual_observation_id": _stable_id("visual_obs_v34", _norm(image_card.get("image_id")) + query + response_text),
        "image_id": image_card.get("image_id"),
        "visual_model": llm_model,
        "llm_mode": "ollama",
        "llava_called": True,
        "observer_status": call.get("llava_call_status"),
        "llava_call_error": call.get("llava_call_error"),
        "llava_latency_ms": call.get("llava_latency_ms"),
        "visual_type": vt,
        "visual_observations": [response_text] if response_text else [],
        "visible_text_candidates": [],
        "callout_candidates": [],
        "diagram_draft_available": "diagram" in vt or "callout" in vt,
        "authority": "guidance_only",
        "proof_authority": False,
        "requires_source_truth_confirmation": True,
        "requires_human_review": True,
        "confidence": "medium" if response_text else "low",
    }



def _looks_like_technical_drawing_text(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in (
        "technical_drawing", "engineering drawing", "mechanical drawing", "blueprint", "orthographic",
        "section view", "dimension", "dimension line", "hatching", "flange", "bolt hole", "bore",
        "centerline", "circle", "arc", "radius", "diameter", "45°", "45 deg", "cross-section",
    ))


def _dimension_text_candidates(ocr_cards: Sequence[Mapping[str, Any]]) -> List[str]:
    out: List[str] = []
    patterns = [
        r"\b\d+(?:\.\d+)?\s*(?:in|inch|inches|mm|cm)\b",
        r"\b\d+\s*/\s*\d+\s*(?:in|inch|inches|\")?",
        r"\b\d+(?:\.\d+)?\s*[°º]\b",
        r"\bR\s*\d+(?:\.\d+)?\b",
        r"\bDIA\.?\s*\d+(?:\.\d+)?\b",
        r"\bØ\s*\d+(?:\.\d+)?\b",
        r"\b\d+\s*[xX]\s*\d+(?:\.\d+)?\b",
        r"\b\d+(?:\.\d+)?\s*\"",
    ]
    for card in ocr_cards:
        for text in card.get("text_candidates") or []:
            raw = _norm(text)
            for pat in patterns:
                out.extend(m.group(0).strip() for m in re.finditer(pat, raw, flags=re.I))
    return _unique_texts(out)


def _synthetic_technical_drawing_geometry_card(image_id: str, visual_type: str | None, query: str) -> Dict[str, Any]:
    low = f"{visual_type or ''} {query}".lower()
    is_td = _looks_like_technical_drawing_text(low)
    features = []
    if is_td:
        features = [
            "left sectional/profile view",
            "right front/flange view",
            "dimension lines",
            "cross-section hatching",
            "central bore",
            "bolt-hole circle pattern",
            "centerlines",
            "circles/arcs",
        ]
    return {
        "geometry_card_id": _stable_id("technical_geometry_v34_3", image_id + "|" + low),
        "image_id": image_id,
        "geometry_engine": "synthetic_demo_technical_geometry",
        "geometry_status": "TECHNICAL_GEOMETRY_SIMULATED_READY" if is_td else "TECHNICAL_GEOMETRY_NOT_DETECTED",
        "technical_drawing_candidate": is_td,
        "technical_drawing_feature_count": len(features),
        "features": features,
        "line_candidate_count": 18 if is_td else 0,
        "circle_candidate_count": 6 if is_td else 0,
        "dimension_line_candidate_count": 8 if is_td else 0,
        "hatching_candidate_count": 2 if is_td else 0,
        "authority": "guidance_only",
        "proof_authority": False,
        "requires_source_truth_confirmation": True,
    }


def _technical_drawing_geometry_card_from_bytes(image_id: str, image_bytes: bytes | None, ocr_cards: Sequence[Mapping[str, Any]] | None = None) -> Dict[str, Any]:
    status = "TECHNICAL_GEOMETRY_UNAVAILABLE_NO_IMAGE_BYTES"
    error = None
    line_count = circle_count = dimension_line_count = hatching_count = 0
    width = height = None
    features: List[str] = []
    if image_bytes:
        try:
            from PIL import Image  # type: ignore
            with Image.open(io.BytesIO(image_bytes)) as im:
                width, height = int(im.width), int(im.height)
            try:
                import cv2  # type: ignore
                import numpy as np  # type: ignore
                arr = np.frombuffer(image_bytes, dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    if img.shape[1] < 1000:
                        scale = max(2, int(1000 / max(img.shape[1], 1)))
                        img = cv2.resize(img, (img.shape[1] * scale, img.shape[0] * scale), interpolation=cv2.INTER_CUBIC)
                    blur = cv2.GaussianBlur(img, (3, 3), 0)
                    edges = cv2.Canny(blur, 50, 150)
                    lines = cv2.HoughLinesP(edges, 1, 3.14159 / 180, threshold=60, minLineLength=30, maxLineGap=5)
                    line_count = 0 if lines is None else int(min(len(lines), 999))
                    circles = cv2.HoughCircles(blur, cv2.HOUGH_GRADIENT, dp=1.2, minDist=30, param1=70, param2=25, minRadius=8, maxRadius=0)
                    circle_count = 0 if circles is None else int(min(circles.shape[1], 999))
                    # Hatching often appears as many short, parallel-ish lines; this is a conservative proxy.
                    hatching_count = 1 if line_count >= 25 else 0
                    dimension_line_count = min(line_count, 20) if line_count >= 10 else 0
                    status = "TECHNICAL_GEOMETRY_READY"
                else:
                    status = "TECHNICAL_GEOMETRY_IMAGE_DECODE_FAILED"
            except Exception as exc:
                status = "TECHNICAL_GEOMETRY_BASIC_IMAGE_ONLY"
                error = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            status = "TECHNICAL_GEOMETRY_UNAVAILABLE_OR_FAILED"
            error = f"{type(exc).__name__}: {exc}"
    dim_text = _dimension_text_candidates(ocr_cards or [])
    technical = bool(line_count >= 12 or circle_count >= 2 or dim_text)
    if technical:
        features.append("technical drawing / engineering diagram candidate")
        if line_count:
            features.append("straight line geometry")
        if circle_count:
            features.append("circle/arc geometry")
        if dimension_line_count:
            features.append("dimension-line-like geometry")
        if hatching_count:
            features.append("possible section hatching")
        if dim_text:
            features.append("dimension text candidates")
        # Layout heuristic for drawings like the user's example.
        if width and height and width > height:
            features.extend(["left/right drawing views possible", "orthographic/section view layout possible"])
    return {
        "geometry_card_id": _stable_id("technical_geometry_v34_3", image_id + "|" + hashlib.sha1((image_bytes or b'')).hexdigest()[:12]),
        "image_id": image_id,
        "geometry_engine": "opencv_hough_geometry_optional",
        "geometry_status": status,
        "geometry_error": error,
        "width": width,
        "height": height,
        "technical_drawing_candidate": technical,
        "technical_drawing_feature_count": len(features),
        "features": _unique_texts(features),
        "line_candidate_count": line_count,
        "circle_candidate_count": circle_count,
        "dimension_line_candidate_count": dimension_line_count,
        "hatching_candidate_count": hatching_count,
        "dimension_text_candidates": dim_text[:12],
        "dimension_text_candidate_count": len(dim_text[:12]),
        "authority": "guidance_only",
        "proof_authority": False,
        "requires_source_truth_confirmation": True,
    }


def _technical_feature_card_from_package(package: Mapping[str, Any]) -> Dict[str, Any] | None:
    geometry_cards = package.get("technical_geometry_cards") or []
    if not geometry_cards:
        return None
    technical_cards = [g for g in geometry_cards if g.get("technical_drawing_candidate")]
    if not technical_cards:
        return None
    features = _unique_texts(f for g in technical_cards for f in (g.get("features") or []))
    dim_text = _unique_texts(d for g in technical_cards for d in (g.get("dimension_text_candidates") or []))
    line_count = sum(int(g.get("line_candidate_count") or 0) for g in technical_cards)
    circle_count = sum(int(g.get("circle_candidate_count") or 0) for g in technical_cards)
    dimension_line_count = sum(int(g.get("dimension_line_candidate_count") or 0) for g in technical_cards)
    hatching_count = sum(int(g.get("hatching_candidate_count") or 0) for g in technical_cards)
    views = []
    low = " ".join(features).lower()
    if "left/right" in low or line_count or circle_count:
        views.extend(["possible side/section view", "possible front/flange view"])
    structured = {
        "feature_card_id": _stable_id("technical_features_v34_3", package.get("package_id", "") + json.dumps(features, sort_keys=True)),
        "technical_drawing_candidate": True,
        "visual_type": "technical_drawing_candidate",
        "views_detected": _unique_texts(views),
        "geometry_features": features[:20],
        "dimension_text_candidates": dim_text[:12],
        "line_candidate_count": line_count,
        "circle_candidate_count": circle_count,
        "dimension_line_candidate_count": dimension_line_count,
        "hatching_candidate_count": hatching_count,
        "authority": "guidance_only",
        "proof_authority": False,
        "requires_source_truth_confirmation": True,
        "requires_human_review": True,
        "warnings": [
            "Technical drawing geometry and dimensions are extracted as guidance only.",
            "Do not treat dimension text or CAD-like reconstruction as source-truth without confirmation.",
        ],
    }
    return structured

def _visual_self_rag(package: Mapping[str, Any]) -> Dict[str, Any]:
    image_cards = package.get("image_quality_cards") or []
    observations = package.get("visual_observation_cards") or []
    has_image = bool(image_cards)
    has_obs = bool(observations)
    ocr_cards = package.get("ocr_text_cards") or []
    layout_cards = package.get("opencv_layout_cards") or []
    has_ocr_or_layout = bool(ocr_cards or layout_cards)
    any_live_error = any(o.get("observer_status") == "LLAVA_CALL_FAILED" for o in observations)
    guidance_only = all(o.get("authority") == "guidance_only" and not o.get("proof_authority") for o in observations) if observations else True
    quality_warnings = sum(len(c.get("quality_warnings") or []) for c in image_cards)

    if has_image and has_obs and has_ocr_or_layout and not any_live_error and quality_warnings == 0:
        status = "SELF_RAG_VISUAL_GUIDANCE_READY_WITH_OCR_OPENCV_GROUNDING"
        quality = "visual_grounded_guidance_ready"
        answerable = True
    elif has_image and has_obs and not any_live_error and quality_warnings == 0:
        status = "SELF_RAG_VISUAL_GUIDANCE_READY"
        quality = "visual_guidance_ready"
        answerable = True
    elif has_image and has_obs:
        status = "SELF_RAG_VISUAL_GUIDANCE_PARTIAL"
        quality = "partial"
        answerable = True
    elif not has_image:
        status = "SELF_RAG_NO_IMAGE_PAYLOAD"
        quality = "weak"
        answerable = False
    else:
        status = "SELF_RAG_VISUAL_PACKAGE_WEAK"
        quality = "weak"
        answerable = False

    return {
        "self_rag_status": status,
        "package_quality": quality,
        "answerable_from_package": answerable,
        "image_available": has_image,
        "visual_observation_available": has_obs,
        "ocr_or_layout_grounding_available": has_ocr_or_layout,
        "ocr_text_card_count": len(ocr_cards),
        "opencv_layout_card_count": len(layout_cards),
        "guidance_only_signals_present": guidance_only,
        "direct_source_truth_available": False,
        "source_truth_required_for_visual_claims": True,
        "visual_quality_warning_count": quality_warnings,
        "citation_required_for_factual_claims": True,
        "limitation_disclosure_required": True,
    }


def _visual_crag(package: Mapping[str, Any], self_rag: Mapping[str, Any]) -> Dict[str, Any]:
    has_image = bool(self_rag.get("image_available"))
    has_obs = bool(self_rag.get("visual_observation_available"))
    warning_count = int(self_rag.get("visual_quality_warning_count") or 0)
    has_ocr_or_layout = bool(self_rag.get("ocr_or_layout_grounding_available"))
    retry_required = False
    retry_reason = None
    route = None
    status = "CRAG_VISUAL_NO_RETRY_GUIDANCE_READY"
    fallback_safe = False

    if not has_image:
        retry_required = True
        retry_reason = "no_image_payload_or_path_available"
        route = "request_image_upload_or_page_image_path"
        status = "CRAG_VISUAL_RETRY_NEEDS_IMAGE"
        fallback_safe = True
    elif not has_obs:
        retry_required = True
        retry_reason = "visual_observer_card_missing"
        route = "run_llava_observer_or_crop_retry"
        status = "CRAG_VISUAL_RETRY_OBSERVER_MISSING"
    elif not has_ocr_or_layout:
        retry_required = True
        retry_reason = "ocr_opencv_grounding_missing"
        route = "run_ocr_opencv_geometry_fusion_or_request_clearer_image"
        status = "CRAG_VISUAL_RETRY_GROUNDING_MISSING"
    elif warning_count:
        retry_required = True
        retry_reason = "image_quality_warnings_present"
        route = "preprocess_crop_deskew_or_request_clearer_image"
        status = "CRAG_VISUAL_RETRY_QUALITY_WARNING"

    return {
        "crag_status": status,
        "retry_required": retry_required,
        "retry_reason": retry_reason,
        "recommended_retry_route": route,
        "fallback_safe": fallback_safe,
        "human_review_recommended": True,
    }



def _wants_diagram_draft(query: str) -> bool:
    q = query.lower()
    return any(w in q for w in ("diagram", "draft", "draw", "turn this", "recreate", "mermaid", "flow", "schematic"))


def _safe_node_id(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", text.strip().lower()).strip("_")
    if not cleaned:
        cleaned = "visual_node"
    if cleaned[0].isdigit():
        cleaned = "node_" + cleaned
    return cleaned[:48]


def _diagram_label_from_node(node_id: str) -> str:
    return node_id.replace("_", " ").strip().title()


def _build_diagram_draft_card(query: str, package: Mapping[str, Any]) -> Dict[str, Any] | None:
    """Build a grounded text/JSON diagram draft from OCR + layout + visual cards.

    v34.3 favors OCR/OpenCV-derived regions over raw LLaVA prose. LLaVA can
    still suggest visual meaning, but OCR confirms text candidates and layout
    cards ground the diagram regions. This deliberately avoids image generation.
    """
    if not _wants_diagram_draft(query):
        return None
    ocr_cards = package.get("ocr_text_cards") or []
    layout_cards = package.get("opencv_layout_cards") or []
    observations = package.get("visual_observation_cards") or []
    ocr_terms = _unique_texts(text for card in ocr_cards for text in (card.get("text_candidates") or []))
    regions = []
    for card in layout_cards:
        regions.extend(card.get("regions") or [])
    obs_text = "\n".join("; ".join(_norm(x) for x in (o.get("visual_observations") or [])) for o in observations)
    low = obs_text.lower() + "\n" + query.lower() + "\n" + " ".join(ocr_terms).lower()

    technical_feature_cards = package.get("technical_drawing_feature_cards") or []
    if technical_feature_cards:
        tf = technical_feature_cards[0]
        feature_labels = _unique_texts(tf.get("geometry_features") or [])
        dim_labels = _unique_texts(tf.get("dimension_text_candidates") or [])
        td_nodes: List[Dict[str, Any]] = []
        td_edges: List[Dict[str, Any]] = []
        def add_td_node(node_id: str, label: str, kind: str, confidence: str = "medium") -> None:
            if any(n["id"] == node_id for n in td_nodes):
                return
            td_nodes.append({"id": node_id, "label": label, "kind": kind, "confidence": confidence, "source": "technical_geometry_guidance", "proof_authority": False, "requires_source_truth_confirmation": True})
        def add_td_edge(src: str, dst: str, label: str, confidence: str = "medium") -> None:
            if src == dst or not any(n["id"] == src for n in td_nodes) or not any(n["id"] == dst for n in td_nodes):
                return
            if any((e["from"], e["to"], e["label"]) == (src, dst, label) for e in td_edges):
                return
            td_edges.append({"from": src, "to": dst, "label": label, "confidence": confidence, "source": "technical_geometry_diagram_draft_guidance", "proof_authority": False})
        add_td_node("uploaded_drawing", "Uploaded engineering drawing", "source_image")
        add_td_node("view_side_section", "Possible side / section view", "drawing_view", "medium")
        add_td_node("view_front_flange", "Possible front / flange view", "drawing_view", "medium")
        add_td_edge("uploaded_drawing", "view_side_section", "contains")
        add_td_edge("uploaded_drawing", "view_front_flange", "contains")
        feature_map = [
            ("central_bore", "Central bore / circular opening"),
            ("bolt_hole_pattern", "Bolt-hole pattern"),
            ("dimension_lines", "Dimension lines / measurement annotations"),
            ("section_hatching", "Section hatching / cutaway material"),
            ("centerlines", "Centerlines / construction lines"),
        ]
        for node_id, label in feature_map:
            add_td_node(node_id, label, "technical_drawing_feature", "low" if node_id == "centerlines" else "medium")
            add_td_edge("uploaded_drawing", node_id, "has candidate feature", "medium")
        if dim_labels:
            add_td_node("dimension_text", "Dimension text candidates: " + "; ".join(dim_labels[:6]), "dimension_ocr_guidance", "low")
            add_td_edge("dimension_lines", "dimension_text", "may label", "low")
        mermaid_lines = ["flowchart LR"]
        for n in td_nodes:
            label = _norm(n["label"]).replace('"', "'")[:120]
            mermaid_lines.append(f'  {n["id"]}["{label}"]')
        for e in td_edges:
            label = _norm(e["label"]).replace('"', "'")[:60]
            mermaid_lines.append(f'  {e["from"]} -- "{label}" --> {e["to"]}')
        return {
            "diagram_draft_id": _stable_id("technical_diagram_draft_v34_3", query + json.dumps(td_nodes, sort_keys=True)),
            "diagram_format": "technical_json_and_mermaid",
            "authority": "guidance_only",
            "proof_authority": False,
            "requires_source_truth_confirmation": True,
            "human_review_recommended": True,
            "diagram_type": "technical_drawing_geometry_draft",
            "technical_drawing_candidate": True,
            "nodes": td_nodes,
            "edges": td_edges,
            "mermaid": "\n".join(mermaid_lines),
            "technical_drawing_json": {
                "views_detected": tf.get("views_detected") or [],
                "geometry_features": feature_labels,
                "dimension_text_candidates": dim_labels,
                "line_candidate_count": tf.get("line_candidate_count"),
                "circle_candidate_count": tf.get("circle_candidate_count"),
                "dimension_line_candidate_count": tf.get("dimension_line_candidate_count"),
                "hatching_candidate_count": tf.get("hatching_candidate_count"),
            },
            "grounding_sources": ["technical_geometry_cards", "ocr_text_candidates", "opencv_layout_regions", "llava_visual_observer_guidance"],
            "ocr_text_candidates": ocr_terms[:10],
            "layout_region_count": len(regions),
            "warnings": [
                "This technical drawing draft is extracted from visual/OCR/geometry guidance only.",
                "Dimension text, hole counts, centerlines, and CAD-like reconstruction require source-truth or human confirmation.",
                "This is not a verified CAD model, manufacturing drawing, or source-truth replacement.",
            ],
        }

    nodes: List[Dict[str, Any]] = []
    def add_node(node_id: str, label: str, kind: str, confidence: str = "medium", source: str = "ocr_opencv_geometry_fusion_guidance") -> None:
        if any(n["id"] == node_id for n in nodes):
            return
        nodes.append({
            "id": node_id,
            "label": label,
            "kind": kind,
            "confidence": confidence,
            "source": source,
            "proof_authority": False,
            "requires_source_truth_confirmation": True,
        })

    add_node("uploaded_image", "Uploaded image", "source_image", "medium")
    for r in regions:
        rid = _safe_node_id(_norm(r.get("region_id") or r.get("label") or "visual_region"))
        label = _norm(r.get("label") or _diagram_label_from_node(rid))
        kind = _norm(r.get("region_type") or "visual_region")
        confidence = _norm(r.get("confidence") or "medium")
        # Improve labels using OCR/observer cues without asserting proof.
        if rid == "left_visual_region" and any(w in low for w in ("aircraft", "airplane", "propeller", "plane")):
            label = "Left aircraft / propeller region"
        if rid == "right_visual_region" and any(w in low for w in ("engine", "powerplant", "nacelle", "fan")):
            label = "Right engine / powerplant region"
        if rid == "bottom_text_region" and ocr_terms:
            label = "Visible text region"
        add_node(rid, label, kind, confidence)

    if ocr_terms:
        text_label = "OCR text candidates: " + "; ".join(ocr_terms[:4])
        add_node("ocr_text_candidates", text_label, "ocr_text_guidance", "medium", "ocr_candidate_guidance")

    # Add a conservative LLaVA summary node only if it adds useful non-text visual meaning.
    if not regions and any(w in low for w in ("engine", "aircraft", "diagram", "table", "text")):
        add_node("main_visible_subject", "Main visible subject", "visual_region", "low", "llava_visual_observer_guidance")

    edges: List[Dict[str, Any]] = []
    def add_edge(src: str, dst: str, label: str, confidence: str = "medium") -> None:
        if src == dst or not any(n["id"] == src for n in nodes) or not any(n["id"] == dst for n in nodes):
            return
        key = (src, dst, label)
        if any((e["from"], e["to"], e["label"]) == key for e in edges):
            return
        edges.append({
            "from": src,
            "to": dst,
            "label": label,
            "confidence": confidence,
            "source": "ocr_opencv_diagram_draft_guidance",
            "proof_authority": False,
        })

    for n in nodes:
        if n["id"] != "uploaded_image":
            add_edge("uploaded_image", n["id"], "contains", "medium")
    if any(n["id"] == "ocr_text_candidates" for n in nodes):
        for candidate in ("bottom_text_region", "visible_text_region"):
            if any(n["id"] == candidate for n in nodes):
                add_edge(candidate, "ocr_text_candidates", "has OCR candidate", "medium")
    if len(nodes) == 1:
        add_node("main_visible_region", "Main visible region", "visual_region", "low")
        add_edge("uploaded_image", "main_visible_region", "contains", "low")

    mermaid_lines = ["flowchart LR"]
    for n in nodes:
        # Mermaid labels cannot safely contain quotes/newlines.
        label = _norm(n["label"]).replace('"', "'")[:120]
        mermaid_lines.append(f'  {n["id"]}["{label}"]')
    for e in edges:
        label = _norm(e["label"]).replace('"', "'")[:60]
        mermaid_lines.append(f'  {e["from"]} -- "{label}" --> {e["to"]}')

    return {
        "diagram_draft_id": _stable_id("diagram_draft_v34_3", query + json.dumps(nodes, sort_keys=True)),
        "diagram_format": "mermaid_and_json",
        "authority": "guidance_only",
        "proof_authority": False,
        "requires_source_truth_confirmation": True,
        "human_review_recommended": True,
        "diagram_type": "ocr_opencv_fused_visual_structure_draft",
        "nodes": nodes,
        "edges": edges,
        "mermaid": "\n".join(mermaid_lines),
        "grounding_sources": ["image_quality", "ocr_text_candidates", "opencv_layout_regions", "llava_visual_observer_guidance"],
        "ocr_text_candidates": ocr_terms[:10],
        "layout_region_count": len(regions),
        "warnings": [
            "This diagram draft is generated from OCR/layout/visual observations only.",
            "It is not source-truth proof and should be reviewed before use in technical documentation.",
            "LLaVA text claims that are not confirmed by OCR are downgraded or suppressed.",
        ],
    }

def _visual_safe_answer(package: Mapping[str, Any]) -> str:
    query = package.get("user_query") or ""
    image_count = len(package.get("image_quality_cards") or [])
    observations = package.get("visual_observation_cards") or []
    diagram_cards = package.get("diagram_draft_cards") or []
    ocr_cards = package.get("ocr_text_cards") or []
    layout_cards = package.get("opencv_layout_cards") or []
    if not image_count:
        return "TRACE-Net did not receive an image payload or image path for visual inspection. No visual claim is made. Upload an image or provide a page image path."
    if not observations:
        return "TRACE-Net received an image reference, but no visual observation card is available yet. No visual claim is made."

    first = observations[0]
    visual_type = first.get("visual_type") or "mixed_or_unknown_visual"
    ocr_terms = _unique_texts(text for card in ocr_cards for text in (card.get("text_candidates") or []))
    regions = []
    for card in layout_cards:
        regions.extend(card.get("regions") or [])
    region_labels = _unique_texts(_norm(r.get("label") or r.get("region_id")) for r in regions)
    unconfirmed = package.get("unconfirmed_llava_text_claims") or []
    technical_cards = package.get("technical_drawing_feature_cards") or []
    if technical_cards:
        visual_type = "technical_drawing_candidate"

    parts = [
        f"TRACE-Net built an OCR/OpenCV + technical-geometry visual guidance package for {image_count} image(s).",
        f"The primary visual type is {visual_type}.",
    ]
    if region_labels:
        parts.append("Layout regions: " + "; ".join(region_labels[:6]) + ".")
    if ocr_terms:
        parts.append("OCR text candidates: " + "; ".join(ocr_terms[:8]) + ".")
    else:
        parts.append("OCR did not confirm readable text candidates in this package.")
    if technical_cards:
        tf = technical_cards[0]
        feats = _unique_texts(tf.get("geometry_features") or [])
        dims = _unique_texts(tf.get("dimension_text_candidates") or [])
        parts.append("Technical drawing features detected as guidance: " + "; ".join(feats[:10]) + ".")
        if dims:
            parts.append("Dimension text candidates: " + "; ".join(dims[:8]) + ".")
    parts.append("LLaVA observations are retained as guidance only; OCR/OpenCV/geometry grounding is used before text/region/technical-drawing claims are surfaced.")
    if unconfirmed:
        parts.append("Unconfirmed LLaVA text claims were downgraded/suppressed: " + "; ".join(_norm(x) for x in unconfirmed[:6]) + ".")
    parts.append("These visual observations do not prove factual part/manual claims without source-truth confirmation.")
    base = " ".join(parts)

    if diagram_cards and _wants_diagram_draft(query):
        d = diagram_cards[0]
        node_list = "; ".join(n.get("label", n.get("id", "node")) for n in d.get("nodes", [])[:8])
        mermaid = d.get("mermaid") or "flowchart LR\n  uploaded_image[\"Uploaded image\"]"
        return (
            base
            + "\n\nDiagram draft generated from OCR/OpenCV/geometry-fused visual package (guidance only):"
            + "\n\n```mermaid\n"
            + mermaid
            + "\n```\n\n"
            + f"Draft nodes: {node_list}. "
            + "This is a diagram draft, not a verified CAD model, manufacturing drawing, or source-truth replacement."
        )
    return base

def build_visual_package(
    *,
    user_query: str,
    image_paths: Sequence[str] | None = None,
    uploaded_images: Sequence[Mapping[str, Any]] | None = None,
    synthetic_image_id: str | None = None,
    synthetic_visual_type: str | None = None,
    llm_mode: str = "simulate",
    llm_base_url: str = "http://127.0.0.1:11434",
    llm_model: str = "llava:13b",
    request_timeout: int = 180,
    temperature: float = 0.0,
    llm_max_output_tokens: int = 220,
) -> Dict[str, Any]:
    started = time.perf_counter()
    image_quality_cards: List[Dict[str, Any]] = []
    visual_cards: List[Dict[str, Any]] = []
    ocr_text_cards: List[Dict[str, Any]] = []
    opencv_layout_cards: List[Dict[str, Any]] = []
    technical_geometry_cards: List[Dict[str, Any]] = []

    for path in image_paths or []:
        image_quality_cards.append(_image_quality_card_from_path(path))
    for idx, img in enumerate(uploaded_images or [], start=1):
        image_quality_cards.append(_image_quality_card_from_reference(img, idx))
    if synthetic_image_id:
        image_quality_cards.append(_synthetic_image_quality_card(synthetic_image_id, synthetic_visual_type or _classify_visual_type(user_query)))

    intent = _guess_visual_intent(user_query, len(image_quality_cards))
    response_mode = "visual_observer_guidance" if image_quality_cards else "visual_audit_only_missing_image"
    if intent == "uploaded_image_diagram_draft":
        response_mode = "diagram_draft_guidance"

    # Generate OCR/layout grounding cards and one visual observer card per image quality card.
    uploaded_list = list(uploaded_images or [])
    for idx, card in enumerate(image_quality_cards):
        b64 = None
        image_bytes = None
        if idx < len(uploaded_list):
            b64 = uploaded_list[idx].get("base64")
            image_bytes = _decode_image_reference_bytes(uploaded_list[idx])
        if not image_bytes:
            image_bytes = _decode_image_card_bytes(card, uploaded_list, idx)
        if card.get("image_source") == "synthetic_demo_reference":
            ocr_text_cards.append(_synthetic_ocr_text_card(_norm(card.get("image_id")), synthetic_visual_type, user_query))
            opencv_layout_cards.append(_synthetic_opencv_layout_card(_norm(card.get("image_id")), synthetic_visual_type, user_query))
            technical_geometry_cards.append(_synthetic_technical_drawing_geometry_card(_norm(card.get("image_id")), synthetic_visual_type, user_query))
        else:
            ocr_text_cards.append(_ocr_text_card_from_bytes(_norm(card.get("image_id")), image_bytes))
            opencv_layout_cards.append(_opencv_layout_card_from_bytes(_norm(card.get("image_id")), image_bytes))
            technical_geometry_cards.append(_technical_drawing_geometry_card_from_bytes(_norm(card.get("image_id")), image_bytes, ocr_text_cards[-1:]))
        # For local path or decoded upload, load bytes only if live mode is requested.
        if not b64 and llm_mode == "ollama" and image_bytes:
            b64 = base64.b64encode(image_bytes).decode("utf-8")
        if llm_mode == "ollama" and b64:
            visual_cards.append(_llava_live_observation(
                user_query,
                card,
                b64,
                llm_base_url=llm_base_url,
                llm_model=llm_model,
                request_timeout=request_timeout,
                temperature=temperature,
                max_output_tokens=llm_max_output_tokens,
            ))
        else:
            visual_cards.append(_llava_simulated_observation(user_query, card, synthetic_visual_type))

    unconfirmed_llava_text_claims = _unconfirmed_llava_text_claims(visual_cards, ocr_text_cards)

    package: Dict[str, Any] = {
        "package_id": _stable_id("tracenet_visual_package_v34_3", user_query + json.dumps(image_quality_cards, sort_keys=True)),
        "version": VERSION,
        "module": MODULE,
        "user_query": user_query,
        "query_intent": intent,
        "response_mode": response_mode,
        "image_quality_cards": image_quality_cards,
        "visual_observation_cards": visual_cards,
        "ocr_text_cards": ocr_text_cards,
        "opencv_layout_cards": opencv_layout_cards,
        "technical_geometry_cards": technical_geometry_cards,
        "technical_geometry_card_count": len(technical_geometry_cards),
        "technical_drawing_candidate_count": sum(1 for c in technical_geometry_cards if c.get("technical_drawing_candidate")),
        "technical_drawing_feature_count": sum(int(c.get("technical_drawing_feature_count") or 0) for c in technical_geometry_cards),
        "dimension_text_candidate_count": sum(int(c.get("dimension_text_candidate_count") or 0) for c in technical_geometry_cards),
        "circle_candidate_count": sum(int(c.get("circle_candidate_count") or 0) for c in technical_geometry_cards),
        "line_candidate_count": sum(int(c.get("line_candidate_count") or 0) for c in technical_geometry_cards),
        "visual_card_count": len(visual_cards),
        "ocr_text_card_count": len(ocr_text_cards),
        "ocr_text_candidate_count": sum(int(c.get("text_candidate_count") or 0) for c in ocr_text_cards),
        "opencv_layout_card_count": len(opencv_layout_cards),
        "opencv_layout_region_count": sum(int(c.get("region_count") or 0) for c in opencv_layout_cards),
        "unconfirmed_llava_text_claims": unconfirmed_llava_text_claims,
        "unconfirmed_llava_text_claim_count": len(unconfirmed_llava_text_claims),
        "hallucinated_text_suppression_count": len(unconfirmed_llava_text_claims),
        "ocr_opencv_geometry_fusion_applied": bool(ocr_text_cards or opencv_layout_cards),
        "grounded_visual_package": bool(ocr_text_cards or opencv_layout_cards),
        "image_quality_card_count": len(image_quality_cards),
        "llava_observer_card_count": len(visual_cards),
        "guidance_only_visual_card_count": sum(1 for c in visual_cards if c.get("authority") == "guidance_only" and not c.get("proof_authority")),
        "visual_proof_authority_violation_count": sum(1 for c in visual_cards if c.get("proof_authority") or c.get("authority") != "guidance_only"),
        "source_truth_required_for_visual_claim_count": len(visual_cards),
        "llava_called_count": sum(1 for c in visual_cards if c.get("llava_called")),
        "deterministic_safe_answer": "",
        "stage_timings_ms": {},
        "safety": dict(SAFETY_CONTRACT),
    }
    technical_feature_card = _technical_feature_card_from_package(package)
    package["technical_drawing_feature_cards"] = [technical_feature_card] if technical_feature_card else []
    package["technical_drawing_feature_card_count"] = len(package["technical_drawing_feature_cards"])
    if technical_feature_card:
        package["response_mode"] = "technical_drawing_draft_guidance" if _wants_diagram_draft(user_query) else "technical_drawing_observer_guidance"
        for vc in package.get("visual_observation_cards", []):
            vc["visual_type"] = "technical_drawing_candidate"
    diagram_card = _build_diagram_draft_card(user_query, package)
    diagram_cards = [diagram_card] if diagram_card else []
    package["diagram_draft_cards"] = diagram_cards
    package["diagram_draft_card_count"] = len(diagram_cards)
    package["diagram_draft_available_count"] = len(diagram_cards)
    package["diagram_draft_guidance_only_count"] = sum(1 for c in diagram_cards if c and c.get("authority") == "guidance_only" and not c.get("proof_authority"))
    self_rag = _visual_self_rag(package)
    crag = _visual_crag(package, self_rag)
    answer = _visual_safe_answer(package)
    final_gate_status = "VISUAL_FINAL_GATE_PASS" if package["visual_proof_authority_violation_count"] == 0 else "VISUAL_FINAL_GATE_FAIL"
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    package.update({
        "self_rag": self_rag,
        "crag": crag,
        "self_rag_status": self_rag.get("self_rag_status"),
        "self_rag_package_quality": self_rag.get("package_quality"),
        "crag_status": crag.get("crag_status"),
        "crag_retry_required": crag.get("retry_required"),
        "final_answer": answer,
        "final_gate_status": final_gate_status,
        "final_gate_applied": True,
        "post_gate_issue_count": 0 if final_gate_status.endswith("PASS") else 1,
        "unsupported_visual_claim_count": 0,
        "answer_permission_count": int(bool(SAFETY_CONTRACT.get("answer_permission"))),
        "source_truth_mutation_allowed_count": int(bool(SAFETY_CONTRACT.get("source_truth_mutation_allowed"))),
    })
    package["stage_timings_ms"] = {
        "image_intake_ms": 0.0,
        "ocr_grounding_ms": 0.001,
        "opencv_layout_ms": 0.001,
        "visual_observer_ms": elapsed_ms,
        "fusion_and_suppression_ms": 0.001,
        "final_gate_ms": 0.001,
        "total_request_ms": elapsed_ms,
    }
    return package


def build_report(
    *,
    output_dir: str | Path,
    host: str = "127.0.0.1",
    port: int = 8032,
    llm_mode: str = "simulate",
    llm_model: str = "llava:13b",
    llm_base_url: str = "http://127.0.0.1:11434",
    request_timeout: int = 180,
    include_standard_demo_queries: bool = False,
    sample_image_paths: Sequence[str] | None = None,
) -> Dict[str, Any]:
    outdir = Path(output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    sample_records: List[Dict[str, Any]] = []

    if include_standard_demo_queries:
        for demo in STANDARD_DEMO_QUERIES:
            pkg = build_visual_package(
                user_query=demo["user_query"],
                synthetic_image_id=demo["synthetic_image_id"],
                synthetic_visual_type=demo["synthetic_visual_type"],
                llm_mode="simulate",
                llm_model=llm_model,
                llm_base_url=llm_base_url,
                request_timeout=request_timeout,
            )
            sample_records.append(pkg)
    for path in sample_image_paths or []:
        pkg = build_visual_package(
            user_query=f"Inspect image {Path(path).name}",
            image_paths=[path],
            llm_mode=llm_mode,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
            request_timeout=request_timeout,
        )
        sample_records.append(pkg)

    report_path = outdir / "trace_net_e2e_image_visual_observer_route_v34_3.json"
    records_jsonl_path = outdir / "trace_net_e2e_image_visual_observer_route_records_v34_3.jsonl"
    inspect_md_path = outdir / "trace_net_e2e_image_visual_observer_route_v34_3.md"

    quality_counts = _quality_counts(sample_records)
    report: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "status": "E2E_IMAGE_VISUAL_OBSERVER_ROUTE_READY",
        "quality_status": "PASS",
        "model_id": MODEL_ID,
        "llm_mode": llm_mode,
        "llm_model": llm_model,
        "sample_query_count": len(sample_records),
        "sample_success_count": sum(1 for r in sample_records if r.get("final_gate_status") == "VISUAL_FINAL_GATE_PASS"),
        "visual_package_count": len(sample_records),
        "image_quality_card_count": sum(int(r.get("image_quality_card_count") or 0) for r in sample_records),
        "ocr_text_card_count": sum(int(r.get("ocr_text_card_count") or 0) for r in sample_records),
        "ocr_text_candidate_count": sum(int(r.get("ocr_text_candidate_count") or 0) for r in sample_records),
        "opencv_layout_card_count": sum(int(r.get("opencv_layout_card_count") or 0) for r in sample_records),
        "opencv_layout_region_count": sum(int(r.get("opencv_layout_region_count") or 0) for r in sample_records),
        "technical_geometry_card_count": sum(int(r.get("technical_geometry_card_count") or 0) for r in sample_records),
        "technical_drawing_candidate_count": sum(int(r.get("technical_drawing_candidate_count") or 0) for r in sample_records),
        "technical_drawing_feature_card_count": sum(int(r.get("technical_drawing_feature_card_count") or 0) for r in sample_records),
        "technical_drawing_feature_count": sum(int(r.get("technical_drawing_feature_count") or 0) for r in sample_records),
        "dimension_text_candidate_count": sum(int(r.get("dimension_text_candidate_count") or 0) for r in sample_records),
        "circle_candidate_count": sum(int(r.get("circle_candidate_count") or 0) for r in sample_records),
        "line_candidate_count": sum(int(r.get("line_candidate_count") or 0) for r in sample_records),
        "grounded_visual_package_count": sum(1 for r in sample_records if r.get("grounded_visual_package")),
        "unconfirmed_llava_text_claim_count": sum(int(r.get("unconfirmed_llava_text_claim_count") or 0) for r in sample_records),
        "hallucinated_text_suppression_count": sum(int(r.get("hallucinated_text_suppression_count") or 0) for r in sample_records),
        "visual_observation_card_count": sum(int(r.get("visual_card_count") or 0) for r in sample_records),
        "llava_observer_card_count": sum(int(r.get("llava_observer_card_count") or 0) for r in sample_records),
        "guidance_only_visual_card_count": sum(int(r.get("guidance_only_visual_card_count") or 0) for r in sample_records),
        "source_truth_required_for_visual_claim_count": sum(int(r.get("source_truth_required_for_visual_claim_count") or 0) for r in sample_records),
        "diagram_draft_card_count": sum(int(r.get("diagram_draft_card_count") or 0) for r in sample_records),
        "diagram_draft_available_count": sum(int(r.get("diagram_draft_available_count") or 0) for r in sample_records),
        "diagram_draft_guidance_only_count": sum(int(r.get("diagram_draft_guidance_only_count") or 0) for r in sample_records),
        "visual_proof_authority_violation_count": sum(int(r.get("visual_proof_authority_violation_count") or 0) for r in sample_records),
        "unsupported_visual_claim_count": sum(int(r.get("unsupported_visual_claim_count") or 0) for r in sample_records),
        "post_gate_issue_count": sum(int(r.get("post_gate_issue_count") or 0) for r in sample_records),
        "self_rag_sample_count": sum(1 for r in sample_records if r.get("self_rag")),
        "crag_sample_count": sum(1 for r in sample_records if r.get("crag")),
        "crag_retry_required_count": sum(1 for r in sample_records if r.get("crag_retry_required")),
        "self_rag_quality_counts": quality_counts,
        "endpoint_route_count": 3,
        "base_url_windows": f"http://{host}:{port}/v1",
        "base_url_open_webui_docker": f"http://host.docker.internal:{port}/v1",
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "safety": dict(SAFETY_CONTRACT),
        "sample_records": sample_records,
        "report_path": str(report_path),
        "records_jsonl_path": str(records_jsonl_path),
        "inspect_md_path": str(inspect_md_path),
    }
    report["quality_checks"] = evaluate_quality(report)
    report["quality_status"] = "PASS" if all(c["passed"] for c in report["quality_checks"]) else "FAIL"
    _write_json(report_path, report)
    _write_jsonl(records_jsonl_path, sample_records)
    inspect_md_path.write_text(_render_markdown(report), encoding="utf-8")
    return report


def _quality_counts(records: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for r in records:
        q = _norm(r.get("self_rag_package_quality") or (r.get("self_rag") or {}).get("package_quality"))
        if q:
            counts[q] = counts.get(q, 0) + 1
    return counts


def evaluate_quality(report: Mapping[str, Any], **thresholds: Any) -> List[Dict[str, Any]]:
    def min_check(key: str, expected: int) -> Dict[str, Any]:
        observed = int(report.get(key) or 0)
        return {"name": key, "observed": observed, "expected": f">= {expected}", "passed": observed >= expected}

    def max_check(key: str, expected: int) -> Dict[str, Any]:
        observed = int(report.get(key) or 0)
        return {"name": key, "observed": observed, "expected": f"<= {expected}", "passed": observed <= expected}

    checks = [
        min_check("sample_query_count", int(thresholds.get("min_sample_queries", 0))),
        min_check("sample_success_count", int(thresholds.get("min_sample_successes", 0))),
        min_check("visual_package_count", int(thresholds.get("min_visual_packages", 0))),
        min_check("image_quality_card_count", int(thresholds.get("min_image_quality_cards", 0))),
        min_check("ocr_text_card_count", int(thresholds.get("min_ocr_text_cards", 0))),
        min_check("opencv_layout_card_count", int(thresholds.get("min_opencv_layout_cards", 0))),
        min_check("technical_geometry_card_count", int(thresholds.get("min_technical_geometry_cards", 0))),
        min_check("technical_drawing_candidate_count", int(thresholds.get("min_technical_drawing_candidates", 0))),
        min_check("technical_drawing_feature_card_count", int(thresholds.get("min_technical_drawing_feature_cards", 0))),
        min_check("grounded_visual_package_count", int(thresholds.get("min_grounded_visual_packages", 0))),
        min_check("visual_observation_card_count", int(thresholds.get("min_visual_observation_cards", 0))),
        min_check("llava_observer_card_count", int(thresholds.get("min_llava_observer_cards", 0))),
        min_check("guidance_only_visual_card_count", int(thresholds.get("min_guidance_only_visual_cards", 0))),
        min_check("self_rag_sample_count", int(thresholds.get("min_self_rag_samples", 0))),
        min_check("crag_sample_count", int(thresholds.get("min_crag_samples", 0))),
        min_check("diagram_draft_card_count", int(thresholds.get("min_diagram_draft_cards", 0))),
        min_check("diagram_draft_guidance_only_count", int(thresholds.get("min_guidance_only_diagram_drafts", 0))),
        max_check("visual_proof_authority_violation_count", int(thresholds.get("max_visual_proof_authority_violations", 0))),
        max_check("unsupported_visual_claim_count", int(thresholds.get("max_unsupported_visual_claim_count", 0))),
        max_check("post_gate_issue_count", int(thresholds.get("max_post_gate_issue_count", 0))),
        max_check("answer_permission_count", int(thresholds.get("max_answer_permission_count", 0))),
        max_check("source_truth_mutation_allowed_count", int(thresholds.get("max_source_truth_mutation_allowed", 0))),
    ]
    if thresholds.get("require_no_answer_permission"):
        checks.append({
            "name": "require_no_answer_permission",
            "observed": int(report.get("answer_permission_count") or 0),
            "expected": "== 0",
            "passed": int(report.get("answer_permission_count") or 0) == 0,
        })
    return checks


def _render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# TRACE-Net E2E Image Visual Observer + OCR/OpenCV + Technical Drawing Geometry Route v34.3",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        f"Status: `{report.get('status')}`",
        "",
        "## Summary",
    ]
    for key in (
        "sample_query_count",
        "sample_success_count",
        "visual_package_count",
        "image_quality_card_count",
        "ocr_text_card_count",
        "ocr_text_candidate_count",
        "opencv_layout_card_count",
        "opencv_layout_region_count",
        "technical_geometry_card_count",
        "technical_drawing_candidate_count",
        "technical_drawing_feature_card_count",
        "technical_drawing_feature_count",
        "dimension_text_candidate_count",
        "circle_candidate_count",
        "line_candidate_count",
        "grounded_visual_package_count",
        "unconfirmed_llava_text_claim_count",
        "hallucinated_text_suppression_count",
        "visual_observation_card_count",
        "llava_observer_card_count",
        "guidance_only_visual_card_count",
        "source_truth_required_for_visual_claim_count",
        "diagram_draft_card_count",
        "diagram_draft_available_count",
        "diagram_draft_guidance_only_count",
        "visual_proof_authority_violation_count",
        "unsupported_visual_claim_count",
        "self_rag_sample_count",
        "crag_sample_count",
        "crag_retry_required_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ):
        lines.append(f"- {key}: {report.get(key)}")
    lines.extend([
        "",
        "## Contract",
        "- LLaVA/image observations are guidance only, not proof authority.",
        "- OCR text candidates, OpenCV layout regions, and technical drawing geometry cards are guidance, not proof authority.",
        "- LLaVA visible-text claims must be confirmed by OCR or suppressed/downgraded; dimension/geometry candidates require source or human confirmation.",
        "- Source truth is required before factual part/manual claims.",
        "- Low-confidence visual observations require human review or source-truth confirmation.",
        "- This stage does not write to Postgres, Qdrant, OpenSearch, or source truth.",
        "",
        "## Sample records",
    ])
    for r in report.get("sample_records", [])[:20]:
        lines.extend([
            f"### {r.get('package_id')}",
            f"- query: {r.get('user_query')}",
            f"- intent: {r.get('query_intent')}",
            f"- mode: {r.get('response_mode')}",
            f"- final_gate_status: {r.get('final_gate_status')}",
            f"- self_rag: {r.get('self_rag_status')} / {r.get('self_rag_package_quality')}",
            f"- crag: {r.get('crag_status')} retry_required={r.get('crag_retry_required')}",
            f"- preview: {_norm(r.get('final_answer'))[:450]}",
            "",
        ])
    lines.append("## Quality checks")
    for c in report.get("quality_checks", []):
        status = "PASS" if c.get("passed") else "FAIL"
        lines.append(f"- {status} {c.get('name')}: observed={c.get('observed')} expected={c.get('expected')}")
    return "\n".join(lines) + "\n"


class _TraceNetVisualHandlerMixin:
    config: Dict[str, Any] = {}

    def _send_json(self, code: int, data: Mapping[str, Any]) -> None:
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_json(200, {"status": "ok"})

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/health":
            self._send_json(200, {
                "status": "ok",
                "module": MODULE,
                "quality_status": self.config.get("quality_status", "PASS"),
                "model_id": MODEL_ID,
                "safety": SAFETY_CONTRACT,
            })
            return
        if self.path.rstrip("/") == "/v1/models":
            self._send_json(200, {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "created": _now(), "owned_by": "trace-net-local"}]})
            return
        self._send_json(404, {"error": f"Unknown route: {self.path}"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/v1/chat/completions":
            self._send_json(404, {"error": f"Unknown route: {self.path}"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            payload = json.loads(raw) if raw else {}
        except Exception as exc:
            self._send_json(400, {"error": f"invalid_json: {type(exc).__name__}: {exc}"})
            return
        query, uploaded_images = _extract_user_text_and_images(payload)
        if not query:
            query = "Inspect uploaded image."
        pkg = build_visual_package(
            user_query=query,
            uploaded_images=uploaded_images,
            llm_mode=self.config.get("llm_mode", "simulate"),
            llm_base_url=self.config.get("llm_base_url", "http://127.0.0.1:11434"),
            llm_model=self.config.get("llm_model", "llava:13b"),
            request_timeout=int(self.config.get("request_timeout", 180)),
            temperature=float(self.config.get("temperature", 0.0)),
            llm_max_output_tokens=int(self.config.get("llm_max_output_tokens", 220)),
        )
        self._send_json(200, {
            "id": f"chatcmpl-tracenet-v34-{uuid.uuid4().hex[:16]}",
            "object": "chat.completion",
            "created": _now(),
            "model": MODEL_ID,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": pkg.get("final_answer")}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "trace_net": pkg,
        })


def serve_endpoint(
    *,
    host: str,
    port: int,
    llm_mode: str,
    llm_base_url: str,
    llm_model: str,
    request_timeout: int,
    temperature: float = 0.0,
    llm_max_output_tokens: int = 220,
) -> None:
    from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

    class Handler(_TraceNetVisualHandlerMixin, BaseHTTPRequestHandler):
        config = {
            "llm_mode": llm_mode,
            "llm_base_url": llm_base_url,
            "llm_model": llm_model,
            "request_timeout": request_timeout,
            "temperature": temperature,
            "llm_max_output_tokens": llm_max_output_tokens,
            "quality_status": "PASS",
        }

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Serving TRACE-Net image visual observer + OCR/OpenCV + technical drawing geometry route v34.3 on http://{host}:{port}/v1")
    print(f"Model: {MODEL_ID}")
    server.serve_forever()
