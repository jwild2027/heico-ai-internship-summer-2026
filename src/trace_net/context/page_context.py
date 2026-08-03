"""Generate AI page-context records for the TIFF document organization graph.

The context layer is optional and derived. It does not replace OCR/TIFF/source
truth. It creates small, auditable PageContext records that can be added to the
organization graph with edges like Page -> HAS_CONTEXT -> PageContext.
"""

from __future__ import annotations

from dataclasses import MISSING, asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Callable, Iterable
from urllib import error, request

DEFAULT_EXPORT_DIR = "local_data/organization/export"
DEFAULT_OUTPUT_DIR = "local_data/organization/context"
DEFAULT_OUTPUT_FILE = "page_contexts.json"
DEFAULT_MODEL = "gemma3:12B"
PROMPT_VERSION = "page_context_v1"


@dataclass(frozen=True)
class PageContext:
    context_id: str
    page_id: str
    short_summary: str
    page_role: str = "unknown"
    topics: tuple[str, ...] = ()
    important_parts: tuple[str, ...] = ()
    confidence: str = "medium"
    model: str = DEFAULT_MODEL
    prompt_version: str = PROMPT_VERSION
    generated_at: str = ""
    manual: str = ""
    ata_code: str = ""
    page_label: str = ""
    source_url: str = ""
    tiff_path: str = ""
    ocr_path: str = ""
    ocr_char_count: int = 0
    source_ocr_hash_hint: str = ""
    elapsed_seconds: float = 0.0
    prompt_char_count: int = 0
    response_char_count: int = 0
    approx_prompt_tokens: int = 0
    approx_response_tokens: int = 0
    approx_total_tokens: int = 0
    quality_score: float = 0.0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PageContextResult:
    status: str
    export_dir: str
    output_path: str
    model: str
    prompt_version: str
    page_count_seen: int
    contexts_written: int
    failed_contexts: int
    skipped_existing: int = 0
    total_elapsed_seconds: float = 0.0
    average_elapsed_seconds: float = 0.0
    total_approx_tokens: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str | Path, data: Any) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def slug(value: Any) -> str:
    text = clean(value).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "unknown"


def context_id_for_page(page_id: str) -> str:
    return f"page_context:{slug(page_id)}"


def first_nonempty(row: dict[str, Any], keys: Iterable[str], default: Any = "") -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def as_records(value: Any, likely_id_key: str = "page_id") -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if not isinstance(value, dict):
        return []
    for key in ("items", "records", "pages", "page_index", "tree"):
        child = value.get(key)
        if isinstance(child, list):
            return [x for x in child if isinstance(x, dict)]
        if isinstance(child, dict):
            return as_records(child, likely_id_key=likely_id_key)
    out: list[dict[str, Any]] = []
    for map_key, map_value in value.items():
        if isinstance(map_value, dict):
            row = dict(map_value)
            row.setdefault(likely_id_key, map_key)
            out.append(row)
    return out


def load_page_records(export_dir: str | Path = DEFAULT_EXPORT_DIR) -> list[dict[str, Any]]:
    path = Path(export_dir) / "page_index.json"
    data = load_json(path)
    return as_records(data, likely_id_key="page_id")


def page_id(row: dict[str, Any]) -> str:
    return clean(first_nonempty(row, ("page_id", "id", "page"), ""))


def page_manual(row: dict[str, Any]) -> str:
    return clean(first_nonempty(row, ("manual", "manual_title", "publication_number", "title", "document_title", "manual_id"), ""))


def page_ata(row: dict[str, Any]) -> str:
    return clean(first_nonempty(row, ("ata_code", "ata", "section_code"), ""))


def page_label(row: dict[str, Any]) -> str:
    return clean(first_nonempty(row, ("page_label", "label", "page_number", "page"), ""))


def page_source(row: dict[str, Any]) -> str:
    return clean(first_nonempty(row, ("source_url", "rescarta_url", "source"), ""))


def page_tiff_path(row: dict[str, Any]) -> str:
    return clean(
        first_nonempty(
            row,
            (
                "tiff_path",
                "tiff",
                "image_path",
                "source_image_path",
                "tiff_file",
                "tiff_file_path",
                "tiff_uri",
            ),
            "",
        )
    )


def page_ocr_path(row: dict[str, Any]) -> str:
    return clean(
        first_nonempty(
            row,
            (
                "ocr_text_path",
                "ocr_path",
                "ocr",
                "text_path",
                "ocr_file",
                "ocr_file_path",
                "ocr_uri",
            ),
            "",
        )
    )


def page_parts(row: dict[str, Any]) -> list[str]:
    raw = first_nonempty(row, ("parts", "part_numbers", "important_parts"), [])
    if isinstance(raw, list):
        parts: list[str] = []
        for item in raw:
            if isinstance(item, dict):
                value = clean(first_nonempty(item, ("part_number", "part", "id"), ""))
            else:
                value = clean(item)
            if value and value not in parts:
                parts.append(value)
        return parts
    if isinstance(raw, str):
        return [x.strip() for x in re.split(r"[,;]\s*", raw) if x.strip()]
    return []


def read_ocr_text(ocr_path: str, max_chars: int = 6000) -> tuple[str, int, str]:
    if not ocr_path:
        return "", 0, "missing OCR path"
    path = Path(ocr_path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return "", 0, f"could not read OCR file: {exc}"
    visible = text.strip()
    if not visible:
        return "", 0, "empty OCR text"
    return visible[:max_chars], len(visible), ""


def build_prompt(page: dict[str, Any], ocr_text: str) -> str:
    parts = page_parts(page)
    meta = {
        "page_id": page_id(page),
        "manual": page_manual(page),
        "ata_code": page_ata(page),
        "page_label": page_label(page),
        "known_parts": parts[:25],
    }
    return (
        "You are generating a small context node for one OCR page in a technical document library.\n"
        "Use ONLY the metadata and OCR text provided. Do not invent facts.\n"
        "Return JSON only, no markdown, with exactly these keys:\n"
        "{\n"
        '  "short_summary": "one sentence summary of what this page appears to contain",\n'
        '  "page_role": "parts_list | procedure | figure | table | front_matter | blank | unknown",\n'
        '  "topics": ["short topic tags"],\n'
        '  "important_parts": ["part numbers visible or strongly supported on this page"],\n'
        '  "confidence": "low | medium | high"\n'
        "}\n\n"
        f"METADATA:\n{json.dumps(meta, indent=2)}\n\n"
        f"OCR TEXT:\n{ocr_text}\n"
    )


def dry_run_context_json(page: dict[str, Any], ocr_text: str) -> dict[str, Any]:
    parts = page_parts(page)[:10]
    ata = page_ata(page)
    label = page_label(page)
    manual = page_manual(page) or "document"
    role = "blank" if not ocr_text.strip() else "unknown"
    if parts:
        role = "parts_list"
    summary_bits = [f"Page {label}" if label else "This page", f"from {manual}"]
    if ata:
        summary_bits.append(f"in ATA {ata}")
    if parts:
        summary_bits.append(f"mentions parts such as {', '.join(parts[:3])}")
    else:
        summary_bits.append("has OCR text available" if ocr_text.strip() else "has empty OCR text")
    return {
        "short_summary": " ".join(summary_bits) + ".",
        "page_role": role,
        "topics": [x for x in (ata, "parts list" if parts else "ocr page") if x],
        "important_parts": parts,
        "confidence": "medium" if ocr_text.strip() else "low",
    }


def strip_json_fences(text: str) -> str:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def load_model_json(raw: str) -> Any:
    # Some local models emit literal control characters or OCR/newline bytes inside
    # JSON strings. strict=False accepts those characters instead of forcing a
    # fallback for otherwise usable model output.
    return json.loads(raw, strict=False)


def parse_context_response(text: str) -> dict[str, Any]:
    raw = strip_json_fences(text)
    try:
        data = load_model_json(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end < start:
            raise ValueError("model response did not contain a JSON object")
        data = load_model_json(raw[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("model response JSON was not an object")
    return data


def normalize_context_payload(payload: dict[str, Any]) -> dict[str, Any]:
    summary = clean(payload.get("short_summary"))
    role = clean(payload.get("page_role")) or "unknown"
    confidence = clean(payload.get("confidence")) or "medium"
    if confidence not in {"low", "medium", "high"}:
        confidence = "medium"

    def clean_list(value: Any) -> tuple[str, ...]:
        if isinstance(value, list):
            out: list[str] = []
            for item in value:
                text = clean(item)
                if text and text not in out:
                    out.append(text)
            return tuple(out)
        if isinstance(value, str):
            out = [x.strip() for x in re.split(r"[,;]\s*", value) if x.strip()]
            return tuple(dict.fromkeys(out))
        return ()

    return {
        "short_summary": summary or "No summary generated.",
        "page_role": role,
        "topics": clean_list(payload.get("topics")),
        "important_parts": clean_list(payload.get("important_parts")),
        "confidence": confidence,
    }


def normalize_ollama_host(host: str | None) -> str:
    """Return a client-safe Ollama HTTP base URL.

    Ollama's OLLAMA_HOST is often configured as a bind address such as
    ``0.0.0.0`` or ``0.0.0.0:11434``. That is useful for the server, but
    Python's HTTP client needs a real URL with a scheme. For local calls,
    ``0.0.0.0`` is better treated as ``127.0.0.1``.
    """
    value = (host or "").strip().rstrip("/")
    if not value:
        value = "127.0.0.1:11434"

    if "://" not in value:
        value = f"http://{value}"

    from urllib.parse import urlsplit, urlunsplit

    parsed = urlsplit(value)
    scheme = parsed.scheme or "http"
    hostname = parsed.hostname or "127.0.0.1"
    if hostname in {"0.0.0.0", "::"}:
        hostname = "127.0.0.1"
    port = parsed.port or 11434

    userinfo = ""
    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo += f":{parsed.password}"
        userinfo += "@"

    netloc = f"{userinfo}{hostname}:{port}"
    path = parsed.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, "", ""))


def ollama_host() -> str:
    return normalize_ollama_host(os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))


def call_ollama_api(prompt: str, model: str, timeout: int = 180) -> str:
    """Call Ollama's local HTTP API and request JSON-mode output."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0},
    }
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{ollama_host()}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:  # nosec - local Ollama API
            raw = resp.read().decode("utf-8", errors="replace")
    except (OSError, error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"ollama API call failed: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("ollama API returned non-JSON response") from exc

    response = data.get("response")
    if not isinstance(response, str):
        raise RuntimeError("ollama API response did not contain a text response")
    return response


def call_ollama_cli(prompt: str, model: str, timeout: int = 180, ollama_command: str = "ollama") -> str:
    # Windows Git Bash / Python can default subprocess text decoding to cp1252,
    # while Ollama/model output is often UTF-8. Force UTF-8 with replacement so
    # odd OCR/model bytes do not crash the page-context scan.
    proc = subprocess.run(
        [ollama_command, "run", model],
        input=prompt,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip() or (proc.stdout or "").strip()
        raise RuntimeError(f"ollama run failed with code {proc.returncode}: {stderr}")
    return proc.stdout or ""


def call_ollama(prompt: str, model: str, timeout: int = 180, ollama_command: str = "ollama") -> str:
    """Call Ollama, preferring the structured local HTTP API."""
    try:
        return call_ollama_api(prompt, model=model, timeout=timeout)
    except RuntimeError as api_exc:
        try:
            return call_ollama_cli(prompt, model=model, timeout=timeout, ollama_command=ollama_command)
        except RuntimeError as cli_exc:
            raise RuntimeError(f"{api_exc}; fallback CLI also failed: {cli_exc}") from cli_exc


def approx_token_count(text: str) -> int:
    """Return a cheap approximate token count for progress reporting.

    This is intentionally model-agnostic. Ollama's local JSON response does not
    always expose stable token counts across versions, so progress logs use a
    clear approximation based on character count.
    """
    value = text or ""
    return max(1, (len(value) + 3) // 4) if value else 0


def context_quality_score(confidence: str, error: str = "") -> float:
    """Map generated context confidence and warnings to a compact progress score."""
    base = {"high": 0.90, "medium": 0.65, "low": 0.35}.get((confidence or "").lower(), 0.50)
    if error:
        base -= 0.20
    return max(0.0, min(1.0, round(base, 2)))


def create_page_context(
    page: dict[str, Any],
    *,
    model: str = DEFAULT_MODEL,
    dry_run: bool = False,
    max_ocr_chars: int = 6000,
    timeout: int = 180,
    llm_callback: Callable[[str, str], str] | None = None,
    generated_at: str | None = None,
) -> PageContext:
    pid = page_id(page)
    if not pid:
        raise ValueError("page record has no page_id")
    ocr_path = page_ocr_path(page)
    ocr_text, char_count, read_error = read_ocr_text(ocr_path, max_chars=max_ocr_chars)
    now = generated_at or utc_now_iso()
    started = time.perf_counter()
    prompt_char_count = 0
    response_char_count = 0

    error = ""
    if dry_run:
        payload = dry_run_context_json(page, ocr_text)
    elif read_error and "empty" in read_error.lower():
        payload = dry_run_context_json(page, ocr_text)
        error = read_error
    else:
        prompt = build_prompt(page, ocr_text)
        prompt_char_count = len(prompt)
        try:
            response = llm_callback(prompt, model) if llm_callback else call_ollama(prompt, model=model, timeout=timeout)
            response_char_count = len(response or "")
            payload = parse_context_response(response)
        except Exception as exc:
            payload = dry_run_context_json(page, ocr_text)
            error = f"context generation failed; fallback used: {exc}"
    norm = normalize_context_payload(payload)
    if read_error and not error:
        error = read_error
    elapsed_seconds = round(time.perf_counter() - started, 3)
    if response_char_count == 0:
        response_char_count = len(norm["short_summary"])
    approx_prompt_tokens = approx_token_count("x" * prompt_char_count)
    approx_response_tokens = approx_token_count("x" * response_char_count)
    approx_total_tokens = approx_prompt_tokens + approx_response_tokens
    quality_score = context_quality_score(norm["confidence"], error)

    return PageContext(
        context_id=context_id_for_page(pid),
        page_id=pid,
        short_summary=norm["short_summary"],
        page_role=norm["page_role"],
        topics=tuple(norm["topics"]),
        important_parts=tuple(norm["important_parts"]),
        confidence=norm["confidence"],
        model=model,
        prompt_version=PROMPT_VERSION,
        generated_at=now,
        manual=page_manual(page),
        ata_code=page_ata(page),
        page_label=page_label(page),
        source_url=page_source(page),
        tiff_path=page_tiff_path(page),
        ocr_path=ocr_path,
        ocr_char_count=char_count,
        source_ocr_hash_hint=f"chars:{char_count}",
        elapsed_seconds=elapsed_seconds,
        prompt_char_count=prompt_char_count,
        response_char_count=response_char_count,
        approx_prompt_tokens=approx_prompt_tokens,
        approx_response_tokens=approx_response_tokens,
        approx_total_tokens=approx_total_tokens,
        quality_score=quality_score,
        error=error,
    )


def normalize_existing_context_dict(item: dict[str, Any]) -> dict[str, Any]:
    """Return a PageContext-compatible dict for cached contexts.

    Older context files may not have progress fields such as ``quality_score``
    or token estimates. Normalize them here so cached progress lines are useful
    and future writes keep a stable schema.
    """
    data: dict[str, Any] = {}
    for key, field_info in PageContext.__dataclass_fields__.items():
        default = field_info.default if field_info.default is not MISSING else ""
        data[key] = item.get(key, default)

    if not data.get("context_id") and data.get("page_id"):
        data["context_id"] = context_id_for_page(data["page_id"])
    if isinstance(data.get("topics"), list):
        data["topics"] = tuple(clean(x) for x in data["topics"] if clean(x))
    if isinstance(data.get("important_parts"), list):
        data["important_parts"] = tuple(clean(x) for x in data["important_parts"] if clean(x))

    try:
        score = float(data.get("quality_score") or 0)
    except (TypeError, ValueError):
        score = 0.0
    if score <= 0 and data.get("confidence"):
        data["quality_score"] = context_quality_score(clean(data.get("confidence")), clean(data.get("error")))

    if not data.get("approx_total_tokens"):
        prompt_tokens = int(data.get("approx_prompt_tokens") or 0)
        response_tokens = int(data.get("approx_response_tokens") or 0)
        data["approx_total_tokens"] = prompt_tokens + response_tokens
    return data


def load_existing_contexts(path: str | Path) -> dict[str, dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return {}
    data = load_json(p)
    contexts = data.get("contexts") if isinstance(data, dict) else data
    out: dict[str, dict[str, Any]] = {}
    if isinstance(contexts, list):
        for item in contexts:
            if not isinstance(item, dict):
                continue
            pid = clean(item.get("page_id"))
            if pid:
                out[pid] = normalize_existing_context_dict(item)
    return out


def generate_page_contexts(
    *,
    export_dir: str | Path = DEFAULT_EXPORT_DIR,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    output_file: str = DEFAULT_OUTPUT_FILE,
    model: str = DEFAULT_MODEL,
    limit: int | None = None,
    page_ids: Iterable[str] = (),
    dry_run: bool = False,
    force: bool = False,
    missing_only: bool = False,
    max_ocr_chars: int = 6000,
    timeout: int = 180,
    llm_callback: Callable[[str, str], str] | None = None,
    progress_callback: Callable[[int, int, PageContext, str], None] | None = None,
) -> tuple[PageContextResult, list[PageContext]]:
    export_path = Path(export_dir)
    out_path = Path(output_dir) / output_file
    all_pages = load_page_records(export_path)
    existing = load_existing_contexts(out_path)

    pages = list(all_pages)
    selected_ids = {clean(x) for x in page_ids if clean(x)}
    if selected_ids:
        pages = [p for p in pages if page_id(p) in selected_ids]
    if missing_only:
        pages = [p for p in pages if page_id(p) and page_id(p) not in existing]
    if limit is not None and limit >= 0:
        pages = pages[:limit]

    contexts: list[PageContext] = []
    skipped = 0
    warnings: list[str] = []
    batch_started = time.perf_counter()
    total = len(pages)
    for idx, page in enumerate(pages, start=1):
        pid = page_id(page)
        if not pid:
            warnings.append("skipped page with no page_id")
            continue
        if not force and pid in existing:
            item = normalize_existing_context_dict(existing[pid])
            context = PageContext(**{k: item.get(k, PageContext.__dataclass_fields__[k].default) for k in PageContext.__dataclass_fields__})
            contexts.append(context)
            skipped += 1
            if progress_callback:
                progress_callback(idx, total, context, "skipped")
            continue
        try:
            context = create_page_context(
                page,
                model=model,
                dry_run=dry_run,
                max_ocr_chars=max_ocr_chars,
                timeout=timeout,
                llm_callback=llm_callback,
            )
            contexts.append(context)
            if progress_callback:
                progress_callback(idx, total, context, "done")
        except Exception as exc:
            warnings.append(f"failed page {pid}: {exc}")

    # Merge newly generated/selected contexts back into the full existing cache.
    # This makes limited/batched runs safe: a --limit 25 run will not delete
    # contexts generated in earlier or later batches.
    merged: dict[str, dict[str, Any]] = dict(existing)
    for context in contexts:
        merged[context.page_id] = context.to_dict()

    ordered_payload_contexts: list[dict[str, Any]] = []
    seen_payload_pages: set[str] = set()
    for page in all_pages:
        pid = page_id(page)
        if pid in merged and pid not in seen_payload_pages:
            ordered_payload_contexts.append(normalize_existing_context_dict(merged[pid]))
            seen_payload_pages.add(pid)
    for pid, item in sorted(merged.items()):
        if pid not in seen_payload_pages:
            ordered_payload_contexts.append(normalize_existing_context_dict(item))

    failed = sum(1 for c in contexts if c.error)
    status = "OK" if ordered_payload_contexts else "NEEDS_ATTENTION"
    total_elapsed = round(time.perf_counter() - batch_started, 3)
    average_elapsed = round(total_elapsed / len(contexts), 3) if contexts else 0.0
    total_tokens = sum(c.approx_total_tokens for c in contexts if c.approx_total_tokens and not (not force and c.page_id in existing))
    result = PageContextResult(
        status=status,
        export_dir=str(export_path),
        output_path=str(out_path),
        model=model,
        prompt_version=PROMPT_VERSION,
        page_count_seen=len(pages),
        contexts_written=len(ordered_payload_contexts),
        failed_contexts=failed,
        skipped_existing=skipped,
        total_elapsed_seconds=total_elapsed,
        average_elapsed_seconds=average_elapsed,
        total_approx_tokens=total_tokens,
        warnings=tuple(warnings),
    )
    payload = {
        "status": result.status,
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "generated_at": utc_now_iso(),
        "export_dir": str(export_path),
        "summary": result.to_dict(),
        "contexts": ordered_payload_contexts,
    }
    write_json(out_path, payload)
    return result, contexts
