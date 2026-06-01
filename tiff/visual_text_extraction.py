"""Model-assisted visual text extraction for scanned TIFF manual pages.

This module adds the next OCR layer after ordinary OCR and page image
classification.  It asks a vision-capable model to turn visual content into
searchable text: figures, diagrams, charts, tables, labels, callouts, notes,
part numbers, and visible relationships on the page.

The implementation is intentionally artifact-based so it can run against the
current local MVP without changing the core graph builder.  It reads page
character cards when available, falls back to page_index.json, writes JSONL
records plus a markdown corpus, and emits a small graph overlay:

    Page -> HAS_VISUAL_TEXT -> VisualTextRecord -> DERIVED_FROM -> EvidenceSource

The output can later be merged into RAG chunks or page context traits.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Protocol, Sequence

DEFAULT_PAGE_CARDS_PATH = Path("local_data/organization/entity_traits/page_character_cards.json")
DEFAULT_PAGE_INDEX_PATH = Path("local_data/organization/export/page_index.json")
DEFAULT_OUTPUT_DIR = Path("local_data/organization/visual_text")
DEFAULT_RECORDS_FILE = "visual_text_extraction.jsonl"
DEFAULT_SUMMARY_FILE = "visual_text_extraction_summary.json"
DEFAULT_CORPUS_MD_FILE = "visual_text_corpus.md"
DEFAULT_GRAPH_NODES_FILE = "visual_text_graph_nodes.json"
DEFAULT_GRAPH_EDGES_FILE = "visual_text_graph_edges.json"
DEFAULT_MODEL = "auto"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_PROMPT_VERSION = "visual_text_v2_2"
DEFAULT_OCR_MAX_CHARS = 4000

VISUAL_TEXT_V2_SECTIONS = (
    "Page type",
    "Visible title/header",
    "Transcribed visible text",
    "Visual summary",
    "OCR/context assist notes",
    "Tables",
    "Figures/diagrams",
    "Charts/graphs",
    "Labels/callouts/part numbers",
    "Warnings/notes",
    "Uncertain/unreadable",
    "Model caution",
)

VISUAL_TEXT_V2_SECTION_DEFAULTS = {
    "Page type": "unknown",
    "Visible title/header": "No readable title or header detected.",
    "Transcribed visible text": "No additional readable text transcribed from the image.",
    "Visual summary": "No additional visual summary available.",
    "OCR/context assist notes": "No OCR/context-only notes reported.",
    "Tables": "No readable table detected.",
    "Figures/diagrams": "No readable figure or diagram detected.",
    "Charts/graphs": "No readable chart or graph detected.",
    "Labels/callouts/part numbers": "No readable labels, callouts, item numbers, part numbers, or references detected.",
    "Warnings/notes": "No visible warnings, cautions, notes, revision notes, or procedural notes detected.",
    "Uncertain/unreadable": "No uncertain or unreadable visual regions reported.",
    "Model caution": "Use this visual extraction as derived context. Verify critical facts against source TIFF/OCR evidence.",
}

VISUAL_TEXT_V2_SECTION_ALIASES = {
    "page visual text": "Visual summary",
    "title": "Visible title/header",
    "header": "Visible title/header",
    "visible header": "Visible title/header",
    "visible title": "Visible title/header",
    "transcription": "Transcribed visible text",
    "visible text": "Transcribed visible text",
    "text": "Transcribed visible text",
    "ocr notes": "OCR/context assist notes",
    "ocr assist notes": "OCR/context assist notes",
    "ocr/context notes": "OCR/context assist notes",
    "ocr/context assist notes": "OCR/context assist notes",
    "context notes": "OCR/context assist notes",
    "assist notes": "OCR/context assist notes",
    "figures": "Figures/diagrams",
    "diagrams": "Figures/diagrams",
    "figures and diagrams": "Figures/diagrams",
    "figure/diagram": "Figures/diagrams",
    "charts": "Charts/graphs",
    "graphs": "Charts/graphs",
    "charts and graphs": "Charts/graphs",
    "labels": "Labels/callouts/part numbers",
    "callouts": "Labels/callouts/part numbers",
    "labels/callouts": "Labels/callouts/part numbers",
    "part numbers": "Labels/callouts/part numbers",
    "warnings": "Warnings/notes",
    "notes": "Warnings/notes",
    "warnings and notes": "Warnings/notes",
    "uncertain": "Uncertain/unreadable",
    "unreadable": "Uncertain/unreadable",
    "uncertain or unreadable": "Uncertain/unreadable",
    "caution": "Model caution",
    "model notes": "Model caution",
}

IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".webp", ".bmp"}
DIRECT_MODEL_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
AUTO_MODEL_NAMES = {"", "auto", "best", "installed"}
# Prefer models that have been verified to return non-empty /api/generate
# image responses in this project.  qwen3-vl can be installed but return an
# empty response with some Ollama/template builds, so it remains available as
# a fallback instead of the first auto-selected model.
VISION_MODEL_PRIORITY = (
    "llava:13b",
    "llava:latest",
    "llama3.2-vision:11b",
    "qwen3-vl:latest",
    "qwen2.5vl:latest",
    "qwen2-vl:latest",
    "moondream:latest",
    "minicpm-v:latest",
    "bakllava:latest",
)
VISION_MODEL_HINTS = ("vl", "llava", "vision", "moondream", "minicpm-v", "bakllava")
DEFAULT_PAGE_ROLES = ("figure", "table", "procedure", "parts_list")
DEFAULT_IMAGE_CLASSES = (
    "likely_figure_or_diagram",
    "likely_table_or_grid",
    "likely_text_or_parts_list",
)


class VisualTextClient(Protocol):
    """A client that converts one page image into searchable visual text."""

    provider_name: str
    model_name: str

    def describe_page(self, image_path: Path, prompt: str, metadata: Mapping[str, Any]) -> str:
        """Return model-generated text for the image."""


@dataclass(frozen=True)
class VisualTextPaths:
    page_cards_path: Path = DEFAULT_PAGE_CARDS_PATH
    page_index_path: Path = DEFAULT_PAGE_INDEX_PATH
    output_dir: Path = DEFAULT_OUTPUT_DIR

    @property
    def records_path(self) -> Path:
        return self.output_dir / DEFAULT_RECORDS_FILE

    @property
    def summary_path(self) -> Path:
        return self.output_dir / DEFAULT_SUMMARY_FILE

    @property
    def corpus_md_path(self) -> Path:
        return self.output_dir / DEFAULT_CORPUS_MD_FILE

    @property
    def graph_nodes_path(self) -> Path:
        return self.output_dir / DEFAULT_GRAPH_NODES_FILE

    @property
    def graph_edges_path(self) -> Path:
        return self.output_dir / DEFAULT_GRAPH_EDGES_FILE


@dataclass(frozen=True)
class VisualTextSafetyLayer:
    """One fallback layer in the visual-text fishnet retry plan.

    Failed pages fall through these layers one at a time.  A layer can shrink
    image size, extend timeout, change temperature, adjust OCR-assist length,
    disable OCR assist, or switch model/prompt version.
    """

    name: str
    max_image_edge: int | None = None
    timeout_seconds: int | None = None
    temperature: float | None = None
    ocr_max_chars: int | None = None
    ocr_assist: bool | None = None
    prompt_version: str | None = None
    model: str | None = None


DEFAULT_FISHNET_SAFETY_LAYER_SPEC = "rescue_768:768:1200,rescue_512:512:1200"


@dataclass(frozen=True)
class ExtractionOptions:
    provider: str = "ollama"
    model: str = DEFAULT_MODEL
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL
    page_ids: tuple[str, ...] = ()
    page_roles: tuple[str, ...] = DEFAULT_PAGE_ROLES
    image_classes: tuple[str, ...] = DEFAULT_IMAGE_CLASSES
    include_blank: bool = False
    max_pages: int | None = 5
    overwrite: bool = False
    timeout_seconds: int = 240
    max_image_edge: int = 2200
    temperature: float = 0.0
    prompt_version: str = DEFAULT_PROMPT_VERSION
    ocr_assist: bool = True
    ocr_max_chars: int = DEFAULT_OCR_MAX_CHARS
    write_graph_overlay: bool = True
    progress: bool = False
    checkpoint_every: int = 0
    retry_error_pages_only: bool = False
    safety_layers: tuple[VisualTextSafetyLayer, ...] = ()


@dataclass
class VisualTextRunResult:
    status: str
    summary: dict[str, Any]
    records: list[dict[str, Any]] = field(default_factory=list)
    graph_nodes: list[dict[str, Any]] = field(default_factory=list)
    graph_edges: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class PlannedVisualTextClient:
    """Client used for dry runs.  It records planned work but does not call a model."""

    provider_name = "planned"
    model_name = "none"

    def describe_page(self, image_path: Path, prompt: str, metadata: Mapping[str, Any]) -> str:
        return """# Page visual text

## Page type
unknown

## Visible title/header
No readable title or header detected.

## Transcribed visible text
Planned extraction only. No model was called.

## Visual summary
Re-run with --provider ollama and a vision model to convert this page image into text.

## OCR/context assist notes
No OCR/context-only notes reported.

## Tables
No readable table detected.

## Figures/diagrams
No readable figure or diagram detected.

## Charts/graphs
No readable chart or graph detected.

## Labels/callouts/part numbers
No readable labels, callouts, item numbers, part numbers, or references detected.

## Warnings/notes
No visible warnings, cautions, notes, revision notes, or procedural notes detected.

## Uncertain/unreadable
Planned dry-run output; visual content has not been analyzed.

## Model caution
Use model output only after a real visual extraction run."""


class MockVisualTextClient:
    """Deterministic client for unit tests and UI wiring tests."""

    provider_name = "mock"
    model_name = "mock-vision-model"

    def describe_page(self, image_path: Path, prompt: str, metadata: Mapping[str, Any]) -> str:
        page_id = str(metadata.get("page_id") or "unknown_page")
        role = str(metadata.get("page_role") or "unknown")
        image_class = str(metadata.get("image_classification") or "unknown")
        return f"""# Page visual text

## Page type
{role}

## Visible title/header
Mock page title

## Transcribed visible text
Mock visual extraction for {page_id}. Image class: {image_class}. Visible part MOCK-123-001.

## Visual summary
Mock visual extraction for {page_id}. Image class: {image_class}.

## OCR/context assist notes
Mock context-only note. Do not treat metadata as visible text.

## Tables
| column | value |
|---|---|
| mock_page | {page_id} |

## Figures/diagrams
Mock figure description with one labeled callout.

## Charts/graphs
No readable chart or graph detected.

## Labels/callouts/part numbers
- MOCK-CALLOUT-1
- MOCK-123-001

## Warnings/notes
No visible warnings, cautions, notes, revision notes, or procedural notes detected.

## Uncertain/unreadable
No uncertain or unreadable visual regions reported.

## Model caution
Mock output only; verify real model output against source TIFF/OCR evidence."""


class OllamaVisionClient:
    """Ollama /api/generate client for local vision models.

    In auto mode, the client tries installed vision models in priority order.
    This matters because some installed Ollama vision tags can accept the image
    request but return an empty response depending on the local model/template
    build.  Explicit model names are respected exactly.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        timeout_seconds: int = 240,
        max_image_edge: int = 2200,
        temperature: float = 0.0,
    ) -> None:
        self.requested_model = str(model or DEFAULT_MODEL)
        self.model_name = self.requested_model
        self.provider_name = "ollama"
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = int(timeout_seconds)
        self.max_image_edge = int(max_image_edge)
        self.temperature = float(temperature)

    def _explicit_model_requested(self) -> bool:
        return bool(self.requested_model and self.requested_model.strip().lower() not in AUTO_MODEL_NAMES)

    def _resolve_model_candidates(self) -> list[str]:
        """Return candidate model tags in the order they should be tried."""

        if self._explicit_model_requested():
            selected = self.requested_model.strip()
            self.model_name = selected
            return [selected]

        names = list_ollama_model_names(self.base_url, timeout_seconds=min(self.timeout_seconds, 30))
        candidates = select_ollama_vision_model_candidates(names)
        if not candidates:
            available = ", ".join(names) if names else "none"
            raise RuntimeError(
                "Could not auto-select an installed Ollama vision model. "
                f"Available models: {available}. Pull or select a vision model, for example: "
                "ollama pull llava:13b, then rerun with --model llava:13b."
            )
        self.model_name = candidates[0]
        return candidates

    def _resolve_model_name(self) -> str:
        """Return the first candidate for compatibility with older callers/tests."""

        return self._resolve_model_candidates()[0]

    def _describe_with_model(self, model_name: str, image_b64: str, prompt: str) -> str:
        payload = {
            "model": model_name,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
            "options": {
                "temperature": self.temperature,
            },
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace").strip()
            except Exception:
                detail = ""
            available: list[str] = []
            try:
                available = list_ollama_model_names(self.base_url, timeout_seconds=10)
            except Exception:
                available = []
            vision = [name for name in available if is_probable_vision_model(name)]
            suggestion = ""
            if vision:
                suggestion = f" Try one of the installed vision models: {', '.join(vision)}."
            elif available:
                suggestion = f" Installed models: {', '.join(available)}."
            raise RuntimeError(
                f"Ollama HTTP {exc.code} at {self.base_url}/api/generate for model {model_name}. "
                f"{detail}{suggestion}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Could not reach Ollama at {self.base_url}. Start Ollama and pull/select a vision model "
                f"such as llava:13b or qwen3-vl:latest. Original error: {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Ollama returned a non-JSON response for model {model_name}.") from exc

        text = str(data.get("response") or "").strip()
        if not text:
            raise RuntimeError(f"Ollama model {model_name} returned an empty response.")
        return text

    def describe_page(self, image_path: Path, prompt: str, metadata: Mapping[str, Any]) -> str:
        candidates = self._resolve_model_candidates()
        image_b64 = encode_image_for_model(image_path, max_image_edge=self.max_image_edge)
        errors: list[str] = []
        for model_name in candidates:
            try:
                text = self._describe_with_model(model_name, image_b64, prompt)
                self.model_name = model_name
                return text
            except Exception as exc:  # noqa: BLE001 - auto mode tries the next installed vision model
                errors.append(f"{model_name}: {exc}")
                if self._explicit_model_requested():
                    break
        detail = "; ".join(errors) if errors else "no candidates were attempted"
        raise RuntimeError(f"No Ollama vision model returned usable text. Attempts: {detail}")

def list_ollama_model_names(base_url: str = DEFAULT_OLLAMA_BASE_URL, timeout_seconds: int = 20) -> list[str]:
    """Return installed Ollama model tags from /api/tags."""

    request = urllib.request.Request(f"{base_url.rstrip('/')}/api/tags", method="GET")
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        data = json.loads(response.read().decode("utf-8"))
    names: list[str] = []
    for model in data.get("models", []):
        if isinstance(model, Mapping):
            name = str(model.get("name") or "").strip()
            if name:
                names.append(name)
    return sorted(set(names))


def is_probable_vision_model(model_name: str) -> bool:
    lowered = str(model_name or "").strip().lower()
    return any(hint in lowered for hint in VISION_MODEL_HINTS)


def select_ollama_vision_model(model_names: Sequence[str]) -> str | None:
    """Pick the first preferred installed vision model for visual text extraction."""

    candidates = select_ollama_vision_model_candidates(model_names)
    return candidates[0] if candidates else None


def select_ollama_vision_model_candidates(model_names: Sequence[str]) -> list[str]:
    """Return all preferred installed vision candidates in retry order."""

    installed = {str(name).strip(): str(name).strip() for name in model_names if str(name).strip()}
    installed_lower = {name.lower(): name for name in installed}
    candidates: list[str] = []
    for candidate in VISION_MODEL_PRIORITY:
        found = installed_lower.get(candidate.lower())
        if found and found not in candidates:
            candidates.append(found)
    for name in sorted(installed):
        if is_probable_vision_model(name) and name not in candidates:
            candidates.append(name)
    return candidates


def parse_visual_text_safety_layers(spec: str | Sequence[str] | None) -> tuple[VisualTextSafetyLayer, ...]:
    """Parse a compact fishnet layer spec.

    Format:
        name:max_image_edge:timeout_seconds[:temperature][:ocr_max_chars][:ocr|noocr][:prompt][:model]

    Examples:
        rescue_768:768:1200
        rescue_512:512:1200:0.0:2500
        noocr_768:768:1200:0.0:0:noocr

    Commas or semicolons separate layers.  Empty specs return no layers.
    """

    if spec is None:
        return ()
    if isinstance(spec, str):
        raw_items = re.split(r"[,;]", spec)
    else:
        raw_items = []
        for item in spec:
            raw_items.extend(re.split(r"[,;]", str(item or "")))

    layers: list[VisualTextSafetyLayer] = []
    for index, raw in enumerate(raw_items, start=1):
        item = raw.strip()
        if not item:
            continue
        parts = [part.strip() for part in item.split(":")]
        if len(parts) == 2:
            name = f"layer_{index}_{parts[0]}"
            max_edge_text, timeout_text = parts
            remainder: list[str] = []
        elif len(parts) >= 3:
            name, max_edge_text, timeout_text, *remainder = parts
        else:
            raise ValueError(
                "Safety layer spec must be name:max_image_edge:timeout_seconds "
                f"or max_image_edge:timeout_seconds; got {item!r}."
            )
        try:
            max_image_edge = int(max_edge_text)
            timeout_seconds = int(timeout_text)
        except ValueError as exc:
            raise ValueError(f"Invalid safety layer numeric settings in {item!r}.") from exc
        if max_image_edge <= 0 or timeout_seconds <= 0:
            raise ValueError(f"Safety layer max_image_edge and timeout_seconds must be positive in {item!r}.")

        temperature: float | None = None
        ocr_max_chars: int | None = None
        ocr_assist: bool | None = None
        prompt_version: str | None = None
        model: str | None = None
        for offset, token in enumerate(remainder):
            lowered = token.strip().lower()
            if not lowered:
                continue
            if lowered in {"ocr", "ocr_on", "with_ocr"}:
                ocr_assist = True
                continue
            if lowered in {"noocr", "no_ocr", "ocr_off", "without_ocr"}:
                ocr_assist = False
                continue
            if lowered.startswith("model="):
                model = token.split("=", 1)[1].strip() or None
                continue
            if lowered.startswith("prompt="):
                prompt_version = token.split("=", 1)[1].strip() or None
                continue
            if offset == 0:
                try:
                    temperature = float(token)
                    continue
                except ValueError:
                    prompt_version = token
                    continue
            if offset == 1:
                try:
                    ocr_max_chars = int(token)
                    continue
                except ValueError:
                    prompt_version = token
                    continue
            if prompt_version is None:
                prompt_version = token
            elif model is None:
                model = token
        layers.append(
            VisualTextSafetyLayer(
                name=name or f"layer_{index}",
                max_image_edge=max_image_edge,
                timeout_seconds=timeout_seconds,
                temperature=temperature,
                ocr_max_chars=ocr_max_chars,
                ocr_assist=ocr_assist,
                prompt_version=prompt_version,
                model=model,
            )
        )
    return tuple(layers)


def default_visual_text_safety_layers() -> tuple[VisualTextSafetyLayer, ...]:
    """Return the built-in fishnet layers for timeout-prone pages."""

    return parse_visual_text_safety_layers(DEFAULT_FISHNET_SAFETY_LAYER_SPEC)


def _apply_safety_layer(options: ExtractionOptions, layer: VisualTextSafetyLayer) -> ExtractionOptions:
    """Return options adjusted for one fallback layer."""

    return replace(
        options,
        max_image_edge=layer.max_image_edge if layer.max_image_edge is not None else options.max_image_edge,
        timeout_seconds=layer.timeout_seconds if layer.timeout_seconds is not None else options.timeout_seconds,
        temperature=layer.temperature if layer.temperature is not None else options.temperature,
        ocr_max_chars=layer.ocr_max_chars if layer.ocr_max_chars is not None else options.ocr_max_chars,
        ocr_assist=layer.ocr_assist if layer.ocr_assist is not None else options.ocr_assist,
        prompt_version=layer.prompt_version if layer.prompt_version else options.prompt_version,
        model=layer.model if layer.model else options.model,
        safety_layers=(),
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _first(mapping: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _strip_entity_prefix(value: Any) -> str:
    text = _text(value)
    for prefix in ("page:", "part:", "document:", "ata_section:", "source_link:", "source_file:"):
        if text.startswith(prefix):
            return text[len(prefix) :]
    return text


def _records_from_any(value: Any, preferred_keys: Sequence[str]) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(record) for record in value if isinstance(record, dict)]
    if not isinstance(value, dict):
        return []
    for key in preferred_keys:
        child = value.get(key)
        if isinstance(child, list):
            return [dict(record) for record in child if isinstance(record, dict)]
        if isinstance(child, dict):
            out: list[dict[str, Any]] = []
            for child_key, child_value in child.items():
                if isinstance(child_value, dict):
                    record = dict(child_value)
                    record.setdefault("id", child_key)
                    if "page" in key:
                        record.setdefault("page_id", child_key)
                    out.append(record)
            return out
    if all(isinstance(v, dict) for v in value.values()):
        out = []
        for child_key, child_value in value.items():
            record = dict(child_value)
            record.setdefault("id", child_key)
            out.append(record)
        return out
    return []


def _split_csv(values: str | Sequence[str] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        raw = values.split(",")
    else:
        raw = []
        for value in values:
            raw.extend(str(value).split(","))
    return tuple(item.strip() for item in raw if item and item.strip())


def _lookup_nested(mapping: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping):
            return default
        current = current.get(key)
    return default if current in (None, "") else current


def _card_page_id(card: Mapping[str, Any]) -> str:
    return _strip_entity_prefix(
        _first(card, "page_id", "entity_id", "id", "node_id", default="")
    )


def _card_role(card: Mapping[str, Any]) -> str:
    context = _as_dict(card.get("context"))
    roles = _as_dict(card.get("roles"))
    direct_traits = card.get("direct_traits")
    role = _first(card, "page_role", "role", "context_role", default=None)
    role = role or _first(context, "page_role", "role", "primary_role", default=None)
    role = role or _first(roles, "page_role", "context_role", "role", default=None)
    if role:
        return _text(role)
    if isinstance(direct_traits, Mapping):
        values = direct_traits.get("context_role") or direct_traits.get("page_role") or direct_traits.get("role")
        if isinstance(values, list) and values:
            return _text(values[0])
    if isinstance(direct_traits, list):
        for value in direct_traits:
            text = _text(value)
            lowered = text.lower()
            if "page_role=" in lowered:
                return text.split("=", 1)[-1].strip()
            if "context_role=" in lowered:
                return text.split("=", 1)[-1].strip()
    return "unknown"


def _card_image_class(card: Mapping[str, Any]) -> str:
    signals = _as_dict(card.get("signals"))
    value = _first(signals, "image_classification", "visual_class", "image_class", default=None)
    value = value or _first(card, "image_classification", "visual_class", "image_class", default=None)
    if value:
        return _text(value)
    direct_traits = card.get("direct_traits")
    if isinstance(direct_traits, Mapping):
        values = direct_traits.get("image_classification") or direct_traits.get("visual_class")
        if isinstance(values, list) and values:
            return _text(values[0])
    if isinstance(direct_traits, list):
        for item in direct_traits:
            text = _text(item)
            lowered = text.lower()
            if "image_class" in lowered or "visual_class" in lowered:
                return text.split("=", 1)[-1].strip()
    return "unknown"


def _card_source(card: Mapping[str, Any]) -> dict[str, Any]:
    source = _as_dict(card.get("source"))
    return {
        "source_url": _first(source, "source_url", "url", default=_first(card, "source_url", "url", default=None)),
        "tiff_path": _first(source, "tiff_path", "image_path", "path", default=_first(card, "tiff_path", "image_path", default=None)),
        "ocr_path": _first(source, "ocr_path", default=_first(card, "ocr_path", default=None)),
    }


def _resolve_path(path_text: Any) -> Path | None:
    text = _text(path_text)
    if not text:
        return None
    # Git Bash often carries Windows-style paths in JSON artifacts.
    text = os.path.expandvars(os.path.expanduser(text))
    return Path(text)


def _existing_records(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            page_id = _text(record.get("page_id"))
            if page_id:
                records[page_id] = record
    return records


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(dict(record), sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _format_seconds(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _progress_line(
    index: int,
    total: int,
    page_id: str,
    status: str,
    char_count: int,
    elapsed_seconds: float,
    run_started_at: float,
) -> str:
    completed = max(index, 1)
    total = max(total, completed)
    avg_seconds = (time.time() - run_started_at) / float(completed)
    remaining_seconds = max(0.0, avg_seconds * float(total - completed))
    return (
        f"[{completed}/{total}] {page_id} -> {status} "
        f"chars={char_count} page_time={_format_seconds(elapsed_seconds)} "
        f"avg={_format_seconds(avg_seconds)} eta={_format_seconds(remaining_seconds)}"
    )


def _write_visual_text_artifacts(
    paths: VisualTextPaths,
    records: Sequence[Mapping[str, Any]],
    graph_nodes: Sequence[Mapping[str, Any]],
    graph_edges: Sequence[Mapping[str, Any]],
    write_graph_overlay: bool,
) -> None:
    _write_jsonl(paths.records_path, records)
    paths.corpus_md_path.write_text(_build_corpus_markdown(records), encoding="utf-8")
    if write_graph_overlay:
        _write_json(paths.graph_nodes_path, {"nodes": list(graph_nodes)})
        _write_json(paths.graph_edges_path, {"edges": list(graph_edges)})


def encode_image_for_model(image_path: Path, max_image_edge: int = 2200) -> str:
    """Return base64 image data accepted by most Ollama vision models.

    PNG/JPEG/WEBP files are sent directly.  TIFF/BMP and other formats are
    converted to PNG with Pillow because many model servers do not accept TIFF
    bytes directly.
    """

    path = Path(image_path)
    suffix = path.suffix.lower()
    if suffix in DIRECT_MODEL_IMAGE_EXTENSIONS:
        return base64.b64encode(path.read_bytes()).decode("ascii")

    try:
        from PIL import Image  # type: ignore
    except Exception as exc:  # pragma: no cover - exercised only without Pillow
        raise RuntimeError(
            f"Pillow is required to convert {path.suffix or 'this image'} files before sending them to a vision model."
        ) from exc

    with Image.open(path) as image:
        try:
            image.seek(0)
        except EOFError:
            pass
        image = image.convert("RGB")
        width, height = image.size
        max_dim = max(width, height)
        if max_dim > max_image_edge > 0:
            scale = max_image_edge / float(max_dim)
            image = image.resize((max(1, int(width * scale)), max(1, int(height * scale))))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def load_page_cards(page_cards_path: Path, page_index_path: Path | None = None) -> list[dict[str, Any]]:
    """Load page cards, falling back to page_index.json when needed."""

    raw = _load_json(page_cards_path, None)
    cards = _records_from_any(raw, ("pages", "page_cards", "page_character_cards"))
    if cards:
        return sorted(cards, key=lambda card: _card_page_id(card))

    if page_index_path is None:
        return []
    raw_index = _load_json(page_index_path, None)
    page_records = _records_from_any(raw_index, ("pages", "page_index", "items"))
    cards = []
    for record in page_records:
        source = {
            "source_url": _first(record, "source_url", "url", default=None),
            "tiff_path": _first(record, "tiff_path", "source_tiff_path", "image_path", default=None),
            "ocr_path": _first(record, "ocr_path", "source_ocr_path", default=None),
        }
        cards.append(
            {
                "page_id": _card_page_id(record),
                "entity_id": f"page:{_card_page_id(record)}",
                "label": _first(record, "label", "page_label", "page_id", default=_card_page_id(record)),
                "parents": {
                    "document_label": _first(record, "manual", "manual_title", "document_label", default=None),
                    "ata_code": _first(record, "ata_code", default=None),
                },
                "source": source,
                "context": {
                    "page_role": _first(record, "page_role", "role", default=None),
                    "summary": _first(record, "summary", "context_summary", default=None),
                },
                "signals": {},
                "parts": record.get("parts") if isinstance(record.get("parts"), list) else [],
            }
        )
    return sorted(cards, key=lambda card: _card_page_id(card))


def select_candidate_cards(
    cards: Sequence[Mapping[str, Any]],
    page_ids: Sequence[str] = (),
    page_roles: Sequence[str] = DEFAULT_PAGE_ROLES,
    image_classes: Sequence[str] = DEFAULT_IMAGE_CLASSES,
    include_blank: bool = False,
    max_pages: int | None = None,
) -> list[dict[str, Any]]:
    wanted_ids = {_strip_entity_prefix(pid) for pid in page_ids if _text(pid)}
    role_filter = {_norm(role) for role in page_roles if _text(role)}
    class_filter = {_norm(cls) for cls in image_classes if _text(cls)}
    selected: list[dict[str, Any]] = []

    for raw in cards:
        card = dict(raw)
        page_id = _card_page_id(card)
        if not page_id:
            continue
        role = _card_role(card)
        image_class = _card_image_class(card)
        is_blank = _norm(role) == "blank" or _norm(image_class) == "likely_blank"
        if is_blank and not include_blank:
            continue
        if wanted_ids:
            if page_id not in wanted_ids and f"page:{page_id}" not in wanted_ids:
                continue
        elif role_filter or class_filter:
            if _norm(role) not in role_filter and _norm(image_class) not in class_filter:
                continue
        selected.append(card)
        if max_pages is not None and max_pages >= 0 and len(selected) >= max_pages:
            break
    return selected


def build_visual_text_prompt(
    card: Mapping[str, Any],
    *,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    ocr_assist_text: str = "",
) -> str:
    page_id = _card_page_id(card)
    role = _card_role(card)
    image_class = _card_image_class(card)
    source = _card_source(card)
    parents = _as_dict(card.get("parents"))
    context = _as_dict(card.get("context"))
    parts = _as_list(card.get("parts"))
    part_text = ", ".join(_text(p.get("part_number") if isinstance(p, Mapping) else p) for p in parts[:35])
    context_summary = _text(_first(context, "summary", "short_summary", default=""))
    ata_code = _text(_first(parents, "ata_code", default=""))
    manual = _text(_first(parents, "document_label", "manual", "manual_title", default=""))
    version = str(prompt_version or DEFAULT_PROMPT_VERSION).lower()

    if version in {"visual_text_v1", "v1"}:
        return f"""You are converting a scanned aircraft technical manual page into searchable text.
Use only what is visible in the image. Do not invent labels, data values, part numbers, or table cells.

Page metadata:
- page_id: {page_id}
- manual/document: {manual or 'unknown'}
- ATA: {ata_code or 'unknown'}
- current page role: {role or 'unknown'}
- image classification: {image_class or 'unknown'}
- known part hints from OCR/catalog: {part_text or 'none'}
- existing context summary: {context_summary or 'none'}
- source URL/path hint: {source.get('source_url') or 'none'}

Task:
Convert visual information into text for retrieval and traceable Q/A. Focus on information that plain OCR often misses:
- tables and grids, preserving rows/columns as markdown tables when readable
- diagrams, figures, callouts, arrows, labels, dimensions, notes, symbols, legends
- charts/graphs, including title, axes, units, legend, trends, and readable data points
- part numbers, item numbers, quantities, nomenclature, figure references, sheet references
- warnings/cautions/notes visible in the image

Return this exact markdown structure:
# Page visual text
## Page type
<one of: blank, text, parts_list, table, figure, diagram, chart, mixed, unknown>

## Visual summary
<short factual summary of what the page visually contains>

## Tables
<markdown table(s) if visible and readable; otherwise say "No readable table detected.">

## Figures/diagrams
<describe diagrams, callouts, arrows, part labels, spatial relationships; otherwise say "No readable figure or diagram detected.">

## Charts/graphs
<describe chart title, axes, legend, trends, data points if readable; otherwise say "No readable chart or graph detected.">

## Labels/callouts/part numbers
<bullet list of visible labels, callouts, item numbers, part numbers, references>

## Warnings/notes
<visible warnings, cautions, notes, revision notes, or procedural notes>

## Uncertain/unreadable
<state what could not be read or what is uncertain>
"""

    ocr_block = ocr_assist_text.strip() if ocr_assist_text else "No OCR text was available for grounding."
    if version in {"visual_text_v2_2", "v2_2", "v2.2", "strict_v2_2"}:
        return f"""You are reading a scanned aircraft technical manual page image and producing a source-review note.

Important behavior:
- You can read and describe the supplied page image.
- Do not apologize or say you cannot transcribe/read images. If text is unclear, write "unreadable".
- Keep image-visible content separate from OCR/context-only content.
- The page image is the only source for visible-page sections.
- OCR/context assist is only a helper. Do not copy OCR/context metadata into visible-page sections unless the same text is visibly printed on the page.
- Never copy these routing fields into visible-page sections: page_id, source URL/path, current page role, image classification, known part hints, existing context summary.

How to use OCR/context assist:
- Use it to decide where to look and to compare likely text.
- Put OCR-only or context-only observations in "OCR/context assist notes".
- If OCR says something but the image is not clear enough to confirm it, say that in "OCR/context assist notes" or "Uncertain/unreadable".

Extraction rules:
- Prefer exact visible words, labels, callouts, part numbers, item numbers, quantities, figure references, sheet references, and titles.
- If a table/grid/list is visible but cells are blurry, describe the columns/structure and use "unreadable" for unclear cells.
- Do not invent warnings, notes, part numbers, quantities, table cells, regulatory language, or procedures.
- One short visual summary is allowed, but it must be based only on the visible/transcribed sections.

Non-visible routing context, for awareness only:
- page_id: {page_id}
- manual/document: {manual or 'unknown'}
- ATA: {ata_code or 'unknown'}
- current page role: {role or 'unknown'}
- image classification: {image_class or 'unknown'}
- known part hints from OCR/catalog: {part_text or 'none'}
- existing context summary: {context_summary or 'none'}
- source URL/path hint: {source.get('source_url') or 'none'}

OCR assist text, for grounding/comparison only:
--- OCR ASSIST START ---
{ocr_block}
--- OCR ASSIST END ---

Return EXACTLY this markdown structure, with every heading present. Use the headings verbatim.
# Page visual text
## Page type
<one of: blank, text, parts_list, table, figure, diagram, chart, mixed, unknown>

## Visible title/header
<only title/header/footer text visibly printed on the page, or "No readable title or header detected.">

## Transcribed visible text
<visible readable text from the image. Use bullets. If nothing else is readable, say "No additional readable text transcribed from the image.">

## Visual summary
<one short factual summary based only on visible/transcribed/table/figure content. Do not paste the full output here.>

## OCR/context assist notes
<OCR/context-only hints, conflicts, or "No OCR/context-only notes reported.">

## Tables
<markdown table if any rows/columns can be read; otherwise describe visible grid/list structure and unreadable cells; if no table/grid/list is visible, say "No readable table detected.">

## Figures/diagrams
<describe figures, diagrams, labels, callouts, arrows, and relationships; otherwise say "No readable figure or diagram detected.">

## Charts/graphs
<describe chart title, axes, legend, trends, and data points if readable; otherwise say "No readable chart or graph detected.">

## Labels/callouts/part numbers
<bullet list of exact visible labels, callouts, item numbers, part numbers, quantities, references. If none visible, say so.>

## Warnings/notes
<visible warnings, cautions, notes, revision notes, or procedural notes. If none visible, say so.>

## Uncertain/unreadable
<bullet list of unreadable regions, blurry fields, OCR/image conflicts, and fields that need source review.>

## Model caution
Use this visual extraction as derived context. Verify critical facts against source TIFF/OCR evidence.
"""

    prompt_label = "STRICT VISUAL TEXT EXTRACTION"
    if version in {"visual_text_v2_1", "v2_1", "v2.1", "strict_v2_1", "visual_text_v2_2", "v2_2", "v2.2", "strict_v2_2"}:
        prompt_label = "STRICT VISUAL TEXT EXTRACTION v2.1"
    return f"""You are performing {prompt_label} for a scanned aircraft technical manual page.

Core rule:
- Transcribe first, summarize second.
- Use the source page image as the authority for visible text.
- Use OCR assist only for grounding, correction, comparison, and context notes.
- Do not invent warnings, notes, part numbers, quantities, table cells, regulatory language, or page meaning.
- If a value is not clearly readable, write "unreadable" instead of guessing.
- If OCR assist conflicts with the image, say so in Uncertain/unreadable.
- Do not say a table is absent just because some cells are blurry. If grid/columns are visible, describe the table structure and mark unreadable cells.

Metadata/context below is NOT visible page text. It is only routing context.
Never copy page_id, source URLs, local file paths, current page role, image classification, known part hints, or existing context summary into Transcribed visible text, Labels/callouts, Tables, Warnings/notes, or Figures/diagrams unless that exact text is visibly present on the page image.
If metadata/OCR helps interpretation but is not visibly confirmed, put it only in OCR/context assist notes.

Page metadata/context only:
- page_id: {page_id}
- manual/document: {manual or 'unknown'}
- ATA: {ata_code or 'unknown'}
- current page role: {role or 'unknown'}
- image classification: {image_class or 'unknown'}
- known part hints from OCR/catalog: {part_text or 'none'}
- existing context summary: {context_summary or 'none'}
- source URL/path hint: {source.get('source_url') or 'none'}

OCR assist text for grounding, correction, and comparison. Do not copy OCR assist text into visible transcription unless it is also visibly confirmed in the image:
--- OCR ASSIST START ---
{ocr_block}
--- OCR ASSIST END ---

Extraction targets:
1. Visible title/header/footer text.
2. Direct transcription of visible text that is readable.
3. Tables/grids as markdown tables when any rows or columns can be read. Use "unreadable" for unclear cells.
4. Figures/diagrams/callouts/arrows/labels/spatial relationships.
5. Charts/graphs including title, axes, units, legend, trends, and readable data points.
6. Visible part numbers, item numbers, quantities, nomenclature, figure references, sheet references.
7. Warnings/cautions/notes only when visible or clearly supported by visible image text.
8. OCR/context notes for useful OCR/context-only information that should not be treated as visible transcription.
9. Unreadable/uncertain areas and why they are uncertain.

Return EXACTLY this markdown structure, with every section present:
# Page visual text
## Page type
<one of: blank, text, parts_list, table, figure, diagram, chart, mixed, unknown>

## Visible title/header
<transcribe visible title/header/footer or say "No readable title or header detected.">

## Transcribed visible text
<direct transcription of readable text. Do not include metadata, source URLs, local file paths, page_id, role/classification hints, or context summary unless visibly printed on the page.>

## Visual summary
<one short factual summary after transcription>

## OCR/context assist notes
<OCR/context-only notes that helped interpretation but are not confirmed as visible text; otherwise say "No OCR/context-only notes reported.">

## Tables
<markdown table(s) if any table/grid/list columns are visible; use "unreadable" cells; otherwise say "No readable table detected.">

## Figures/diagrams
<describe figures, diagrams, labels, callouts, arrows, and relationships; otherwise say "No readable figure or diagram detected.">

## Charts/graphs
<describe chart title, axes, legend, trends, and data points if readable; otherwise say "No readable chart or graph detected.">

## Labels/callouts/part numbers
<bullet list of visible labels, callouts, item numbers, part numbers, quantities, references. Do not list metadata-only page role/classification/source information. If none visible, say so.>

## Warnings/notes
<visible warnings, cautions, notes, revision notes, or procedural notes. If none visible, say so.>

## Uncertain/unreadable
<bullet list of unreadable regions, blurry fields, OCR/image conflicts, and fields that need source review.>

## Model caution
<one sentence explaining that uncertain fields must be verified against the TIFF/OCR source.>
"""


def build_visual_text_client(options: ExtractionOptions) -> VisualTextClient:
    provider = options.provider.strip().lower()
    if provider in {"mock", "test"}:
        return MockVisualTextClient()
    if provider in {"planned", "plan", "dry-run", "none"}:
        return PlannedVisualTextClient()
    if provider == "ollama":
        return OllamaVisionClient(
            model=options.model,
            base_url=options.ollama_base_url,
            timeout_seconds=options.timeout_seconds,
            max_image_edge=options.max_image_edge,
            temperature=options.temperature,
        )
    raise ValueError(f"Unsupported visual text provider: {options.provider}")


def _record_for_skip(card: Mapping[str, Any], status: str, reason: str, options: ExtractionOptions) -> dict[str, Any]:
    page_id = _card_page_id(card)
    source = _card_source(card)
    provider = options.provider
    model = options.model if provider != "planned" else "none"
    return {
        "page_id": page_id,
        "entity_id": _first(card, "entity_id", default=f"page:{page_id}"),
        "status": status,
        "reason": reason,
        "provider": provider,
        "model": model,
        "page_role": _card_role(card),
        "image_classification": _card_image_class(card),
        "source": source,
        "created_at": utc_now_iso(),
        "visual_text_markdown": "",
        "visual_text_plain": "",
        "char_count": 0,
    }

def _plain_text_from_markdown(markdown: str) -> str:
    text = re.sub(r"```.*?```", " ", markdown, flags=re.S)
    text = re.sub(r"[#*_`>|\-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text




def _canonical_section_title(title: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(title or "").strip()).strip("#:")
    for expected in VISUAL_TEXT_V2_SECTIONS:
        if cleaned.lower() == expected.lower():
            return expected
    return VISUAL_TEXT_V2_SECTION_ALIASES.get(cleaned.lower(), cleaned)


def _is_underline_heading(line: str, next_line: str) -> bool:
    """Return True for setext-style headings such as 'Page type' + '-----'."""

    title = _canonical_section_title(line.strip())
    if title not in VISUAL_TEXT_V2_SECTIONS:
        return False
    stripped_next = next_line.strip()
    return bool(stripped_next) and set(stripped_next) <= {"-", "="} and len(stripped_next) >= 3


def _looks_like_section_label(line: str) -> str | None:
    """Handle model outputs that omit markdown hashes but still use section labels."""

    cleaned = re.sub(r"\s+", " ", str(line or "").strip()).strip("#: ")
    if not cleaned:
        return None
    title = _canonical_section_title(cleaned)
    return title if title in VISUAL_TEXT_V2_SECTIONS else None


def parse_visual_text_sections(markdown: str) -> dict[str, str]:
    """Parse markdown sections produced by the visual-text model.

    LLaVA sometimes returns requested headings as plain labels or setext-style
    headings instead of using ``##`` markdown.  This parser accepts all three
    forms so the normalizer does not accidentally put the whole model response
    under ``Visual summary``.
    """

    lines = str(markdown or "").splitlines()
    sections: dict[str, list[str]] = {}
    current: str | None = None
    preamble: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        next_line = lines[i + 1] if i + 1 < len(lines) else ""
        if stripped.startswith("## "):
            current = _canonical_section_title(stripped[3:].strip())
            sections.setdefault(current, [])
            i += 1
            continue
        if stripped.startswith("# "):
            heading = _canonical_section_title(stripped[2:].strip())
            if heading in VISUAL_TEXT_V2_SECTIONS:
                current = heading
                sections.setdefault(current, [])
            else:
                current = None
            i += 1
            continue
        if _is_underline_heading(stripped, next_line):
            current = _canonical_section_title(stripped)
            sections.setdefault(current, [])
            i += 2
            continue
        plain_label = _looks_like_section_label(stripped)
        if plain_label and (current is None or not stripped.endswith(".")):
            current = plain_label
            sections.setdefault(current, [])
            i += 1
            continue
        if current is None:
            if stripped:
                preamble.append(line)
            i += 1
            continue
        sections.setdefault(current, []).append(line)
        i += 1
    parsed = {title: "\n".join(lines).strip() for title, lines in sections.items()}
    if preamble and not parsed.get("Visual summary"):
        parsed["Visual summary"] = "\n".join(preamble).strip()
    return parsed


def normalize_visual_text_markdown(markdown: str, *, prompt_version: str = DEFAULT_PROMPT_VERSION) -> str:
    """Return markdown with every v2 section present in a stable order."""

    raw = str(markdown or "").strip()
    if str(prompt_version or "").lower() not in {"visual_text_v2", "v2", "strict_v2", "strict", "visual_text_v2_1", "v2_1", "v2.1", "strict_v2_1", "visual_text_v2_2", "v2_2", "v2.2", "strict_v2_2"}:
        return raw
    sections = parse_visual_text_sections(raw)
    lines = ["# Page visual text", ""]
    for title in VISUAL_TEXT_V2_SECTIONS:
        value = str(sections.get(title) or "").strip()
        if not value:
            value = VISUAL_TEXT_V2_SECTION_DEFAULTS[title]
        lines.extend([f"## {title}", value, ""])
    extra_titles = [title for title in sections if title not in VISUAL_TEXT_V2_SECTIONS and str(sections[title]).strip()]
    if extra_titles:
        lines.extend(["## Additional model output", ""])
        for title in extra_titles:
            lines.extend([f"### {title}", str(sections[title]).strip(), ""])
    return "\n".join(lines).rstrip() + "\n"


def _section_text(markdown: str, title: str) -> str:
    return str(parse_visual_text_sections(markdown).get(title) or "").strip()


def _is_negative_or_empty_section(value: Any) -> bool:
    text = " ".join(str(value or "").strip().lower().split())
    if not text:
        return True
    negative_markers = (
        "no readable",
        "no visible",
        "none visible",
        "not visible",
        "not detected",
        "detected.",
        "no additional readable",
        "no uncertain or unreadable",
        "none in mock output",
        "unknown",
    )
    if text in {"none", "n/a", "na", "unknown", "no"}:
        return True
    return any(text.startswith(marker) for marker in negative_markers)


def _word_count(value: Any) -> int:
    return len(re.findall(r"\b\w+\b", str(value or "")))


def _part_number_count(value: Any) -> int:
    return len(set(re.findall(r"\b[A-Z0-9]{1,4}[-/][A-Z0-9][A-Z0-9\-/\.]{2,}\b", str(value or "").upper())))


METADATA_LEAK_PATTERNS: tuple[tuple[str, str], ...] = (
    ("page_id", r"\bpage[_ -]?id\b|\bt_p_\d+_\d+_p\d{6}\b"),
    ("source_url", r"https?://localhost|https?://127\.0\.0\.1|/rescarta/|\brescarta\b"),
    ("local_path", r"local_data[\\/]|[A-Za-z]:[\\/]|\.tiff?\b|\.txt\b"),
    ("page_role_hint", r"\bcurrent page role\b|\bpage role\s*[:=]|\brole\s*=\s*(parts_list|figure|table|procedure|front_matter|blank)"),
    ("image_classification_hint", r"\bimage classification\b|\bimage_classification\b|\blikely_(table_or_grid|figure_or_diagram|text_or_parts_list|blank)\b"),
    ("known_part_hints", r"\bknown part hints\b|\bpart hints from ocr\b|\bocr/catalog\b"),
    ("existing_context_summary", r"\bexisting context summary\b|\bcontext summary\b"),
    ("ocr_assist_marker", r"\bocr assist\b|---\s*ocr assist\s*(start|end)\s*---"),
)


def _metadata_leakage_markers(value: Any) -> list[str]:
    text = str(value or "")
    markers: list[str] = []
    for name, pattern in METADATA_LEAK_PATTERNS:
        if re.search(pattern, text, flags=re.I):
            markers.append(name)
    return sorted(set(markers))


def _metadata_leakage_text(sections: Mapping[str, str]) -> str:
    """Return sections that should contain only visible page evidence.

    OCR/context assist notes and Model caution are intentionally excluded: v2.1
    gives the model a safe place for context-only information.
    """

    visible_only_sections = (
        "Visible title/header",
        "Transcribed visible text",
        "Tables",
        "Figures/diagrams",
        "Charts/graphs",
        "Labels/callouts/part numbers",
        "Warnings/notes",
    )
    return "\n".join(str(sections.get(title) or "") for title in visible_only_sections)


def score_visual_text_markdown(markdown: str, *, prompt_version: str = DEFAULT_PROMPT_VERSION) -> dict[str, Any]:
    """Score visual extraction usefulness without claiming factual correctness."""

    normalized = normalize_visual_text_markdown(markdown, prompt_version=prompt_version)
    sections = parse_visual_text_sections(normalized)
    missing = [title for title in VISUAL_TEXT_V2_SECTIONS if not str(sections.get(title) or "").strip()]
    tables = sections.get("Tables", "")
    figures = sections.get("Figures/diagrams", "")
    charts = sections.get("Charts/graphs", "")
    labels = sections.get("Labels/callouts/part numbers", "")
    warnings = sections.get("Warnings/notes", "")
    uncertain = sections.get("Uncertain/unreadable", "")
    ocr_context_notes = sections.get("OCR/context assist notes", "")
    visible_text = sections.get("Transcribed visible text", "")
    summary = sections.get("Visual summary", "")
    leakage_markers = _metadata_leakage_markers(_metadata_leakage_text(sections))
    has_table_rows = "|" in tables and len([line for line in tables.splitlines() if "|" in line]) >= 2
    visible_part_number_text = labels + "\n" + visible_text + "\n" + tables + "\n" + figures
    visible_part_number_count = _part_number_count(visible_part_number_text)
    has_part_numbers = visible_part_number_count > 0
    hallucination_markers = (
        "appears to",
        "likely",
        "probably",
        "for illustrative purposes only",
        "should not be used as",
        "not to be used as a substitute",
        "may be",
        "could be",
    )
    refusal_markers = (
        "unable to transcribe text from images",
        "cannot transcribe text from images",
        "can't transcribe text from images",
        "unable to read images",
        "cannot read images",
        "if you have a specific question",
        "i can provide you with guidance",
    )
    lowered = normalized.lower()
    summary_words = _word_count(summary)
    transcribed_words = _word_count(visible_text)
    prompt_key = str(prompt_version or "").lower()
    if prompt_key in {"visual_text_v2_2", "v2_2", "v2.2", "strict_v2_2"}:
        prompt_label = "visual_text_v2_2"
    elif prompt_key in {"visual_text_v2_1", "v2_1", "v2.1", "strict_v2_1"}:
        prompt_label = "visual_text_v2_1"
    else:
        prompt_label = "visual_text_v2"
    refusal_like = any(marker in lowered for marker in refusal_markers)
    return {
        "prompt_version": prompt_label,
        "required_sections_present": not missing,
        "missing_required_sections": missing,
        "section_count": sum(1 for title in VISUAL_TEXT_V2_SECTIONS if str(sections.get(title) or "").strip()),
        "has_page_type": not _is_negative_or_empty_section(sections.get("Page type")),
        "has_visible_title_or_header": not _is_negative_or_empty_section(sections.get("Visible title/header")),
        "has_visual_summary": not _is_negative_or_empty_section(summary),
        "has_transcribed_visible_text": not _is_negative_or_empty_section(visible_text),
        "has_tables_section": not _is_negative_or_empty_section(tables),
        "has_table_rows": has_table_rows,
        "has_figure_description": not _is_negative_or_empty_section(figures),
        "has_chart_description": not _is_negative_or_empty_section(charts),
        "has_labels_or_callouts": not _is_negative_or_empty_section(labels),
        "has_part_numbers": has_part_numbers,
        "visible_part_number_count": visible_part_number_count,
        "has_warnings_or_notes": not _is_negative_or_empty_section(warnings),
        "has_uncertain_or_unreadable": not _is_negative_or_empty_section(uncertain),
        "has_ocr_context_notes": not _is_negative_or_empty_section(ocr_context_notes),
        "metadata_leakage_risk": bool(leakage_markers),
        "metadata_leakage_markers": leakage_markers,
        "metadata_leakage_marker_count": len(leakage_markers),
        "too_summary_heavy": summary_words >= 35 and transcribed_words < 20 and not has_table_rows,
        "too_short": len(normalized.strip()) < 350,
        "refusal_like": refusal_like,
        "hallucination_risk": any(marker in lowered for marker in hallucination_markers) or refusal_like,
    }


def _read_ocr_assist_text(card: Mapping[str, Any], max_chars: int = DEFAULT_OCR_MAX_CHARS) -> str:
    """Read a bounded OCR snippet for model grounding when available."""

    source = _card_source(card)
    ocr_path = _resolve_path(source.get("ocr_path"))
    if not ocr_path or not ocr_path.exists() or not ocr_path.is_file():
        return ""
    try:
        text = ocr_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    if max_chars > 0 and len(text) > max_chars:
        return text[:max_chars].rstrip() + " ... [OCR snippet truncated]"
    return text

def _looks_blank(card: Mapping[str, Any]) -> bool:
    return _norm(_card_role(card)) == "blank" or _norm(_card_image_class(card)) == "likely_blank"


def _image_path_exists(path: Path | None) -> bool:
    return bool(path and path.exists() and path.is_file())


def _make_success_record(
    card: Mapping[str, Any],
    markdown: str,
    prompt: str,
    client: VisualTextClient,
    options: ExtractionOptions,
    started_at: float,
    ocr_assist_text: str = "",
    safety_layer_name: str = "primary",
    safety_layer_index: int = 0,
    fishnet_attempts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    page_id = _card_page_id(card)
    source = _card_source(card)
    parents = _as_dict(card.get("parents"))
    context = _as_dict(card.get("context"))
    elapsed = round(time.time() - started_at, 3)
    normalized_markdown = normalize_visual_text_markdown(markdown, prompt_version=options.prompt_version)
    visual_scores = score_visual_text_markdown(normalized_markdown, prompt_version=options.prompt_version)
    return {
        "page_id": page_id,
        "entity_id": _first(card, "entity_id", default=f"page:{page_id}"),
        "status": "planned" if client.provider_name == "planned" else "ok",
        "provider": client.provider_name,
        "model": client.model_name,
        "page_role": _card_role(card),
        "image_classification": _card_image_class(card),
        "parents": {
            "document_id": _first(parents, "document_id", default=None),
            "document_label": _first(parents, "document_label", "manual", default=None),
            "ata_id": _first(parents, "ata_id", default=None),
            "ata_code": _first(parents, "ata_code", default=None),
        },
        "source": source,
        "context": {
            "summary": _first(context, "summary", "short_summary", default=None),
            "topics": context.get("topics") if isinstance(context.get("topics"), list) else [],
            "important_parts": context.get("important_parts") if isinstance(context.get("important_parts"), list) else [],
        },
        "known_parts": card.get("parts") if isinstance(card.get("parts"), list) else [],
        "prompt_version": str(options.prompt_version or DEFAULT_PROMPT_VERSION),
        "prompt_preview": prompt[:1600],
        "ocr_assist_used": bool(ocr_assist_text.strip()),
        "ocr_assist_char_count": len(ocr_assist_text.strip()),
        "ocr_assist_preview": ocr_assist_text.strip()[:1600],
        "max_image_edge": int(options.max_image_edge or 0),
        "timeout_seconds": int(options.timeout_seconds or 0),
        "temperature": float(options.temperature or 0.0),
        "fishnet_layer": safety_layer_name,
        "fishnet_layer_index": int(safety_layer_index),
        "fishnet_rescued": int(safety_layer_index) > 0,
        "fishnet_attempts": [dict(attempt) for attempt in fishnet_attempts],
        "visual_text_scores": visual_scores,
        "created_at": utc_now_iso(),
        "elapsed_seconds": elapsed,
        "visual_text_markdown": normalized_markdown.strip(),
        "visual_text_plain": _plain_text_from_markdown(normalized_markdown),
        "char_count": len(normalized_markdown.strip()),
    }


def _make_error_record(
    card: Mapping[str, Any],
    error: BaseException,
    client: VisualTextClient,
    options: ExtractionOptions,
    safety_layer_name: str = "primary",
    safety_layer_index: int = 0,
    fishnet_attempts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    page_id = _card_page_id(card)
    source = _card_source(card)
    return {
        "page_id": page_id,
        "entity_id": _first(card, "entity_id", default=f"page:{page_id}"),
        "status": "error",
        "provider": client.provider_name,
        "model": client.model_name,
        "page_role": _card_role(card),
        "image_classification": _card_image_class(card),
        "source": source,
        "created_at": utc_now_iso(),
        "max_image_edge": int(options.max_image_edge or 0),
        "timeout_seconds": int(options.timeout_seconds or 0),
        "temperature": float(options.temperature or 0.0),
        "fishnet_layer": safety_layer_name,
        "fishnet_layer_index": int(safety_layer_index),
        "fishnet_rescued": False,
        "fishnet_attempts": [dict(attempt) for attempt in fishnet_attempts],
        "error": str(error),
        "visual_text_markdown": "",
        "visual_text_plain": "",
        "char_count": 0,
    }


def _build_corpus_markdown(records: Sequence[Mapping[str, Any]]) -> str:
    parts = ["# HEICO visual text corpus", ""]
    ok_records = [record for record in records if record.get("status") in {"ok", "planned"}]
    for record in sorted(ok_records, key=lambda r: _text(r.get("page_id"))):
        page_id = _text(record.get("page_id"))
        parents = _as_dict(record.get("parents"))
        source = _as_dict(record.get("source"))
        parts.append(f"## Page {page_id}")
        parts.append("")
        parts.append(f"- status: {record.get('status')}")
        parts.append(f"- provider: {record.get('provider')}")
        parts.append(f"- model: {record.get('model')}")
        parts.append(f"- ATA: {parents.get('ata_code') or ''}")
        parts.append(f"- page_role: {record.get('page_role') or ''}")
        parts.append(f"- image_classification: {record.get('image_classification') or ''}")
        if source.get("source_url"):
            parts.append(f"- source_url: {source.get('source_url')}")
        if source.get("tiff_path"):
            parts.append(f"- tiff_path: {source.get('tiff_path')}")
        parts.append("")
        parts.append(str(record.get("visual_text_markdown") or "").strip())
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _build_graph_overlay(records: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    evidence_id = "evidence:visual_text_extraction"
    nodes.append(
        {
            "id": evidence_id,
            "type": "evidence_source",
            "kind": "visual_text_extraction",
            "label": "Model-assisted visual text extraction",
            "artifact_path": str(DEFAULT_OUTPUT_DIR / DEFAULT_RECORDS_FILE),
        }
    )
    for record in sorted(records, key=lambda r: _text(r.get("page_id"))):
        if record.get("status") not in {"ok", "planned"}:
            continue
        page_id = _text(record.get("page_id"))
        if not page_id:
            continue
        visual_id = f"visual_text:{page_id}"
        nodes.append(
            {
                "id": visual_id,
                "type": "visual_text_context",
                "page_id": page_id,
                "label": f"Visual text for {page_id}",
                "provider": record.get("provider"),
                "model": record.get("model"),
                "status": record.get("status"),
                "page_role": record.get("page_role"),
                "image_classification": record.get("image_classification"),
                "char_count": record.get("char_count", 0),
                "prompt_version": record.get("prompt_version"),
                "ocr_assist_used": record.get("ocr_assist_used"),
                "scores": _as_dict(record.get("visual_text_scores")),
                "plain_text_preview": _text(record.get("visual_text_plain"))[:500],
            }
        )
        edges.append(
            {
                "id": f"edge:page:{page_id}:has_visual_text",
                "source": f"page:{page_id}",
                "target": visual_id,
                "type": "HAS_VISUAL_TEXT",
            }
        )
        edges.append(
            {
                "id": f"edge:{visual_id}:derived_from",
                "source": visual_id,
                "target": evidence_id,
                "type": "DERIVED_FROM",
            }
        )
        edges.append(
            {
                "id": f"edge:{visual_id}:summarizes_page",
                "source": visual_id,
                "target": f"page:{page_id}",
                "type": "SUMMARIZES_VISUAL_CONTENT_OF",
            }
        )
    return nodes, edges


def build_visual_text_summary(
    records: Sequence[Mapping[str, Any]],
    selected_count: int,
    total_cards: int,
    options: ExtractionOptions,
    warnings: Sequence[str] = (),
    graph_nodes: Sequence[Mapping[str, Any]] = (),
    graph_edges: Sequence[Mapping[str, Any]] = (),
    provider_name: str | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    role_counts: dict[str, int] = {}
    class_counts: dict[str, int] = {}
    score_counts: dict[str, int] = {
        "v2_records": 0,
        "v2_1_records": 0,
        "v2_2_records": 0,
        "required_sections_present": 0,
        "has_transcribed_visible_text": 0,
        "has_tables_section": 0,
        "has_table_rows": 0,
        "has_figure_description": 0,
        "has_labels_or_callouts": 0,
        "has_part_numbers": 0,
        "has_uncertain_or_unreadable": 0,
        "has_ocr_context_notes": 0,
        "refusal_like": 0,
        "metadata_leakage_risk": 0,
        "too_summary_heavy": 0,
        "too_short": 0,
        "hallucination_risk": 0,
    }
    visible_part_number_total = 0
    metadata_leakage_marker_total = 0
    fishnet_rescued_records = 0
    fishnet_attempt_total = 0
    fishnet_layer_counts: dict[str, int] = {}
    fishnet_failed_records = 0
    for record in records:
        status_counts[_text(record.get("status") or "unknown")] = status_counts.get(_text(record.get("status") or "unknown"), 0) + 1
        role_counts[_text(record.get("page_role") or "unknown")] = role_counts.get(_text(record.get("page_role") or "unknown"), 0) + 1
        class_counts[_text(record.get("image_classification") or "unknown")] = class_counts.get(_text(record.get("image_classification") or "unknown"), 0) + 1
        scores = _as_dict(record.get("visual_text_scores"))
        score_prompt = _text(scores.get("prompt_version") or record.get("prompt_version")).lower()
        if score_prompt in {"visual_text_v2", "v2", "strict_v2", "strict", "visual_text_v2_1", "v2_1", "v2.1", "strict_v2_1", "visual_text_v2_2", "v2_2", "v2.2", "strict_v2_2"}:
            score_counts["v2_records"] += 1
        if score_prompt == "visual_text_v2_1":
            score_counts["v2_1_records"] += 1
        if score_prompt == "visual_text_v2_2":
            score_counts["v2_2_records"] += 1
        for key in tuple(score_counts):
            if key in {"v2_records", "v2_1_records", "v2_2_records"}:
                continue
            if bool(scores.get(key)):
                score_counts[key] += 1
        try:
            visible_part_number_total += int(scores.get("visible_part_number_count") or 0)
        except (TypeError, ValueError):
            pass
        try:
            metadata_leakage_marker_total += int(scores.get("metadata_leakage_marker_count") or 0)
        except (TypeError, ValueError):
            pass
        attempts = _as_list(record.get("fishnet_attempts"))
        fishnet_attempt_total += len(attempts)
        layer_name = _text(record.get("fishnet_layer") or (attempts[-1].get("layer") if attempts and isinstance(attempts[-1], Mapping) else ""))
        if layer_name:
            fishnet_layer_counts[layer_name] = fishnet_layer_counts.get(layer_name, 0) + 1
        if bool(record.get("fishnet_rescued")):
            fishnet_rescued_records += 1
        if _text(record.get("status")).lower() == "error" and len(attempts) > 1:
            fishnet_failed_records += 1

    ok_count = status_counts.get("ok", 0)
    planned_count = status_counts.get("planned", 0)
    error_count = status_counts.get("error", 0)
    missing_count = status_counts.get("skipped_missing_image", 0)
    blank_count = status_counts.get("skipped_blank", 0)
    char_total = sum(int(record.get("char_count") or 0) for record in records if record.get("status") in {"ok", "planned"})
    pages_with_text = sum(1 for record in records if record.get("status") in {"ok", "planned"} and int(record.get("char_count") or 0) > 0)
    accepted_count = ok_count + planned_count
    if error_count == 0 and (accepted_count > 0 or selected_count == 0):
        run_status = "OK"
    elif accepted_count > 0 and error_count > 0:
        run_status = "PARTIAL"
    else:
        run_status = "FAIL"

    return {
        "status": run_status,
        "created_at": utc_now_iso(),
        "provider": provider_name or options.provider,
        "model": model_name or (options.model if options.provider != "planned" else "none"),
        "total_page_cards": total_cards,
        "selected_pages": selected_count,
        "retry_error_pages_only": bool(options.retry_error_pages_only),
        "fishnet_safety_layers_enabled": bool(options.safety_layers),
        "fishnet_safety_layer_count": len(options.safety_layers),
        "fishnet_safety_layers": [layer.name for layer in options.safety_layers],
        "fishnet_rescued_records": fishnet_rescued_records,
        "fishnet_failed_records": fishnet_failed_records,
        "fishnet_attempt_total": fishnet_attempt_total,
        "fishnet_layer_counts": dict(sorted(fishnet_layer_counts.items())),
        "records": len(records),
        "ok_records": ok_count,
        "planned_records": planned_count,
        "error_records": error_count,
        "skipped_missing_image_records": missing_count,
        "skipped_blank_records": blank_count,
        "pages_with_visual_text": pages_with_text,
        "visual_text_char_total": char_total,
        "visual_text_avg_chars": round(char_total / pages_with_text, 2) if pages_with_text else 0.0,
        "status_counts": dict(sorted(status_counts.items())),
        "page_role_counts": dict(sorted(role_counts.items())),
        "image_classification_counts": dict(sorted(class_counts.items())),
        "prompt_version": str(options.prompt_version or DEFAULT_PROMPT_VERSION),
        "ocr_assist_enabled": bool(options.ocr_assist),
        "ocr_max_chars": int(options.ocr_max_chars or 0),
        "visual_text_v2_records": score_counts["v2_records"],
        "visual_text_v2_1_records": score_counts["v2_1_records"],
        "visual_text_v2_2_records": score_counts["v2_2_records"],
        "visual_text_required_sections_records": score_counts["required_sections_present"],
        "visual_text_transcribed_records": score_counts["has_transcribed_visible_text"],
        "visual_text_table_section_records": score_counts["has_tables_section"],
        "visual_text_table_row_records": score_counts["has_table_rows"],
        "visual_text_figure_description_records": score_counts["has_figure_description"],
        "visual_text_label_callout_records": score_counts["has_labels_or_callouts"],
        "visual_text_part_number_records": score_counts["has_part_numbers"],
        "visual_text_visible_part_number_total": visible_part_number_total,
        "visual_text_uncertain_records": score_counts["has_uncertain_or_unreadable"],
        "visual_text_ocr_context_note_records": score_counts["has_ocr_context_notes"],
        "visual_text_metadata_leakage_records": score_counts["metadata_leakage_risk"],
        "visual_text_metadata_leakage_marker_total": metadata_leakage_marker_total,
        "visual_text_summary_heavy_records": score_counts["too_summary_heavy"],
        "visual_text_too_short_records": score_counts["too_short"],
        "visual_text_hallucination_risk_records": score_counts["hallucination_risk"],
        "visual_text_refusal_like_records": score_counts["refusal_like"],
        "graph_overlay_nodes": len(graph_nodes),
        "graph_overlay_edges": len(graph_edges),
        "warnings": list(warnings),
    }


def run_visual_text_extraction(
    paths: VisualTextPaths = VisualTextPaths(),
    options: ExtractionOptions = ExtractionOptions(),
    client: VisualTextClient | None = None,
) -> VisualTextRunResult:
    """Run visual text extraction and write artifacts."""

    paths.output_dir.mkdir(parents=True, exist_ok=True)
    cards = load_page_cards(paths.page_cards_path, paths.page_index_path)
    existing = _existing_records(paths.records_path) if (not options.overwrite or options.retry_error_pages_only) else {}

    selection_max_pages = None if options.retry_error_pages_only else options.max_pages
    selected = select_candidate_cards(
        cards,
        page_ids=options.page_ids,
        page_roles=options.page_roles,
        image_classes=options.image_classes,
        include_blank=options.include_blank,
        max_pages=selection_max_pages,
    )
    if options.retry_error_pages_only:
        error_page_ids = {
            page_id
            for page_id, record in existing.items()
            if _text(record.get("status")).lower() == "error"
        }
        selected = [card for card in selected if _card_page_id(card) in error_page_ids]
        if options.max_pages is not None and options.max_pages >= 0:
            selected = selected[: options.max_pages]

    provided_client = client
    base_client = provided_client or build_visual_text_client(options)
    warnings: list[str] = []
    run_started_at = time.time()
    processed_in_this_run = 0
    checkpoint_every = max(0, int(options.checkpoint_every or 0))

    if options.progress:
        layer_text = ", ".join(
            f"{layer.name}(edge={layer.max_image_edge or options.max_image_edge},timeout={layer.timeout_seconds or options.timeout_seconds})"
            for layer in options.safety_layers
        ) or "none"
        print(
            "Visual text extraction progress: "
            f"selected_pages={len(selected)} provider={base_client.provider_name} "
            f"model={getattr(base_client, 'model_name', options.model)} max_image_edge={options.max_image_edge} "
            f"retry_errors_only={options.retry_error_pages_only} fishnet_layers={layer_text}",
            flush=True,
        )

    for index, card in enumerate(selected, start=1):
        page_started_at = time.time()
        page_id = _card_page_id(card)
        if not page_id:
            continue
        if page_id in existing and not options.overwrite and not options.retry_error_pages_only:
            record = existing[page_id]
            if options.progress:
                print(
                    _progress_line(
                        index,
                        len(selected),
                        page_id,
                        "already_done",
                        int(record.get("char_count") or 0),
                        time.time() - page_started_at,
                        run_started_at,
                    ),
                    flush=True,
                )
            continue
        if _looks_blank(card) and not options.include_blank:
            existing[page_id] = _record_for_skip(card, "skipped_blank", "blank page skipped", options)
        else:
            source = _card_source(card)
            image_path = _resolve_path(source.get("tiff_path"))
            if not _image_path_exists(image_path):
                existing[page_id] = _record_for_skip(card, "skipped_missing_image", "missing TIFF/image path", options)
            else:
                attempt_plan: list[tuple[str, int, ExtractionOptions]] = [("primary", 0, options)]
                for layer_index, layer in enumerate(options.safety_layers, start=1):
                    attempt_plan.append((layer.name, layer_index, _apply_safety_layer(options, layer)))
                fishnet_attempts: list[dict[str, Any]] = []
                last_error: BaseException | None = None
                last_client: VisualTextClient = base_client
                last_options: ExtractionOptions = options
                for layer_name, layer_index, active_options in attempt_plan:
                    attempt_started = time.time()
                    active_client = provided_client or (base_client if layer_index == 0 else build_visual_text_client(active_options))
                    last_client = active_client
                    last_options = active_options
                    try:
                        ocr_assist_text = _read_ocr_assist_text(card, active_options.ocr_max_chars) if active_options.ocr_assist else ""
                        prompt = build_visual_text_prompt(
                            card,
                            prompt_version=active_options.prompt_version,
                            ocr_assist_text=ocr_assist_text,
                        )
                        markdown = active_client.describe_page(
                            Path(image_path),
                            prompt,
                            {
                                "page_id": page_id,
                                "page_role": _card_role(card),
                                "image_classification": _card_image_class(card),
                                "ocr_assist_used": bool(ocr_assist_text),
                                "prompt_version": active_options.prompt_version,
                                "fishnet_layer": layer_name,
                                "fishnet_layer_index": layer_index,
                                "max_image_edge": active_options.max_image_edge,
                                "timeout_seconds": active_options.timeout_seconds,
                            },
                        )
                        fishnet_attempts.append(
                            {
                                "layer": layer_name,
                                "layer_index": layer_index,
                                "status": "ok",
                                "model": getattr(active_client, "model_name", active_options.model),
                                "max_image_edge": int(active_options.max_image_edge or 0),
                                "timeout_seconds": int(active_options.timeout_seconds or 0),
                                "elapsed_seconds": round(time.time() - attempt_started, 3),
                            }
                        )
                        existing[page_id] = _make_success_record(
                            card,
                            markdown,
                            prompt,
                            active_client,
                            active_options,
                            page_started_at,
                            ocr_assist_text=ocr_assist_text,
                            safety_layer_name=layer_name,
                            safety_layer_index=layer_index,
                            fishnet_attempts=fishnet_attempts,
                        )
                        break
                    except Exception as exc:  # noqa: BLE001 - failures fall through the fishnet
                        last_error = exc
                        fishnet_attempts.append(
                            {
                                "layer": layer_name,
                                "layer_index": layer_index,
                                "status": "error",
                                "model": getattr(active_client, "model_name", active_options.model),
                                "max_image_edge": int(active_options.max_image_edge or 0),
                                "timeout_seconds": int(active_options.timeout_seconds or 0),
                                "elapsed_seconds": round(time.time() - attempt_started, 3),
                                "error": str(exc),
                            }
                        )
                        if layer_index < len(attempt_plan) - 1 and options.progress:
                            next_layer_name, _next_index, next_options = attempt_plan[layer_index + 1]
                            print(
                                f"  fishnet: {page_id} failed in {layer_name}; "
                                f"moving to {next_layer_name} "
                                f"(edge={next_options.max_image_edge}, timeout={next_options.timeout_seconds})",
                                flush=True,
                            )
                        continue
                else:
                    # No attempt succeeded.
                    error = last_error or RuntimeError("all visual-text attempts failed")
                    existing[page_id] = _make_error_record(
                        card,
                        error,
                        last_client,
                        last_options,
                        safety_layer_name=fishnet_attempts[-1]["layer"] if fishnet_attempts else "primary",
                        safety_layer_index=int(fishnet_attempts[-1]["layer_index"] if fishnet_attempts else 0),
                        fishnet_attempts=fishnet_attempts,
                    )
                    warnings.append(f"{page_id}: {error}")

        processed_in_this_run += 1
        record = existing[page_id]
        page_elapsed = time.time() - page_started_at
        if options.progress:
            extra = ""
            if record.get("fishnet_rescued"):
                extra = f" layer={record.get('fishnet_layer')} attempts={len(_as_list(record.get('fishnet_attempts')))}"
            print(
                _progress_line(
                    index,
                    len(selected),
                    page_id,
                    str(record.get("status") or "unknown") + extra,
                    int(record.get("char_count") or 0),
                    page_elapsed,
                    run_started_at,
                ),
                flush=True,
            )

        if checkpoint_every and processed_in_this_run % checkpoint_every == 0:
            checkpoint_records = sorted(existing.values(), key=lambda record: _text(record.get("page_id")))
            checkpoint_nodes, checkpoint_edges = (
                _build_graph_overlay(checkpoint_records) if options.write_graph_overlay else ([], [])
            )
            _write_visual_text_artifacts(
                paths,
                checkpoint_records,
                checkpoint_nodes,
                checkpoint_edges,
                options.write_graph_overlay,
            )

    records = sorted(existing.values(), key=lambda record: _text(record.get("page_id")))
    graph_nodes, graph_edges = _build_graph_overlay(records) if options.write_graph_overlay else ([], [])
    summary = build_visual_text_summary(
        records,
        selected_count=len(selected),
        total_cards=len(cards),
        options=options,
        warnings=warnings,
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
        provider_name=client.provider_name,
        model_name=client.model_name,
    )

    _write_visual_text_artifacts(paths, records, graph_nodes, graph_edges, options.write_graph_overlay)
    _write_json(paths.summary_path, summary)

    return VisualTextRunResult(
        status=str(summary.get("status", "FAIL")),
        summary=summary,
        records=records,
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
        warnings=warnings,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract searchable text from visual page content using a vision model.")
    parser.add_argument("--page-cards", type=Path, default=DEFAULT_PAGE_CARDS_PATH)
    parser.add_argument("--page-index", type=Path, default=DEFAULT_PAGE_INDEX_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--provider", choices=("ollama", "mock", "planned"), default="ollama")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama model tag. Use auto to pick an installed vision model.")
    parser.add_argument("--ollama-base-url", default=DEFAULT_OLLAMA_BASE_URL)
    parser.add_argument("--list-ollama-models", action="store_true", help="List installed Ollama models and the auto-selected vision model, then exit.")
    parser.add_argument("--page-id", action="append", default=[])
    parser.add_argument("--page-roles", default=",".join(DEFAULT_PAGE_ROLES))
    parser.add_argument("--image-classes", default=",".join(DEFAULT_IMAGE_CLASSES))
    parser.add_argument("--include-blank", action="store_true")
    parser.add_argument("--max-pages", type=int, default=5, help="Pilot safety limit. Use --all-pages for every selected page.")
    parser.add_argument("--all-pages", action="store_true", help="Process every selected page instead of the pilot limit.")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--retry-errors-only",
        action="store_true",
        help="Preserve existing OK records and reprocess only pages whose previous visual-text record has status=error.",
    )
    parser.add_argument(
        "--fishnet",
        action="store_true",
        help="Enable default safety layers for failed pages: rescue_768:768:1200,rescue_512:512:1200.",
    )
    parser.add_argument(
        "--safety-layers",
        default="",
        help=(
            "Custom comma-separated fallback layers. Format: "
            "name:max_image_edge:timeout_seconds[:temperature][:ocr_max_chars][:ocr|noocr]. "
            "Example: rescue_768:768:1200,rescue_512:512:1200."
        ),
    )
    parser.add_argument("--timeout-seconds", type=int, default=240)
    parser.add_argument("--max-image-edge", type=int, default=2200)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument(
        "--prompt-version",
        choices=("visual_text_v1", "visual_text_v2", "visual_text_v2_1", "visual_text_v2_2", "v1", "v2", "v2_1", "v2_2"),
        default=DEFAULT_PROMPT_VERSION,
        help="Prompt/output format version. visual_text_v2_2 is the current strict OCR-assisted visual extraction prompt.",
    )
    parser.add_argument("--no-ocr-assist", action="store_true", help="Do not include existing OCR text in the visual model prompt.")
    parser.add_argument("--ocr-max-chars", type=int, default=DEFAULT_OCR_MAX_CHARS, help="Maximum OCR characters included in the v2 prompt.")
    parser.add_argument("--no-graph-overlay", action="store_true")
    parser.add_argument("--quiet", action="store_true", help="Disable per-page progress output.")
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=1,
        help="Write partial JSONL/corpus/graph outputs after every N completed pages. Use 0 to disable checkpoint writes.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.list_ollama_models:
        try:
            names = list_ollama_model_names(args.ollama_base_url)
            selected = select_ollama_vision_model(names)
        except Exception as exc:  # noqa: BLE001
            print(f"Could not list Ollama models at {args.ollama_base_url}: {exc}")
            return 1
        print("Installed Ollama models:")
        for name in names:
            marker = "  *" if name == selected else "   "
            print(f"{marker} {name}")
        print(f"Auto-selected vision model: {selected or 'none'}")
        return 0 if selected else 1

    paths = VisualTextPaths(page_cards_path=args.page_cards, page_index_path=args.page_index, output_dir=args.output_dir)
    max_pages = None if args.all_pages else args.max_pages
    safety_layers = parse_visual_text_safety_layers(args.safety_layers) if args.safety_layers else (default_visual_text_safety_layers() if args.fishnet else ())
    options = ExtractionOptions(
        provider=args.provider,
        model=args.model,
        ollama_base_url=args.ollama_base_url,
        page_ids=tuple(args.page_id or ()),
        page_roles=_split_csv(args.page_roles),
        image_classes=_split_csv(args.image_classes),
        include_blank=args.include_blank,
        max_pages=max_pages,
        overwrite=args.overwrite,
        timeout_seconds=args.timeout_seconds,
        max_image_edge=args.max_image_edge,
        temperature=args.temperature,
        prompt_version=args.prompt_version,
        ocr_assist=not args.no_ocr_assist,
        ocr_max_chars=args.ocr_max_chars,
        write_graph_overlay=not args.no_graph_overlay,
        progress=not args.quiet,
        checkpoint_every=args.checkpoint_every,
        retry_error_pages_only=args.retry_errors_only,
        safety_layers=safety_layers,
    )
    result = run_visual_text_extraction(paths, options)
    print("Visual text extraction")
    print(f"  Status: {result.status}")
    print(f"  Provider: {result.summary.get('provider')}")
    print(f"  Model: {result.summary.get('model')}")
    print(f"  Output dir: {paths.output_dir}")
    print("  Summary:")
    for key in (
        "total_page_cards",
        "selected_pages",
        "records",
        "ok_records",
        "planned_records",
        "error_records",
        "skipped_missing_image_records",
        "skipped_blank_records",
        "pages_with_visual_text",
        "visual_text_char_total",
        "visual_text_avg_chars",
        "prompt_version",
        "ocr_assist_enabled",
        "fishnet_safety_layers_enabled",
        "fishnet_safety_layer_count",
        "fishnet_rescued_records",
        "fishnet_failed_records",
        "fishnet_attempt_total",
        "fishnet_layer_counts",
        "visual_text_v2_records",
        "visual_text_required_sections_records",
        "visual_text_transcribed_records",
        "visual_text_table_row_records",
        "visual_text_label_callout_records",
        "visual_text_part_number_records",
        "visual_text_ocr_context_note_records",
        "visual_text_metadata_leakage_records",
        "visual_text_summary_heavy_records",
        "visual_text_hallucination_risk_records",
        "graph_overlay_nodes",
        "graph_overlay_edges",
    ):
        print(f"    {key}: {result.summary.get(key)}")
    if result.summary.get("status_counts"):
        print("  Status counts:")
        for key, value in result.summary["status_counts"].items():
            print(f"    {key}: {value}")
    samples = [r for r in result.records if r.get("status") in {"ok", "planned"}][:5]
    if samples:
        print("  Sample records:")
        for record in samples:
            print(f"    {record.get('page_id')} | {record.get('status')} | chars={record.get('char_count', 0)}")
    if result.warnings:
        print("  Warnings:")
        for warning in result.warnings[:10]:
            print(f"    {warning}")
    print("\nFiles written:")
    print(f"  records: {paths.records_path}")
    print(f"  summary: {paths.summary_path}")
    print(f"  corpus_md: {paths.corpus_md_path}")
    if options.write_graph_overlay:
        print(f"  graph_nodes: {paths.graph_nodes_path}")
        print(f"  graph_edges: {paths.graph_edges_path}")
    return 0 if result.status == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
