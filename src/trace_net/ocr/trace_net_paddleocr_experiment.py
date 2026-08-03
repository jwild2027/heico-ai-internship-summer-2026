"""TRACE-Net PaddleOCR table-tile experiment.

This module is intentionally an experiment layer. It reads table tile images created by
TRACE-Net's table crop/tile executor and runs a table/OCR backend over those tiles.
The default backends are safe:

* planned: create planned records without importing PaddleOCR.
* mock: deterministic local fake extraction for tests/smoke checks.
* paddleocr: use PaddleOCR PP-StructureV3 if installed.
* auto: use PaddleOCR if import succeeds, otherwise planned.

The produced artifacts are separate from the core graph/RAG artifacts until a quality
review decides whether the output is useful.
"""

from __future__ import annotations

import argparse
import html
import importlib
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

PART_NUMBER_RE = re.compile(
    r"\b(?:[A-Z]{1,4}\d{2,}|\d{2,4})(?:[-./]?[A-Z0-9]{2,}){1,6}\b",
    re.IGNORECASE,
)

DEFAULT_TILE_PLAN = Path("local_data/organization/table_extraction/table_tile_plan.jsonl")
DEFAULT_OUTPUT_DIR = Path("local_data/organization/table_extraction/paddleocr_experiment")


@dataclass(frozen=True)
class PaddleOcrExperimentPaths:
    tile_plan_path: Path = DEFAULT_TILE_PLAN
    output_dir: Path = DEFAULT_OUTPUT_DIR

    @property
    def records_path(self) -> Path:
        return self.output_dir / "paddleocr_tile_text_records.jsonl"

    @property
    def summary_path(self) -> Path:
        return self.output_dir / "paddleocr_tile_text_summary.json"

    @property
    def corpus_md_path(self) -> Path:
        return self.output_dir / "paddleocr_tile_text_corpus.md"

    @property
    def review_html_path(self) -> Path:
        return self.output_dir / "paddleocr_tile_text_review.html"

    @property
    def graph_nodes_path(self) -> Path:
        return self.output_dir / "paddleocr_tile_text_graph_nodes.json"

    @property
    def graph_edges_path(self) -> Path:
        return self.output_dir / "paddleocr_tile_text_graph_edges.json"

    @property
    def quality_path(self) -> Path:
        return self.output_dir / "paddleocr_tile_text_quality.json"


@dataclass(frozen=True)
class PaddleOcrExperimentOptions:
    provider: str = "planned"  # planned | mock | paddleocr | auto
    model_name: str = "PP-StructureV3"
    device: str | None = None
    lang: str = "en"
    max_tiles: int | None = None
    max_pages: int | None = None
    page_id: str | None = None
    include_markdown: bool = True
    overwrite: bool = True
    use_table_recognition: bool = True
    use_formula_recognition: bool = False
    use_chart_recognition: bool = False
    use_doc_orientation_classify: bool = False
    use_doc_unwarping: bool = False
    use_textline_orientation: bool = False


class PaddleOcrUnavailable(RuntimeError):
    pass


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                records.append(value)
    return records


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(dict(rec), sort_keys=True) + "\n")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:
        return ""


def _path_from_any(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value)
    if not s:
        return None
    return s


def _extract_page_id(record: Mapping[str, Any]) -> str:
    for key in ("page_id", "entity_id", "id"):
        value = record.get(key)
        if isinstance(value, str) and value:
            if value.startswith("page:"):
                return value.split(":", 1)[1]
            return value
    return "unknown_page"


def _extract_tile_paths_from_record(record: Mapping[str, Any], tile_plan_path: Path) -> list[dict[str, Any]]:
    page_id = _extract_page_id(record)
    tiles: list[dict[str, Any]] = []

    raw_tiles = record.get("tiles") or record.get("tile_images") or record.get("tile_records")
    if isinstance(raw_tiles, list):
        for i, item in enumerate(raw_tiles, 1):
            if isinstance(item, str):
                tile_path = item
                tile_id = f"tile_{i:03d}"
            elif isinstance(item, Mapping):
                tile_path = (
                    _path_from_any(item.get("tile_path"))
                    or _path_from_any(item.get("path"))
                    or _path_from_any(item.get("image_path"))
                    or _path_from_any(item.get("output_path"))
                )
                tile_id = _safe_str(item.get("tile_id") or item.get("id") or f"tile_{i:03d}")
            else:
                continue
            if tile_path:
                tiles.append({"page_id": page_id, "tile_id": tile_id, "tile_index": i, "tile_path": tile_path})

    # Fallback to the directory convention used by the TRACE-Net table tile executor.
    if not tiles:
        # .../table_extraction/table_tile_plan.jsonl -> .../table_extraction/tiles/<page_id>/tile_*.png
        table_root = tile_plan_path.parent
        tile_dir = table_root / "tiles" / page_id
        if tile_dir.exists():
            for i, path in enumerate(sorted(tile_dir.glob("tile_*.png")), 1):
                tiles.append(
                    {
                        "page_id": page_id,
                        "tile_id": path.stem,
                        "tile_index": i,
                        "tile_path": str(path),
                    }
                )

    # Also tolerate older records that carry one tile path per JSONL line.
    if not tiles:
        tile_path = (
            _path_from_any(record.get("tile_path"))
            or _path_from_any(record.get("image_path"))
            or _path_from_any(record.get("path"))
        )
        if tile_path:
            tiles.append({"page_id": page_id, "tile_id": "tile_001", "tile_index": 1, "tile_path": tile_path})

    return tiles


def load_tile_jobs(tile_plan_path: Path, *, max_pages: int | None = None, max_tiles: int | None = None, page_id: str | None = None) -> list[dict[str, Any]]:
    plan_records = _read_jsonl(tile_plan_path)
    jobs: list[dict[str, Any]] = []
    selected_pages: set[str] = set()
    for rec in plan_records:
        status = str(rec.get("status", "ok")).lower()
        if status not in {"ok", "planned", "candidate"}:
            continue
        pid = _extract_page_id(rec)
        if page_id and pid != page_id:
            continue
        if max_pages is not None and pid not in selected_pages and len(selected_pages) >= max_pages:
            continue
        selected_pages.add(pid)
        base = {
            "page_id": pid,
            "page_route": rec.get("route") or rec.get("repair_route") or rec.get("table_route"),
            "source_record_status": rec.get("status"),
        }
        for tile in _extract_tile_paths_from_record(rec, tile_plan_path):
            job = dict(base)
            job.update(tile)
            jobs.append(job)
            if max_tiles is not None and len(jobs) >= max_tiles:
                return jobs
    return jobs


def extract_part_numbers(text: str) -> list[str]:
    found = []
    seen = set()
    for match in PART_NUMBER_RE.findall(text or ""):
        normalized = match.strip().upper()
        if len(normalized) < 5:
            continue
        if normalized not in seen:
            seen.add(normalized)
            found.append(normalized)
    return found


def _recursive_collect(value: Any, *, key_path: str = "") -> dict[str, Any]:
    """Collect useful text/table pieces from arbitrary PaddleOCR result objects."""
    out = {
        "plain_texts": [],
        "markdown_texts": [],
        "html_tables": [],
        "cell_texts": [],
        "raw_keys": set(),
    }

    def visit(v: Any, path: str) -> None:
        if isinstance(v, Mapping):
            for k, child in v.items():
                k_str = str(k)
                out["raw_keys"].add(k_str)
                child_path = f"{path}.{k_str}" if path else k_str
                if k_str in {"pred_html", "html", "table_html"} and isinstance(child, str):
                    out["html_tables"].append(child)
                elif k_str in {"block_content", "text", "rec_text", "markdown_texts", "markdown", "content"} and isinstance(child, str):
                    if k_str.startswith("markdown"):
                        out["markdown_texts"].append(child)
                    else:
                        out["plain_texts"].append(child)
                elif k_str == "rec_texts" and isinstance(child, list):
                    for item in child:
                        s = _safe_str(item).strip()
                        if s:
                            out["cell_texts"].append(s)
                            out["plain_texts"].append(s)
                else:
                    visit(child, child_path)
        elif isinstance(v, list):
            for i, item in enumerate(v):
                visit(item, f"{path}[{i}]")
        elif isinstance(v, tuple):
            for i, item in enumerate(v):
                visit(item, f"{path}[{i}]")
        elif isinstance(v, str):
            # Avoid dumping giant repr strings from arbitrary objects; only use strings from known-ish paths.
            lower_path = path.lower()
            if any(token in lower_path for token in ("text", "content", "html", "markdown", "rec")):
                out["plain_texts"].append(v)

    visit(value, key_path)
    out["raw_keys"] = sorted(out["raw_keys"])
    return out


def _object_to_struct(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Mapping):
        return {str(k): _object_to_struct(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_object_to_struct(v) for v in value]
    for attr in ("json", "markdown"):
        if hasattr(value, attr):
            try:
                return {attr: _object_to_struct(getattr(value, attr))}
            except Exception:
                pass
    if hasattr(value, "to_dict"):
        try:
            return _object_to_struct(value.to_dict())
        except Exception:
            pass
    return _safe_str(value)


class PlannedPaddleProvider:
    provider_name = "planned"
    model_name = "none"

    def run_tile(self, tile_path: Path) -> dict[str, Any]:
        return {
            "status": "planned",
            "plain_text": "PaddleOCR PP-StructureV3 experiment planned; no OCR backend was run.",
            "markdown": "",
            "html_tables": [],
            "cell_texts": [],
            "raw_result_keys": [],
        }


class MockPaddleProvider:
    provider_name = "mock"
    model_name = "mock-pp-structurev3"

    def run_tile(self, tile_path: Path) -> dict[str, Any]:
        stem = tile_path.stem
        page = tile_path.parent.name if tile_path.parent else "unknown"
        text = f"Mock PaddleOCR table tile text for {page} {stem}. Part 120-00000-001 QTY 1."
        return {
            "status": "ok",
            "plain_text": text,
            "markdown": f"| page | tile | part | qty |\n|---|---|---|---|\n| {page} | {stem} | 120-00000-001 | 1 |",
            "html_tables": ["<table><tr><td>120-00000-001</td><td>1</td></tr></table>"],
            "cell_texts": ["120-00000-001", "1"],
            "raw_result_keys": ["mock"],
        }


class PaddleOcrProvider:
    provider_name = "paddleocr"

    def __init__(self, options: PaddleOcrExperimentOptions):
        module = importlib.import_module("paddleocr")
        cls = getattr(module, "PPStructureV3", None)
        if cls is None:
            raise PaddleOcrUnavailable("paddleocr.PPStructureV3 is not available. Install PaddleOCR 3.x with document parsing support.")
        kwargs: dict[str, Any] = {
            "lang": options.lang,
            "use_table_recognition": options.use_table_recognition,
            "use_formula_recognition": options.use_formula_recognition,
            "use_chart_recognition": options.use_chart_recognition,
            "use_doc_orientation_classify": options.use_doc_orientation_classify,
            "use_doc_unwarping": options.use_doc_unwarping,
            "use_textline_orientation": options.use_textline_orientation,
        }
        if options.device:
            kwargs["device"] = options.device
        # Some versions may not accept every keyword. Retry with a minimal init if needed.
        try:
            self.pipeline = cls(**kwargs)
        except TypeError:
            minimal = {"lang": options.lang}
            if options.device:
                minimal["device"] = options.device
            self.pipeline = cls(**minimal)
        self.model_name = options.model_name

    def run_tile(self, tile_path: Path) -> dict[str, Any]:
        output = self.pipeline.predict(str(tile_path))
        results = []
        for res in output:
            results.append(_object_to_struct(res))
        collected = _recursive_collect(results)
        plain_texts = [s.strip() for s in collected["plain_texts"] if _safe_str(s).strip()]
        markdown_texts = [s.strip() for s in collected["markdown_texts"] if _safe_str(s).strip()]
        html_tables = [s.strip() for s in collected["html_tables"] if _safe_str(s).strip()]
        cell_texts = [s.strip() for s in collected["cell_texts"] if _safe_str(s).strip()]
        plain_text = "\n".join(dict.fromkeys(plain_texts))
        markdown = "\n\n".join(dict.fromkeys(markdown_texts))
        return {
            "status": "ok" if (plain_text or markdown or html_tables or cell_texts) else "empty",
            "plain_text": plain_text,
            "markdown": markdown,
            "html_tables": html_tables,
            "cell_texts": list(dict.fromkeys(cell_texts)),
            "raw_result_keys": collected["raw_keys"],
        }


def _make_provider(options: PaddleOcrExperimentOptions) -> Any:
    provider = options.provider.lower()
    if provider == "planned":
        return PlannedPaddleProvider()
    if provider == "mock":
        return MockPaddleProvider()
    if provider == "paddleocr":
        return PaddleOcrProvider(options)
    if provider == "auto":
        try:
            return PaddleOcrProvider(options)
        except Exception:
            return PlannedPaddleProvider()
    raise ValueError(f"Unsupported provider: {options.provider}")


def _record_from_tile(job: Mapping[str, Any], provider: Any, options: PaddleOcrExperimentOptions) -> dict[str, Any]:
    tile_path = Path(_safe_str(job.get("tile_path")))
    started = time.perf_counter()
    base = {
        "page_id": job.get("page_id"),
        "tile_id": job.get("tile_id"),
        "tile_index": job.get("tile_index"),
        "tile_path": str(tile_path),
        "page_route": job.get("page_route"),
        "provider": provider.provider_name,
        "model": getattr(provider, "model_name", options.model_name),
    }
    if not tile_path.exists():
        return {
            **base,
            "status": "error",
            "error": f"Tile image does not exist: {tile_path}",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "plain_text": "",
            "markdown": "",
            "html_tables": [],
            "cell_texts": [],
            "part_numbers": [],
        }
    try:
        result = provider.run_tile(tile_path)
        text_blob = "\n".join(
            [
                _safe_str(result.get("plain_text")),
                _safe_str(result.get("markdown")),
                "\n".join(_safe_str(v) for v in _as_list(result.get("cell_texts"))),
                "\n".join(_safe_str(v) for v in _as_list(result.get("html_tables"))),
            ]
        )
        return {
            **base,
            **result,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "part_numbers": extract_part_numbers(text_blob),
            "plain_text_chars": len(_safe_str(result.get("plain_text"))),
            "markdown_chars": len(_safe_str(result.get("markdown"))),
            "html_table_count": len(_as_list(result.get("html_tables"))),
            "cell_text_count": len(_as_list(result.get("cell_texts"))),
        }
    except Exception as exc:
        return {
            **base,
            "status": "error",
            "error": str(exc),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "plain_text": "",
            "markdown": "",
            "html_tables": [],
            "cell_texts": [],
            "part_numbers": [],
            "plain_text_chars": 0,
            "markdown_chars": 0,
            "html_table_count": 0,
            "cell_text_count": 0,
        }


def summarize_records(records: Sequence[Mapping[str, Any]], *, provider: str, model: str) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    pages = set()
    tile_text_char_total = 0
    part_number_records = 0
    html_table_records = 0
    cell_text_records = 0
    for rec in records:
        status = str(rec.get("status", "unknown")).lower()
        status_counts[status] = status_counts.get(status, 0) + 1
        if rec.get("page_id"):
            pages.add(str(rec.get("page_id")))
        tile_text_char_total += len(_safe_str(rec.get("plain_text"))) + len(_safe_str(rec.get("markdown")))
        if rec.get("part_numbers"):
            part_number_records += 1
        if rec.get("html_tables"):
            html_table_records += 1
        if rec.get("cell_texts"):
            cell_text_records += 1
    ok = status_counts.get("ok", 0)
    planned = status_counts.get("planned", 0)
    empty = status_counts.get("empty", 0)
    error = status_counts.get("error", 0)
    if error and ok:
        status = "PARTIAL"
    elif error and not ok and not planned:
        status = "FAIL"
    else:
        status = "OK"
    return {
        "status": status,
        "provider": provider,
        "model": model,
        "records": len(records),
        "pages": len(pages),
        "ok_records": ok,
        "planned_records": planned,
        "empty_records": empty,
        "error_records": error,
        "status_counts": status_counts,
        "tile_text_char_total": tile_text_char_total,
        "tile_text_avg_chars": round(tile_text_char_total / max(1, ok + empty + planned), 2),
        "part_number_records": part_number_records,
        "html_table_records": html_table_records,
        "cell_text_records": cell_text_records,
    }


def build_graph_overlay(records: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = [
        {"id": "paddleocr_table_tile_experiment", "type": "evidence_source", "label": "PaddleOCR Table Tile Experiment"}
    ]
    edges: list[dict[str, Any]] = []
    for rec in records:
        page_id = _safe_str(rec.get("page_id"))
        tile_id = _safe_str(rec.get("tile_id")) or "tile"
        context_id = f"paddleocr_tile_text:{page_id}:{tile_id}"
        nodes.append(
            {
                "id": context_id,
                "type": "table_tile_text_context",
                "page_id": page_id,
                "tile_id": tile_id,
                "status": rec.get("status"),
                "provider": rec.get("provider"),
                "part_numbers": rec.get("part_numbers", []),
            }
        )
        if page_id:
            edges.append({"source": f"page:{page_id}", "target": context_id, "type": "HAS_TABLE_TILE_TEXT"})
        edges.append({"source": context_id, "target": "paddleocr_table_tile_experiment", "type": "DERIVED_FROM"})
        for pn in _as_list(rec.get("part_numbers")):
            part_node = f"part_candidate:{str(pn).upper()}"
            nodes.append({"id": part_node, "type": "part_candidate", "part_number": str(pn).upper()})
            edges.append({"source": context_id, "target": part_node, "type": "MENTIONS_PART_CANDIDATE"})
    # Deduplicate nodes by id.
    dedup: dict[str, dict[str, Any]] = {}
    for node in nodes:
        dedup[str(node.get("id"))] = node
    return list(dedup.values()), edges


def write_corpus(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    lines = ["# PaddleOCR Table Tile Text Corpus", ""]
    for rec in records:
        lines.append(f"## {rec.get('page_id')} / {rec.get('tile_id')}")
        lines.append("")
        lines.append(f"Status: `{rec.get('status')}`  ")
        lines.append(f"Tile: `{rec.get('tile_path')}`  ")
        if rec.get("part_numbers"):
            lines.append(f"Part numbers: {', '.join(_as_list(rec.get('part_numbers')))}")
        if rec.get("plain_text"):
            lines.append("\n### Plain text\n")
            lines.append(_safe_str(rec.get("plain_text")))
        if rec.get("markdown"):
            lines.append("\n### Markdown\n")
            lines.append(_safe_str(rec.get("markdown")))
        if rec.get("html_tables"):
            lines.append("\n### HTML tables\n")
            for html_text in _as_list(rec.get("html_tables")):
                lines.append("```html")
                lines.append(_safe_str(html_text))
                lines.append("```")
        if rec.get("error"):
            lines.append(f"\nError: `{rec.get('error')}`")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_review_html(path: Path, records: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]) -> None:
    cards = []
    for rec in records:
        tile_path = _safe_str(rec.get("tile_path"))
        image_src = html.escape(tile_path.replace("\\", "/"))
        plain = html.escape(_safe_str(rec.get("plain_text"))[:3000])
        markdown = html.escape(_safe_str(rec.get("markdown"))[:3000])
        parts = ", ".join(html.escape(str(p)) for p in _as_list(rec.get("part_numbers"))) or "none"
        cards.append(
            f"""
            <section class=card>
              <h2>{html.escape(_safe_str(rec.get('page_id')))} / {html.escape(_safe_str(rec.get('tile_id')))}</h2>
              <p><b>Status:</b> {html.escape(_safe_str(rec.get('status')))} &nbsp; <b>Provider:</b> {html.escape(_safe_str(rec.get('provider')))}</p>
              <p><b>Parts:</b> {parts}</p>
              <p><b>Tile:</b> <code>{html.escape(tile_path)}</code></p>
              <img src="{image_src}" loading="lazy" />
              <h3>Plain text</h3><pre>{plain}</pre>
              <h3>Markdown</h3><pre>{markdown}</pre>
            </section>
            """
        )
    body = "\n".join(cards)
    text = f"""<!doctype html>
<html><head><meta charset=utf-8><title>PaddleOCR Table Tile Review</title>
<style>
body {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 24px; background:#f6f7fb; }}
.summary, .card {{ background: white; border: 1px solid #ddd; border-radius: 12px; padding: 16px; margin: 16px 0; }}
img {{ max-width: 100%; border: 1px solid #ccc; background: white; }}
pre {{ white-space: pre-wrap; background: #f0f2f5; padding: 12px; border-radius: 8px; overflow-x: auto; }}
code {{ background: #eef; padding: 2px 4px; border-radius: 4px; }}
</style></head><body>
<h1>TRACE-Net PaddleOCR Table Tile Experiment</h1>
<div class=summary><pre>{html.escape(json.dumps(dict(summary), indent=2))}</pre></div>
{body}
</body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_paddleocr_table_experiment(paths: PaddleOcrExperimentPaths, options: PaddleOcrExperimentOptions) -> dict[str, Any]:
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    jobs = load_tile_jobs(
        paths.tile_plan_path,
        max_pages=options.max_pages,
        max_tiles=options.max_tiles,
        page_id=options.page_id,
    )
    provider = _make_provider(options)
    records = [_record_from_tile(job, provider, options) for job in jobs]
    summary = summarize_records(records, provider=provider.provider_name, model=getattr(provider, "model_name", options.model_name))
    summary.update(
        {
            "tile_plan_path": str(paths.tile_plan_path),
            "output_dir": str(paths.output_dir),
            "jobs": len(jobs),
        }
    )
    nodes, edges = build_graph_overlay(records)
    summary["graph_nodes"] = len(nodes)
    summary["graph_edges"] = len(edges)

    _write_jsonl(paths.records_path, records)
    _write_json(paths.summary_path, summary)
    _write_json(paths.graph_nodes_path, nodes)
    _write_json(paths.graph_edges_path, edges)
    write_corpus(paths.corpus_md_path, records)
    write_review_html(paths.review_html_path, records, summary)
    return {"summary": summary, "records": records, "graph_nodes": nodes, "graph_edges": edges}


def build_quality_report(
    paths: PaddleOcrExperimentPaths,
    *,
    min_records: int = 1,
    min_ok_records: int = 0,
    max_error_records: int = 0,
    min_part_number_records: int | None = None,
    min_html_table_records: int | None = None,
    require_status_ok: bool = True,
) -> dict[str, Any]:
    summary = _as_dict(json.loads(paths.summary_path.read_text(encoding="utf-8"))) if paths.summary_path.exists() else {}
    records = _read_jsonl(paths.records_path)
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, message: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "message": message})

    add("paddleocr_artifacts_present", paths.summary_path.exists() and paths.records_path.exists(), f"summary={paths.summary_path.exists()}; records={paths.records_path.exists()}.")
    status = str(summary.get("status", "missing")).upper()
    add("paddleocr_status", (status == "OK") or not require_status_ok, f"status={status}; require_status_ok={require_status_ok}.")
    add("paddleocr_records", len(records) >= min_records, f"records jsonl={len(records)}; minimum={min_records}.")
    ok_records = int(summary.get("ok_records", 0) or 0)
    error_records = int(summary.get("error_records", 0) or 0)
    add("paddleocr_ok_records", ok_records >= min_ok_records, f"ok_records={ok_records}; minimum={min_ok_records}.")
    add("paddleocr_error_records", error_records <= max_error_records, f"error_records={error_records}; max={max_error_records}.")
    if min_part_number_records is not None:
        value = int(summary.get("part_number_records", 0) or 0)
        add("paddleocr_part_number_records", value >= min_part_number_records, f"part_number_records={value}; minimum={min_part_number_records}.")
    if min_html_table_records is not None:
        value = int(summary.get("html_table_records", 0) or 0)
        add("paddleocr_html_table_records", value >= min_html_table_records, f"html_table_records={value}; minimum={min_html_table_records}.")
    add("paddleocr_graph_nodes", int(summary.get("graph_nodes", 0) or 0) >= 1, f"graph_nodes={summary.get('graph_nodes')}.")
    add("paddleocr_graph_edges", int(summary.get("graph_edges", 0) or 0) >= 1 or len(records) == 0, f"graph_edges={summary.get('graph_edges')}.")

    ok = all(c["ok"] for c in checks)
    report_summary = {
        "paddleocr_summary_present": paths.summary_path.exists(),
        "paddleocr_records_present": paths.records_path.exists(),
        "paddleocr_status": summary.get("status"),
        "paddleocr_provider": summary.get("provider"),
        "paddleocr_model": summary.get("model"),
        "paddleocr_records": len(records),
        "paddleocr_pages": summary.get("pages"),
        "paddleocr_ok_records": ok_records,
        "paddleocr_planned_records": summary.get("planned_records"),
        "paddleocr_empty_records": summary.get("empty_records"),
        "paddleocr_error_records": error_records,
        "paddleocr_part_number_records": summary.get("part_number_records"),
        "paddleocr_html_table_records": summary.get("html_table_records"),
        "paddleocr_cell_text_records": summary.get("cell_text_records"),
        "paddleocr_text_chars": summary.get("tile_text_char_total"),
        "paddleocr_graph_nodes": summary.get("graph_nodes"),
        "paddleocr_graph_edges": summary.get("graph_edges"),
        "paddleocr_records_path": str(paths.records_path),
        "paddleocr_summary_path": str(paths.summary_path),
    }
    return {"status": "OK" if ok else "FAIL", "summary": report_summary, "checks": checks}


def _print_run_result(result: Mapping[str, Any], paths: PaddleOcrExperimentPaths) -> None:
    s = _as_dict(result.get("summary"))
    print("TRACE-Net PaddleOCR table-tile experiment")
    print(f"  Status: {s.get('status')}")
    print(f"  Provider: {s.get('provider')}")
    print(f"  Model: {s.get('model')}")
    print(f"  Output dir: {paths.output_dir}")
    print("  Summary:")
    for key in [
        "records",
        "pages",
        "ok_records",
        "planned_records",
        "empty_records",
        "error_records",
        "tile_text_char_total",
        "tile_text_avg_chars",
        "part_number_records",
        "html_table_records",
        "cell_text_records",
        "graph_nodes",
        "graph_edges",
    ]:
        print(f"    {key}: {s.get(key)}")
    print("Files written:")
    print(f"  records: {paths.records_path}")
    print(f"  summary: {paths.summary_path}")
    print(f"  corpus_md: {paths.corpus_md_path}")
    print(f"  review_html: {paths.review_html_path}")
    print(f"  graph_nodes: {paths.graph_nodes_path}")
    print(f"  graph_edges: {paths.graph_edges_path}")


def _print_quality_report(report: Mapping[str, Any], paths: PaddleOcrExperimentPaths) -> None:
    print("TRACE-Net PaddleOCR table-tile quality gate")
    print(f"  Status: {report.get('status')}")
    print("  Summary:")
    for key, value in _as_dict(report.get("summary")).items():
        print(f"    {key}: {value}")
    print("  Checks:")
    for check in _as_list(report.get("checks")):
        marker = "OK" if check.get("ok") else "FAIL"
        print(f"    {marker} {check.get('name')}: {check.get('message')}")
    print(f"\nJSON: {paths.quality_path}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a PaddleOCR PP-StructureV3 experiment on TRACE-Net table tiles.")
    parser.add_argument("--tile-plan", default=str(DEFAULT_TILE_PLAN))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--provider", choices=["planned", "mock", "paddleocr", "auto"], default="planned")
    parser.add_argument("--device", default=None)
    parser.add_argument("--lang", default="en")
    parser.add_argument("--max-tiles", type=int, default=None)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--page-id", default=None)
    parser.add_argument("--no-table-recognition", action="store_true")
    parser.add_argument("--use-formula-recognition", action="store_true")
    parser.add_argument("--use-chart-recognition", action="store_true")
    parser.add_argument("--open", action="store_true", help="Open the HTML review in the OS browser after writing it.")
    args = parser.parse_args(argv)

    paths = PaddleOcrExperimentPaths(tile_plan_path=Path(args.tile_plan), output_dir=Path(args.output_dir))
    options = PaddleOcrExperimentOptions(
        provider=args.provider,
        device=args.device,
        lang=args.lang,
        max_tiles=args.max_tiles,
        max_pages=args.max_pages,
        page_id=args.page_id,
        use_table_recognition=not args.no_table_recognition,
        use_formula_recognition=args.use_formula_recognition,
        use_chart_recognition=args.use_chart_recognition,
    )
    result = run_paddleocr_table_experiment(paths, options)
    _print_run_result(result, paths)
    if args.open:
        try:
            import webbrowser

            webbrowser.open(paths.review_html_path.resolve().as_uri())
        except Exception:
            pass
    return 0 if result["summary"].get("status") in {"OK", "PARTIAL"} else 1


def quality_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net PaddleOCR table-tile experiment quality.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-ok-records", type=int, default=0)
    parser.add_argument("--max-error-records", type=int, default=0)
    parser.add_argument("--min-part-number-records", type=int, default=None)
    parser.add_argument("--min-html-table-records", type=int, default=None)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    paths = PaddleOcrExperimentPaths(output_dir=Path(args.output_dir))
    report = build_quality_report(
        paths,
        min_records=args.min_records,
        min_ok_records=args.min_ok_records,
        max_error_records=args.max_error_records,
        min_part_number_records=args.min_part_number_records,
        min_html_table_records=args.min_html_table_records,
        require_status_ok=not args.allow_partial,
    )
    if args.write_json:
        _write_json(paths.quality_path, report)
    _print_quality_report(report, paths)
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
