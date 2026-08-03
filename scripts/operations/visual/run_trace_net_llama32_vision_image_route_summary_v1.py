from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


ROOT = Path(".")
TRACE_DIR = Path("local_data/organization/trace_net")

MODEL = os.environ.get("TRACE_NET_VISION_MODEL", "llama3.2-vision:11b")
OLLAMA_URL = os.environ.get("TRACE_NET_OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
MAX_PAGES = int(os.environ.get("TRACE_NET_MAX_IMAGE_PAGES", "12"))
TIMEOUT_SECONDS = int(os.environ.get("TRACE_NET_VISION_TIMEOUT_SECONDS", "420"))

OUTPUT_DIR = Path(os.environ.get(
    "TRACE_NET_OUTPUT_DIR",
    "local_data/organization/trace_net/llama32_vision_image_route_summary_v1",
))

IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"]


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


def discover_image_visual_pages() -> List[Dict[str, Any]]:
    """
    Searches TRACE-Net JSON artifacts for records routed to image_visual.
    Works across route_manifest / dispatch_manifest / route cards without assuming one schema.
    """
    records: Dict[str, Dict[str, Any]] = {}

    for path in TRACE_DIR.rglob("*.json"):
        name = str(path).replace("\\", "/").lower()
        if any(skip in name for skip in ["/llm_", "/h38", "/h37", "/h36", "/h35"]):
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        if "image_visual" not in text:
            continue

        try:
            data = json.loads(text)
        except Exception:
            continue

        for d in iter_dicts(data):
            blob = json.dumps(d, ensure_ascii=False).lower()
            if "image_visual" not in blob:
                continue

            route = norm(
                d.get("route")
                or d.get("primary_route")
                or d.get("selected_route")
                or d.get("route_name")
                or d.get("page_route")
            ).lower()

            if route and route != "image_visual" and "image_visual" not in route:
                continue

            page_id = norm(
                d.get("page_id")
                or d.get("source_page_id")
                or d.get("source_id")
                or d.get("image_page_id")
            )

            page_number = norm(
                d.get("page")
                or d.get("page_number")
                or d.get("source_page")
                or d.get("manual_page")
            )

            if not page_id:
                m = re.search(r"(?:p|page)[_-]?0*([0-9]{1,5})", blob)
                if m:
                    page_number = page_number or m.group(1)
                    page_id = f"p{int(m.group(1)):06d}"

            if not page_id and not page_number:
                continue

            key = page_id or f"page_{page_number}"
            rec = records.setdefault(key, {
                "page_id": page_id,
                "page_number": page_number,
                "route": "image_visual",
                "source_route_artifacts": [],
            })
            rec["source_route_artifacts"].append(str(path))

    out = list(records.values())
    out.sort(key=lambda r: (
        int(re.sub(r"\D", "", r.get("page_number") or r.get("page_id") or "999999") or "999999"),
        r.get("page_id") or "",
    ))
    return out


def page_digits(page_id: str, page_number: str) -> List[str]:
    vals = []
    for x in [page_number, page_id]:
        for m in re.findall(r"\d{1,6}", x or ""):
            vals.append(m)
            vals.append(m.zfill(6))
            vals.append(m.zfill(4))
    return list(dict.fromkeys(vals))


def find_image_for_page(page_id: str, page_number: str) -> Optional[Path]:
    candidates = []

    tokens = [page_id] if page_id else []
    tokens += page_digits(page_id, page_number)

    search_roots = [
        TRACE_DIR,
        Path("local_data"),
    ]

    for root in search_roots:
        if not root.exists():
            continue

        for token in tokens:
            if not token:
                continue
            for ext in IMAGE_EXTS:
                candidates.extend(root.rglob(f"*{token}*{ext}"))

    # Prefer non-overlay source-ish files, but overlays are still useful if source PNG/TIFF not found.
    def score(p: Path) -> tuple:
        s = str(p).replace("\\", "/").lower()
        overlay_penalty = 10 if "overlay" in s or "contact_sheet" in s else 0
        size_bonus = -p.stat().st_size if p.exists() else 0
        return (overlay_penalty, size_bonus, len(s))

    candidates = [p for p in candidates if p.exists() and p.is_file()]
    candidates = sorted(set(candidates), key=score)
    return candidates[0] if candidates else None


def image_to_base64_png_or_native(path: Path) -> str:
    """
    Ollama accepts base64 image bytes. PNG/JPEG are safest. For TIFF, try Pillow conversion.
    """
    if path.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp"]:
        return base64.b64encode(path.read_bytes()).decode("ascii")

    try:
        from PIL import Image
    except Exception as e:
        raise RuntimeError(
            f"Pillow is required to convert TIFF page {path}. Install with: python -m pip install pillow"
        ) from e

    out_dir = OUTPUT_DIR / "converted_png"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / (path.stem + ".png")

    with Image.open(path) as im:
        im = im.convert("RGB")
        im.save(out)

    return base64.b64encode(out.read_bytes()).decode("ascii")


def load_engram_guidance(max_rules: int = 16) -> str:
    candidates = [
        TRACE_DIR / "engineering_engram_memory_layers_v1/trace_net_engineering_engram_memory_layers_v1.json",
        TRACE_DIR / "engineering_engram_core_v1/trace_net_engineering_engram_core_v1.json",
    ]

    rules = []
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = read_json(path)
        except Exception:
            continue

        for d in iter_dicts(data):
            rule = norm(d.get("rule") or d.get("text") or d.get("content") or d.get("guidance"))
            layer = norm(d.get("memory_layer") or d.get("layer") or d.get("memory_type"))
            proof_role = norm(d.get("proof_role"))
            if rule and len(rule) > 20:
                prefix = f"{layer}: " if layer else ""
                suffix = f" [{proof_role}]" if proof_role else ""
                rules.append(f"- {prefix}{rule}{suffix}")

    # Seed critical engineering behavior even if memory file shape changes.
    seed = [
        "- working_memory: V2 summaries and vision summaries may guide planning, but cannot prove source claims.",
        "- semantic_memory: visual figure links can support figure-to-part identity only when source-trace evidence exists.",
        "- procedural_memory: if evidence is uncertain, say uncertain instead of inventing.",
        "- procedural_memory: do not claim interchangeability, fit, effectivity, replacement approval, or installation safety.",
        "- trait_memory: answer like a cautious engineer: observed evidence, confidence, uncertainty, limits.",
        "- critic_memory: Self-RAG should check if the visual summary overclaims beyond visible evidence.",
    ]

    merged = []
    seen = set()
    for x in seed + rules:
        k = x.lower()
        if k not in seen:
            seen.add(k)
            merged.append(x)
        if len(merged) >= max_rules:
            break

    return "\n".join(merged)


def build_prompt(page_record: Dict[str, Any], engram_guidance: str) -> str:
    page_id = page_record.get("page_id") or ""
    page_number = page_record.get("page_number") or ""

    return f"""
TRACE-NET IMAGE_VISUAL ENGINEERING SUMMARY

You are the local vision specialist for TRACE-Net.
Act like a cautious aircraft-manual engineer, not a generic caption model.

ENGRAM BEHAVIOR GUIDANCE:
{engram_guidance}

PAGE CONTEXT:
page_id: {page_id}
page_number: {page_number}
route: image_visual

TASK:
Analyze the attached manual page image. Return compact JSON only.

JSON schema:
{{
  "page_id": "{page_id}",
  "page_number": "{page_number}",
  "image_type": "diagram | figure | table | mixed | blank | unknown",
  "engineering_summary": "short cautious summary of what is visible",
  "visible_figures": [],
  "visible_callouts": [],
  "visible_part_numbers": [],
  "visible_nomenclature": [],
  "table_or_ipl_regions": [],
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
  "recommended_followup_routes": [
    "ocr",
    "table",
    "exact_search",
    "graph"
  ]
}}

Rules:
- Do not invent text that is not visible.
- If OCR-like text is unclear, put it in uncertainties.
- Do not claim a part is approved, interchangeable, safe, effective, or installable.
- Prefer short, structured, engineer-style observations.
- Output JSON only. No markdown.
""".strip()


def call_ollama_vision(prompt: str, image_b64: str) -> str:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
        "options": {
            "temperature": 0.05,
        },
    }

    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    return data.get("response", "").strip()


def maybe_parse_json(text: str) -> Any:
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
    answer_dir = OUTPUT_DIR / "responses"
    answer_dir.mkdir(parents=True, exist_ok=True)

    pages = discover_image_visual_pages()
    engram_guidance = load_engram_guidance()

    selected = []
    for page in pages:
        img = find_image_for_page(page.get("page_id", ""), page.get("page_number", ""))
        if img:
            page["image_path"] = str(img)
            selected.append(page)
        if len(selected) >= MAX_PAGES:
            break

    manifest = {
        "status": "TRACE_NET_LLAMA32_VISION_IMAGE_ROUTE_SUMMARY_STARTED",
        "module": "trace_net_llama32_vision_image_route_summary_v1",
        "model": MODEL,
        "ollama_url": OLLAMA_URL,
        "max_pages": MAX_PAGES,
        "discovered_image_visual_page_count": len(pages),
        "selected_page_count": len(selected),
        "engram_guidance": engram_guidance,
        "records": [],
        "safety_contract": {
            "vision_summary_guidance_only": True,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
        },
    }

    if not selected:
        manifest["status"] = "TRACE_NET_LLAMA32_VISION_IMAGE_ROUTE_SUMMARY_NO_IMAGE_FILES_FOUND"
        write_json(OUTPUT_DIR / "trace_net_llama32_vision_image_route_summary_v1.json", manifest)
        print("status=NO_IMAGE_FILES_FOUND")
        print("Tip: confirm image/TIFF/PNG files exist under local_data and route artifacts contain image_visual.")
        return 1

    start = time.time()

    for idx, page in enumerate(selected, 1):
        page_id = page.get("page_id") or f"page_{idx:04d}"
        image_path = Path(page["image_path"])

        record = {
            "page_id": page.get("page_id", ""),
            "page_number": page.get("page_number", ""),
            "route": "image_visual",
            "image_path": str(image_path),
            "model": MODEL,
            "summary_status": "PENDING",
            "response_text_path": "",
            "parsed_json": None,
            "error": "",
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        }

        try:
            image_b64 = image_to_base64_png_or_native(image_path)
            prompt = build_prompt(page, engram_guidance)
            response = call_ollama_vision(prompt, image_b64)
            parsed = maybe_parse_json(response)

            safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", page_id)[:80]
            response_path = answer_dir / f"{idx:04d}_{safe_name}_llama32_vision_response.txt"
            response_path.write_text(response, encoding="utf-8")

            record.update({
                "summary_status": "PASS" if response else "EMPTY_RESPONSE",
                "response_text_path": str(response_path),
                "parsed_json": parsed,
                "response_preview": response[:1200],
            })

        except Exception as e:
            record.update({
                "summary_status": "ERROR",
                "error": str(e),
            })

        manifest["records"].append(record)
        write_json(OUTPUT_DIR / "trace_net_llama32_vision_image_route_summary_v1.json", manifest)

        elapsed = time.time() - start
        print(
            f"[vision progress] {idx}/{len(selected)} "
            f"page_id={record['page_id']} status={record['summary_status']} "
            f"elapsed={elapsed:.1f}s image={image_path}",
            flush=True,
        )

    pass_count = sum(1 for r in manifest["records"] if r["summary_status"] == "PASS")
    error_count = sum(1 for r in manifest["records"] if r["summary_status"] == "ERROR")

    manifest.update({
        "status": "TRACE_NET_LLAMA32_VISION_IMAGE_ROUTE_SUMMARY_BUILT",
        "quality_status": "PASS" if pass_count > 0 and error_count == 0 else "PARTIAL",
        "summary": {
            "record_count": len(manifest["records"]),
            "pass_count": pass_count,
            "error_count": error_count,
            "model": MODEL,
            "vision_summary_guidance_only_count": len(manifest["records"]),
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "write_attempt_count": 0,
        },
    })

    write_json(OUTPUT_DIR / "trace_net_llama32_vision_image_route_summary_v1.json", manifest)

    print("status=" + manifest["status"])
    print("quality_status=" + manifest["quality_status"])
    print("record_count=" + str(len(manifest["records"])))
    print("pass_count=" + str(pass_count))
    print("error_count=" + str(error_count))
    print("output=" + str(OUTPUT_DIR / "trace_net_llama32_vision_image_route_summary_v1.json"))

    return 0 if pass_count > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
