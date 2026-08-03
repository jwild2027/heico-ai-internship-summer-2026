from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

TRACE_DIR = Path("local_data/organization/trace_net")
MODEL = os.environ.get("TRACE_NET_VISION_MODEL", "llama3.2-vision:11b")
OLLAMA_URL = os.environ.get("TRACE_NET_OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
MAX_PAGES = int(os.environ.get("TRACE_NET_MAX_IMAGE_PAGES", "12"))
TIMEOUT_SECONDS = int(os.environ.get("TRACE_NET_VISION_TIMEOUT_SECONDS", "420"))
OUTPUT_DIR = Path(os.environ.get("TRACE_NET_OUTPUT_DIR", "local_data/organization/trace_net/llama32_vision_image_route_summary_v2"))
IMAGE_VISUAL_EVIDENCE_PACK = Path(os.environ.get("TRACE_NET_IMAGE_VISUAL_EVIDENCE_PACK", "local_data/organization/trace_net/image_visual_evidence_nomenclature_merger_v1/trace_net_image_visual_evidence_pack_with_nomenclature_v1.json"))
IMAGE_ROOTS = [Path(p) for p in os.environ.get("TRACE_NET_IMAGE_ROOTS", "local_data").split(";") if p.strip()]
ALLOW_PREVIEWS = os.environ.get("TRACE_NET_ALLOW_PREVIEW_IMAGES", "0") == "1"
IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"]
BAD_PAGE_PREFIXES = ("metadata_page_", "source_p")
BAD_PATH_PARTS = ("table_full_region_recovery/previews", "contact_sheet", "overlay", "debug", "__pycache__")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def norm(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()


def iter_dicts(obj: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from iter_dicts(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_dicts(item)


def looks_like_bad_page_id(page_id: str) -> bool:
    low = page_id.lower()
    return low.startswith(BAD_PAGE_PREFIXES) or "metadata" in low


def extract_page_id(d: Dict[str, Any]) -> str:
    for k in ["page_id", "source_page_id", "source_trace_page_id", "image_page_id", "manual_page_id", "trace_page_id"]:
        v = norm(d.get(k))
        if v and not looks_like_bad_page_id(v):
            return v
    blob = json.dumps(d, ensure_ascii=False)
    m = re.search(r"\bt_p_[A-Za-z0-9_]+_p\d{6}\b", blob)
    if m:
        return m.group(0)
    m = re.search(r"\bp\d{6}\b", blob)
    if m:
        return m.group(0)
    return ""


def extract_page_number(page_id: str, d: Dict[str, Any]) -> str:
    for k in ["page_number", "page", "source_page", "manual_page"]:
        v = norm(d.get(k))
        if re.fullmatch(r"\d{1,6}", v):
            return str(int(v))
    m = re.search(r"p0*([0-9]{1,6})\b", page_id)
    if m:
        return str(int(m.group(1)))
    return ""


def infer_visual_record(d: Dict[str, Any], source_hint_is_visual_pack: bool = False) -> bool:
    if source_hint_is_visual_pack:
        return True
    blob = json.dumps(d, ensure_ascii=False).lower()
    route = norm(d.get("route") or d.get("primary_route") or d.get("selected_route") or d.get("route_name") or d.get("page_route")).lower()
    return route == "image_visual" or "image_visual" in route or '"image_visual"' in blob


def discover_image_visual_pages() -> List[Dict[str, Any]]:
    candidates: Dict[str, Dict[str, Any]] = {}
    paths: List[tuple[Path, bool]] = []
    if IMAGE_VISUAL_EVIDENCE_PACK.exists():
        paths.append((IMAGE_VISUAL_EVIDENCE_PACK, True))
    for p in TRACE_DIR.rglob("*.json"):
        s = str(p).replace("\\", "/").lower()
        if p == IMAGE_VISUAL_EVIDENCE_PACK:
            continue
        if any(skip in s for skip in ["/llm_", "/h38", "/h37", "/h36", "/h35", "vision_image_route_summary"]):
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "image_visual" in txt or "visual" in s:
            paths.append((p, False))
    for path, is_visual_pack in paths:
        try:
            data = read_json(path)
        except Exception:
            continue
        for d in iter_dicts(data):
            if not infer_visual_record(d, is_visual_pack):
                continue
            page_id = extract_page_id(d)
            if not page_id or looks_like_bad_page_id(page_id):
                continue
            page_number = extract_page_number(page_id, d)
            rec = candidates.setdefault(page_id, {"page_id": page_id, "page_number": page_number, "route": "image_visual", "source_route_artifacts": [], "source_record_count": 0})
            if page_number and not rec.get("page_number"):
                rec["page_number"] = page_number
            rec["source_route_artifacts"].append(str(path))
            rec["source_record_count"] += 1
            for k, v in d.items():
                if isinstance(v, str) and any(v.lower().endswith(ext) for ext in IMAGE_EXTS):
                    rec.setdefault("candidate_image_paths", []).append(v)
    out = list(candidates.values())
    out.sort(key=lambda r: (int(r.get("page_number") or 999999), r.get("page_id") or ""))
    return out


def path_is_allowed_image(path: Path) -> bool:
    if not path.exists() or not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
        return False
    s = str(path).replace("\\", "/").lower()
    if not ALLOW_PREVIEWS and any(bad in s for bad in BAD_PATH_PARTS):
        return False
    return True


def score_image_candidate(path: Path, page_id: str) -> tuple:
    s = str(path).replace("\\", "/").lower()
    preview_penalty = 20 if "preview" in s else 0
    overlay_penalty = 20 if "overlay" in s or "contact_sheet" in s else 0
    source_bonus = -10 if "source" in s or "page" in s or "tiff" in s else 0
    exact_bonus = -20 if page_id.lower() and page_id.lower() in path.name.lower() else 0
    size_score = -min(path.stat().st_size if path.exists() else 0, 20_000_000)
    return (preview_penalty + overlay_penalty + source_bonus + exact_bonus, size_score, len(s))


def exact_page_tokens(page_id: str, page_number: str) -> List[str]:
    toks = []
    if page_id:
        toks.append(page_id)
        m = re.search(r"(p\d{6})\b", page_id)
        if m:
            toks.append(m.group(1))
    if page_number and page_number.isdigit():
        toks.append("p" + str(int(page_number)).zfill(6))
    out, seen = [], set()
    for t in toks:
        if len(t) >= 5 and t not in seen:
            out.append(t); seen.add(t)
    return out


def find_image_for_page(page: Dict[str, Any]) -> Optional[Path]:
    page_id = page.get("page_id", "")
    page_number = page.get("page_number", "")
    direct = []
    for raw in page.get("candidate_image_paths") or []:
        p = Path(raw)
        if path_is_allowed_image(p):
            direct.append(p)
    if direct:
        return sorted(direct, key=lambda p: score_image_candidate(p, page_id))[0]
    candidates = []
    for root in IMAGE_ROOTS:
        if not root.exists():
            continue
        for tok in exact_page_tokens(page_id, page_number):
            for ext in IMAGE_EXTS:
                candidates.extend(root.rglob(f"*{tok}*{ext}"))
    candidates = [p for p in set(candidates) if path_is_allowed_image(p)]
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: score_image_candidate(p, page_id))[0]


def image_to_b64(path: Path) -> str:
    if path.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp"]:
        return base64.b64encode(path.read_bytes()).decode("ascii")
    try:
        from PIL import Image
    except Exception as e:
        raise RuntimeError("TIFF conversion requires Pillow. Run: python -m pip install pillow") from e
    out_dir = OUTPUT_DIR / "converted_png"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / (path.stem + ".png")
    with Image.open(path) as im:
        im.convert("RGB").save(out)
    return base64.b64encode(out.read_bytes()).decode("ascii")


def load_engram_guidance(max_rules: int = 14) -> str:
    paths = [TRACE_DIR / "engineering_engram_memory_layers_v1/trace_net_engineering_engram_memory_layers_v1.json", TRACE_DIR / "engineering_engram_core_v1/trace_net_engineering_engram_core_v1.json"]
    seed = [
        "- Vision summaries are guidance only; they are not proof.",
        "- Act like a cautious engineer: observations, confidence, uncertainty, limits.",
        "- Do not claim interchangeability, effectivity, fit, replacement approval, or installation safety.",
        "- If text is hard to read, say uncertain instead of inventing.",
        "- OCR/table/exact/graph routes must verify factual source claims.",
    ]
    rules = []
    for p in paths:
        if not p.exists():
            continue
        try:
            data = read_json(p)
        except Exception:
            continue
        for d in iter_dicts(data):
            rule = norm(d.get("rule") or d.get("text") or d.get("content") or d.get("guidance"))
            layer = norm(d.get("memory_layer") or d.get("layer"))
            if rule and len(rule) > 20:
                rules.append(f"- {layer + ': ' if layer else ''}{rule}")
    out, seen = [], set()
    for r in seed + rules:
        if r.lower() not in seen:
            out.append(r); seen.add(r.lower())
        if len(out) >= max_rules:
            break
    return "\n".join(out)


def build_prompt(page: Dict[str, Any], engram_guidance: str) -> str:
    page_id = page.get("page_id", "")
    page_number = page.get("page_number", "")
    return f"""
TRACE-NET IMAGE_VISUAL ENGINEERING SUMMARY

You are the local vision specialist for TRACE-Net. Act like a cautious aircraft-manual engineer.

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
  "possible_relationships": [{{"relationship": "figure-to-part | callout-to-part | text-near-part | unknown", "subject": "", "object": "", "confidence": "low | medium | high", "why": ""}}],
  "uncertainties": [],
  "limits": ["Vision summary is guidance only and is not source proof.", "Do not infer interchangeability, effectivity, fit, replacement approval, or installation safety."],
  "recommended_followup_routes": ["ocr", "table", "exact_search", "graph"]
}}

Rules:
- Do not invent unreadable text.
- Use uncertainty when unsure.
- Output JSON only.
""".strip()


def call_ollama(prompt: str, image_b64: str) -> str:
    payload = {"model": MODEL, "prompt": prompt, "images": [image_b64], "stream": False, "options": {"temperature": 0.05}}
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return (data.get("response") or "").strip()


def maybe_json(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    responses = OUTPUT_DIR / "responses"
    responses.mkdir(parents=True, exist_ok=True)
    pages = discover_image_visual_pages()
    selected = []
    missing_images = []
    for p in pages:
        img = find_image_for_page(p)
        if img:
            p["image_path"] = str(img)
            selected.append(p)
        else:
            missing_images.append({"page_id": p.get("page_id", ""), "page_number": p.get("page_number", ""), "source_record_count": p.get("source_record_count", 0)})
        if len(selected) >= MAX_PAGES:
            break
    engram = load_engram_guidance()
    manifest = {"status": "TRACE_NET_LLAMA32_VISION_IMAGE_ROUTE_SUMMARY_V2_STARTED", "module": "trace_net_llama32_vision_image_route_summary_v2", "model": MODEL, "ollama_url": OLLAMA_URL, "image_visual_evidence_pack": str(IMAGE_VISUAL_EVIDENCE_PACK), "image_roots": [str(p) for p in IMAGE_ROOTS], "allow_previews": ALLOW_PREVIEWS, "max_pages": MAX_PAGES, "discovered_image_visual_page_count": len(pages), "selected_page_count": len(selected), "missing_image_count_before_limit": len(missing_images), "missing_image_examples": missing_images[:20], "engram_guidance": engram, "records": [], "safety_contract": {"vision_summary_guidance_only": True, "answer_permission": False, "source_truth_mutation_allowed": False, "postgres_write_attempt": False, "qdrant_write_attempt": False, "opensearch_write_attempt": False}}
    if not selected:
        manifest["status"] = "TRACE_NET_LLAMA32_VISION_IMAGE_ROUTE_SUMMARY_V2_NO_IMAGE_FILES_FOUND"
        manifest["quality_status"] = "FAIL"
        write_json(OUTPUT_DIR / "trace_net_llama32_vision_image_route_summary_v2.json", manifest)
        print("status=NO_IMAGE_FILES_FOUND")
        print("missing_image_examples=" + json.dumps(missing_images[:5], indent=2))
        print("Tip: set TRACE_NET_IMAGE_ROOTS to the folder containing page PNG/TIFF files.")
        return 1
    start = time.time()
    for idx, page in enumerate(selected, 1):
        image_path = Path(page["image_path"])
        page_id = page.get("page_id") or f"page_{idx:04d}"
        safe_page = re.sub(r"[^A-Za-z0-9_.-]+", "_", page_id)[:100]
        rec = {"page_id": page.get("page_id", ""), "page_number": page.get("page_number", ""), "route": "image_visual", "image_path": str(image_path), "model": MODEL, "summary_status": "PENDING", "error": "", "response_text_path": "", "parsed_json": None, "answer_permission": False, "source_truth_mutation_allowed": False}
        try:
            image_b64 = image_to_b64(image_path)
            prompt = build_prompt(page, engram)
            response = call_ollama(prompt, image_b64)
            if not response:
                raise RuntimeError("empty Ollama response")
            response_path = responses / f"{idx:04d}_{safe_page}_response.txt"
            response_path.write_text(response, encoding="utf-8")
            rec.update({"summary_status": "PASS", "response_text_path": str(response_path), "response_preview": response[:1500], "parsed_json": maybe_json(response)})
        except Exception as e:
            rec.update({"summary_status": "ERROR", "error": repr(e)})
        manifest["records"].append(rec)
        write_json(OUTPUT_DIR / "trace_net_llama32_vision_image_route_summary_v2.json", manifest)
        elapsed = time.time() - start
        error_tail = f" error={rec['error'][:180]}" if rec["error"] else ""
        print(f"[vision v2 progress] {idx}/{len(selected)} page_id={rec['page_id']} status={rec['summary_status']} elapsed={elapsed:.1f}s image={image_path}{error_tail}", flush=True)
    pass_count = sum(1 for r in manifest["records"] if r["summary_status"] == "PASS")
    error_count = sum(1 for r in manifest["records"] if r["summary_status"] == "ERROR")
    manifest.update({"status": "TRACE_NET_LLAMA32_VISION_IMAGE_ROUTE_SUMMARY_V2_BUILT", "quality_status": "PASS" if pass_count and not error_count else ("PARTIAL" if pass_count else "FAIL"), "summary": {"record_count": len(manifest["records"]), "pass_count": pass_count, "error_count": error_count, "missing_image_count_before_limit": len(missing_images), "model": MODEL, "vision_summary_guidance_only_count": len(manifest["records"]), "answer_permission_count": 0, "source_truth_mutation_allowed_count": 0, "write_attempt_count": 0}})
    write_json(OUTPUT_DIR / "trace_net_llama32_vision_image_route_summary_v2.json", manifest)
    print("status=" + manifest["status"])
    print("quality_status=" + manifest["quality_status"])
    print("record_count=" + str(len(manifest["records"])))
    print("pass_count=" + str(pass_count))
    print("error_count=" + str(error_count))
    print("output=" + str(OUTPUT_DIR / "trace_net_llama32_vision_image_route_summary_v2.json"))
    return 0 if pass_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
