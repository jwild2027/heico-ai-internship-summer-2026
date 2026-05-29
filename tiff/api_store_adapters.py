"""Adapter-backed services for the TIFF FastAPI boundary.

This module keeps the public API independent of the current local storage
layout.  Today the adapters read local JSON artifacts and call the existing
RAG/trace scripts.  Later the same adapter methods can be backed by
PostgreSQL, OpenSearch, Qdrant, and real ResCarta source resolution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Iterable, Mapping, MutableMapping, Protocol


DEFAULT_EXPORT_DIR = Path("local_data/organization/export")
DEFAULT_GRAPH_DIR = Path("local_data/organization/graph")
DEFAULT_FEEDBACK_DIR = Path("local_data/feedback")
DEFAULT_CONFIG_PATH = Path("local_config.yaml")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(payload), sort_keys=True) + "\n")


def _norm_key(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def _flatten_items(data: Any) -> list[dict[str, Any]]:
    """Return a best-effort flat list of object dictionaries from a JSON tree."""
    out: list[dict[str, Any]] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            # Treat leaf-ish dictionaries as candidate records, then recurse.
            if any(k in obj for k in ("page_id", "part_number", "part", "ata_code", "source_url", "pages")):
                out.append(obj)
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)

    walk(data)
    return out


def _first(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _count_pages(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        if "count" in value and isinstance(value["count"], int):
            return value["count"]
        return len(value)
    return None


def _run_command(args: list[str], timeout: int = 120) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            args,
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        elapsed = time.perf_counter() - start
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "elapsed_seconds": round(elapsed, 3),
            "command": args,
        }
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - start
        return {
            "returncode": 124,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or f"Command timed out after {timeout}s",
            "elapsed_seconds": round(elapsed, 3),
            "command": args,
            "timeout": True,
        }


class CatalogStore(Protocol):
    def summary(self) -> dict[str, Any]: ...
    def get_part(self, part_number: str) -> dict[str, Any]: ...
    def get_page(self, page_id: str) -> dict[str, Any]: ...
    def get_ata(self, ata_code: str, limit: int = 25) -> dict[str, Any]: ...


class TraceStore(Protocol):
    def trace_part(self, part_number: str, limit: int = 8) -> dict[str, Any]: ...
    def trace_page(self, page_id: str) -> dict[str, Any]: ...
    def trace_vector(self, page_id: str, chunk_id: str | None = None, score: float | None = None) -> dict[str, Any]: ...


class AnswerStore(Protocol):
    def ask(self, question: str, timeout_seconds: int = 120) -> dict[str, Any]: ...


class FeedbackStore(Protocol):
    def save_feedback(self, feedback: Mapping[str, Any]) -> dict[str, Any]: ...
    def summary(self) -> dict[str, Any]: ...


class QualityStore(Protocol):
    def status(self) -> dict[str, Any]: ...


@dataclass(slots=True)
class LocalCatalogStore:
    export_dir: Path = DEFAULT_EXPORT_DIR

    def _load_summary(self) -> dict[str, Any]:
        return _read_json(self.export_dir / "organization_summary.json", {}) or {}

    def _load_part_tree(self) -> Any:
        return _read_json(self.export_dir / "part_tree.json", {})

    def _load_page_index(self) -> Any:
        return _read_json(self.export_dir / "page_index.json", {})

    def _load_ata_tree(self) -> Any:
        return _read_json(self.export_dir / "ata_tree.json", {})

    def summary(self) -> dict[str, Any]:
        summary = self._load_summary()
        return {
            "ok": bool(summary),
            "export_dir": str(self.export_dir),
            "summary": summary,
        }

    def get_part(self, part_number: str) -> dict[str, Any]:
        target_norm = _norm_key(part_number)
        data = self._load_part_tree()
        candidates = _flatten_items(data)

        # Support map-style part_tree payloads where the key is the part id/number.
        if isinstance(data, dict):
            for key, value in data.items():
                if _norm_key(key) == target_norm:
                    if isinstance(value, dict):
                        candidates.insert(0, {"part_number": key, **value})
                    else:
                        candidates.insert(0, {"part_number": key, "value": value})

        for item in candidates:
            number = _first(item.get("part_number"), item.get("part"), item.get("number"), item.get("id"))
            if _norm_key(str(number)) == target_norm:
                pages = _first(item.get("pages"), item.get("page_ids"), item.get("source_pages"), item.get("appearances"))
                return {
                    "found": True,
                    "part_number": str(number),
                    "nomenclature": _first(item.get("nomenclature"), item.get("name"), item.get("title")),
                    "pages_count": _count_pages(pages),
                    "pages": pages if isinstance(pages, list) else None,
                    "record": item,
                }
        return {"found": False, "part_number": part_number, "record": None}

    def get_page(self, page_id: str) -> dict[str, Any]:
        target_norm = _norm_key(page_id)
        data = self._load_page_index()
        candidates = _flatten_items(data)
        if isinstance(data, dict):
            for key, value in data.items():
                if _norm_key(key) == target_norm:
                    if isinstance(value, dict):
                        candidates.insert(0, {"page_id": key, **value})
                    else:
                        candidates.insert(0, {"page_id": key, "value": value})

        for item in candidates:
            pid = _first(item.get("page_id"), item.get("id"))
            if _norm_key(str(pid)) == target_norm:
                source_url = _first(item.get("source_url"), item.get("rescarta_url"), item.get("url"))
                tiff_path = _first(item.get("source_image_path"), item.get("tiff_path"), item.get("tiff"))
                ocr_path = _first(item.get("ocr_text_path"), item.get("ocr_path"), item.get("ocr"))
                return {
                    "found": True,
                    "page_id": str(pid),
                    "label": _first(item.get("page_label"), item.get("label"), item.get("page")),
                    "ata_code": _first(item.get("ata_code"), item.get("ata")),
                    "document": _first(item.get("manual"), item.get("document"), item.get("document_title")),
                    "source_link_present": bool(source_url or tiff_path or ocr_path),
                    "source_url": source_url,
                    "tiff_path": tiff_path,
                    "ocr_path": ocr_path,
                    "record": item,
                }
        return {"found": False, "page_id": page_id, "record": None}

    def get_ata(self, ata_code: str, limit: int = 25) -> dict[str, Any]:
        target_norm = _norm_key(ata_code)
        data = self._load_ata_tree()
        matches: list[dict[str, Any]] = []
        candidates = _flatten_items(data)
        if isinstance(data, dict):
            for key, value in data.items():
                if _norm_key(key) == target_norm:
                    if isinstance(value, dict):
                        candidates.insert(0, {"ata_code": key, **value})
                    else:
                        candidates.insert(0, {"ata_code": key, "value": value})
        for item in candidates:
            code = _first(item.get("ata_code"), item.get("ata"), item.get("code"), item.get("id"))
            if _norm_key(str(code)) == target_norm:
                matches.append(item)
        return {"found": bool(matches), "ata_code": ata_code, "count": len(matches), "items": matches[:limit]}


@dataclass(slots=True)
class LocalTraceStore:
    graph_dir: Path = DEFAULT_GRAPH_DIR

    def _read_trace_report(self) -> dict[str, Any]:
        return _read_json(self.graph_dir / "traceability_report.json", {}) or {}

    def trace_part(self, part_number: str, limit: int = 8) -> dict[str, Any]:
        args = [sys.executable, "scripts/trace_document_graph.py", "--part", part_number, "--limit", str(limit), "--strict", "--write-json"]
        result = _run_command(args)
        report = self._read_trace_report()
        return {"ok": result["returncode"] == 0, "trace": report, "command_result": result}

    def trace_page(self, page_id: str) -> dict[str, Any]:
        args = [sys.executable, "scripts/trace_document_graph.py", "--page", page_id, "--strict", "--write-json"]
        result = _run_command(args)
        report = self._read_trace_report()
        return {"ok": result["returncode"] == 0, "trace": report, "command_result": result}

    def trace_vector(self, page_id: str, chunk_id: str | None = None, score: float | None = None) -> dict[str, Any]:
        args = [sys.executable, "scripts/trace_document_graph.py", "--vector-page", page_id, "--strict", "--write-json"]
        if chunk_id:
            args.extend(["--vector-chunk", chunk_id])
        if score is not None:
            args.extend(["--vector-score", str(score)])
        result = _run_command(args)
        report = self._read_trace_report()
        return {"ok": result["returncode"] == 0, "trace": report, "command_result": result}


@dataclass(slots=True)
class LocalAnswerStore:
    config_path: Path = DEFAULT_CONFIG_PATH

    def ask(self, question: str, timeout_seconds: int = 120) -> dict[str, Any]:
        args = [sys.executable, "scripts/ask_tiff_rag.py", "--config", str(self.config_path), question]
        result = _run_command(args, timeout=timeout_seconds)
        stdout = result.get("stdout", "")
        llm_used = "LLM used: True" in stdout
        embeddings_used = "Embeddings used: True" in stdout
        return {
            "ok": result["returncode"] == 0,
            "question": question,
            "answer_text": stdout,
            "llm_used": llm_used,
            "embeddings_used": embeddings_used,
            "command_result": result,
        }


@dataclass(slots=True)
class LocalFeedbackStore:
    feedback_dir: Path = DEFAULT_FEEDBACK_DIR
    feedback_file_name: str = "api_user_feedback.jsonl"
    summary_file_name: str = "api_user_feedback_summary.json"

    @property
    def feedback_path(self) -> Path:
        return self.feedback_dir / self.feedback_file_name

    @property
    def summary_path(self) -> Path:
        return self.feedback_dir / self.summary_file_name

    def save_feedback(self, feedback: Mapping[str, Any]) -> dict[str, Any]:
        record = dict(feedback)
        record.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        record.setdefault("feedback_id", f"fb_{int(time.time() * 1000)}")
        _append_jsonl(self.feedback_path, record)
        summary = self.summary()
        return {"ok": True, "record": record, "summary": summary}

    def _records(self) -> list[dict[str, Any]]:
        if not self.feedback_path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in self.feedback_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records

    def summary(self) -> dict[str, Any]:
        records = self._records()
        by_rating: dict[str, int] = {}
        by_category: dict[str, int] = {}
        for record in records:
            rating = str(record.get("rating") or "unknown")
            category = str(record.get("category") or "unknown")
            by_rating[rating] = by_rating.get(rating, 0) + 1
            by_category[category] = by_category.get(category, 0) + 1
        summary = {
            "ok": True,
            "feedback_path": str(self.feedback_path),
            "total": len(records),
            "by_rating": by_rating,
            "by_category": by_category,
            "recent": records[-10:],
        }
        _write_json(self.summary_path, summary)
        return summary


@dataclass(slots=True)
class LocalQualityStore:
    quality_path: Path = Path("local_data/pipeline_runs/latest_quality_gate.json")
    manifest_path: Path = Path("local_data/pipeline_runs/latest_backend_pipeline.json")
    graph_quality_path: Path = Path("local_data/organization/graph/graph_quality.json")
    api_adapter_quality_path: Path = Path("local_data/api/api_adapter_quality.json")

    def status(self) -> dict[str, Any]:
        quality = _read_json(self.quality_path, {}) or {}
        manifest = _read_json(self.manifest_path, {}) or {}
        graph_quality = _read_json(self.graph_quality_path, {}) or {}
        api_adapter_quality = _read_json(self.api_adapter_quality_path, {}) or {}
        status = _first(
            quality.get("status"),
            quality.get("summary", {}).get("status") if isinstance(quality.get("summary"), dict) else None,
            manifest.get("status"),
            "unknown",
        )
        return {
            "ok": str(status).lower() in {"ok", "pass", "passed"},
            "status": status,
            "quality": quality,
            "manifest": manifest,
            "graph_quality": graph_quality,
            "api_adapter_quality": api_adapter_quality,
        }


@dataclass(slots=True)
class ApiStores:
    catalog: CatalogStore = field(default_factory=LocalCatalogStore)
    trace: TraceStore = field(default_factory=LocalTraceStore)
    answer: AnswerStore = field(default_factory=LocalAnswerStore)
    feedback: FeedbackStore = field(default_factory=LocalFeedbackStore)
    quality: QualityStore = field(default_factory=LocalQualityStore)


def build_local_api_stores(config_path: str | Path = DEFAULT_CONFIG_PATH) -> ApiStores:
    return ApiStores(answer=LocalAnswerStore(Path(config_path)))
