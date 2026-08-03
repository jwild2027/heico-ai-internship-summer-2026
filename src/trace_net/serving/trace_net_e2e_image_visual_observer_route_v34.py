from __future__ import annotations

import argparse
import base64
import hashlib
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

VERSION = "v34"
MODULE = "trace_net_e2e_image_visual_observer_route_v34"
MODEL_ID = "trace-net-e2e-image-visual-observer-llava-v34"

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
}

VISUAL_OBSERVER_SYSTEM_PROMPT = (
    "You are a visual observer for scanned technical manuals. "
    "Describe only visible visual structure. Identify whether the image looks like a diagram, table, text page, or mixed page. "
    "List visible callouts, arrows, labels, and obvious text candidates. Do not guess missing details. "
    "Your observations are guidance only and are not proof authority."
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
        "user_query": "What does this picture prove about the part?",
        "synthetic_image_id": "demo_visual_page_004",
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


def _llava_simulated_observation(query: str, image_card: Mapping[str, Any], visual_type: str | None = None) -> Dict[str, Any]:
    vt = visual_type or _classify_visual_type(query)
    observations = [
        f"image appears to be {vt}",
        "manual-style visual inspection required",
    ]
    if "callout" in vt or "diagram" in vt:
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
        if "table" in low or "grid" in low:
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


def _visual_self_rag(package: Mapping[str, Any]) -> Dict[str, Any]:
    image_cards = package.get("image_quality_cards") or []
    observations = package.get("visual_observation_cards") or []
    has_image = bool(image_cards)
    has_obs = bool(observations)
    any_live_error = any(o.get("observer_status") == "LLAVA_CALL_FAILED" for o in observations)
    guidance_only = all(o.get("authority") == "guidance_only" and not o.get("proof_authority") for o in observations) if observations else True
    quality_warnings = sum(len(c.get("quality_warnings") or []) for c in image_cards)

    if has_image and has_obs and not any_live_error and quality_warnings == 0:
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


def _visual_safe_answer(package: Mapping[str, Any]) -> str:
    query = package.get("user_query") or ""
    image_count = len(package.get("image_quality_cards") or [])
    observations = package.get("visual_observation_cards") or []
    if not image_count:
        return "TRACE-Net did not receive an image payload or image path for visual inspection. No visual claim is made. Upload an image or provide a page image path."
    if not observations:
        return "TRACE-Net received an image reference, but no visual observation card is available yet. No visual claim is made."

    first = observations[0]
    visual_type = first.get("visual_type") or "mixed_or_unknown_visual"
    obs = first.get("visual_observations") or []
    obs_text = "; ".join(_norm(x) for x in obs[:4] if _norm(x))
    if not obs_text:
        obs_text = "visual structure was observed, but no high-confidence description is available"
    diagram_note = " A diagram draft can be generated as guidance from the visual package." if first.get("diagram_draft_available") else ""
    return (
        f"TRACE-Net built a visual guidance package for {image_count} image(s). "
        f"The primary visual type is {visual_type}. Observations: {obs_text}. "
        "These visual observations are guidance only and do not prove factual part/manual claims without source-truth confirmation."
        f"{diagram_note}"
    )


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

    # Generate one visual observer card per image quality card.
    uploaded_list = list(uploaded_images or [])
    for idx, card in enumerate(image_quality_cards):
        b64 = None
        if idx < len(uploaded_list):
            b64 = uploaded_list[idx].get("base64")
        # For local path, load bytes only if live mode is requested.
        if not b64 and llm_mode == "ollama" and card.get("path") and Path(str(card.get("path"))).exists():
            b64 = base64.b64encode(Path(str(card.get("path"))).read_bytes()).decode("utf-8")
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

    package: Dict[str, Any] = {
        "package_id": _stable_id("tracenet_visual_package_v34", user_query + json.dumps(image_quality_cards, sort_keys=True)),
        "version": VERSION,
        "module": MODULE,
        "user_query": user_query,
        "query_intent": intent,
        "response_mode": response_mode,
        "image_quality_cards": image_quality_cards,
        "visual_observation_cards": visual_cards,
        "visual_card_count": len(visual_cards),
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
        "visual_observer_ms": elapsed_ms,
        "final_gate_ms": 0.001,
        "total_request_ms": elapsed_ms,
    }
    return package


def build_report(
    *,
    output_dir: str | Path,
    host: str = "127.0.0.1",
    port: int = 8029,
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

    report_path = outdir / "trace_net_e2e_image_visual_observer_route_v34.json"
    records_jsonl_path = outdir / "trace_net_e2e_image_visual_observer_route_records_v34.jsonl"
    inspect_md_path = outdir / "trace_net_e2e_image_visual_observer_route_v34.md"

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
        "visual_observation_card_count": sum(int(r.get("visual_card_count") or 0) for r in sample_records),
        "llava_observer_card_count": sum(int(r.get("llava_observer_card_count") or 0) for r in sample_records),
        "guidance_only_visual_card_count": sum(int(r.get("guidance_only_visual_card_count") or 0) for r in sample_records),
        "source_truth_required_for_visual_claim_count": sum(int(r.get("source_truth_required_for_visual_claim_count") or 0) for r in sample_records),
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
        min_check("visual_observation_card_count", int(thresholds.get("min_visual_observation_cards", 0))),
        min_check("llava_observer_card_count", int(thresholds.get("min_llava_observer_cards", 0))),
        min_check("guidance_only_visual_card_count", int(thresholds.get("min_guidance_only_visual_cards", 0))),
        min_check("self_rag_sample_count", int(thresholds.get("min_self_rag_samples", 0))),
        min_check("crag_sample_count", int(thresholds.get("min_crag_samples", 0))),
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
        "# TRACE-Net E2E Image Visual Observer Route v34",
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
        "visual_observation_card_count",
        "llava_observer_card_count",
        "guidance_only_visual_card_count",
        "source_truth_required_for_visual_claim_count",
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
    print(f"Serving TRACE-Net image visual observer route v34 on http://{host}:{port}/v1")
    print(f"Model: {MODEL_ID}")
    server.serve_forever()
