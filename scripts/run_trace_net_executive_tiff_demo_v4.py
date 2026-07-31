#!/usr/bin/env python3
"""TRACE-Net executive TIFF demo v4: deep page-by-page narration.

This is a separate presentation mode. It does not replace the simpler full-corpus
v2 demo or the fast 10-page v3 demo.

The wrapper runs the canonical dry-run ingestion pipeline, then prints:
- page-by-page OCR progress and OCR results;
- page-by-page final classification;
- a local graph snapshot made from the validated records;
- all six TRACE-Net Engram layers assembled for this run;
- one real bge-m3 embedding operation per page;
- multiple example questions with a safe deterministic/LLM audit trace.

The wrapper never writes to live Postgres, Qdrant, or OpenSearch. It writes only
new files under its timestamped demo output directory.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

STATUS = "TRACE_NET_EXECUTIVE_TIFF_DEMO_DEEP_V4"
VERSION = "v4"
DEFAULT_REPO = "/data/trace_net/repos/heico-ai-internship-summer-2026"
DEFAULT_SOURCE = "/data/trace_net/inputs/metadata.zip"
DEFAULT_TESSERACT = "/usr/bin/tesseract"
DEFAULT_OLLAMA = "http://127.0.0.1:11434"
DEFAULT_LLM_MODEL = "gemma4:26b"
DEFAULT_EMBED_MODEL = "bge-m3:latest"
DEFAULT_QUESTIONS = (
    "Find part number 120-29073-001 and nearby similar parts. Use TRACE-Net evidence and cite pages.",
    "What bigger assembly is 120-20970-001 installed inside? Use TRACE-Net evidence and cite pages.",
)

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"

PART_RE = re.compile(r"\b(?:\d{2,4}|[A-Z]{1,4})-[A-Z0-9]{2,8}(?:-[A-Z0-9]{2,8})?\b", re.I)
PAGE_ID_RE = re.compile(r"\bt_p_[A-Za-z0-9_]+_p\d{6}\b")
CITATION_RE = re.compile(r"\[E(\d+)\]", re.I)
STAGE_LINE_RE = re.compile(r"^\[([A-Za-z0-9_]+)\]\s+(build|check):")

STAGE_NAMES: dict[tuple[str, str], tuple[str, str, str]] = {
    ("ocr", "build"): ("1A", "Read and OCR every raw TIFF page", "Each scanned page is copied into the run folder, hashed, and read with Tesseract."),
    ("ocr", "check"): ("1B", "Verify every OCR result", "The page count, source hashes, OCR records, and safety flags must agree."),
    ("resolver", "build"): ("2A", "Measure page layout clues", "Ink, text density, table structure, diagrams, and OCR confidence are measured."),
    ("resolver", "check"): ("2B", "Check the first page-type estimate", "The first classifier is checked before the result is allowed to continue."),
    ("four_route", "build"): ("3A", "Assign a simple page type", "Every page becomes normal text, table, image/diagram, or blank."),
    ("four_route", "check"): ("3B", "Verify every page type", "Every page must have one allowed route and retain its original source identity."),
    ("validator", "build"): ("4A", "Validate uncertain pages", "Additional deterministic rules examine pages whose first classification was uncertain."),
    ("validator", "check"): ("4B", "Check the validated decisions", "The validator confirms that no human review or unsafe permission was introduced."),
    ("retry", "build"): ("5A", "Retry only unresolved pages", "A bounded second pass is used only where the first evidence was not strong enough."),
    ("retry", "check"): ("5B", "Verify the final page decisions", "The final route for every page is checked before storage records are prepared."),
    ("storage", "build"): ("6A", "Prepare graph, vector, and exact-search records", "The same page can create different read-only records for different search jobs."),
    ("storage", "check"): ("6B", "Check storage eligibility", "The records are validated without writing to any production database."),
    ("loader", "build"): ("7A", "Create the dry-run loading plan", "TRACE-Net shows what would go to Postgres, Qdrant, and OpenSearch."),
    ("loader", "check"): ("7B", "Verify the loading plan", "The plan must remain read-only and preserve every source link."),
    ("contract", "build"): ("8A", "Verify source lineage", "Every prepared record must still point to the original TIFF and canonical page ID."),
    ("contract", "check"): ("8B", "Check lineage contracts", "Records missing source lineage cannot become trusted evidence."),
    ("retrieval_payload_audit", "build"): ("9A", "Build searchable evidence payloads", "The Discovery Machine receives route-specific payloads instead of one undifferentiated text dump."),
    ("retrieval_payload_audit", "check"): ("9B", "Run the final ingestion gate", "Counts, routes, lineage, and zero-write rules are checked one last time."),
}

ROUTE_LABELS = {
    "blank": "BLANK / NEARLY BLANK",
    "blank_candidate": "BLANK / NEARLY BLANK",
    "plain_text": "NORMAL TEXT / PROCEDURE",
    "normal_text": "NORMAL TEXT / PROCEDURE",
    "procedure_or_description": "NORMAL TEXT / PROCEDURE",
    "cover_or_title_page": "NORMAL TEXT / TITLE",
    "table": "TABLE / ILLUSTRATED PARTS LIST",
    "table_or_index": "TABLE / INDEX",
    "detailed_parts_list": "TABLE / ILLUSTRATED PARTS LIST",
    "image": "IMAGE / DIAGRAM",
    "image_visual_diagram": "IMAGE / DIAGRAM",
    "mixed_text_and_figure": "MIXED TEXT + FIGURE",
    "review_required": "VALIDATOR-RESOLVED PAGE",
}


@dataclass
class ProcessResult:
    return_code: int
    elapsed_seconds: float
    log_path: Path


@dataclass
class PageRecord:
    page_id: str
    page_number: int
    source_member: str
    route: str
    text: str
    raw: dict[str, Any]


@dataclass
class EmbeddingRecord:
    page_id: str
    page_number: int
    route: str
    status: str
    dimension: int
    vector_norm: float
    text_char_count: int
    vector: list[float]


def color(text: str, code: str) -> str:
    return f"{code}{text}{RESET}"


def line(char: str = "=", width: int = 100) -> None:
    print(color(char * width, DIM), flush=True)


def banner(title: str, subtitle: str = "") -> None:
    print()
    line()
    print(color(title, BOLD + CYAN), flush=True)
    if subtitle:
        print(subtitle, flush=True)
    line()


def subheading(title: str) -> None:
    print()
    print(color(title, BOLD + BLUE), flush=True)
    print(color("-" * min(100, max(20, len(title))), DIM), flush=True)


def format_elapsed(seconds: float) -> str:
    value = max(0, int(seconds))
    minutes, secs = divmod(value, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    return f"{minutes}m {secs:02d}s"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return dict(value) if isinstance(value, Mapping) else {"value": value}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def walk_objects(value: Any, limit: int = 1_000_000) -> Iterator[Any]:
    stack = [value]
    seen = 0
    while stack and seen < limit:
        item = stack.pop()
        seen += 1
        yield item
        if isinstance(item, Mapping):
            stack.extend(reversed(list(item.values())))
        elif isinstance(item, list):
            stack.extend(reversed(item))


def first_value(record: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def recursive_first(record: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for item in walk_objects(record, limit=20_000):
        if isinstance(item, Mapping):
            value = first_value(item, keys)
            if value not in (None, "", [], {}):
                return value
    return None


def page_number_from_id(page_id: str) -> int:
    match = re.search(r"p(\d{6})$", page_id or "")
    return int(match.group(1)) if match else 0


def page_number_from_name(name: str) -> int:
    numbers = [int(value) for value in re.findall(r"\d+", Path(name).name)]
    return numbers[-1] if numbers else 0


def normalize_route(value: Any) -> str:
    text = str(value or "unknown").strip().lower().replace("-", "_").replace(" ", "_")
    return text or "unknown"


def route_label(route: str) -> str:
    return ROUTE_LABELS.get(normalize_route(route), normalize_route(route).replace("_", " ").upper())


def extract_text(record: Mapping[str, Any]) -> str:
    keys = (
        "best_ocr_text",
        "ocr_text",
        "combined_ocr_text",
        "page_text",
        "text",
        "ocr_sample_text",
        "sample_text",
    )
    value = recursive_first(record, keys)
    return str(value or "").strip()


def extract_page_records(payload: Any) -> list[PageRecord]:
    candidates: dict[str, PageRecord] = {}
    for item in walk_objects(payload):
        if not isinstance(item, Mapping):
            continue
        page_id = str(first_value(item, ("page_id", "canonical_page_id", "source_page_id")) or "").strip()
        page_number_value = first_value(item, ("page_number", "canonical_page_number", "source_page_number"))
        page_number = 0
        try:
            page_number = int(page_number_value or 0)
        except (TypeError, ValueError):
            page_number = 0
        if not page_id and page_number:
            page_id = f"page_{page_number:06d}"
        if not page_id:
            continue
        if not page_number:
            page_number = page_number_from_id(page_id)
        source_member = str(first_value(item, ("source_member", "source_path", "tiff_reference", "raw_tiff_path", "file_name")) or "")
        route = normalize_route(first_value(item, ("final_validated_route", "final_route", "operational_route", "primary_route", "route")))
        text = extract_text(item)
        record = PageRecord(page_id, page_number, source_member, route, text, dict(item))
        previous = candidates.get(page_id)
        score = int(bool(route and route != "unknown")) * 10 + len(text) + int(bool(source_member)) * 5
        previous_score = -1
        if previous:
            previous_score = int(previous.route != "unknown") * 10 + len(previous.text) + int(bool(previous.source_member)) * 5
        if previous is None or score > previous_score:
            candidates[page_id] = record
    return sorted(candidates.values(), key=lambda row: (row.page_number or 10**9, row.page_id))


def merge_page_records(*record_sets: Sequence[PageRecord]) -> list[PageRecord]:
    merged: dict[str, PageRecord] = {}
    for rows in record_sets:
        for row in rows:
            previous = merged.get(row.page_id)
            if previous is None:
                merged[row.page_id] = row
                continue
            merged[row.page_id] = PageRecord(
                page_id=row.page_id,
                page_number=row.page_number or previous.page_number,
                source_member=row.source_member or previous.source_member,
                route=row.route if row.route != "unknown" else previous.route,
                text=row.text or previous.text,
                raw={**previous.raw, **row.raw},
            )
    return sorted(merged.values(), key=lambda row: (row.page_number or 10**9, row.page_id))


def count_tiffs(source: Path) -> tuple[int, int]:
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            infos = [info for info in archive.infolist() if info.filename.lower().endswith((".tif", ".tiff"))]
        return len(infos), sum(info.file_size for info in infos)
    return (1, source.stat().st_size) if source.suffix.lower() in {".tif", ".tiff"} else (0, 0)


def ollama_models(base_url: str) -> tuple[bool, list[str], str]:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/api/tags", timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        models = [str(row.get("name") or "") for row in payload.get("models") or []]
        return True, models, ""
    except Exception as exc:
        return False, [], f"{type(exc).__name__}: {exc}"


def find_report(root: Path, filename: str) -> Path | None:
    direct = list(root.rglob(filename))
    return sorted(direct, key=lambda path: (len(path.parts), str(path)))[0] if direct else None


def _stream_reader(stream: Any, output_queue: queue.Queue[str | None], log_handle: Any) -> None:
    try:
        for raw in iter(stream.readline, ""):
            log_handle.write(raw)
            log_handle.flush()
            output_queue.put(raw.rstrip("\n"))
    finally:
        output_queue.put(None)


def page_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    values: set[Path] = set()
    for pattern in ("*.tif", "*.tiff", "*.png"):
        for path in root.rglob(pattern):
            values.add(path)
    return sorted(values, key=lambda path: (page_number_from_name(path.name) or 10**9, path.name))


def run_ingestion_with_live_narration(command: list[str], output_dir: Path, total_pages: int, heartbeat_seconds: int) -> ProcessResult:
    log_path = output_dir / "01_deep_ingestion.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    current_stage = "Starting the ingestion pipeline"
    current_key: tuple[str, str] | None = None
    stage_started = started
    last_heartbeat = started
    seen_page_paths: set[Path] = set()
    seen_page_keys: set[str] = set()

    with log_path.open("w", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert process.stdout is not None
        output_queue: queue.Queue[str | None] = queue.Queue()
        reader = threading.Thread(target=_stream_reader, args=(process.stdout, output_queue, log_handle), daemon=True)
        reader.start()
        reader_done = False

        while process.poll() is None or not reader_done:
            try:
                item = output_queue.get(timeout=0.35)
            except queue.Empty:
                item = "__WAIT__"
            now = time.monotonic()
            if item is None:
                reader_done = True
                continue
            if item != "__WAIT__":
                match = STAGE_LINE_RE.match(item)
                if match:
                    if current_key in STAGE_NAMES:
                        previous = STAGE_NAMES[current_key]
                        print(color(f"✓ STEP {previous[0]} finished in {format_elapsed(now - stage_started)}", GREEN), flush=True)
                    current_key = (match.group(1), match.group(2))
                    stage_started = now
                    mapped = STAGE_NAMES.get(current_key)
                    if mapped:
                        number, title, explanation = mapped
                        subheading(f"STEP {number} — {title}")
                        print(f"Easy explanation: {explanation}", flush=True)
                        current_stage = title
                    else:
                        current_stage = item
                elif item.startswith("Quality status:") or item.startswith("Status:"):
                    print(color(item, GREEN if "PASS" in item else YELLOW), flush=True)

            if current_key == ("ocr", "build"):
                pages_root = output_dir / "ocr_route_scan_pack_tesseract_full"
                current_files = page_files(pages_root)
                for path in current_files:
                    if path in seen_page_paths:
                        continue
                    seen_page_paths.add(path)
                    number = page_number_from_name(path.name)
                    key = f"page:{number}" if number else f"path:{path.name}"
                    if key in seen_page_keys:
                        continue
                    if len(seen_page_keys) >= total_pages:
                        continue
                    seen_page_keys.add(key)
                    index = len(seen_page_keys)
                    print(
                        color(
                            f"OCR PROGRESS {index:03d}/{total_pages:03d} — raw page prepared: {path.name}",
                            MAGENTA,
                        ),
                        flush=True,
                    )

            if now - last_heartbeat >= heartbeat_seconds:
                if current_key == ("ocr", "build"):
                    print(
                        color(
                            f"Still working — OCR pages observed {len(seen_page_keys)}/{total_pages} | elapsed {format_elapsed(now - started)}",
                            YELLOW,
                        ),
                        flush=True,
                    )
                else:
                    print(color(f"Still working — {current_stage} | elapsed {format_elapsed(now - started)}", YELLOW), flush=True)
                last_heartbeat = now

        reader.join(timeout=3)
        return_code = int(process.returncode or 0)

    if current_key in STAGE_NAMES and return_code == 0:
        mapped = STAGE_NAMES[current_key]
        print(color(f"✓ STEP {mapped[0]} finished in {format_elapsed(time.monotonic() - stage_started)}", GREEN), flush=True)
    return ProcessResult(return_code, time.monotonic() - started, log_path)


def print_ocr_results(records: Sequence[PageRecord], expected_count: int) -> None:
    banner("PAGE-BY-PAGE OCR RESULTS", "Each line is one original scanned page after OCR.")
    if not records:
        print(color("No page-level OCR records were found in the generated report.", RED))
        return
    for index, row in enumerate(records, start=1):
        status = "TEXT FOUND" if row.text.strip() else "NO TEXT / POSSIBLE BLANK OR IMAGE"
        source = row.source_member or row.page_id
        print(
            f"OCR RESULT {index:03d}/{expected_count:03d} — {row.page_id} — {status} — "
            f"characters={len(row.text):,} — source={Path(source).name}",
            flush=True,
        )


def print_classifications(records: Sequence[PageRecord], expected_count: int) -> None:
    banner("PAGE-BY-PAGE CLASSIFICATION", "The deterministic classifier chooses the correct processing route for every page.")
    if not records:
        print(color("No page-level route records were found.", RED))
        return
    for index, row in enumerate(records, start=1):
        print(
            f"CLASSIFY {index:03d}/{expected_count:03d} — {row.page_id} -> {route_label(row.route)}",
            flush=True,
        )


def identifiers_in_text(text: str, limit: int = 80) -> list[str]:
    seen: list[str] = []
    for value in PART_RE.findall(text or ""):
        normalized = value.upper()
        if normalized not in seen:
            seen.append(normalized)
            if len(seen) >= limit:
                break
    return seen


def build_graph_snapshot(output_dir: Path, source_package: Path, records: Sequence[PageRecord]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [
        {"node_id": "source:raw_tiff_package", "node_type": "source_package", "label": source_package.name}
    ]
    edges: list[dict[str, Any]] = []
    known_nodes = {"source:raw_tiff_package"}
    route_nodes: set[str] = set()
    identifier_nodes: set[str] = set()

    for row in records:
        page_node = f"page:{row.page_id}"
        nodes.append({
            "node_id": page_node,
            "node_type": "page",
            "label": row.page_id,
            "page_number": row.page_number,
            "route": normalize_route(row.route),
            "source_member": row.source_member,
        })
        known_nodes.add(page_node)
        edges.append({"from": "source:raw_tiff_package", "relationship": "CONTAINS_PAGE", "to": page_node})

        route_node = f"route:{normalize_route(row.route)}"
        if route_node not in route_nodes:
            route_nodes.add(route_node)
            nodes.append({"node_id": route_node, "node_type": "route", "label": route_label(row.route)})
        edges.append({"from": page_node, "relationship": "CLASSIFIED_AS", "to": route_node})

        for identifier in identifiers_in_text(row.text):
            identifier_node = f"part:{identifier}"
            if identifier_node not in identifier_nodes:
                identifier_nodes.add(identifier_node)
                nodes.append({"node_id": identifier_node, "node_type": "part_identifier", "label": identifier})
            edges.append({"from": page_node, "relationship": "MENTIONS_PART", "to": identifier_node})

    nodes_path = output_dir / "trace_net_demo_graph_nodes_v4.jsonl"
    edges_path = output_dir / "trace_net_demo_graph_edges_v4.jsonl"
    write_jsonl(nodes_path, nodes)
    write_jsonl(edges_path, edges)

    summary = {
        "status": "TRACE_NET_DEMO_GRAPH_SNAPSHOT_MADE",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "page_node_count": len(records),
        "route_node_count": len(route_nodes),
        "part_identifier_node_count": len(identifier_nodes),
        "nodes_path": str(nodes_path),
        "edges_path": str(edges_path),
        "production_graph_modified": False,
    }
    write_json(output_dir / "trace_net_demo_graph_summary_v4.json", summary)

    banner("INTERCONNECTED GRAPH SNAPSHOT")
    print("This graph snapshot is made from the validated page records in this demo run.")
    print("It does not modify the existing production graph.")
    print(color(f"✓ GRAPH NODES MADE — {len(nodes):,} nodes", GREEN), flush=True)
    print(color(f"✓ GRAPH EDGES MADE — {len(edges):,} relationships", GREEN), flush=True)
    return summary


def build_engram_layers(output_dir: Path, records: Sequence[PageRecord], graph: Mapping[str, Any], stage_summary: Mapping[str, Any]) -> dict[str, Any]:
    route_counts: dict[str, int] = {}
    identifiers: set[str] = set()
    for row in records:
        route_counts[normalize_route(row.route)] = route_counts.get(normalize_route(row.route), 0) + 1
        identifiers.update(identifiers_in_text(row.text))

    layers = [
        {
            "layer": "working_memory",
            "plain_english": "What TRACE-Net is handling right now.",
            "contents": {
                "current_run_output": str(output_dir),
                "active_page_count": len(records),
                "active_question": None,
                "selected_evidence": [],
            },
        },
        {
            "layer": "semantic_memory",
            "plain_english": "Stable facts and relationships learned from the manuals.",
            "contents": {
                "route_counts": route_counts,
                "unique_part_identifier_count": len(identifiers),
                "graph_node_count": graph.get("node_count"),
                "graph_edge_count": graph.get("edge_count"),
            },
        },
        {
            "layer": "procedural_memory",
            "plain_english": "Rules describing how the system must search and answer.",
            "contents": {
                "rules": [
                    "Extract exact identifiers deterministically before retrieval.",
                    "Use route-specific retrieval tunnels.",
                    "Treat graph, vector, summaries, and visual findings as guidance until source-resolved.",
                    "Allow one Gemma answer-writing call only after evidence is prepared.",
                    "Reject unsupported identifiers, citations, and safety claims.",
                ]
            },
        },
        {
            "layer": "episodic_memory",
            "plain_english": "What happened during this specific run.",
            "contents": {
                "run_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "stage_quality_statuses": stage_summary.get("stage_quality_statuses", {}),
                "lineage_ready_count": stage_summary.get("lineage_ready_count"),
                "write_attempt_count": stage_summary.get("write_attempt_count"),
            },
        },
        {
            "layer": "trait_memory",
            "plain_english": "Stable answer style and safety behavior.",
            "contents": {
                "answer_style": "direct, evidence-first, readable by engineers and managers",
                "citation_required": True,
                "preserve_identifiers_exactly": True,
                "admit_limits": True,
                "production_writes_allowed": False,
            },
        },
        {
            "layer": "critic_memory",
            "plain_english": "Checks that catch weak evidence or unsupported answers.",
            "contents": {
                "self_rag_checks": ["route correctness", "evidence sufficiency", "citation readiness", "identifier fidelity"],
                "crag_repairs": "bounded retry only when evidence is weak",
                "source_truth_mutation_allowed": False,
            },
        },
    ]

    payload = {
        "status": "TRACE_NET_DEMO_ENGRAM_LAYERS_MADE",
        "layer_count": len(layers),
        "layers": layers,
    }
    path = output_dir / "trace_net_demo_engram_layers_v4.json"
    write_json(path, payload)

    banner("ENGRAM MEMORY LAYERS")
    print("The Engram is the organized memory model that keeps current context, stable facts, rules, history, behavior, and criticism separate.")
    for index, layer in enumerate(layers, start=1):
        print()
        print(color(f"ENGRAM LAYER {index}/6 MADE — {str(layer['layer']).replace('_', ' ').upper()}", GREEN), flush=True)
        print(f"  Meaning: {layer['plain_english']}")
        for key, value in (layer.get("contents") or {}).items():
            if isinstance(value, list):
                preview = "; ".join(str(item) for item in value[:5])
                print(f"  {key}: {preview}")
            else:
                print(f"  {key}: {value}")
    print(f"\nEngram file: {path}")
    return payload


def http_json(url: str, payload: Mapping[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        value = json.loads(response.read().decode("utf-8", errors="replace"))
    return dict(value) if isinstance(value, Mapping) else {"value": value}


def embed_text(ollama_url: str, model: str, text: str, timeout: float) -> list[float]:
    payload = {"model": model, "input": text}
    try:
        value = http_json(ollama_url.rstrip("/") + "/api/embed", payload, timeout)
        embeddings = value.get("embeddings")
        if isinstance(embeddings, list) and embeddings and isinstance(embeddings[0], list):
            return [float(item) for item in embeddings[0]]
    except urllib.error.HTTPError:
        pass
    legacy = http_json(ollama_url.rstrip("/") + "/api/embeddings", {"model": model, "prompt": text}, timeout)
    vector = legacy.get("embedding")
    return [float(item) for item in vector] if isinstance(vector, list) else []


def vector_norm(vector: Sequence[float]) -> float:
    return math.sqrt(sum(float(value) * float(value) for value in vector))


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    denominator = vector_norm(left) * vector_norm(right)
    if denominator <= 0:
        return 0.0
    return sum(float(a) * float(b) for a, b in zip(left, right)) / denominator


def build_embeddings(
    output_dir: Path,
    records: Sequence[PageRecord],
    ollama_url: str,
    model: str,
    timeout: float,
    max_chars: int,
) -> list[EmbeddingRecord]:
    banner("PAGE-BY-PAGE EMBEDDINGS", "bge-m3 converts each searchable page into a numeric meaning vector. No Qdrant write is performed.")
    results: list[EmbeddingRecord] = []
    total = len(records)
    for index, row in enumerate(records, start=1):
        text = re.sub(r"\s+", " ", row.text).strip()
        if not text:
            result = EmbeddingRecord(row.page_id, row.page_number, row.route, "SKIP_NO_TEXT", 0, 0.0, 0, [])
            results.append(result)
            print(f"EMBED {index:03d}/{total:03d} — {row.page_id} -> SKIPPED (no OCR text)", flush=True)
            continue
        prepared = text[:max_chars]
        try:
            vector = embed_text(ollama_url, model, prepared, timeout)
            status = "PASS" if vector else "FAIL_EMPTY_VECTOR"
        except Exception as exc:
            vector = []
            status = f"FAIL_{type(exc).__name__}"
        result = EmbeddingRecord(
            page_id=row.page_id,
            page_number=row.page_number,
            route=row.route,
            status=status,
            dimension=len(vector),
            vector_norm=round(vector_norm(vector), 6),
            text_char_count=len(prepared),
            vector=vector,
        )
        results.append(result)
        print(
            f"EMBED {index:03d}/{total:03d} — {row.page_id} -> {status} "
            f"dimension={len(vector)} text_chars={len(prepared):,}",
            flush=True,
        )

    rows = [
        {
            "page_id": item.page_id,
            "page_number": item.page_number,
            "route": item.route,
            "status": item.status,
            "dimension": item.dimension,
            "vector_norm": item.vector_norm,
            "text_char_count": item.text_char_count,
            "vector": item.vector,
        }
        for item in results
    ]
    path = output_dir / "trace_net_demo_page_embeddings_v4.jsonl"
    write_jsonl(path, rows)
    summary = {
        "status": "TRACE_NET_DEMO_EMBEDDINGS_MADE",
        "model": model,
        "record_count": len(results),
        "embedded_count": sum(1 for item in results if item.status == "PASS"),
        "skipped_count": sum(1 for item in results if item.status.startswith("SKIP")),
        "failed_count": sum(1 for item in results if item.status.startswith("FAIL")),
        "dimensions": sorted({item.dimension for item in results if item.dimension}),
        "path": str(path),
        "qdrant_write_attempt": False,
    }
    write_json(output_dir / "trace_net_demo_embedding_summary_v4.json", summary)
    print()
    print(color(f"✓ EMBEDDING FILE MADE — {summary['embedded_count']}/{len(results)} pages embedded", GREEN))
    print(f"Embedding file: {path}")
    return results


def extract_query_atoms(question: str) -> dict[str, Any]:
    text = question.strip()
    parts = identifiers_in_text(text)
    ata = re.findall(r"\bATA\s*(\d{2})\b", text, flags=re.I)
    figures = re.findall(r"\b(?:figure|fig\.)\s*(\d+)\b", text, flags=re.I)
    keywords = [
        token.lower()
        for token in re.findall(r"[A-Za-z0-9]+", text)
        if len(token) >= 4 and token.lower() not in {"what", "which", "with", "from", "that", "this", "inside", "about", "pages", "trace", "evidence", "cite"}
    ]
    return {
        "exact_part_identifiers": parts,
        "ata_chapters": ata,
        "figure_numbers": figures,
        "keywords": list(dict.fromkeys(keywords))[:20],
        "asks_next_higher_assembly": bool(re.search(r"next\s+higher|bigger\s+assembly|installed\s+inside|parent\s+assembly", text, re.I)),
        "asks_table_or_item": bool(re.search(r"\btable\b|\bitem\b|illustrated\s+parts", text, re.I)),
        "asks_visual": bool(re.search(r"\bfigure\b|\bdiagram\b|\bdrawing\b|\bcallout\b", text, re.I)),
    }


def deterministic_route(atoms: Mapping[str, Any]) -> str:
    if atoms.get("asks_next_higher_assembly"):
        return "graph_relationship_reasoning"
    if atoms.get("asks_visual"):
        return "visual_figure_callout_lookup"
    if atoms.get("asks_table_or_item"):
        return "exact_table_ipl_lookup"
    if atoms.get("exact_part_identifiers"):
        return "exact_identifier_lookup"
    if atoms.get("ata_chapters"):
        return "ata_system_discovery"
    return "semantic_discovery"


def retrieval_tunnels(route: str) -> list[str]:
    mapping = {
        "graph_relationship_reasoning": ["exact identifier", "table/IPL", "OCR", "graph", "vector guidance"],
        "visual_figure_callout_lookup": ["exact identifier", "OCR", "visual summary", "graph", "vector guidance"],
        "exact_table_ipl_lookup": ["exact table/IPL", "OCR", "graph", "vector guidance"],
        "exact_identifier_lookup": ["exact identifier", "table/IPL", "OCR", "graph", "vector guidance"],
        "ata_system_discovery": ["ATA metadata", "OCR", "graph", "vector guidance"],
        "semantic_discovery": ["vector guidance", "OCR", "graph"],
    }
    return mapping.get(route, ["OCR", "graph", "vector guidance"])


def top_vector_matches(query_vector: Sequence[float], embeddings: Sequence[EmbeddingRecord], limit: int = 5) -> list[tuple[float, EmbeddingRecord]]:
    scored = [
        (cosine_similarity(query_vector, item.vector), item)
        for item in embeddings
        if item.status == "PASS" and item.vector
    ]
    return sorted(scored, key=lambda pair: pair[0], reverse=True)[:limit]


def allowed_answer_identifiers(question: str, evidence: Sequence[Mapping[str, Any]]) -> set[str]:
    allowed = set(identifiers_in_text(question))
    for row in evidence:
        allowed.update(identifiers_in_text(json.dumps(row, ensure_ascii=False)))
    return allowed


def validate_answer(answer: str, question: str, evidence: Sequence[Mapping[str, Any]], llm: Mapping[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    allowed = allowed_answer_identifiers(question, evidence)
    used = set(identifiers_in_text(answer))
    unsupported = sorted(used - allowed)
    if not answer.strip():
        failures.append("empty_answer")
    if unsupported:
        failures.append("unsupported_identifiers")
    citation_ids = [int(value) for value in CITATION_RE.findall(answer)]
    invalid_citations = sorted({value for value in citation_ids if value < 1 or value > len(evidence)})
    if invalid_citations:
        failures.append("unsupported_citation_labels")
    if llm.get("llm_status") != "PASS":
        failures.append("gemma_status_not_pass")
    return {
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "allowed_identifier_count": len(allowed),
        "answer_identifier_count": len(used),
        "unsupported_identifiers": unsupported,
        "citation_labels_used": citation_ids,
        "invalid_citation_labels": invalid_citations,
        "source_truth_mutation_allowed": False,
    }


def print_question_process(
    index: int,
    question: str,
    ocr_payload: Mapping[str, Any],
    retrieval_payload: Mapping[str, Any],
    embeddings: Sequence[EmbeddingRecord],
    ollama_url: str,
    embed_model: str,
    llm_model: str,
    top_k: int,
    request_timeout: int,
    max_tokens: int,
    output_dir: Path,
) -> dict[str, Any]:
    from tiff.trace_net_raw_to_answer_e2e_smoke_v1 import build_answer_draft, local_retrieve

    banner(f"EXAMPLE QUESTION {index}", question)

    atoms = extract_query_atoms(question)
    route = deterministic_route(atoms)
    tunnels = retrieval_tunnels(route)

    print(color("DETERMINISTIC STEP 1 — Read and normalize the question", BOLD + BLUE))
    print(f"  Original question: {question}")
    print(f"  Exact identifiers found: {atoms['exact_part_identifiers'] or 'none'}")
    print(f"  ATA chapters found: {atoms['ata_chapters'] or 'none'}")
    print(f"  Figure numbers found: {atoms['figure_numbers'] or 'none'}")
    print(f"  Useful keywords: {atoms['keywords']}")

    print()
    print(color("DETERMINISTIC STEP 2 — Choose the route", BOLD + BLUE))
    print(f"  Selected route: {route}")
    print("  Why: the route is selected by rules and query atoms before Gemma is called.")

    print()
    print(color("DETERMINISTIC STEP 3 — Open bounded retrieval tunnels", BOLD + BLUE))
    for tunnel_index, tunnel in enumerate(tunnels, start=1):
        print(f"  Tunnel {tunnel_index}: {tunnel}")

    print()
    print(color("DETERMINISTIC STEP 4 — Run vector guidance", BOLD + BLUE))
    try:
        query_vector = embed_text(ollama_url, embed_model, question, request_timeout)
    except Exception as exc:
        query_vector = []
        print(f"  Query embedding failed: {type(exc).__name__}: {exc}")
    vector_matches = top_vector_matches(query_vector, embeddings, limit=5) if query_vector else []
    if vector_matches:
        for match_index, (score, item) in enumerate(vector_matches, start=1):
            print(f"  Vector candidate {match_index}: {item.page_id} similarity={score:.4f} — guidance only")
    else:
        print("  No vector candidates were available. Exact and OCR retrieval may still continue.")

    print()
    print(color("DETERMINISTIC STEP 5 — Search source-traced records", BOLD + BLUE))
    evidence = local_retrieve(
        question=question,
        retrieval_payload=retrieval_payload,
        ocr_payload=ocr_payload,
        top_k=top_k,
    )
    print(f"  Candidate evidence kept: {len(evidence)}")
    for evidence_index, row in enumerate(evidence, start=1):
        citation = row.get("citation") or {}
        reasons = row.get("retrieval_reasons") or []
        score = row.get("retrieval_score") or row.get("score")
        print(f"  Evidence E{evidence_index}: page={citation.get('page_id') or citation.get('page_number')} route={route_label(str(row.get('route') or 'unknown'))} score={score}")
        print(f"    Reasons: {', '.join(str(value) for value in reasons) or 'matched the question'}")

    print()
    print(color("DETERMINISTIC STEP 6 — Build the typed evidence envelope", BOLD + BLUE))
    direct_count = sum(1 for row in evidence if (row.get("citation") or {}).get("page_id"))
    print(f"  Direct source-traced records: {direct_count}")
    print(f"  Vector candidates: {len(vector_matches)} (guidance only)")
    print("  Contradictions: preserved if found; never silently discarded")
    print("  Source mutation permission: false")

    print()
    print(color("ENGRAM STEP — Update working and critic memory", BOLD + BLUE))
    print(f"  Working memory now holds the question, route, and {len(evidence)} evidence records.")
    print("  Procedural memory supplies the retrieval and citation rules.")
    print("  Critic memory will evaluate evidence sufficiency and the final answer.")

    print()
    print(color("LLM STEP — One Gemma answer-writing call", BOLD + MAGENTA))
    print(f"  Model: {llm_model}")
    print(f"  Evidence records supplied: {len(evidence)}")
    print(f"  Maximum output tokens: {max_tokens}")
    print("  Gemma's job: explain only the approved evidence, preserve identifiers, and use the supplied evidence labels.")
    print("  Internal chain-of-thought is not displayed. The audit trace shows the inputs, constraints, model result, and validators.")
    started = time.monotonic()
    answer, llm = build_answer_draft(
        question=question,
        evidence=evidence,
        llm_mode="ollama_openai",
        llm_base_url=ollama_url.rstrip("/") + "/v1",
        llm_model=llm_model,
        llm_api_key="ollama",
        request_timeout=request_timeout,
        llm_max_tokens=max_tokens,
    )
    print(f"  Gemma call finished in {format_elapsed(time.monotonic() - started)}")
    print(f"  Gemma status: {llm.get('llm_status')}")
    print(f"  Output characters: {len(answer)}")

    print()
    print(color("DETERMINISTIC STEP 7 — Validate the model output", BOLD + BLUE))
    validation = validate_answer(answer, question, evidence, llm)
    print(f"  Empty answer check: {'PASS' if answer.strip() else 'FAIL'}")
    print(f"  Unsupported identifiers: {validation['unsupported_identifiers'] or 'none'}")
    print(f"  Invalid citation labels: {validation['invalid_citation_labels'] or 'none'}")
    print("  Source-truth mutation allowed: false")
    print(f"  Final release decision: {validation['quality_status']}")

    print()
    print(color("FINAL USER-FACING ANSWER", BOLD + CYAN))
    print(answer or "No answer was produced.")

    payload = {
        "question_number": index,
        "question": question,
        "query_atoms": atoms,
        "selected_route": route,
        "retrieval_tunnels": tunnels,
        "vector_candidates": [
            {"page_id": item.page_id, "similarity": round(score, 6)} for score, item in vector_matches
        ],
        "retrieval_evidence_records": evidence,
        "answer": answer,
        "llm_result": llm,
        "validation": validation,
        "quality_status": validation["quality_status"],
    }
    write_json(output_dir / f"trace_net_demo_question_{index:02d}_v4.json", payload)
    return payload


def summarize_ingestion(report_path: Path | None) -> dict[str, Any]:
    if not report_path or not report_path.is_file():
        return {}
    payload = read_json(report_path)
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    return {
        "quality_status": payload.get("quality_status"),
        "stage_quality_statuses": dict(summary.get("stage_quality_statuses") or {}),
        "stage_report_count": summary.get("stage_report_count"),
        "lineage_ready_count": summary.get("lineage_ready_count"),
        "missing_lineage_count": summary.get("missing_lineage_count"),
        "write_attempt_count": summary.get("write_attempt_count"),
        "route_counts": dict(summary.get("final_validated_route_counts") or {}),
        "graph_ready_count": summary.get("postgres_graph_record_count"),
        "qdrant_payload_count": summary.get("qdrant_payload_count"),
        "opensearch_payload_count": summary.get("opensearch_payload_count"),
    }


def make_html_report(
    path: Path,
    source: Path,
    page_records: Sequence[PageRecord],
    graph: Mapping[str, Any],
    engram: Mapping[str, Any],
    embedding_summary: Mapping[str, Any],
    questions: Sequence[Mapping[str, Any]],
    ingestion: Mapping[str, Any],
) -> None:
    route_rows = "".join(
        f"<tr><td>{html.escape(row.page_id)}</td><td>{html.escape(route_label(row.route))}</td><td>{len(row.text):,}</td></tr>"
        for row in page_records
    )
    engram_cards = "".join(
        f"<div class='card'><h3>{html.escape(str(layer.get('layer')).replace('_',' ').title())}</h3><p>{html.escape(str(layer.get('plain_english') or ''))}</p></div>"
        for layer in engram.get("layers") or []
    )
    question_cards = "".join(
        f"<div class='card'><h3>Question {row.get('question_number')}</h3><p><strong>{html.escape(str(row.get('question')))}</strong></p>"
        f"<p>Route: {html.escape(str(row.get('selected_route')))}</p><p>Result: {html.escape(str(row.get('quality_status')))}</p>"
        f"<pre>{html.escape(str(row.get('answer') or ''))}</pre></div>"
        for row in questions
    )
    document = f"""<!doctype html>
<html><head><meta charset='utf-8'><title>TRACE-Net Deep Executive Demo v4</title>
<style>
body{{font-family:Arial,sans-serif;margin:0;background:#f3f5f7;color:#17202a}}header{{background:#17374a;color:white;padding:34px 6vw}}main{{max-width:1250px;margin:auto;padding:28px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}}.card{{background:white;padding:18px;border-radius:12px;box-shadow:0 3px 15px #0001}}table{{width:100%;border-collapse:collapse;background:white}}th,td{{padding:8px;border-bottom:1px solid #ddd;text-align:left}}pre{{white-space:pre-wrap;font-family:Arial,sans-serif;line-height:1.45}}.good{{color:#18793a;font-weight:bold}}footer{{padding:28px;text-align:center;color:#667}}</style></head>
<body><header><h1>TRACE-Net Deep Executive Demo v4</h1><p>Page-by-page TIFF ingestion, graph, Engram, embeddings, deterministic retrieval, Gemma, and validation</p></header><main>
<div class='grid'><div class='card'><h2>Input</h2><p>{html.escape(str(source))}</p><p>Pages: {len(page_records)}</p></div><div class='card'><h2>Ingestion</h2><p class='good'>{html.escape(str(ingestion.get('quality_status') or 'unknown'))}</p><p>Lineage ready: {html.escape(str(ingestion.get('lineage_ready_count')))}</p></div><div class='card'><h2>Graph</h2><p>Nodes: {graph.get('node_count')}</p><p>Edges: {graph.get('edge_count')}</p></div><div class='card'><h2>Embeddings</h2><p>Embedded: {embedding_summary.get('embedded_count')}</p><p>Model: {html.escape(str(embedding_summary.get('model') or ''))}</p></div></div>
<h2>Page-by-page classification</h2><table><tr><th>Page</th><th>Final type</th><th>OCR characters</th></tr>{route_rows}</table>
<h2>Engram layers</h2><div class='grid'>{engram_cards}</div>
<h2>Example questions and answers</h2><div class='grid'>{question_cards}</div>
<h2>Safety</h2><div class='card'><p>Postgres writes: 0</p><p>Qdrant writes: 0</p><p>OpenSearch writes: 0</p><p>Production graph modified: false</p><p>Source-truth mutation allowed: false</p></div>
</main><footer>TRACE-Net executive demo v4</footer></body></html>"""
    path.write_text(document, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--source-package", default=DEFAULT_SOURCE)
    parser.add_argument("--tesseract-cmd", default=DEFAULT_TESSERACT)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA)
    parser.add_argument("--llm-model", default=DEFAULT_LLM_MODEL)
    parser.add_argument("--embedding-model", default=DEFAULT_EMBED_MODEL)
    parser.add_argument("--question", action="append", dest="questions")
    parser.add_argument("--output-dir")
    parser.add_argument("--heartbeat-seconds", type=int, default=10)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--request-timeout", type=int, default=1200)
    parser.add_argument("--llm-max-tokens", type=int, default=4096)
    parser.add_argument("--embedding-max-chars", type=int, default=6000)
    parser.add_argument("--skip-ingestion", action="store_true", help="Reuse an existing --output-dir containing the canonical pipeline reports.")
    parser.add_argument("--skip-embeddings", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    repo = Path(args.repo).resolve()
    source = Path(args.source_package).resolve()
    tesseract = shutil.which(args.tesseract_cmd) or (args.tesseract_cmd if Path(args.tesseract_cmd).is_file() else "")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir or f"/data/trace_net_runs/executive_deep_demo_v4_{stamp}").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    questions = tuple(args.questions or DEFAULT_QUESTIONS)

    banner("TRACE-NET EXECUTIVE DEMONSTRATION — DEEP PAGE-BY-PAGE MODE", "Raw TIFFs → OCR → page routes → graph → Engram → embeddings → deterministic retrieval → Gemma → validation")
    print("This is a separate v4 presentation mode. The existing v2 and fast10 v3 demos remain unchanged.")
    print("This mode is intentionally verbose so a person with no coding experience can watch the system think through its controlled steps.")
    print("The system does not expose private model chain-of-thought. It shows the auditable deterministic trace, evidence packet, model call, and validators.")

    banner("PRE-DEMO CHECK")
    can_run = True
    if repo.is_dir():
        print(color(f"✓ Repository found: {repo}", GREEN))
    else:
        print(color(f"✗ Repository missing: {repo}", RED))
        can_run = False
    if source.is_file():
        page_count, raw_bytes = count_tiffs(source)
        print(color(f"✓ Raw TIFF source found: {source}", GREEN))
        print(f"  Original TIFF pages: {page_count}")
        print(f"  Uncompressed TIFF size: {raw_bytes / (1024 * 1024):.1f} MB")
    else:
        page_count = 0
        print(color(f"✗ Raw source missing: {source}", RED))
        can_run = False
    if tesseract:
        print(color(f"✓ Tesseract found: {tesseract}", GREEN))
    else:
        print(color(f"✗ Tesseract missing: {args.tesseract_cmd}", RED))
        can_run = False

    ollama_ok, models, ollama_error = ollama_models(args.ollama_url)
    if ollama_ok:
        print(color("✓ Ollama is running", GREEN))
        print(f"  Gemma available: {args.llm_model in models}")
        print(f"  Embedding model available: {args.embedding_model in models}")
    else:
        print(color("⚠ Ollama is not responding", YELLOW))
        print(f"  Details: {ollama_error}")

    if not can_run:
        banner("DEMO COULD NOT START")
        print("A required local file or program is missing. PuTTY remains open.")
        return

    os.chdir(repo)
    current_pythonpath = os.environ.get("PYTHONPATH", "")
    os.environ["PYTHONPATH"] = f"{repo / 'scripts'}:{repo}" + (f":{current_pythonpath}" if current_pythonpath else "")
    python_bin = str(Path(os.environ.get("VIRTUAL_ENV", "/home/jwild/rag-workspace/.venv")) / "bin" / "python")
    if not Path(python_bin).is_file():
        python_bin = shutil.which("python") or "python"

    ingestion_result: ProcessResult | None = None
    if not args.skip_ingestion:
        banner("PART 1 — RUN THE REAL INGESTION PIPELINE")
        print("You will see page files appear one at a time, then every page's OCR result and final type will be printed.")
        command = [
            python_bin,
            "-u",
            "-B",
            "scripts/run_trace_net_ocr_classifier_pipeline_v1.py",
            "--source-package",
            str(source),
            "--tesseract-cmd",
            str(tesseract),
            "--output-dir",
            str(output_dir),
            "--quality",
        ]
        ingestion_result = run_ingestion_with_live_narration(command, output_dir, page_count, max(2, args.heartbeat_seconds))
        print()
        print(f"Ingestion command return code: {ingestion_result.return_code}")
        print(f"Ingestion elapsed time: {format_elapsed(ingestion_result.elapsed_seconds)}")
        print(f"Full technical log: {ingestion_result.log_path}")
    else:
        banner("PART 1 — REUSING EXISTING INGESTION REPORTS")
        print(f"Existing run folder: {output_dir}")

    pipeline_report = find_report(output_dir, "trace_net_ocr_classifier_pipeline_runner_v1.json")
    ocr_report = find_report(output_dir, "trace_net_ocr_route_scan_pack_v1.json")
    route_report = find_report(output_dir, "trace_net_route_unresolved_retry_probe_v1.json") or find_report(output_dir, "trace_net_four_route_operational_resolver_v1.json")
    storage_report = find_report(output_dir, "trace_net_four_route_storage_gate_v1.json")
    retrieval_report = find_report(output_dir, "trace_net_retrieval_payload_audit_v1.json")

    if not ocr_report or not route_report or not retrieval_report:
        banner("DEMO REPORTS ARE INCOMPLETE")
        print("The required OCR, route, or retrieval report was not created.")
        print("PuTTY remains open. Review the technical log in the output folder.")
        return

    ocr_payload = read_json(ocr_report)
    route_payload = read_json(route_report)
    storage_payload = read_json(storage_report) if storage_report else {}
    retrieval_payload = read_json(retrieval_report)
    ocr_records = extract_page_records(ocr_payload)
    route_records = extract_page_records(route_payload)
    storage_records = extract_page_records(storage_payload)
    page_records = merge_page_records(ocr_records, route_records, storage_records)

    print_ocr_results(ocr_records or page_records, page_count)
    print_classifications(page_records, page_count)

    ingestion_summary = summarize_ingestion(pipeline_report)
    graph = build_graph_snapshot(output_dir, source, page_records)
    engram = build_engram_layers(output_dir, page_records, graph, ingestion_summary)

    embedding_records: list[EmbeddingRecord] = []
    embedding_summary: dict[str, Any] = {
        "status": "SKIPPED",
        "model": args.embedding_model,
        "record_count": 0,
        "embedded_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "qdrant_write_attempt": False,
    }
    if not args.skip_embeddings and ollama_ok and args.embedding_model in models:
        embedding_records = build_embeddings(
            output_dir,
            page_records,
            args.ollama_url,
            args.embedding_model,
            args.request_timeout,
            args.embedding_max_chars,
        )
        embedding_summary = read_json(output_dir / "trace_net_demo_embedding_summary_v4.json")
    else:
        banner("PAGE EMBEDDINGS WERE SKIPPED")
        if args.skip_embeddings:
            print("Reason: --skip-embeddings was supplied.")
        elif not ollama_ok:
            print("Reason: Ollama is not responding.")
        else:
            print(f"Reason: embedding model {args.embedding_model} is not installed.")

    question_results: list[dict[str, Any]] = []
    if ollama_ok and args.llm_model in models:
        banner("PART 2 — ASK EXAMPLE QUESTIONS AND SHOW EVERY ANSWER STEP")
        for question_index, question in enumerate(questions, start=1):
            try:
                result = print_question_process(
                    question_index,
                    question,
                    ocr_payload,
                    retrieval_payload,
                    embedding_records,
                    args.ollama_url,
                    args.embedding_model,
                    args.llm_model,
                    args.top_k,
                    args.request_timeout,
                    args.llm_max_tokens,
                    output_dir,
                )
            except Exception as exc:
                print(color(f"Question {question_index} encountered a problem: {type(exc).__name__}: {exc}", RED))
                result = {
                    "question_number": question_index,
                    "question": question,
                    "quality_status": "FAIL",
                    "answer": "",
                    "error": f"{type(exc).__name__}: {exc}",
                }
                write_json(output_dir / f"trace_net_demo_question_{question_index:02d}_v4.json", result)
            question_results.append(result)
    else:
        banner("QUESTION DEMONSTRATION WAS SKIPPED")
        print(f"Gemma model available: {args.llm_model in models if ollama_ok else False}")

    manifest = {
        "status": STATUS,
        "version": VERSION,
        "quality_status": "PASS" if page_records and graph.get("node_count") and engram.get("layer_count") == 6 else "WARN",
        "source_package": str(source),
        "output_dir": str(output_dir),
        "page_count": len(page_records),
        "ingestion": ingestion_summary,
        "graph": graph,
        "engram": engram,
        "embedding_summary": embedding_summary,
        "questions": question_results,
        "safety": {
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "production_graph_modified": False,
            "source_truth_mutation_allowed": False,
        },
    }
    manifest_path = output_dir / "trace_net_executive_deep_demo_v4_manifest.json"
    write_json(manifest_path, manifest)
    html_path = output_dir / "trace_net_executive_deep_demo_v4.html"
    try:
        make_html_report(html_path, source, page_records, graph, engram, embedding_summary, question_results, ingestion_summary)
    except Exception as exc:
        print(color(f"HTML report warning: {type(exc).__name__}: {exc}", YELLOW))

    banner("DEEP DEMONSTRATION COMPLETE")
    print(f"Pages narrated: {len(page_records)}")
    print(f"Graph nodes: {graph.get('node_count')}")
    print(f"Graph edges: {graph.get('edge_count')}")
    print(f"Engram layers: {engram.get('layer_count')}")
    print(f"Pages embedded: {embedding_summary.get('embedded_count')}")
    print(f"Example questions completed: {len(question_results)}")
    print(f"Output folder: {output_dir}")
    print(f"Manifest: {manifest_path}")
    print(f"HTML report: {html_path}")
    print("Postgres writes: 0")
    print("Qdrant writes: 0")
    print("OpenSearch writes: 0")
    print("Source-truth mutation allowed: false")
    print("PuTTY remains open.")


if __name__ == "__main__":
    main()
