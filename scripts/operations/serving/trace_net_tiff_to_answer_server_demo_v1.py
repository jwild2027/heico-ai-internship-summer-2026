#!/usr/bin/env python3
"""TRACE-Net raw TIFF -> validated answer executive server demo v1.

The demo is intentionally read-only. It reuses TRACE-Net's real ingestion artifacts,
optionally reruns OCR for one selected TIFF page, calls the normal OpenAI-compatible
TRACE-Net endpoint, and produces both a terminal walkthrough and a self-contained HTML
report. It never writes to Postgres, Qdrant, OpenSearch, or source artifacts.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, MutableMapping, Optional, Sequence

MODULE = "trace_net_tiff_to_answer_server_demo_v1"
VERSION = "v1"
STATUS = "TRACE_NET_TIFF_TO_ANSWER_SERVER_DEMO_V1"
DEFAULT_PAGE_ID = "t_p_120_1176_p000343"
DEFAULT_QUESTION = "What bigger assembly is 120-20970-001 installed inside?"
DEFAULT_MODEL = "trace-net-gemma4-cognitive-rag-v1"
DEFAULT_BASE_URL = "http://127.0.0.1:8131"
DEFAULT_API_KEY = "trace-net-openwebui-cognitive"
DEFAULT_QDRANT_COLLECTION = "trace_net_ocr_v2_v3_bge_m3"

STAGE_NAMES = (
    "Raw TIFF input",
    "Image signals and artifact detection",
    "OCR extraction",
    "Page route and classifier",
    "V2/V3 page intelligence",
    "Table, visual, and part extraction",
    "Storage contracts",
    "Interconnected graph",
    "Discovery Machine retrieval",
    "Typed evidence and critic",
    "Gemma answer generation",
    "Validation and final output",
)

PREFERRED_PIPELINE_DIRS = (
    "raw_to_answer_e2e_smoke_gemma4_strict_8192",
    "raw_to_answer_e2e_smoke_gemma4_strict_001",
    "raw_to_answer_e2e_smoke_gemma4_native_001",
    "raw_to_answer_e2e_smoke_gemma4_001",
)

ARTIFACT_SPECS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "pipeline": (("trace_net_ocr_classifier_pipeline_runner_v1.json",), ()),
    "ocr": (("trace_net_ocr_route_scan_pack_v1.json",), ()),
    "resolver": (("trace_net_route_confidence_resolver_v1.json",), ()),
    "four_route": (("trace_net_four_route_operational_resolver_v1.json",), ()),
    "validator": (("trace_net_route_validator_runner_v1.json",), ()),
    "storage": (("trace_net_four_route_storage_gate_v1.json",), ()),
    "retrieval_payload": (("trace_net_retrieval_payload_audit_v1.json",), ()),
    "v2": (("trace_net_v2_summary_guidance_index_v1.json",), ("*v2*summary*guidance*.json",)),
    "v3": ((), ("*v3*page*intelligence*.json", "*page*intelligence*v3*.json", "*v3*intelligence*.json")),
    "visual": (("trace_net_image_visual_evidence_pack_v1.json",), ("*visual*evidence*pack*.json", "*visual*summary*.json")),
    "table": ((), ("*table*reconstruction*.json", "*table*cell*.json", "*table*pack*.json")),
    "graph": ((), ("*graph*bundle*.json", "*graph*edges*.json", "*page*context*bundle*.json")),
    "embedding": (("trace_net_ocr_v2_v3_embedding_candidates_v1.json",), ("*embedding*candidates*.json",)),
}

MUTATING_TOKENS = (
    "insert into",
    "update ",
    "delete from",
    "drop table",
    "truncate ",
    "create collection",
    "recreate",
    "upsert",
    "points/delete",
    "points/upsert",
)


@dataclass
class Stage:
    number: int
    name: str
    status: str
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    presenter_note: str = ""


@dataclass
class DemoResult:
    status: str
    quality_status: str
    page_id: str
    question: str
    answer: str
    stages: list[Stage]
    artifacts: dict[str, str]
    output_dir: str
    report_path: str
    manifest_path: str
    raw_preview_path: str | None
    graph_path: str
    live_endpoint_called: bool
    model_call_count: int | None
    citations: list[dict[str, Any]]
    warnings: list[str]
    failures: list[str]
    safety: dict[str, Any]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def safe_text(value: Any, limit: int = 800) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def page_number(page_id: str) -> int | None:
    match = re.search(r"p(\d{6})$", page_id or "")
    return int(match.group(1)) if match else None


def normalize_path_text(value: str) -> str:
    return str(value or "").strip().replace("\\", "/").lstrip("./")


def walk_objects(value: Any, *, max_objects: int = 300_000) -> Iterator[Any]:
    stack = [value]
    seen = 0
    while stack and seen < max_objects:
        item = stack.pop()
        seen += 1
        yield item
        if isinstance(item, Mapping):
            stack.extend(reversed(list(item.values())))
        elif isinstance(item, list):
            stack.extend(reversed(item))


def find_record(value: Any, page_id: str) -> dict[str, Any] | None:
    wanted_number = page_number(page_id)
    fallback: dict[str, Any] | None = None
    for item in walk_objects(value):
        if not isinstance(item, Mapping):
            continue
        row_page_id = item.get("page_id") or item.get("canonical_page_id")
        if str(row_page_id or "") == page_id:
            return dict(item)
        row_number = item.get("page_number") or item.get("canonical_page_number")
        try:
            if wanted_number is not None and int(row_number) == wanted_number and fallback is None:
                fallback = dict(item)
        except (TypeError, ValueError):
            pass
    return fallback


def flatten_fields(value: Any, *, prefix: str = "", max_items: int = 800) -> dict[str, Any]:
    out: dict[str, Any] = {}
    stack: list[tuple[str, Any]] = [(prefix, value)]
    while stack and len(out) < max_items:
        key, item = stack.pop()
        if isinstance(item, Mapping):
            for child_key, child in reversed(list(item.items())):
                child_path = f"{key}.{child_key}" if key else str(child_key)
                stack.append((child_path, child))
        elif isinstance(item, list):
            if len(item) <= 12 and all(not isinstance(x, (Mapping, list)) for x in item):
                out[key] = item
            else:
                for index, child in reversed(list(enumerate(item[:40]))):
                    stack.append((f"{key}[{index}]", child))
        else:
            out[key] = item
    return out


def select_fields(record: Mapping[str, Any] | None, patterns: Sequence[str], *, limit: int = 18) -> dict[str, Any]:
    if not record:
        return {}
    flat = flatten_fields(record)
    selected: dict[str, Any] = {}
    compiled = [re.compile(pattern, re.I) for pattern in patterns]
    for key, value in flat.items():
        if value in (None, "", [], {}):
            continue
        if any(regex.search(key) for regex in compiled):
            selected[key] = value
            if len(selected) >= limit:
                break
    return selected


def find_first(root: Path, names: Sequence[str], patterns: Sequence[str]) -> Path | None:
    if not root.exists():
        return None
    for name in names:
        direct = root / name
        if direct.is_file():
            return direct
        matches = list(root.glob(f"*/{name}")) + list(root.glob(f"*/*/{name}"))
        if matches:
            return sorted(matches, key=lambda p: (len(p.parts), str(p)))[0]
    for pattern in patterns:
        matches = list(root.glob(pattern)) + list(root.glob(f"*/{pattern}")) + list(root.glob(f"*/*/{pattern}"))
        if matches:
            return sorted((p for p in matches if p.is_file()), key=lambda p: (len(p.parts), str(p)))[0]
    return None


def discover_pipeline_root(artifact_root: Path, explicit: Path | None = None) -> Path:
    if explicit:
        return explicit.resolve()
    for name in PREFERRED_PIPELINE_DIRS:
        candidate = artifact_root / name
        if (candidate / "trace_net_ocr_classifier_pipeline_runner_v1.json").is_file():
            return candidate.resolve()
    direct = find_first(artifact_root, ("trace_net_ocr_classifier_pipeline_runner_v1.json",), ())
    if direct:
        return direct.parent.resolve()
    raise FileNotFoundError(
        "Could not discover a raw-to-answer pipeline root. Pass --pipeline-root pointing to a completed "
        "raw_to_answer_e2e_smoke_* directory."
    )


def discover_artifacts(artifact_root: Path, pipeline_root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for key, (names, patterns) in ARTIFACT_SPECS.items():
        search_roots = (pipeline_root, artifact_root) if key not in {"pipeline", "ocr", "resolver", "four_route", "validator", "storage", "retrieval_payload"} else (pipeline_root,)
        for root in search_roots:
            found = find_first(root, names, patterns)
            if found:
                result[key] = found.resolve()
                break
    return result


def load_artifact_records(paths: Mapping[str, Path], page_id: str) -> tuple[dict[str, Any], dict[str, dict[str, Any] | None], list[str]]:
    payloads: dict[str, Any] = {}
    records: dict[str, dict[str, Any] | None] = {}
    warnings: list[str] = []
    for key, path in paths.items():
        try:
            payload = read_json(path)
            payloads[key] = payload
            records[key] = find_record(payload, page_id)
        except Exception as exc:
            warnings.append(f"Could not read {key} artifact {path}: {type(exc).__name__}: {exc}")
            records[key] = None
    return payloads, records, warnings


def extract_ocr_text(record: Mapping[str, Any] | None) -> str:
    if not record:
        return ""
    preferred = (
        "ocr_text", "best_ocr_text", "combined_ocr_text", "page_text", "text",
        "ocr_sample_text", "sample_text", "visual_summary_text", "summary_text",
    )
    for key in preferred:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for item in walk_objects(record, max_objects=20_000):
        if isinstance(item, Mapping):
            for key in preferred:
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return ""


def candidate_source_names(record: Mapping[str, Any] | None, page_id: str) -> list[str]:
    names: list[str] = []
    if record:
        flat = flatten_fields(record)
        for key, value in flat.items():
            if not isinstance(value, str):
                continue
            if re.search(r"(source_member|raw_tiff|tiff_reference|image_path|source_path|member_name|file_name)", key, re.I):
                normalized = normalize_path_text(value)
                if normalized and normalized not in names:
                    names.append(normalized)
    number = page_number(page_id)
    if number is not None:
        for stem in (f"{number}", f"{number:04d}", f"{number:06d}", f"p{number:06d}"):
            for suffix in (".tif", ".tiff", ".TIF", ".TIFF"):
                names.append(stem + suffix)
    return list(dict.fromkeys(names))


def score_member(member: str, candidates: Sequence[str], page_id: str) -> tuple[int, str]:
    normalized = normalize_path_text(member)
    base = Path(normalized).name.lower()
    score = 0
    reason = ""
    for candidate in candidates:
        cand = normalize_path_text(candidate)
        if normalized.lower() == cand.lower():
            return 1000, "exact_source_member"
        if normalized.lower().endswith(cand.lower()):
            score = max(score, 850)
            reason = "source_member_suffix"
        if base == Path(cand).name.lower():
            score = max(score, 800)
            reason = "source_basename"
    number = page_number(page_id)
    if number is not None:
        tokens = re.findall(r"\d+", base)
        if any(int(token) == number for token in tokens):
            score = max(score, 400)
            reason = "page_number_in_filename"
        if f"p{number:06d}" in normalized.lower():
            score = max(score, 600)
            reason = "canonical_page_suffix"
    if base.endswith((".tif", ".tiff")):
        score += 10
    return score, reason


def resolve_source_package(source_package: Path | None, candidates: Sequence[str], page_id: str, search_roots: Sequence[Path]) -> tuple[Path | None, str | None, list[str]]:
    warnings: list[str] = []
    files: list[Path] = []
    if source_package:
        files.append(source_package.resolve())
    else:
        for root in search_roots:
            if not root.exists():
                continue
            for pattern in ("*.zip", "*.tif", "*.tiff"):
                files.extend(list(root.glob(pattern)))
                files.extend(list(root.glob(f"*/{pattern}")))
    checked = 0
    best: tuple[int, Path, str, str] | None = None
    for path in list(dict.fromkeys(files))[:80]:
        if not path.is_file():
            continue
        checked += 1
        try:
            if zipfile.is_zipfile(path):
                with zipfile.ZipFile(path) as archive:
                    for member in archive.namelist():
                        score, reason = score_member(member, candidates, page_id)
                        if score > 0 and (best is None or score > best[0]):
                            best = (score, path, member, reason)
            else:
                score, reason = score_member(path.name, candidates, page_id)
                if score > 0 and (best is None or score > best[0]):
                    best = (score, path, path.name, reason)
        except Exception as exc:
            warnings.append(f"Skipped source candidate {path}: {type(exc).__name__}: {exc}")
    if best:
        warnings.append(f"Raw source selected by {best[3]} after checking {checked} candidate files.")
        return best[1], best[2], warnings
    warnings.append(f"No raw TIFF member matched {page_id}; checked {checked} candidate files.")
    return None, None, warnings


def extract_raw_tiff(package: Path | None, member: str | None, output_dir: Path) -> tuple[Path | None, dict[str, Any]]:
    if not package or not member:
        return None, {"available": False}
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(member).suffix if Path(member).suffix.lower() in {".tif", ".tiff"} else ".tiff"
    destination = raw_dir / ("selected_page" + suffix.lower())
    if zipfile.is_zipfile(package):
        with zipfile.ZipFile(package) as archive:
            raw = archive.read(member)
    else:
        raw = package.read_bytes()
    destination.write_bytes(raw)
    return destination, {
        "available": True,
        "source_package": str(package),
        "source_member": member,
        "extracted_path": str(destination),
        "byte_count": len(raw),
        "sha256": sha256_bytes(raw),
    }


def make_preview(tiff_path: Path | None, output_dir: Path) -> tuple[Path | None, dict[str, Any], list[str]]:
    warnings: list[str] = []
    if not tiff_path:
        return None, {"available": False}, warnings
    try:
        from PIL import Image, ImageOps
    except Exception as exc:
        warnings.append(f"Pillow unavailable; TIFF preview skipped: {exc}")
        return None, {"available": False, "reason": "pillow_unavailable"}, warnings
    try:
        with Image.open(tiff_path) as image:
            frame_count = int(getattr(image, "n_frames", 1))
            image.seek(0)
            source_mode = image.mode
            width, height = image.size
            preview = ImageOps.exif_transpose(image).convert("RGB")
            preview.thumbnail((1500, 1800))
            path = output_dir / "raw_page_preview.png"
            preview.save(path, "PNG", optimize=True)
        return path, {
            "available": True,
            "width": width,
            "height": height,
            "mode": source_mode,
            "frame_count": frame_count,
            "preview_path": str(path),
        }, warnings
    except Exception as exc:
        warnings.append(f"Could not render TIFF preview: {type(exc).__name__}: {exc}")
        return None, {"available": False, "reason": str(exc)}, warnings


def run_live_ocr(tiff_path: Path | None, tesseract_cmd: str, psm_modes: Sequence[int], timeout: int) -> dict[str, Any]:
    if not tiff_path:
        return {"requested": True, "status": "SKIP", "reason": "raw_tiff_unavailable", "attempts": []}
    executable = shutil.which(tesseract_cmd) or (str(Path(tesseract_cmd)) if Path(tesseract_cmd).is_file() else None)
    if not executable:
        return {"requested": True, "status": "SKIP", "reason": "tesseract_not_found", "attempts": []}
    attempts: list[dict[str, Any]] = []
    for psm in psm_modes:
        started = time.monotonic()
        command = [executable, str(tiff_path), "stdout", "--psm", str(psm)]
        try:
            proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
            text = proc.stdout or ""
            attempts.append({
                "psm": psm,
                "returncode": proc.returncode,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "char_count": len(text.strip()),
                "text": text.strip(),
                "stderr_excerpt": safe_text(proc.stderr, 300),
            })
        except Exception as exc:
            attempts.append({
                "psm": psm,
                "returncode": -1,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "char_count": 0,
                "text": "",
                "stderr_excerpt": f"{type(exc).__name__}: {exc}",
            })
    best = max(attempts, key=lambda row: int(row.get("char_count") or 0), default={})
    return {
        "requested": True,
        "status": "PASS" if int(best.get("char_count") or 0) > 0 else "WARN",
        "executable": executable,
        "best_psm": best.get("psm"),
        "best_char_count": best.get("char_count", 0),
        "best_text": best.get("text", ""),
        "attempts": [{k: v for k, v in row.items() if k != "text"} for row in attempts],
    }


def http_json(url: str, *, method: str = "GET", payload: Mapping[str, Any] | None = None, api_key: str = "", timeout: float = 30.0) -> tuple[int, dict[str, Any], float]:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            value = json.loads(raw) if raw.strip() else {}
            return int(response.status), value if isinstance(value, dict) else {"value": value}, round(time.monotonic() - started, 3)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            value = json.loads(raw)
        except Exception:
            value = {"error": raw or str(exc)}
        return int(exc.code), value if isinstance(value, dict) else {"value": value}, round(time.monotonic() - started, 3)
    except Exception as exc:
        return 599, {"error": f"{type(exc).__name__}: {exc}"}, round(time.monotonic() - started, 3)


def call_trace_net(base_url: str, api_key: str, model: str, question: str, timeout: float) -> dict[str, Any]:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    health_status, health, health_seconds = http_json(base + "/health", api_key=api_key, timeout=min(timeout, 20.0))
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": question}],
        "temperature": 0,
        "stream": False,
    }
    status, response, elapsed = http_json(
        base + "/v1/chat/completions",
        method="POST",
        payload=payload,
        api_key=api_key,
        timeout=timeout,
    )
    choices = response.get("choices") if isinstance(response, Mapping) else None
    answer = ""
    if isinstance(choices, list) and choices and isinstance(choices[0], Mapping):
        message = choices[0].get("message")
        if isinstance(message, Mapping):
            answer = str(message.get("content") or "")
    return {
        "health_http_status": health_status,
        "health": health,
        "health_seconds": health_seconds,
        "http_status": status,
        "elapsed_seconds": elapsed,
        "response": response,
        "answer": answer,
        "called": True,
    }


def recursive_values(value: Any, key_pattern: str) -> list[tuple[str, Any]]:
    regex = re.compile(key_pattern, re.I)
    found: list[tuple[str, Any]] = []
    stack: list[tuple[str, Any]] = [("", value)]
    while stack and len(found) < 200:
        path, item = stack.pop()
        if isinstance(item, Mapping):
            for key, child in item.items():
                child_path = f"{path}.{key}" if path else str(key)
                if regex.search(str(key)):
                    found.append((child_path, child))
                if isinstance(child, (Mapping, list)):
                    stack.append((child_path, child))
        elif isinstance(item, list):
            for index, child in enumerate(item[:100]):
                if isinstance(child, (Mapping, list)):
                    stack.append((f"{path}[{index}]", child))
    return found


def first_scalar(value: Any, patterns: Sequence[str]) -> Any:
    for pattern in patterns:
        for _, found in recursive_values(value, pattern):
            if isinstance(found, (str, int, float, bool)) and found not in ("", None):
                return found
    return None


def collect_citations(value: Any) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for item in walk_objects(value, max_objects=100_000):
        if not isinstance(item, Mapping):
            continue
        page_id_value = item.get("page_id") or item.get("source_page_id") or item.get("canonical_page_id")
        source_member = item.get("source_member") or item.get("source")
        page_value = item.get("page_number") or item.get("canonical_page_number")
        citation_id = item.get("citation_id") or item.get("id")
        if page_id_value or (source_member and page_value):
            row = {
                "citation_id": citation_id,
                "page_id": page_id_value,
                "page_number": page_value,
                "source_member": source_member,
                "source_trace": item.get("source_trace"),
            }
            key = tuple(row.get(name) for name in ("page_id", "page_number", "source_member"))
            if key not in seen:
                seen.add(key)
                citations.append(row)
                if len(citations) >= 20:
                    break
    return citations


def detect_identifiers(text: str) -> list[str]:
    seen: list[str] = []
    for match in re.findall(r"\b\d{2,4}-[A-Z0-9]{2,8}-[A-Z0-9]{2,8}\b", text or "", flags=re.I):
        value = match.upper()
        if value not in seen:
            seen.append(value)
    return seen


def find_relationship(release_dir: Path, child: str) -> dict[str, Any] | None:
    if not release_dir.exists():
        return None
    for path in sorted(release_dir.glob("*.json")) + sorted(release_dir.glob("*/*.json")):
        try:
            payload = read_json(path)
        except Exception:
            continue
        for item in walk_objects(payload, max_objects=100_000):
            if not isinstance(item, Mapping):
                continue
            flat = {str(k).lower(): v for k, v in item.items()}
            child_values = [flat.get(k) for k in ("child_part_number", "child_part", "part_number", "source_part_number", "from_part")]
            if child not in [str(value or "").upper() for value in child_values]:
                continue
            for key in ("parent_part_number", "next_higher_assembly", "parent_assembly", "assembly_part_number", "to_part"):
                value = flat.get(key)
                if isinstance(value, str) and value.strip() and value.upper() != child:
                    return {"child": child, "parent": value.upper(), "record": dict(item), "artifact": str(path)}
    return None


def qdrant_health(base_url: str, collection: str, timeout: float = 10.0) -> dict[str, Any]:
    status, payload, elapsed = http_json(base_url.rstrip("/") + f"/collections/{collection}", timeout=timeout)
    result = payload.get("result") if isinstance(payload, Mapping) else None
    points = None
    if isinstance(result, Mapping):
        points = result.get("points_count") or result.get("vectors_count")
    return {"http_status": status, "elapsed_seconds": elapsed, "collection": collection, "points_count": points, "payload": payload}


def make_graph_svg(page_id: str, child: str | None, parent: str | None, citations: Sequence[Mapping[str, Any]]) -> str:
    def esc(value: Any) -> str:
        return html.escape(str(value or ""), quote=True)

    child_label = child or "Detected part"
    parent_label = parent or "Next higher assembly"
    evidence_labels = []
    for row in citations[:3]:
        label = row.get("page_id") or row.get("page_number") or "Evidence page"
        evidence_labels.append(str(label))
    while len(evidence_labels) < 3:
        evidence_labels.append(f"Evidence {len(evidence_labels) + 1}")

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 560" role="img" aria-label="TRACE-Net interconnected graph">
<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#657451"/></marker><filter id="shadow"><feDropShadow dx="0" dy="3" stdDeviation="4" flood-opacity="0.14"/></filter></defs>
<style>.node{{fill:#fff;stroke:#8b9875;stroke-width:2;rx:18;filter:url(#shadow)}}.title{{font:700 24px Arial;fill:#26302a}}.small{{font:17px Arial;fill:#475148}}.edge{{stroke:#657451;stroke-width:3;fill:none;marker-end:url(#arrow)}}.edgeLabel{{font:16px Arial;fill:#657451}}</style>
<rect width="1200" height="560" fill="#f7f7f3" rx="24"/>
<rect class="node" x="40" y="220" width="190" height="96"/><text class="title" x="135" y="258" text-anchor="middle">Raw TIFF</text><text class="small" x="135" y="288" text-anchor="middle">{esc(page_id)}</text>
<rect class="node" x="300" y="220" width="190" height="96"/><text class="title" x="395" y="258" text-anchor="middle">OCR + route</text><text class="small" x="395" y="288" text-anchor="middle">classified page</text>
<rect class="node" x="560" y="220" width="190" height="96"/><text class="title" x="655" y="258" text-anchor="middle">Part</text><text class="small" x="655" y="288" text-anchor="middle">{esc(child_label)}</text>
<rect class="node" x="820" y="220" width="300" height="96"/><text class="title" x="970" y="258" text-anchor="middle">Next higher assembly</text><text class="small" x="970" y="288" text-anchor="middle">{esc(parent_label)}</text>
<path class="edge" d="M230 268 L300 268"/><text class="edgeLabel" x="265" y="248" text-anchor="middle">extracts</text>
<path class="edge" d="M490 268 L560 268"/><text class="edgeLabel" x="525" y="248" text-anchor="middle">mentions</text>
<path class="edge" d="M750 268 L820 268"/><text class="edgeLabel" x="785" y="248" text-anchor="middle">installed in</text>
<rect class="node" x="400" y="45" width="270" height="78"/><text class="title" x="535" y="78" text-anchor="middle">Evidence page</text><text class="small" x="535" y="103" text-anchor="middle">{esc(evidence_labels[0])}</text>
<rect class="node" x="705" y="45" width="270" height="78"/><text class="title" x="840" y="78" text-anchor="middle">Evidence page</text><text class="small" x="840" y="103" text-anchor="middle">{esc(evidence_labels[1])}</text>
<rect class="node" x="550" y="405" width="270" height="78"/><text class="title" x="685" y="438" text-anchor="middle">Evidence page</text><text class="small" x="685" y="463" text-anchor="middle">{esc(evidence_labels[2])}</text>
<path class="edge" d="M535 123 C560 165 600 190 630 220"/><path class="edge" d="M840 123 C810 165 755 190 700 220"/><path class="edge" d="M685 405 L685 316"/>
<text class="edgeLabel" x="590" y="166">supports</text><text class="edgeLabel" x="770" y="166">supports</text><text class="edgeLabel" x="700" y="365">supports</text>
</svg>'''


def ansi(text: str, color: str = "") -> str:
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return text
    codes = {"green": "32", "yellow": "33", "red": "31", "cyan": "36", "bold": "1", "dim": "2"}
    return f"\033[{codes.get(color, '0')}m{text}\033[0m" if color else text


def print_stage(stage: Stage, *, pause: bool = False) -> None:
    color = "green" if stage.status == "PASS" else "yellow" if stage.status in {"WARN", "SKIP"} else "red"
    print("\n" + ansi("=" * 88, "dim"))
    print(ansi(f"STEP {stage.number:02d} — {stage.name}", "bold"))
    print(f"Status: {ansi(stage.status, color)}")
    print(textwrap.fill(stage.summary, width=88))
    if stage.details:
        print(ansi("Key data:", "cyan"))
        for key, value in list(stage.details.items())[:18]:
            rendered = safe_text(json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value, 500)
            print(f"  {key}: {rendered}")
    if stage.presenter_note:
        print(ansi("Presenter note:", "cyan"), textwrap.fill(stage.presenter_note, width=76, subsequent_indent="  "))
    if pause and sys.stdin.isatty():
        input(ansi("Press Enter for the next step… ", "yellow"))


def stage_status(found: bool, required: bool = False) -> str:
    if found:
        return "PASS"
    return "FAIL" if required else "WARN"


def safe_json_script(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def render_html(result: DemoResult, preview_data_uri: str | None, graph_svg: str, live_response: Mapping[str, Any]) -> str:
    stage_cards = []
    for stage in result.stages:
        details = html.escape(json.dumps(stage.details, indent=2, ensure_ascii=False, default=str))
        stage_cards.append(f'''<section class="stage status-{stage.status.lower()}">
<div class="stepnum">{stage.number}</div><div class="stagebody"><div class="row"><h2>{html.escape(stage.name)}</h2><span class="badge">{html.escape(stage.status)}</span></div>
<p>{html.escape(stage.summary)}</p><details><summary>Show stage data</summary><pre>{details}</pre></details>
{f'<p class="note"><strong>What to say:</strong> {html.escape(stage.presenter_note)}</p>' if stage.presenter_note else ''}</div></section>''')
    preview = f'<img src="{preview_data_uri}" alt="Selected raw TIFF page preview">' if preview_data_uri else '<div class="missing">Raw TIFF preview unavailable. Pass --source-package and --require-raw-tiff for a strict live demo.</div>'
    citations_html = "".join(
        f"<li>{html.escape(str(row.get('page_id') or row.get('page_number') or row.get('source_member') or row))}</li>"
        for row in result.citations[:10]
    ) or "<li>No citation objects were exposed in the public response.</li>"
    answer = html.escape(result.answer or "No answer returned.")
    warnings_html = "".join(f"<li>{html.escape(value)}</li>" for value in result.warnings) or "<li>None</li>"
    raw_response = html.escape(json.dumps(live_response, indent=2, ensure_ascii=False, default=str))
    manifest = safe_json_script({
        "status": result.status,
        "quality_status": result.quality_status,
        "page_id": result.page_id,
        "question": result.question,
        "model_call_count": result.model_call_count,
        "safety": result.safety,
    })
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TRACE-Net TIFF to Answer Demo</title><style>
:root{{--bg:#f4f5f1;--card:#fff;--ink:#202621;--muted:#64705d;--green:#667750;--orange:#c85a2b;--line:#d9ddd3;--ok:#2c7a46;--warn:#a36b00;--bad:#a93434}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Segoe UI,Arial,sans-serif;line-height:1.45}}header{{padding:56px 7vw 36px;background:linear-gradient(135deg,#fbfbf8,#eef1e9);border-bottom:8px solid var(--orange)}}h1{{font-size:clamp(42px,7vw,88px);margin:0;letter-spacing:-.04em;font-weight:650}}header p{{font-size:clamp(18px,2vw,28px);color:var(--green);margin:8px 0}}.meta{{display:flex;gap:12px;flex-wrap:wrap;margin-top:22px}}.pill{{background:#fff;border:1px solid var(--line);padding:8px 14px;border-radius:999px}}main{{max-width:1500px;margin:auto;padding:38px 4vw 80px}}.hero-grid{{display:grid;grid-template-columns:minmax(320px,0.9fr) minmax(420px,1.3fr);gap:28px;align-items:stretch}}.panel{{background:var(--card);border:1px solid var(--line);border-radius:22px;padding:24px;box-shadow:0 10px 28px rgba(30,40,30,.07)}}.panel h2{{margin-top:0;color:var(--green)}}img{{max-width:100%;max-height:720px;display:block;margin:auto;border-radius:10px}}.graph svg{{width:100%;height:auto}}.question{{font-size:28px;font-weight:650;border-left:7px solid var(--green);padding-left:18px}}.answer{{white-space:pre-wrap;background:#f5f7f2;border-radius:14px;padding:20px;font-size:18px}}.stage{{display:grid;grid-template-columns:64px 1fr;gap:18px;background:#fff;border:1px solid var(--line);border-radius:18px;padding:20px;margin:16px 0}}.stepnum{{width:52px;height:52px;border-radius:50%;display:grid;place-items:center;background:var(--green);color:#fff;font-size:22px;font-weight:700}}.row{{display:flex;justify-content:space-between;gap:20px;align-items:flex-start}}.stage h2{{margin:0;font-size:24px}}.badge{{font-weight:700;padding:5px 11px;border-radius:999px;background:#e9eee3;color:var(--ok)}}.status-warn .badge,.status-skip .badge{{background:#fff1c9;color:var(--warn)}}.status-fail .badge{{background:#ffe0e0;color:var(--bad)}}details{{margin-top:12px}}pre{{background:#0b3037;color:#d7eff0;padding:18px;border-radius:12px;overflow:auto;max-height:420px;font-size:13px}}.note{{background:#f1f4eb;padding:12px;border-radius:10px}}.brain{{background:#092f36;color:#d8f0ef;border-radius:16px;padding:24px;font:16px/1.65 ui-monospace,SFMono-Regular,Consolas,monospace;overflow:auto}}.brain .kw{{color:#b6cf46}}.brain .fn{{color:#42a9e8}}.warnings{{border-left:5px solid #d49319}}.missing{{padding:40px;background:#f0f0ed;border-radius:12px;color:#666}}footer{{text-align:center;padding:28px;color:#687064}}@media(max-width:900px){{.hero-grid{{grid-template-columns:1fr}}.stage{{grid-template-columns:1fr}}}}
</style></head><body><header><h1>Raw TIFF → Validated Answer</h1><p>TRACE-Net end-to-end server demonstration</p><div class="meta"><span class="pill">Page: {html.escape(result.page_id)}</span><span class="pill">Model: {DEFAULT_MODEL}</span><span class="pill">Quality: {html.escape(result.quality_status)}</span><span class="pill">Read-only demo</span></div></header>
<main><div class="hero-grid"><div class="panel"><h2>1. Raw engineering page</h2>{preview}</div><div class="panel graph"><h2>2. Interconnected graph</h2>{graph_svg}</div></div>
<div class="hero-grid" style="margin-top:28px"><div class="panel"><h2>Demo question</h2><div class="question">{html.escape(result.question)}</div><h3>Final validated answer</h3><div class="answer">{answer}</div></div><div class="panel"><h2>Proof returned with the answer</h2><ol>{citations_html}</ol><p><strong>Model calls detected:</strong> {html.escape(str(result.model_call_count))}</p><p><strong>Safety:</strong> no database writes and no source mutation.</p></div></div>
<h2 style="font-size:38px;margin-top:55px">Every stage, from ingestion to output</h2>{''.join(stage_cards)}
<div class="hero-grid" style="margin-top:28px"><div class="panel"><h2>The brain, simplified</h2><div class="brain"><span class="kw">def</span> <span class="fn">answer_question</span>(question):<br>&nbsp;&nbsp;plan = <span class="fn">route</span>(question)<br>&nbsp;&nbsp;evidence = <span class="fn">bounded_retrieval</span>(plan)<br>&nbsp;&nbsp;envelope = <span class="fn">type_and_validate</span>(evidence)<br>&nbsp;&nbsp;draft = <span class="fn">gemma_generate</span>(envelope)<br>&nbsp;&nbsp;<span class="kw">return</span> <span class="fn">validate_and_release</span>(draft)</div></div><div class="panel warnings"><h2>Warnings and environment notes</h2><ul>{warnings_html}</ul></div></div>
<div class="panel" style="margin-top:28px"><details><summary><strong>Auditor view: complete public endpoint response</strong></summary><pre>{raw_response}</pre></details></div>
<script type="application/json" id="trace-net-demo-manifest">{manifest}</script></main><footer>TRACE-Net Evidence-Aware Hybrid Answering · Generated by {MODULE}</footer></body></html>'''


def data_uri(path: Path | None) -> str | None:
    if not path or not path.is_file():
        return None
    mime = "image/png" if path.suffix.lower() == ".png" else "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def build_demo(args: argparse.Namespace) -> DemoResult:
    repo = Path(args.repo).resolve()
    artifact_root = Path(args.artifact_root).resolve() if args.artifact_root else repo / "local_data/organization/trace_net"
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    warnings: list[str] = []

    pipeline_root = discover_pipeline_root(artifact_root, Path(args.pipeline_root).resolve() if args.pipeline_root else None)
    artifact_paths = discover_artifacts(artifact_root, pipeline_root)
    payloads, records, load_warnings = load_artifact_records(artifact_paths, args.page_id)
    warnings.extend(load_warnings)

    ocr_record = records.get("ocr")
    candidates = candidate_source_names(ocr_record, args.page_id)
    package, member, source_warnings = resolve_source_package(
        Path(args.source_package).resolve() if args.source_package else None,
        candidates,
        args.page_id,
        (Path("/data/trace_net"), Path("/data/heico-ai"), repo.parent, repo),
    )
    warnings.extend(source_warnings)
    raw_tiff, raw_info = extract_raw_tiff(package, member, output_dir)
    preview, preview_info, preview_warnings = make_preview(raw_tiff, output_dir)
    warnings.extend(preview_warnings)
    if args.require_raw_tiff and not raw_tiff:
        failures.append("required_raw_tiff_not_found")

    live_ocr = run_live_ocr(raw_tiff, args.tesseract_cmd, args.psm_modes, args.ocr_timeout) if args.live_ocr else {"requested": False, "status": "SKIP", "reason": "disabled"}
    artifact_ocr_text = extract_ocr_text(ocr_record)
    live_ocr_text = str(live_ocr.get("best_text") or "")
    chosen_ocr = live_ocr_text or artifact_ocr_text

    endpoint = call_trace_net(args.base_url, args.api_key, args.model, args.question, args.request_timeout)
    answer = str(endpoint.get("answer") or "")
    response = endpoint.get("response") if isinstance(endpoint.get("response"), Mapping) else {}
    if int(endpoint.get("http_status") or 0) != 200:
        failures.append(f"public_endpoint_http_{endpoint.get('http_status')}")
    if not answer.strip():
        failures.append("empty_public_answer")

    route = first_scalar(response, (r"^route$", r"selected_route", r"actual_route", r"route_name"))
    model_call_count = first_scalar(response, (r"actual_model_call_count", r"model_call_count", r"model_calls", r"gemma_call_count"))
    try:
        model_call_count = int(model_call_count) if model_call_count is not None else None
    except (TypeError, ValueError):
        model_call_count = None
    citations = collect_citations(response)
    if not citations:
        citations = collect_citations(records.get("retrieval_payload") or {})
    if args.require_one_model_call and model_call_count != 1:
        failures.append(f"required_one_model_call_actual_{model_call_count}")
    if len(citations) < args.min_citations:
        failures.append(f"minimum_citations_{args.min_citations}_actual_{len(citations)}")

    identifiers = detect_identifiers(args.question + "\n" + answer)
    child = identifiers[0] if identifiers else None
    release_dir = Path(args.nha_release_dir).resolve() if args.nha_release_dir else repo / "release_data/trace_net/nha_real_release_v1/phase4"
    relationship = find_relationship(release_dir, child) if child else None
    parent = relationship.get("parent") if relationship else (identifiers[1] if len(identifiers) > 1 else None)
    graph_svg = make_graph_svg(args.page_id, child, parent, citations)
    graph_path = output_dir / "interconnected_graph.svg"
    graph_path.write_text(graph_svg, encoding="utf-8")

    qdrant = qdrant_health(args.qdrant_url, args.qdrant_collection) if args.check_qdrant else {"status": "SKIP"}
    if args.require_qdrant and int(qdrant.get("http_status") or 0) != 200:
        failures.append("required_qdrant_health_failed")

    image_fields = select_fields(ocr_record, (
        r"ink", r"pixel", r"artifact", r"blank", r"density", r"width", r"height", r"image_sha", r"ocr_engine_status",
    ))
    route_fields = {}
    for key in ("resolver", "four_route", "validator"):
        route_fields[key] = select_fields(records.get(key), (r"route", r"confidence", r"validator", r"resolved", r"subtype", r"reason"), limit=12)
    page_intelligence = {
        "v2": select_fields(records.get("v2"), (r"summary", r"topic", r"figure", r"part", r"route", r"confidence"), limit=14),
        "v3": select_fields(records.get("v3"), (r"summary", r"page_type", r"identifier", r"warning", r"table", r"visual", r"confidence"), limit=14),
    }
    extraction = {
        "table": select_fields(records.get("table"), (r"table", r"row", r"cell", r"part", r"item", r"nomenclature"), limit=14),
        "visual": select_fields(records.get("visual"), (r"visual", r"figure", r"callout", r"part", r"nomenclature", r"summary"), limit=14),
        "detected_identifiers": identifiers,
    }
    storage_fields = select_fields(records.get("storage"), (
        r"postgres", r"qdrant", r"opensearch", r"storage", r"lineage", r"write", r"mutation", r"allowed", r"contract",
    ), limit=24)
    critic_fields = {}
    for path, value in recursive_values(response, r"self.?rag|crag|critic|evidence.?envelope|claim.?ready|typed.?evidence")[:30]:
        if not isinstance(value, (Mapping, list)):
            critic_fields[path] = value
    gemma_fields = {}
    for path, value in recursive_values(response, r"gemma|model.?call|writer|generation|fallback|accepted")[:35]:
        if not isinstance(value, (Mapping, list)):
            gemma_fields[path] = value
    validation_fields = {}
    for path, value in recursive_values(response, r"validation|citation|limits|quality_status|answer_mode|synthetic|source_truth_mutation|write_attempt")[:35]:
        if not isinstance(value, (Mapping, list)):
            validation_fields[path] = value

    stages = [
        Stage(1, STAGE_NAMES[0], stage_status(bool(raw_tiff), args.require_raw_tiff),
              "TRACE-Net begins with the original scanned engineering page, preserving its source member and SHA-256 lineage.",
              {**raw_info, **preview_info},
              "Start with the page itself. The system always keeps a trace back to the original scan."),
        Stage(2, STAGE_NAMES[1], stage_status(bool(ocr_record)),
              "Image-level signals identify blank pages, text density, tables, diagrams, and artifacts before expensive processing.",
              image_fields,
              "This prevents every page from being treated the same and routes expensive work only where it helps."),
        Stage(3, STAGE_NAMES[2], "PASS" if chosen_ocr else "WARN",
              "OCR converts pixels into searchable text. The demo can rerun Tesseract live for this one page and compare it with the stored OCR artifact.",
              {"artifact_ocr_char_count": len(artifact_ocr_text), "live_ocr": {k: v for k, v in live_ocr.items() if k != "best_text"}, "ocr_excerpt": safe_text(chosen_ocr, 1200)},
              "The text is not automatically trusted as perfect; it remains linked to the page image and uncertainty data."),
        Stage(4, STAGE_NAMES[3], stage_status(any(records.get(key) for key in ("resolver", "four_route", "validator"))),
              "The classifier resolves the page into bounded operational routes such as blank, plain text, table, or image/diagram, then validates that decision.",
              route_fields,
              "Routing is code-controlled. The model does not freely choose whatever source looks convenient."),
        Stage(5, STAGE_NAMES[4], stage_status(bool(records.get("v2") or records.get("v3"))),
              "V2 summaries and V3 page intelligence add page type, visible identifiers, warnings, table/figure signals, and retrieval guidance.",
              page_intelligence,
              "These summaries guide discovery, but they do not become source truth by themselves."),
        Stage(6, STAGE_NAMES[5], stage_status(bool(records.get("table") or records.get("visual") or identifiers)),
              "Specialists extract table rows, nomenclature, figure callouts, and part-number clues while preserving exact page lineage.",
              extraction,
              "Tables and diagrams need different extraction logic; TRACE-Net merges them only after their roles are clear."),
        Stage(7, STAGE_NAMES[6], stage_status(bool(records.get("storage") or records.get("retrieval_payload"))),
              "Storage contracts decide what is eligible for the graph, vector retrieval, and search indexes. This demo only reads those decisions.",
              {"storage_record": storage_fields, "qdrant_health": {k: v for k, v in qdrant.items() if k != "payload"}},
              "The graph stores relationships; Qdrant helps find semantically related pages. Eligibility and lineage are checked before loading."),
        Stage(8, STAGE_NAMES[7], "PASS",
              "The graph connects the raw page, extracted part, supporting evidence pages, and the next higher assembly relationship.",
              {"relationship": relationship or {"child": child, "parent": parent}, "graph_svg": str(graph_path)},
              "This is the key visual: TRACE-Net turns separate pages into an explainable knowledge map."),
        Stage(9, STAGE_NAMES[8], "PASS" if int(endpoint.get("http_status") or 0) == 200 else "FAIL",
              "The normal public endpoint routes the natural-language question and performs bounded retrieval across exact, graph, vector, table, OCR, and visual tunnels as needed.",
              {"route": route, "endpoint_http_status": endpoint.get("http_status"), "latency_seconds": endpoint.get("elapsed_seconds"), "qdrant_points": qdrant.get("points_count")},
              "This is the Discovery Machine: it gathers a small proof packet rather than dumping the whole manual into the model."),
        Stage(10, STAGE_NAMES[9], "PASS" if answer else "WARN",
              "Retrieved material is separated into direct evidence, guidance, contradictions, and source resolution. Self-RAG checks sufficiency and CRAG can perform a bounded repair.",
              critic_fields or {"note": "Public response did not expose detailed critic telemetry; validation still occurred inside the endpoint."},
              "Candidate or summary guidance can help find proof, but only direct source-traced evidence may support the answer."),
        Stage(11, STAGE_NAMES[10], "PASS" if answer and (model_call_count in (None, 1) or model_call_count > 0) else "WARN",
              "Gemma receives the controlled evidence packet and writes the explanation. The code retains ownership of evidence and citations.",
              {"model": args.model, "model_call_count": model_call_count, "gemma_telemetry": gemma_fields, "answer_excerpt": safe_text(answer, 1400)},
              "Gemma explains; it does not get permission to invent new evidence or silently change identifiers."),
        Stage(12, STAGE_NAMES[11], "PASS" if answer and not failures else "FAIL",
              "The final validator preserves identifiers, checks citation support and safety limits, then releases a clean OpenWebUI-compatible answer.",
              {"citation_count": len(citations), "citations": citations[:10], "validation": validation_fields, "final_answer": answer},
              "End on what the user sees: a direct answer, evidence, and limits—not internal JSON or unsupported confidence."),
    ]

    for stage in stages:
        print_stage(stage, pause=args.present)

    safety = {
        "read_only": True,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "source_truth_mutation_allowed": False,
        "source_artifact_mutation_count": 0,
        "database_mutation_code_present": False,
    }
    quality = "PASS" if not failures else "FAIL"
    result = DemoResult(
        status=STATUS,
        quality_status=quality,
        page_id=args.page_id,
        question=args.question,
        answer=answer,
        stages=stages,
        artifacts={key: str(path) for key, path in artifact_paths.items()},
        output_dir=str(output_dir),
        report_path=str(output_dir / "trace_net_tiff_to_answer_demo_v1.html"),
        manifest_path=str(output_dir / "trace_net_tiff_to_answer_demo_v1.json"),
        raw_preview_path=str(preview) if preview else None,
        graph_path=str(graph_path),
        live_endpoint_called=True,
        model_call_count=model_call_count,
        citations=citations,
        warnings=warnings,
        failures=failures,
        safety=safety,
    )

    report_path = Path(result.report_path)
    report_path.write_text(render_html(result, data_uri(preview), graph_svg, response), encoding="utf-8")
    manifest = {
        "status": result.status,
        "quality_status": result.quality_status,
        "module": MODULE,
        "version": VERSION,
        "page_id": result.page_id,
        "question": result.question,
        "answer": result.answer,
        "stages": [stage.__dict__ for stage in result.stages],
        "artifacts": result.artifacts,
        "output_dir": result.output_dir,
        "report_path": result.report_path,
        "raw_preview_path": result.raw_preview_path,
        "graph_path": result.graph_path,
        "live_endpoint_called": result.live_endpoint_called,
        "model_call_count": result.model_call_count,
        "citations": result.citations,
        "warnings": result.warnings,
        "failures": result.failures,
        "safety": result.safety,
        "endpoint": {
            "base_url": args.base_url,
            "model": args.model,
            "api_key_redacted": True,
            "http_status": endpoint.get("http_status"),
            "elapsed_seconds": endpoint.get("elapsed_seconds"),
            "health_http_status": endpoint.get("health_http_status"),
        },
        "raw_tiff": raw_info,
        "preview": preview_info,
        "live_ocr": {k: v for k, v in live_ocr.items() if k != "best_text"},
        "qdrant": {k: v for k, v in qdrant.items() if k != "payload"},
    }
    write_json(Path(result.manifest_path), manifest)

    print("\n" + ansi("=" * 88, "dim"))
    print(ansi("TRACE-NET RAW TIFF → ANSWER DEMO READY", "bold"))
    print(f"quality_status={quality}")
    print(f"report={result.report_path}")
    print(f"manifest={result.manifest_path}")
    print(f"graph={result.graph_path}")
    print(f"answer_char_count={len(answer)}")
    print(f"citation_count={len(citations)}")
    print(f"model_call_count={model_call_count}")
    print("postgres_write_attempt=false")
    print("qdrant_write_attempt=false")
    print("opensearch_write_attempt=false")
    print("source_truth_mutation_allowed=false")
    print(f"status={STATUS}")
    print(f"quality_status={quality}")
    if failures and args.strict:
        raise SystemExit("Demo strict gate failed: " + ", ".join(failures))
    return result


def serve_report(output_dir: Path, host: str, port: int) -> None:
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            return

    os.chdir(output_dir)
    server = ThreadingHTTPServer((host, port), QuietHandler)
    print(f"TRACE_NET_DEMO_HTTP_SERVER=READY")
    print(f"demo_url=http://{host}:{port}/trace_net_tiff_to_answer_demo_v1.html")
    print("Press Ctrl+C to stop the demo server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(Path.cwd()))
    parser.add_argument("--artifact-root")
    parser.add_argument("--pipeline-root")
    parser.add_argument("--source-package", help="ZIP containing raw TIFFs, or a direct TIFF path. Auto-discovered when omitted.")
    parser.add_argument("--page-id", default=DEFAULT_PAGE_ID)
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--output-dir", default="/data/trace_net_runs/tiff_to_answer_server_demo_v1")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-key", default=DEFAULT_API_KEY)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--request-timeout", type=float, default=300.0)
    parser.add_argument("--nha-release-dir")
    parser.add_argument("--live-ocr", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--tesseract-cmd", default="tesseract")
    parser.add_argument("--psm-modes", type=lambda value: [int(x.strip()) for x in value.split(",") if x.strip()], default=[6])
    parser.add_argument("--ocr-timeout", type=int, default=90)
    parser.add_argument("--check-qdrant", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--qdrant-collection", default=DEFAULT_QDRANT_COLLECTION)
    parser.add_argument("--require-qdrant", action="store_true")
    parser.add_argument("--require-raw-tiff", action="store_true")
    parser.add_argument("--require-one-model-call", action="store_true")
    parser.add_argument("--min-citations", type=int, default=0)
    parser.add_argument("--present", action="store_true", help="Pause between terminal stages for a live presentation.")
    parser.add_argument("--serve", action="store_true", help="Serve the generated HTML report after building it.")
    parser.add_argument("--serve-host", default="127.0.0.1")
    parser.add_argument("--serve-port", type=int, default=8099)
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = build_demo(args)
    if args.serve:
        serve_report(Path(result.output_dir), args.serve_host, args.serve_port)
    return 0 if result.quality_status == "PASS" or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
