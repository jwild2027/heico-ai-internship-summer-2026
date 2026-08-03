from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

VERSION = "v35"
MODULE = "trace_net_e2e_route_scoped_visual_context_builder_v35"
STATUS_READY = "E2E_ROUTE_SCOPED_VISUAL_CONTEXT_BUILDER_READY"

PAGE_ID_RE = re.compile(r"t_p_\d+_\d+_p\d{6}", re.I)
TIFF_NAME_RE = re.compile(r"(?P<num>\d{1,8})\.(?:tif|tiff)$", re.I)
VISUAL_ROUTES = {
    "image_visual",
    "visual",
    "diagram",
    "diagram_candidate",
    "callout_diagram_candidate",
    "technical_drawing_candidate",
    "engineering_drawing_candidate",
    "mechanical_drawing_candidate",
}

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
    "route_scoped_visual_context_builder": True,
    "uses_existing_route_or_lightweight_fallback": True,
    "visual_context_guidance_only": True,
    "source_truth_required_for_visual_claims": True,
    "llava_not_called_by_default": True,
    "batch_context_not_answer_permission": True,
}


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
    return f"{prefix}_{hashlib.sha1(text.encode('utf-8', errors='ignore')).hexdigest()[:16]}"


def _write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: str | Path, rows: Sequence[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        p.write_text("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows) + "\n", encoding="utf-8")
    else:
        p.write_text("", encoding="utf-8")


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


def _walk_json(obj: Any) -> Iterable[Any]:
    yield obj
    if isinstance(obj, Mapping):
        for v in obj.values():
            yield from _walk_json(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_json(v)


def _extract_page_id(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    m = PAGE_ID_RE.search(text)
    return m.group(0) if m else ""


def _page_id(prefix: str, page_number: int) -> str:
    return f"{prefix}_p{page_number:06d}"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _parse_metadata_xml(xml_text: str, *, page_id_prefix: str) -> Dict[str, Any]:
    root = ET.fromstring(xml_text.encode("utf-8"))
    label = root.attrib.get("LABEL", "")
    objid = root.attrib.get("OBJID", "")
    files: List[Dict[str, Any]] = []
    for elem in root.iter():
        if _local_name(elem.tag) != "file":
            continue
        file_id = elem.attrib.get("ID", "")
        mimetype = elem.attrib.get("MIMETYPE", "")
        size = int(elem.attrib.get("SIZE", "0") or 0)
        checksum = elem.attrib.get("CHECKSUM", "")
        href = ""
        for child in elem:
            if _local_name(child.tag) == "FLocat":
                href = child.attrib.get("{http://www.w3.org/1999/xlink}href") or child.attrib.get("href") or ""
                break
        filename = href.replace("file://./", "").replace("file://", "").strip()
        m = TIFF_NAME_RE.search(filename)
        if not m:
            continue
        page_number = int(m.group("num"))
        files.append({
            "page_id": _page_id(page_id_prefix, page_number),
            "page_number": page_number,
            "filename": filename,
            "file_id": file_id,
            "mimetype": mimetype,
            "declared_size": size,
            "checksum_sha1": checksum,
            "metadata_href": href,
        })
    files.sort(key=lambda r: int(r.get("page_number") or 0))
    return {"label": label, "objid": objid, "page_records": files}


def _discover_tiff_pages_from_zip(zip_path: str | Path, *, page_id_prefix: str) -> Tuple[Dict[str, Any], zipfile.ZipFile]:
    zf = zipfile.ZipFile(zip_path)
    meta_name = next((n for n in zf.namelist() if Path(n).name.lower() == "metadata.xml"), "")
    if meta_name:
        xml_text = zf.read(meta_name).decode("utf-8", errors="replace")
        manifest = _parse_metadata_xml(xml_text, page_id_prefix=page_id_prefix)
    else:
        records = []
        for name in zf.namelist():
            m = TIFF_NAME_RE.search(Path(name).name)
            if not m:
                continue
            n = int(m.group("num"))
            info = zf.getinfo(name)
            records.append({
                "page_id": _page_id(page_id_prefix, n),
                "page_number": n,
                "filename": Path(name).name,
                "zip_member": name,
                "declared_size": int(info.file_size),
                "mimetype": "image/tiff",
            })
        records.sort(key=lambda r: int(r.get("page_number") or 0))
        manifest = {"label": "", "objid": "", "page_records": records}
    member_by_name = {Path(n).name: n for n in zf.namelist()}
    for rec in manifest["page_records"]:
        rec["source_container"] = str(zip_path)
        rec["source_type"] = "zip_member"
        rec["zip_member"] = member_by_name.get(Path(_norm(rec.get("filename"))).name, _norm(rec.get("filename")))
        try:
            rec["actual_size"] = int(zf.getinfo(rec["zip_member"]).file_size)
        except Exception:
            rec["actual_size"] = rec.get("declared_size") or 0
    return manifest, zf


def _discover_tiff_pages_from_dir(tiff_dir: str | Path, *, page_id_prefix: str) -> Dict[str, Any]:
    root = Path(tiff_dir)
    records = []
    for p in sorted(list(root.glob("*.tif")) + list(root.glob("*.tiff"))):
        m = TIFF_NAME_RE.search(p.name)
        if not m:
            continue
        n = int(m.group("num"))
        records.append({
            "page_id": _page_id(page_id_prefix, n),
            "page_number": n,
            "filename": p.name,
            "path": str(p),
            "source_type": "local_tiff_path",
            "actual_size": int(p.stat().st_size),
            "mimetype": "image/tiff",
        })
    return {"label": root.name, "objid": "", "page_records": records}


def _route_fields_from_obj(obj: Mapping[str, Any]) -> List[str]:
    vals: List[str] = []
    for k, v in obj.items():
        lk = _lower(k)
        if lk in {"route", "routes", "page_route", "primary_route", "route_label", "route_type", "dispatch_route", "visual_type"} or "route" in lk:
            if isinstance(v, list):
                vals.extend(_lower(x) for x in v)
            else:
                vals.append(_lower(v))
    return [x for x in vals if x]


def load_route_index(route_manifest_path: str | Path | None) -> Dict[str, Dict[str, Any]]:
    data = _read_json(route_manifest_path)
    out: Dict[str, Dict[str, Any]] = {}
    if not data:
        return out
    for obj in _walk_json(data):
        if not isinstance(obj, Mapping):
            continue
        pid = _extract_page_id(obj) or _norm(obj.get("page_id")) or _norm(obj.get("source_page_id"))
        if not pid:
            continue
        routes = _route_fields_from_obj(obj)
        if not routes:
            continue
        existing = out.setdefault(pid, {"page_id": pid, "routes": [], "source_records": 0})
        for route in routes:
            if route not in existing["routes"]:
                existing["routes"].append(route)
        existing["source_records"] += 1
    return out


def _read_page_bytes(page: Mapping[str, Any], zf: zipfile.ZipFile | None = None) -> bytes | None:
    if page.get("source_type") == "zip_member" and zf is not None:
        try:
            return zf.read(_norm(page.get("zip_member")))
        except Exception:
            return None
    path = page.get("path")
    if path and Path(str(path)).exists():
        try:
            return Path(str(path)).read_bytes()
        except Exception:
            return None
    return None


def _basic_image_stats(image_bytes: bytes | None) -> Dict[str, Any]:
    stats: Dict[str, Any] = {"width": None, "height": None, "mode": None, "pixel_count": 0, "ink_ratio": None, "image_open_status": "IMAGE_NOT_OPENED"}
    if not image_bytes:
        return stats
    try:
        from PIL import Image  # type: ignore
        import io
        with Image.open(io.BytesIO(image_bytes)) as im:
            stats.update({"width": int(im.width), "height": int(im.height), "mode": im.mode, "pixel_count": int(im.width * im.height), "image_open_status": "IMAGE_OPENED"})
            g = im.convert("L")
            small = g.resize((min(256, g.width), max(1, int(g.height * min(256, g.width) / max(g.width, 1))))) if g.width > 256 else g
            vals = list(small.getdata())
            if vals:
                stats["ink_ratio"] = round(sum(1 for v in vals if v < 230) / len(vals), 5)
    except Exception as exc:
        stats["image_open_status"] = f"IMAGE_OPEN_FAILED:{type(exc).__name__}"
    return stats


def _optional_ocr_card(image_id: str, image_bytes: bytes | None) -> Dict[str, Any]:
    try:
        from tiff.trace_net_e2e_image_visual_observer_route_v34_3 import _ocr_text_card_from_bytes  # type: ignore
        return _ocr_text_card_from_bytes(image_id, image_bytes)
    except Exception as exc:
        return {
            "ocr_card_id": _stable_id("ocr_text_v35", image_id),
            "image_id": image_id,
            "ocr_engine": "v34_3_optional_import_or_tesseract_unavailable",
            "ocr_status": "OCR_SKIPPED_OR_UNAVAILABLE",
            "ocr_error": f"{type(exc).__name__}: {exc}",
            "text_candidates": [],
            "text_candidate_count": 0,
            "authority": "guidance_only",
            "proof_authority": False,
            "requires_source_truth_confirmation": True,
        }


def _optional_geometry_card(image_id: str, image_bytes: bytes | None, ocr_cards: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    try:
        from tiff.trace_net_e2e_image_visual_observer_route_v34_3 import _technical_drawing_geometry_card_from_bytes  # type: ignore
        return _technical_drawing_geometry_card_from_bytes(image_id, image_bytes, ocr_cards)
    except Exception as exc:
        return {
            "technical_geometry_card_id": _stable_id("technical_geometry_v35", image_id),
            "image_id": image_id,
            "geometry_engine": "v34_3_optional_import_unavailable",
            "geometry_status": "TECHNICAL_GEOMETRY_SKIPPED_OR_UNAVAILABLE",
            "geometry_error": f"{type(exc).__name__}: {exc}",
            "line_candidate_count": 0,
            "circle_candidate_count": 0,
            "dimension_line_candidate_count": 0,
            "hatching_candidate_count": 0,
            "dimension_text_candidates": [],
            "dimension_text_candidate_count": 0,
            "technical_drawing_candidate": False,
            "technical_features": [],
            "authority": "guidance_only",
            "proof_authority": False,
            "requires_source_truth_confirmation": True,
        }


def _fallback_route_for_page(page: Mapping[str, Any], stats: Mapping[str, Any], geometry_card: Mapping[str, Any] | None = None) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    size = int(page.get("actual_size") or page.get("declared_size") or 0)
    ink = stats.get("ink_ratio")
    if size and size < 6000:
        return "blank_candidate", ["very_small_tiff_file"]
    geometry_card = geometry_card or {}
    if geometry_card.get("technical_drawing_candidate"):
        return "technical_drawing_candidate", ["technical_geometry_candidate"]
    if int(geometry_card.get("circle_candidate_count") or 0) > 0 and int(geometry_card.get("line_candidate_count") or 0) >= 10:
        return "image_visual", ["line_and_circle_geometry"]
    if ink is not None and isinstance(ink, float) and ink > 0.10 and int(geometry_card.get("line_candidate_count") or 0) > 20:
        return "image_visual", ["dense_line_geometry"]
    # Cheap fallback when no route manifest exists: collect a small, capped set of
    # non-blank/ink-bearing pages for later route-specific visual context. The
    # existing route manifest remains preferred when available.
    if ink is not None and isinstance(ink, float) and ink > 0.015 and size > 10000:
        return "image_visual", ["fallback_ink_bearing_page_candidate"]
    return "normal_text_or_unclassified", ["no_visual_route_signal"]


def _is_visual_route(routes: Sequence[str]) -> bool:
    joined = " ".join(_lower(r) for r in routes)
    return any(v in joined for v in VISUAL_ROUTES) or any(w in joined for w in ("drawing", "diagram", "callout", "visual"))


def _build_prompt_context(card: Mapping[str, Any]) -> Dict[str, Any]:
    feats = card.get("technical_features") or []
    ocr = card.get("ocr_text_candidates") or []
    route = _norm(card.get("visual_context_type") or card.get("selected_route"))
    page_id = _norm(card.get("page_id"))
    lines = [
        f"Page {page_id} has stored visual context route {route}.",
        "This visual context is guidance only and is not source-truth proof.",
    ]
    if feats:
        lines.append("Detected visual/geometry guidance: " + "; ".join(_norm(f) for f in feats[:8]) + ".")
    if ocr:
        lines.append("OCR text candidates: " + "; ".join(_norm(x) for x in ocr[:8]) + ".")
    else:
        lines.append("OCR text candidates were not confirmed for this page context card.")
    return {
        "prompt_context_id": _stable_id("image_visual_prompt_context_v35", page_id),
        "page_id": page_id,
        "route": route,
        "context_text": " ".join(lines),
        "authority": "guidance_only",
        "proof_authority": False,
        "requires_source_truth_confirmation": True,
    }


def build_visual_context(
    *,
    output_dir: str | Path,
    page_bundle_zip: str | Path | None = None,
    tiff_dir: str | Path | None = None,
    route_dispatch_manifest: str | Path | None = None,
    page_id_prefix: str = "t_p_120_1176",
    max_visual_pages: int = 50,
    include_fallback_classifier: bool = True,
    enable_local_visual_analysis: bool = False,
) -> Dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    zf: zipfile.ZipFile | None = None
    if page_bundle_zip:
        source_manifest, zf = _discover_tiff_pages_from_zip(page_bundle_zip, page_id_prefix=page_id_prefix)
    elif tiff_dir:
        source_manifest = _discover_tiff_pages_from_dir(tiff_dir, page_id_prefix=page_id_prefix)
    else:
        source_manifest = {"label": "", "objid": "", "page_records": []}

    route_index = load_route_index(route_dispatch_manifest)
    candidates: List[Dict[str, Any]] = []
    context_cards: List[Dict[str, Any]] = []
    prompt_contexts: List[Dict[str, Any]] = []

    route_source = "route_dispatch_manifest" if route_index else "fallback_lightweight_image_classifier"
    source_pages = source_manifest.get("page_records") or []

    for page in source_pages:
        pid = _norm(page.get("page_id"))
        route_info = route_index.get(pid, {})
        manifest_routes = route_info.get("routes") or []
        image_bytes: bytes | None = None
        stats: Dict[str, Any] = {"image_open_status": "NOT_ANALYZED"}
        ocr_card: Dict[str, Any] | None = None
        geometry_card: Dict[str, Any] | None = None
        selected_route = ""
        reasons: List[str] = []

        if manifest_routes and _is_visual_route(manifest_routes):
            selected_route = manifest_routes[0]
            reasons = ["existing_route_manifest_visual_route"]
        elif manifest_routes:
            # If the existing classifier already gave this page a non-visual route,
            # do not override it with the lightweight fallback. The fallback is only
            # for bundles where route metadata is absent/incomplete.
            selected_route = manifest_routes[0]
            reasons = ["existing_route_manifest_non_visual_route"]
        elif include_fallback_classifier:
            if not route_index and len(context_cards) >= max_visual_pages:
                selected_route = "fallback_scan_cap_not_evaluated"
                reasons = ["fallback_scan_stopped_after_max_visual_pages"]
            else:
                image_bytes = _read_page_bytes(page, zf)
                stats = _basic_image_stats(image_bytes)
                selected_route, reasons = _fallback_route_for_page(page, stats, None)
        else:
            selected_route = "route_manifest_non_visual_or_missing"
            reasons = ["no_visual_route_signal"]

        is_visual = _is_visual_route([selected_route])
        candidate = {
            "candidate_id": _stable_id("image_visual_candidate_v35", pid + selected_route),
            "page_id": pid,
            "page_number": page.get("page_number"),
            "filename": page.get("filename"),
            "source_type": page.get("source_type"),
            "zip_member": page.get("zip_member"),
            "path": page.get("path"),
            "declared_size": page.get("declared_size"),
            "actual_size": page.get("actual_size"),
            "manifest_routes": manifest_routes,
            "selected_route": selected_route,
            "route_source": "route_dispatch_manifest" if manifest_routes else route_source,
            "candidate_reasons": reasons,
            "is_visual_context_candidate": bool(is_visual),
            "guidance_only": True,
            "proof_authority": False,
            "requires_source_truth_confirmation": True,
        }
        candidates.append(candidate)
        if not is_visual:
            continue
        if len(context_cards) >= max_visual_pages:
            continue
        image_id = _stable_id("stored_page_image_v35", pid)
        if image_bytes is None and (enable_local_visual_analysis or stats.get("image_open_status") == "NOT_ANALYZED"):
            image_bytes = _read_page_bytes(page, zf)
        if stats.get("image_open_status") == "NOT_ANALYZED":
            stats = _basic_image_stats(image_bytes)
        if enable_local_visual_analysis:
            if ocr_card is None:
                ocr_card = _optional_ocr_card(image_id, image_bytes)
            if geometry_card is None:
                geometry_card = _optional_geometry_card(image_id, image_bytes, [ocr_card])
        else:
            if ocr_card is None:
                ocr_card = {
                    "ocr_card_id": _stable_id("ocr_text_v35", image_id),
                    "image_id": image_id,
                    "ocr_engine": "not_run_in_route_scoped_context_builder",
                    "ocr_status": "OCR_NOT_RUN_USE_EXISTING_OCR_ROUTE_STAGE",
                    "text_candidates": [],
                    "text_candidate_count": 0,
                    "authority": "guidance_only",
                    "proof_authority": False,
                    "requires_source_truth_confirmation": True,
                }
            if geometry_card is None:
                geometry_card = {
                    "technical_geometry_card_id": _stable_id("technical_geometry_v35", image_id),
                    "image_id": image_id,
                    "geometry_engine": "not_run_in_route_scoped_context_builder",
                    "geometry_status": "GEOMETRY_NOT_RUN_USE_V34_IMAGE_ROUTE_FOR_ENRICHMENT",
                    "line_candidate_count": 0,
                    "circle_candidate_count": 0,
                    "dimension_line_candidate_count": 0,
                    "hatching_candidate_count": 0,
                    "dimension_text_candidates": [],
                    "dimension_text_candidate_count": 0,
                    "technical_drawing_candidate": "technical" in _lower(selected_route),
                    "technical_features": [selected_route] if "technical" in _lower(selected_route) else [],
                    "authority": "guidance_only",
                    "proof_authority": False,
                    "requires_source_truth_confirmation": True,
                }
        technical_features = list(geometry_card.get("technical_features") or [])
        visual_type = selected_route
        if geometry_card.get("technical_drawing_candidate") and "technical_drawing_candidate" not in visual_type:
            visual_type = "technical_drawing_candidate"
        ocr_candidates = list(ocr_card.get("text_candidates") or [])
        card = {
            "visual_context_card_id": _stable_id("image_visual_context_v35", pid),
            "page_id": pid,
            "page_number": page.get("page_number"),
            "filename": page.get("filename"),
            "source_type": page.get("source_type"),
            "source_container": page.get("source_container"),
            "zip_member": page.get("zip_member"),
            "selected_route": selected_route,
            "route_source": candidate["route_source"],
            "visual_context_type": visual_type,
            "image_stats": stats,
            "ocr_text_card": ocr_card,
            "ocr_text_candidates": ocr_candidates[:25],
            "ocr_text_candidate_count": len(ocr_candidates[:25]),
            "technical_geometry_card": geometry_card,
            "technical_features": technical_features,
            "technical_feature_count": len(technical_features),
            "line_candidate_count": int(geometry_card.get("line_candidate_count") or 0),
            "circle_candidate_count": int(geometry_card.get("circle_candidate_count") or 0),
            "dimension_line_candidate_count": int(geometry_card.get("dimension_line_candidate_count") or 0),
            "hatching_candidate_count": int(geometry_card.get("hatching_candidate_count") or 0),
            "dimension_text_candidates": list(geometry_card.get("dimension_text_candidates") or []),
            "dimension_text_candidate_count": int(geometry_card.get("dimension_text_candidate_count") or 0),
            "status": "IMAGE_VISUAL_CONTEXT_CARD_BUILT",
            "authority": "guidance_only",
            "guidance_only": True,
            "proof_authority": False,
            "requires_source_truth_confirmation": True,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        }
        context_cards.append(card)
        prompt_contexts.append(_build_prompt_context(card))

    if zf is not None:
        zf.close()

    candidates_jsonl_path = out / "trace_net_route_scoped_visual_context_candidates_v35.jsonl"
    context_jsonl_path = out / "trace_net_route_scoped_visual_context_cards_v35.jsonl"
    prompt_jsonl_path = out / "trace_net_route_scoped_visual_prompt_context_v35.jsonl"
    report_path = out / "trace_net_route_scoped_visual_context_builder_v35.json"
    inspect_md_path = out / "trace_net_route_scoped_visual_context_builder_v35.md"

    _write_jsonl(candidates_jsonl_path, candidates)
    _write_jsonl(context_jsonl_path, context_cards)
    _write_jsonl(prompt_jsonl_path, prompt_contexts)

    visual_candidates = [c for c in candidates if c.get("is_visual_context_candidate")]
    technical_cards = [c for c in context_cards if "technical" in _lower(c.get("visual_context_type")) or c.get("technical_feature_count", 0)]
    report: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "status": STATUS_READY,
        "quality_status": "UNKNOWN",
        "created_at": _now(),
        "contract": SAFETY_CONTRACT,
        "source_label": source_manifest.get("label"),
        "source_objid": source_manifest.get("objid"),
        "source_page_count": len(source_pages),
        "route_index_page_count": len(route_index),
        "route_candidate_count": len(candidates),
        "image_visual_candidate_count": len(visual_candidates),
        "visual_context_card_count": len(context_cards),
        "visual_prompt_context_count": len(prompt_contexts),
        "technical_drawing_context_card_count": len(technical_cards),
        "ocr_text_card_count": len(context_cards),
        "ocr_text_candidate_count": sum(int(c.get("ocr_text_candidate_count") or 0) for c in context_cards),
        "technical_geometry_card_count": len(context_cards),
        "line_candidate_count": sum(int(c.get("line_candidate_count") or 0) for c in context_cards),
        "circle_candidate_count": sum(int(c.get("circle_candidate_count") or 0) for c in context_cards),
        "dimension_line_candidate_count": sum(int(c.get("dimension_line_candidate_count") or 0) for c in context_cards),
        "hatching_candidate_count": sum(int(c.get("hatching_candidate_count") or 0) for c in context_cards),
        "dimension_text_candidate_count": sum(int(c.get("dimension_text_candidate_count") or 0) for c in context_cards),
        "guidance_only_visual_context_count": sum(1 for c in context_cards if c.get("guidance_only") is True and c.get("proof_authority") is False),
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "visual_proof_authority_violation_count": 0,
        "post_gate_issue_count": 0,
        "llava_call_count": 0,
        "raw_5tb_scan_at_query_time_count": 0,
        "report_path": str(report_path),
        "candidates_jsonl_path": str(candidates_jsonl_path),
        "visual_context_cards_jsonl_path": str(context_jsonl_path),
        "visual_prompt_context_jsonl_path": str(prompt_jsonl_path),
        "inspect_md_path": str(inspect_md_path),
        "sample_candidates": candidates[:10],
        "sample_visual_context_cards": context_cards[:5],
    }
    _write_json(report_path, report)
    _write_inspect_md(inspect_md_path, report)
    return report


def _write_inspect_md(path: str | Path, report: Mapping[str, Any]) -> None:
    lines = [
        "# TRACE-Net Route-Scoped Visual Context Builder v35",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        f"Status: `{report.get('status')}`",
        "",
        "## Summary",
    ]
    for key in [
        "source_page_count", "route_index_page_count", "route_candidate_count", "image_visual_candidate_count",
        "visual_context_card_count", "visual_prompt_context_count", "technical_drawing_context_card_count",
        "ocr_text_card_count", "ocr_text_candidate_count", "technical_geometry_card_count", "line_candidate_count",
        "circle_candidate_count", "dimension_line_candidate_count", "hatching_candidate_count", "guidance_only_visual_context_count",
        "answer_permission_count", "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {report.get(key)}")
    lines.extend([
        "",
        "## Contract",
        "- This stage consumes existing stored page files and route metadata; it does not create answer authority.",
        "- Visual context cards are guidance only.",
        "- LLaVA is not called by default in this offline builder; expensive visual models can enrich cards later.",
        "- No Postgres/Qdrant/OpenSearch writes and no source-truth mutation are allowed.",
        "",
        "## Sample visual context cards",
    ])
    for c in report.get("sample_visual_context_cards", []) or []:
        lines.append(f"### {c.get('page_id')} — `{c.get('visual_context_type')}`")
        feats = c.get("technical_features") or []
        if feats:
            lines.append("- features: " + "; ".join(_norm(x) for x in feats[:8]))
        ocr = c.get("ocr_text_candidates") or []
        if ocr:
            lines.append("- OCR: " + "; ".join(_norm(x) for x in ocr[:8]))
        else:
            lines.append("- OCR: no confirmed candidates")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _check(name: str, observed: Any, op: str, expected: Any) -> Dict[str, Any]:
    passed = False
    if op == ">=":
        passed = observed >= expected
    elif op == "<=":
        passed = observed <= expected
    elif op == "==":
        passed = observed == expected
    elif op == "is_false":
        passed = observed is False
    return {"name": name, "observed": observed, "operator": op, "expected": expected, "passed": bool(passed)}


def evaluate_quality(report: Mapping[str, Any], **thresholds: Any) -> List[Dict[str, Any]]:
    checks = [
        _check("source_page_count", int(report.get("source_page_count") or 0), ">=", int(thresholds.get("min_source_pages") or 0)),
        _check("route_candidate_count", int(report.get("route_candidate_count") or 0), ">=", int(thresholds.get("min_route_candidates") or 0)),
        _check("image_visual_candidate_count", int(report.get("image_visual_candidate_count") or 0), ">=", int(thresholds.get("min_image_visual_candidates") or 0)),
        _check("visual_context_card_count", int(report.get("visual_context_card_count") or 0), ">=", int(thresholds.get("min_visual_context_cards") or 0)),
        _check("visual_prompt_context_count", int(report.get("visual_prompt_context_count") or 0), ">=", int(thresholds.get("min_visual_prompt_contexts") or 0)),
        _check("guidance_only_visual_context_count", int(report.get("guidance_only_visual_context_count") or 0), ">=", int(thresholds.get("min_guidance_only_visual_contexts") or 0)),
        _check("technical_geometry_card_count", int(report.get("technical_geometry_card_count") or 0), ">=", int(thresholds.get("min_technical_geometry_cards") or 0)),
        _check("visual_proof_authority_violation_count", int(report.get("visual_proof_authority_violation_count") or 0), "<=", int(thresholds.get("max_visual_proof_authority_violations") or 0)),
        _check("post_gate_issue_count", int(report.get("post_gate_issue_count") or 0), "<=", int(thresholds.get("max_post_gate_issue_count") or 0)),
        _check("answer_permission_count", int(report.get("answer_permission_count") or 0), "<=", int(thresholds.get("max_answer_permission_count") or 0)),
        _check("source_truth_mutation_allowed_count", int(report.get("source_truth_mutation_allowed_count") or 0), "<=", int(thresholds.get("max_source_truth_mutation_allowed") or 0)),
    ]
    if thresholds.get("require_no_answer_permission"):
        checks.append(_check("require_no_answer_permission", int(report.get("answer_permission_count") or 0), "==", 0))
    return checks


def apply_quality(report: Dict[str, Any], checks: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    report["quality_checks"] = list(checks)
    report["quality_status"] = "PASS" if all(c.get("passed") for c in checks) else "FAIL"
    _write_json(report["report_path"], report)
    _write_inspect_md(report["inspect_md_path"], report)
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Build TRACE-Net route-scoped visual context cards v35")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--page-bundle-zip")
    ap.add_argument("--tiff-dir")
    ap.add_argument("--route-dispatch-manifest")
    ap.add_argument("--page-id-prefix", default="t_p_120_1176")
    ap.add_argument("--max-visual-pages", type=int, default=50)
    ap.add_argument("--disable-fallback-classifier", action="store_true")
    ap.add_argument("--enable-local-visual-analysis", action="store_true", help="Run local OCR/geometry enrichment now instead of only building route-scoped placeholders")
    ap.add_argument("--min-source-pages", type=int, default=0)
    ap.add_argument("--min-route-candidates", type=int, default=0)
    ap.add_argument("--min-image-visual-candidates", type=int, default=0)
    ap.add_argument("--min-visual-context-cards", type=int, default=0)
    ap.add_argument("--min-visual-prompt-contexts", type=int, default=0)
    ap.add_argument("--min-guidance-only-visual-contexts", type=int, default=0)
    ap.add_argument("--min-technical-geometry-cards", type=int, default=0)
    ap.add_argument("--max-visual-proof-authority-violations", type=int, default=0)
    ap.add_argument("--max-post-gate-issue-count", type=int, default=0)
    ap.add_argument("--max-answer-permission-count", type=int, default=0)
    ap.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    ap.add_argument("--require-no-answer-permission", action="store_true")
    ap.add_argument("--quality", action="store_true")
    args = ap.parse_args(argv)
    report = build_visual_context(
        output_dir=args.output_dir,
        page_bundle_zip=args.page_bundle_zip,
        tiff_dir=args.tiff_dir,
        route_dispatch_manifest=args.route_dispatch_manifest,
        page_id_prefix=args.page_id_prefix,
        max_visual_pages=args.max_visual_pages,
        include_fallback_classifier=not args.disable_fallback_classifier,
        enable_local_visual_analysis=args.enable_local_visual_analysis,
    )
    checks = evaluate_quality(
        report,
        min_source_pages=args.min_source_pages,
        min_route_candidates=args.min_route_candidates,
        min_image_visual_candidates=args.min_image_visual_candidates,
        min_visual_context_cards=args.min_visual_context_cards,
        min_visual_prompt_contexts=args.min_visual_prompt_contexts,
        min_guidance_only_visual_contexts=args.min_guidance_only_visual_contexts,
        min_technical_geometry_cards=args.min_technical_geometry_cards,
        max_visual_proof_authority_violations=args.max_visual_proof_authority_violations,
        max_post_gate_issue_count=args.max_post_gate_issue_count,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    report = apply_quality(report, checks)
    print("TRACE-Net Route-Scoped Visual Context Builder v35")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "source_page_count", "route_index_page_count", "route_candidate_count", "image_visual_candidate_count",
        "visual_context_card_count", "visual_prompt_context_count", "technical_drawing_context_card_count",
        "ocr_text_card_count", "ocr_text_candidate_count", "technical_geometry_card_count",
        "line_candidate_count", "circle_candidate_count", "dimension_line_candidate_count", "hatching_candidate_count",
        "guidance_only_visual_context_count", "answer_permission_count", "source_truth_mutation_allowed_count",
        "report_path", "visual_context_cards_jsonl_path", "visual_prompt_context_jsonl_path",
    ]:
        print(f" {key}: {report.get(key)}")
    if args.quality and report.get("quality_status") != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
