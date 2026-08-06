#!/usr/bin/env python3
"""TRACE-Net executive demo v5: deep narrated 10-page mode.

This is a separate presentation mode. It does not replace:
- v2: simple full 509-page executive demo;
- v3: simple fast 10-page executive demo;
- v4/v4.1: deep full 509-page executive demo.

The wrapper creates a temporary ten-page TIFF ZIP, runs the same chronological
TRACE-Net ingestion stages with ten-page quality thresholds, and then reuses the
corrected v4.1 presentation functions for final page routes, graph construction,
Engram layers, BGE-M3 embeddings, deterministic retrieval, one Gemma writing
call, and output validation.

No live Postgres, Qdrant, or OpenSearch writes are performed. The original TIFF
ZIP and the corrected full-corpus v4 run are not modified.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

STATUS = "TRACE_NET_EXECUTIVE_TIFF_DEMO_FAST10_DEEP_V5_1"
VERSION = "v5.1"
DEFAULT_REPO = "/data/trace_net/repos/heico-ai-internship-summer-2026"
DEFAULT_SOURCE = "/data/trace_net/inputs/metadata.zip"
DEFAULT_TESSERACT = "/usr/bin/tesseract"
DEFAULT_OLLAMA = "http://127.0.0.1:11434"
DEFAULT_LLM_MODEL = "gemma4:26b"
DEFAULT_EMBED_MODEL = "bge-m3:latest"
DEFAULT_START_PAGE = 339
REQUIRED_PAGE_COUNT = 10
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

STAGE_INFO: dict[tuple[str, str], tuple[str, str, str]] = {
    ("ocr", "build"): ("1A", "Read and OCR the 10 selected TIFF pages", "Each selected scan is copied, hashed, and read with Tesseract."),
    ("ocr", "check"): ("1B", "Verify all 10 OCR results", "Page count, source hashes, OCR records, and safety flags must agree."),
    ("resolver", "build"): ("2A", "Measure the layout clues on each page", "Ink, text density, table structure, figures, and OCR confidence are measured."),
    ("resolver", "check"): ("2B", "Check the first page-type estimates", "The first classifier is checked before any page may continue."),
    ("four_route", "build"): ("3A", "Assign one simple page type", "Each page becomes normal text, table, image/diagram, or blank."),
    ("four_route", "check"): ("3B", "Verify the four-route assignments", "Every selected page must keep its source identity and use an allowed route."),
    ("validator", "build"): ("4A", "Validate uncertain page decisions", "Additional deterministic rules inspect pages that were not obvious initially."),
    ("validator", "check"): ("4B", "Check the validated decisions", "The validator confirms the decisions remain safe and automatic."),
    ("retry", "build"): ("5A", "Retry only unresolved pages", "Only unresolved pages receive a bounded second deterministic probe."),
    ("retry", "check"): ("5B", "Verify the final page decisions", "Each page must have either a validated retrieval route or a safe graph-only route."),
    ("storage", "build"): ("6A", "Prepare graph, vector, and exact-search records", "The same page creates different read-only records for different search jobs."),
    ("storage", "check"): ("6B", "Check storage eligibility", "Records are validated without writing to production databases."),
    ("loader", "build"): ("7A", "Create a dry-run loading plan", "TRACE-Net shows what would go to Postgres, Qdrant, and OpenSearch."),
    ("loader", "check"): ("7B", "Verify the loading plan", "The plan must remain read-only, safe, and source-traceable."),
    ("contract", "build"): ("8A", "Verify source lineage", "Every record must still point to one of the ten original TIFF pages."),
    ("contract", "check"): ("8B", "Check the lineage contracts", "Records without complete lineage cannot become trusted evidence."),
    ("retrieval_payload_audit", "build"): ("9A", "Build searchable evidence payloads", "The Discovery Machine receives route-specific evidence packages."),
    ("retrieval_payload_audit", "check"): ("9B", "Run the final ingestion gate", "Counts, routes, lineage, and zero-write rules are checked one last time."),
}


@dataclass(frozen=True)
class Fast10Paths:
    root: Path

    @property
    def subset_zip(self) -> Path:
        return self.root / "input" / "trace_net_fast10_deep_v5_source.zip"

    @property
    def subset_manifest(self) -> Path:
        return self.root / "input" / "trace_net_fast10_deep_v5_subset_manifest.json"

    @property
    def ocr_dir(self) -> Path:
        return self.root / "ocr_route_scan_pack_fast10_deep_v5"

    @property
    def resolver_dir(self) -> Path:
        return self.root / "route_confidence_resolver_fast10_deep_v5"

    @property
    def four_route_dir(self) -> Path:
        return self.root / "four_route_operational_resolver_fast10_deep_v5"

    @property
    def validator_dir(self) -> Path:
        return self.root / "route_validator_runner_fast10_deep_v5"

    @property
    def retry_dir(self) -> Path:
        return self.root / "route_unresolved_retry_probe_fast10_deep_v5"

    @property
    def storage_dir(self) -> Path:
        return self.root / "four_route_storage_gate_fast10_deep_v5"

    @property
    def loader_dir(self) -> Path:
        return self.root / "dry_run_loader_planner_fast10_deep_v5"

    @property
    def contract_dir(self) -> Path:
        return self.root / "loader_contract_audit_fast10_deep_v5"

    @property
    def payload_dir(self) -> Path:
        return self.root / "retrieval_payload_audit_fast10_deep_v5"

    @property
    def reports(self) -> dict[str, Path]:
        return {
            "ocr": self.ocr_dir / "trace_net_ocr_route_scan_pack_v1.json",
            "resolver": self.resolver_dir / "trace_net_route_confidence_resolver_v1.json",
            "four_route": self.four_route_dir / "trace_net_four_route_operational_resolver_v1.json",
            "validator": self.validator_dir / "trace_net_route_validator_runner_v1.json",
            "retry": self.retry_dir / "trace_net_route_unresolved_retry_probe_v1.json",
            "storage": self.storage_dir / "trace_net_four_route_storage_gate_v1.json",
            "loader": self.loader_dir / "trace_net_dry_run_loader_planner_v1.json",
            "contract": self.contract_dir / "trace_net_loader_contract_audit_v1.json",
            "retrieval_payload_audit": self.payload_dir / "trace_net_retrieval_payload_audit_v1.json",
        }


@dataclass(frozen=True)
class StageCommand:
    stage: str
    kind: str
    command: list[str]
    report: Path


@dataclass
class StageResult:
    return_code: int
    elapsed_seconds: float
    log_path: Path


def load_deep_module() -> Any:
    return importlib.import_module("run_trace_net_executive_tiff_demo_v4")


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
    minutes, seconds = divmod(value, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    return f"{minutes}m {seconds:02d}s"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return dict(value) if isinstance(value, Mapping) else {"value": value}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def page_number_from_member(name: str) -> int | None:
    values = [int(value) for value in re.findall(r"\d+", Path(name).name)]
    return values[-1] if values else None


def tiff_members(source_zip: Path) -> list[str]:
    with zipfile.ZipFile(source_zip) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith((".tif", ".tiff"))]
    return sorted(members, key=lambda name: (page_number_from_member(name) or 10**9, name))


def select_page_members(source_zip: Path, start_page: int, page_count: int = REQUIRED_PAGE_COUNT) -> list[str]:
    by_page: dict[int, str] = {}
    for member in tiff_members(source_zip):
        number = page_number_from_member(member)
        if number is not None and number not in by_page:
            by_page[number] = member
    requested = list(range(start_page, start_page + page_count))
    missing = [number for number in requested if number not in by_page]
    if missing:
        raise ValueError("Source ZIP is missing requested TIFF page(s): " + ", ".join(map(str, missing)))
    return [by_page[number] for number in requested]


def create_subset_zip(source_zip: Path, destination: Path, start_page: int) -> dict[str, Any]:
    selected = select_page_members(source_zip, start_page, REQUIRED_PAGE_COUNT)
    destination.parent.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    with zipfile.ZipFile(source_zip) as source, zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for member in selected:
            raw = source.read(member)
            total_bytes += len(raw)
            target.writestr(member, raw)
        target.writestr(
            "trace_net_fast10_deep_v5_subset_manifest.json",
            json.dumps(
                {
                    "mode": "fast10_deep_v5",
                    "source_package": str(source_zip),
                    "start_page": start_page,
                    "end_page": start_page + REQUIRED_PAGE_COUNT - 1,
                    "page_count": REQUIRED_PAGE_COUNT,
                    "selected_members": selected,
                },
                indent=2,
                sort_keys=True,
            ) + "\n",
        )
    return {
        "status": "TRACE_NET_FAST10_DEEP_V5_SUBSET_MADE",
        "mode": "fast10_deep_v5",
        "source_package": str(source_zip),
        "subset_package": str(destination),
        "start_page": start_page,
        "end_page": start_page + REQUIRED_PAGE_COUNT - 1,
        "page_count": REQUIRED_PAGE_COUNT,
        "uncompressed_tiff_bytes": total_bytes,
        "selected_members": selected,
        "original_source_modified": False,
    }


def ollama_models(base_url: str) -> tuple[bool, list[str], str]:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/api/tags", timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        models = [str(row.get("name") or "") for row in payload.get("models") or []]
        return True, models, ""
    except Exception as exc:
        return False, [], f"{type(exc).__name__}: {exc}"


def build_stage_plan(
    *,
    repo: Path,
    paths: Fast10Paths,
    python_bin: str,
    tesseract_cmd: str,
    psm_modes: str,
    request_timeout: int,
) -> list[StageCommand]:
    reports = paths.reports
    taxonomy = repo / "local_data/organization/trace_net/route_label_taxonomy/trace_net_route_label_taxonomy_v1.json"
    commands: list[StageCommand] = []

    def add(stage: str, kind: str, args: list[str]) -> None:
        commands.append(StageCommand(stage, kind, [python_bin, "-u", "-B", *args], reports[stage]))

    add("ocr", "build", [
        "scripts/build/ocr/build_trace_net_ocr_route_scan_pack_v1.py",
        "--source-package", str(paths.subset_zip),
        "--output-dir", str(paths.ocr_dir),
        "--run-tesseract", "--tesseract-cmd", tesseract_cmd,
        "--psm-modes", psm_modes,
        "--request-timeout", str(request_timeout),
        "--write-page-images",
    ])
    add("ocr", "check", [
        "scripts/maintenance/ocr/check_trace_net_ocr_route_scan_pack_v1_quality.py",
        "--report-path", str(reports["ocr"]), "--write-json",
        "--require-source-page-count", "10", "--min-route-records", "10", "--min-raw-image-hash-count", "10",
        "--require-comparison-manifest", "--max-unsafe", "0", "--require-no-answer-permission",
        "--require-no-source-truth-mutation", "--require-no-write-attempts",
    ])
    add("resolver", "build", [
        "scripts/build/router/build_trace_net_route_confidence_resolver_v1.py",
        "--scan-pack", str(reports["ocr"]), "--route-label-taxonomy", str(taxonomy),
        "--output-dir", str(paths.resolver_dir), "--high-threshold", "85", "--medium-threshold", "60",
    ])
    add("resolver", "check", [
        "scripts/maintenance/s6_retrieval/check_trace_net_route_confidence_resolver_v1_quality.py",
        "--report-path", str(reports["resolver"]), "--write-json", "--min-records", "10",
        "--min-auto-resolved", "0", "--min-multi-route-required", "0", "--min-validator-required", "0",
        "--max-cover-or-title-page-routes", "10", "--max-image-visual-diagram-routes", "10",
        "--require-source-quality-pass", "--require-no-human-review-required", "--max-unsafe", "0",
        "--require-no-answer-permission", "--require-no-source-truth-mutation", "--require-no-write-attempts",
    ])
    add("four_route", "build", [
        "scripts/build/ingestion/build_trace_net_four_route_operational_resolver_v1.py",
        "--route-confidence-resolver", str(reports["resolver"]), "--output-dir", str(paths.four_route_dir),
    ])
    add("four_route", "check", [
        "scripts/maintenance/s6_retrieval/check_trace_net_four_route_operational_resolver_v1_quality.py",
        "--report-path", str(reports["four_route"]), "--write-json", "--min-records", "10",
        "--min-auto-resolved", "0", "--min-validator-required", "0", "--min-multi-route-required", "0",
        "--require-source-quality-pass", "--require-four-operational-routes-only", "--require-no-human-review-required",
        "--max-unknown-subtypes", "0", "--max-unsafe", "0", "--require-no-answer-permission",
        "--require-no-source-truth-mutation", "--require-no-write-attempts",
    ])
    add("validator", "build", [
        "scripts/build/validation/build_trace_net_route_validator_runner_v1.py",
        "--four-route-resolver", str(reports["four_route"]), "--output-dir", str(paths.validator_dir),
    ])
    add("validator", "check", [
        "scripts/maintenance/s6_retrieval/check_trace_net_route_validator_runner_v1_quality.py",
        "--report-path", str(reports["validator"]), "--write-json", "--min-records", "10",
        "--min-validated", "0", "--min-unresolved", "0", "--min-qdrant-allowed", "0", "--min-opensearch-allowed", "0",
        "--require-source-quality-pass", "--require-no-human-review-required", "--require-decision-files",
        "--require-four-validated-routes-only", "--max-unsafe", "0", "--require-no-answer-permission",
        "--require-no-source-truth-mutation", "--require-no-write-attempts",
    ])
    add("retry", "build", [
        "scripts/build/ingestion/build_trace_net_route_unresolved_retry_probe_v1.py",
        "--route-validator-runner", str(reports["validator"]), "--output-dir", str(paths.retry_dir),
        "--quality",
    ])
    add("retry", "check", [
        "scripts/maintenance/s6_retrieval/check_trace_net_route_unresolved_retry_probe_v1_quality.py",
        "--report-path", str(reports["retry"]), "--write-json", "--min-records", "10",
        "--min-final-validated", "9", "--min-retry-validated", "0", "--max-remaining-unresolved", "1",
        "--require-source-quality-pass", "--require-no-human-review-required", "--require-decision-files",
        "--require-four-validated-routes-only", "--max-unsafe", "0", "--require-no-answer-permission",
        "--require-no-source-truth-mutation", "--require-no-write-attempts",
    ])
    add("storage", "build", [
        "scripts/build/ingestion/build_trace_net_four_route_storage_gate_v1.py",
        "--route-unresolved-retry-probe", str(reports["retry"]), "--output-dir", str(paths.storage_dir),
    ])
    add("storage", "check", [
        "scripts/maintenance/validation/check_trace_net_four_route_storage_gate_v1_quality.py",
        "--report-path", str(reports["storage"]), "--write-json", "--min-records", "10",
        "--min-postgres-graph-records", "10", "--min-qdrant-allowed", "0", "--min-opensearch-allowed", "0",
        "--max-final-do-not-embed", "10", "--require-source-quality-pass", "--require-decision-files",
        "--require-no-human-review-required", "--max-unsafe", "0", "--require-no-answer-permission",
        "--require-no-source-truth-mutation", "--require-no-write-attempts",
    ])
    add("loader", "build", [
        "scripts/build/operations/build_trace_net_dry_run_loader_planner_v1.py",
        "--four-route-storage-gate", str(reports["storage"]), "--output-dir", str(paths.loader_dir),
    ])
    add("loader", "check", [
        "scripts/maintenance/core/check_trace_net_dry_run_loader_planner_v1_quality.py",
        "--report-path", str(reports["loader"]), "--write-json", "--min-records", "10",
        "--min-postgres-plans", "10", "--min-qdrant-plans", "0", "--min-opensearch-plans", "0",
        "--max-blocked-records", "10", "--require-source-quality-pass", "--require-decision-files",
        "--require-dry-run-only", "--require-no-human-review-required", "--max-unsafe", "0",
        "--require-no-answer-permission", "--require-no-source-truth-mutation", "--require-no-write-attempts",
    ])
    add("contract", "build", [
        "scripts/build/core/build_trace_net_loader_contract_audit_v1.py",
        "--dry-run-loader-planner", str(reports["loader"]), "--ocr-route-scan-pack", str(reports["ocr"]),
        "--output-dir", str(paths.contract_dir),
    ])
    add("contract", "check", [
        "scripts/maintenance/core/check_trace_net_loader_contract_audit_v1_quality.py",
        "--report-path", str(reports["contract"]), "--write-json", "--min-records", "10",
        "--min-lineage-ready", "10", "--max-missing-lineage", "0", "--min-postgres-contract-ready", "10",
        "--min-qdrant-contract-ready", "0", "--min-opensearch-contract-ready", "0",
        "--require-source-quality-pass", "--require-dry-run-only", "--require-no-human-review-required",
        "--max-unsafe", "0", "--require-no-answer-permission", "--require-no-source-truth-mutation",
        "--require-no-write-attempts",
    ])
    add("retrieval_payload_audit", "build", [
        "scripts/benchmark/s6_retrieval/build_trace_net_retrieval_payload_audit_v1.py",
        "--loader-contract-audit", str(reports["contract"]), "--ocr-route-scan-pack", str(reports["ocr"]),
        "--output-dir", str(paths.payload_dir),
    ])
    add("retrieval_payload_audit", "check", [
        "scripts/benchmark/s6_retrieval/check_trace_net_retrieval_payload_audit_v1_quality.py",
        "--report-path", str(reports["retrieval_payload_audit"]), "--write-json", "--min-records", "10",
        "--min-route-separation-pass", "0", "--min-qdrant-payloads", "0", "--min-opensearch-payloads", "0",
        "--max-violation-records", "0", "--require-source-quality-pass", "--require-no-human-review-required",
        "--max-unsafe", "0", "--require-no-answer-permission", "--require-no-source-truth-mutation",
        "--require-no-write-attempts",
    ])
    return commands


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
        values.update(root.rglob(pattern))
    return sorted(values, key=lambda path: (page_number_from_member(path.name) or 10**9, path.name))


def run_stage(command: StageCommand, paths: Fast10Paths, heartbeat_seconds: int) -> StageResult:
    number, title, explanation = STAGE_INFO[(command.stage, command.kind)]
    subheading(f"STEP {number} — {title}")
    print(f"Easy explanation: {explanation}", flush=True)
    print(color("Progress: starting now...", YELLOW), flush=True)

    log_dir = paths.root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{number}_{command.stage}_{command.kind}.log"
    started = time.monotonic()
    seen_pages: set[int] = set()
    last_heartbeat = started

    with log_path.open("w", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            command.command,
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
            if item is None:
                reader_done = True
                continue
            now = time.monotonic()

            if command.stage == "ocr" and command.kind == "build":
                for path in page_files(paths.ocr_dir):
                    page_number = page_number_from_member(path.name)
                    if page_number is None or page_number in seen_pages or len(seen_pages) >= REQUIRED_PAGE_COUNT:
                        continue
                    seen_pages.add(page_number)
                    print(
                        color(
                            f"OCR PROGRESS {len(seen_pages):02d}/10 — manual page {page_number} prepared — {path.name}",
                            MAGENTA,
                        ),
                        flush=True,
                    )

            if item != "__WAIT__" and (item.startswith("Quality status:") or item.startswith("Status:")):
                print(color(item, GREEN if "PASS" in item else YELLOW), flush=True)

            if now - last_heartbeat >= heartbeat_seconds:
                if command.stage == "ocr" and command.kind == "build":
                    print(color(f"Still working — OCR pages observed {len(seen_pages)}/10 | elapsed {format_elapsed(now - started)}", YELLOW), flush=True)
                else:
                    print(color(f"Still working — {title} | elapsed {format_elapsed(now - started)}", YELLOW), flush=True)
                last_heartbeat = now

        reader.join(timeout=3)
        return_code = int(process.returncode or 0)

    elapsed = time.monotonic() - started
    if return_code == 0:
        print(color(f"✓ STEP {number} finished in {format_elapsed(elapsed)}", GREEN), flush=True)
    else:
        print(color(f"⚠ STEP {number} reported a problem after {format_elapsed(elapsed)}", RED), flush=True)
        print(f"Technical log: {log_path}")
        try:
            recent = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
            for value in recent:
                print(color(value, DIM))
        except Exception:
            pass
    return StageResult(return_code, elapsed, log_path)


def summary_of(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = payload.get("summary")
    return dict(value) if isinstance(value, Mapping) else {}


def first_count(summary: Mapping[str, Any], keys: Sequence[str]) -> int:
    for key in keys:
        value = summary.get(key)
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return 0


def print_stage_checkpoint(stage: str, report: Path) -> None:
    if not report.is_file():
        print(color("Checkpoint report was not created.", RED))
        return
    payload = read_json(report)
    summary = summary_of(payload)
    print(f"Easy-English checkpoint: {stage} quality = {payload.get('quality_status')}")
    if stage == "ocr":
        print(f"  Pages represented: {first_count(summary, ('route_record_count', 'record_count', 'page_record_count', 'source_page_count'))}")
        print(f"  Pages with OCR text: {first_count(summary, ('page_with_ocr_text_count', 'ocr_success_count', 'ocr_text_ready_count'))}")
    elif stage in {"resolver", "four_route", "validator", "retry"}:
        routes = summary.get("final_validated_route_counts") or summary.get("primary_route_counts") or summary.get("route_counts")
        print(f"  Current page-route counts: {routes or {}}")
    elif stage == "storage":
        print(f"  Graph-ready page records: {first_count(summary, ('postgres_graph_record_count',))}")
        print(f"  Vector-eligible page records: {first_count(summary, ('qdrant_embedding_allowed_count',))}")
        print(f"  Exact-search page records: {first_count(summary, ('opensearch_index_allowed_count',))}")
    elif stage == "loader":
        print(f"  Dry-run Postgres plans: {first_count(summary, ('postgres_dry_run_plan_count',))}")
        print(f"  Dry-run Qdrant plans: {first_count(summary, ('qdrant_dry_run_plan_count',))}")
        print(f"  Dry-run OpenSearch plans: {first_count(summary, ('opensearch_dry_run_plan_count',))}")
    elif stage == "contract":
        print(f"  Records with complete source lineage: {first_count(summary, ('lineage_ready_count',))}")
        print(f"  Missing source lineage: {first_count(summary, ('missing_lineage_count',))}")
    elif stage == "retrieval_payload_audit":
        print(f"  Vector payloads: {first_count(summary, ('qdrant_payload_count',))}")
        print(f"  Exact-search payloads: {first_count(summary, ('opensearch_payload_count',))}")
        print(f"  Safety violations: {first_count(summary, ('violation_record_count',))}")


def build_ingestion_summary(paths: Fast10Paths, stage_results: Sequence[tuple[StageCommand, StageResult]]) -> dict[str, Any]:
    payloads: dict[str, dict[str, Any]] = {}
    for stage, path in paths.reports.items():
        if path.is_file():
            payloads[stage] = read_json(path)
    statuses = {stage: payload.get("quality_status") for stage, payload in payloads.items()}
    all_commands_pass = len(stage_results) == len(STAGE_INFO) and all(result.return_code == 0 for _, result in stage_results)
    all_reports_pass = len(payloads) == 9 and all(status == "PASS" for status in statuses.values())
    retry = summary_of(payloads.get("retry") or {})
    storage = summary_of(payloads.get("storage") or {})
    contract = summary_of(payloads.get("contract") or {})
    retrieval = summary_of(payloads.get("retrieval_payload_audit") or {})
    write_attempt_count = sum(
        first_count(summary_of(payload), (
            "write_attempt_count", "postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"
        ))
        for payload in payloads.values()
    )
    failures: list[str] = []
    if not all_commands_pass:
        failures.append("one or more chronological stage commands did not pass")
    if not all_reports_pass:
        failures.append("one or more of the nine stage reports is missing or not PASS")
    fully_validated_route_count = first_count(retry, ("final_validated_route_count",))
    validator_gated_graph_only_count = first_count(retry, ("remaining_validator_gated_unresolved_count",))
    safely_routed_page_count = fully_validated_route_count + validator_gated_graph_only_count
    if safely_routed_page_count != 10:
        failures.append("validated plus graph-only routed page count is not 10")
    if validator_gated_graph_only_count > 1:
        failures.append("more than one page remained validator-gated in the focused demo")
    if first_count(storage, ("postgres_graph_record_count",)) != 10:
        failures.append("graph-ready page record count is not 10")
    if first_count(storage, ("invalid_operational_route_count",)) != 0:
        failures.append("one or more storage records has an invalid operational route")
    if first_count(contract, ("lineage_ready_count",)) != 10:
        failures.append("lineage-ready record count is not 10")
    if first_count(contract, ("missing_lineage_count",)) != 0:
        failures.append("one or more records is missing source lineage")
    if write_attempt_count:
        failures.append("a live database write attempt was recorded")
    return {
        "status": "TRACE_NET_FAST10_DEEP_V5_INGESTION_SUMMARY",
        "quality_status": "PASS" if not failures else "FAIL",
        "selected_page_count": 10,
        "stage_quality_statuses": statuses,
        "stage_report_count": len(payloads),
        "final_validated_route_counts": dict(storage.get("final_validated_route_counts") or retry.get("final_validated_route_counts") or {}),
        "fully_validated_route_count": fully_validated_route_count,
        "validator_gated_graph_only_count": validator_gated_graph_only_count,
        "safely_routed_page_count": safely_routed_page_count,
        "lineage_ready_count": first_count(contract, ("lineage_ready_count",)),
        "missing_lineage_count": first_count(contract, ("missing_lineage_count",)),
        "postgres_graph_record_count": first_count(storage, ("postgres_graph_record_count",)),
        "qdrant_payload_count": first_count(retrieval, ("qdrant_payload_count",)),
        "opensearch_payload_count": first_count(retrieval, ("opensearch_payload_count",)),
        "write_attempt_count": write_attempt_count,
        "failures": failures,
        "live_database_writes_enabled": False,
    }


def validator_gated_page_ids(storage_payload: Mapping[str, Any]) -> set[str]:
    """Return pages that have a display route but remain graph-only for safety."""
    page_ids: set[str] = set()
    for record in storage_payload.get("records") or []:
        if not isinstance(record, Mapping):
            continue
        if bool(record.get("validator_gated")) or str(record.get("storage_decision") or "") == "graph_only_validator_gated":
            page_id = str(record.get("page_id") or "").strip()
            if page_id:
                page_ids.add(page_id)
    return page_ids


def print_v5_classifications(deep: Any, records: Sequence[Any], expected_count: int, graph_only_ids: set[str]) -> None:
    deep.banner(
        "PAGE-BY-PAGE CLASSIFICATION",
        "Every page receives a visible type. Low-confidence pages remain graph-only and cannot become direct retrieval evidence.",
    )
    for index, row in enumerate(records, start=1):
        route = deep.canonical_operational_route(row.route)
        suffix = " — GRAPH-ONLY SAFETY HOLD" if row.page_id in graph_only_ids else " — VALIDATED FOR NORMAL PROCESSING"
        print(
            f"CLASSIFY {index:02d}/{expected_count:02d} — {row.page_id} -> {deep.route_label(route)}{suffix}",
            flush=True,
        )


def build_v5_embeddings(
    deep: Any,
    output_dir: Path,
    records: Sequence[Any],
    graph_only_ids: set[str],
    ollama_url: str,
    model: str,
    timeout: float,
    max_chars: int,
) -> list[Any]:
    deep.banner(
        "PAGE-BY-PAGE EMBEDDINGS",
        "BGE-M3 converts validated searchable pages into meaning vectors. Graph-only safety-hold pages are visibly skipped.",
    )
    results: list[Any] = []
    total = len(records)
    for index, row in enumerate(records, start=1):
        text = re.sub(r"\s+", " ", row.text).strip()
        if row.page_id in graph_only_ids:
            result = deep.EmbeddingRecord(row.page_id, row.page_number, row.route, "SKIP_VALIDATOR_GATED", 0, 0.0, len(text), [])
            results.append(result)
            print(
                f"EMBED {index:02d}/{total:02d} — {row.page_id} -> SKIPPED (validator-gated graph-only safety hold)",
                flush=True,
            )
            continue
        if not text:
            result = deep.EmbeddingRecord(row.page_id, row.page_number, row.route, "SKIP_NO_TEXT", 0, 0.0, 0, [])
            results.append(result)
            print(f"EMBED {index:02d}/{total:02d} — {row.page_id} -> SKIPPED (no OCR text)", flush=True)
            continue
        prepared = text[:max_chars]
        try:
            vector = deep.embed_text(ollama_url, model, prepared, timeout)
            status = "PASS" if vector else "FAIL_EMPTY_VECTOR"
        except Exception as exc:
            vector = []
            status = f"FAIL_{type(exc).__name__}"
        result = deep.EmbeddingRecord(
            page_id=row.page_id,
            page_number=row.page_number,
            route=row.route,
            status=status,
            dimension=len(vector),
            vector_norm=round(deep.vector_norm(vector), 6),
            text_char_count=len(prepared),
            vector=vector,
        )
        results.append(result)
        print(
            f"EMBED {index:02d}/{total:02d} — {row.page_id} -> {status} "
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
    deep.write_jsonl(path, rows)
    summary = {
        "status": "TRACE_NET_DEMO_EMBEDDINGS_MADE",
        "model": model,
        "record_count": len(results),
        "embedded_count": sum(1 for item in results if item.status == "PASS"),
        "skipped_count": sum(1 for item in results if item.status.startswith("SKIP")),
        "validator_gated_skip_count": sum(1 for item in results if item.status == "SKIP_VALIDATOR_GATED"),
        "failed_count": sum(1 for item in results if item.status.startswith("FAIL")),
        "dimensions": sorted({item.dimension for item in results if item.dimension}),
        "path": str(path),
        "qdrant_write_attempt": False,
    }
    deep.write_json(output_dir / "trace_net_demo_embedding_summary_v4.json", summary)
    print()
    print(color(f"✓ EMBEDDING FILE MADE — {summary['embedded_count']}/{len(results)} pages embedded", GREEN))
    if graph_only_ids:
        print(color(f"✓ SAFETY HOLD ENFORCED — {len(graph_only_ids)} page skipped from embedding", GREEN))
    print(f"Embedding file: {path}")
    return results


def copy_if_present(source: Path, destination: Path) -> None:
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def write_v5_html(deep: Any, path: Path, source: Path, page_records: Sequence[Any], graph: Mapping[str, Any], engram: Mapping[str, Any], embeddings: Mapping[str, Any], questions: Sequence[Mapping[str, Any]], ingestion: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(".temporary.html")
    deep.make_html_report(temporary, source, page_records, graph, engram, embeddings, questions, ingestion)
    content = temporary.read_text(encoding="utf-8")
    content = content.replace("TRACE-Net Deep Executive Demo v4", "TRACE-Net Fast10 Deep Executive Demo v5")
    content = content.replace("TRACE-Net executive demo v4", "TRACE-Net fast10 deep executive demo v5")
    content = content.replace(
        "<main>",
        "<main><div class='card'><h2>Focused demonstration subset</h2><p><strong>This run processed exactly 10 original TIFF pages.</strong></p><p>It demonstrates the full chronology quickly and is not presented as a full-corpus benchmark.</p></div>",
        1,
    )
    path.write_text(content, encoding="utf-8")
    temporary.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--source-package", default=DEFAULT_SOURCE)
    parser.add_argument("--tesseract-cmd", default=DEFAULT_TESSERACT)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA)
    parser.add_argument("--llm-model", default=DEFAULT_LLM_MODEL)
    parser.add_argument("--embedding-model", default=DEFAULT_EMBED_MODEL)
    parser.add_argument("--start-page", type=int, default=DEFAULT_START_PAGE)
    parser.add_argument("--question", action="append", dest="questions")
    parser.add_argument("--output-dir")
    parser.add_argument("--heartbeat-seconds", type=int, default=5)
    parser.add_argument("--psm-modes", default="3,6,11")
    parser.add_argument("--ocr-timeout", type=int, default=240)
    parser.add_argument("--request-timeout", type=int, default=1200)
    parser.add_argument("--llm-max-tokens", type=int, default=4096)
    parser.add_argument("--embedding-max-chars", type=int, default=6000)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--skip-ingestion", action="store_true", help="Reuse a completed v5 --output-dir.")
    parser.add_argument("--skip-embeddings", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    repo = Path(args.repo).resolve()
    source = Path(args.source_package).resolve()
    tesseract = shutil.which(args.tesseract_cmd) or (args.tesseract_cmd if Path(args.tesseract_cmd).is_file() else "")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir or f"/data/trace_net_runs/executive_fast10_deep_v5_{stamp}").resolve()
    paths = Fast10Paths(output_dir)
    paths.root.mkdir(parents=True, exist_ok=True)
    questions = tuple(args.questions or DEFAULT_QUESTIONS)

    banner(
        "TRACE-NET EXECUTIVE DEMONSTRATION — DEEP 10-PAGE MODE v5.1",
        "10 TIFFs → OCR → final page routes → graph → Engram → embeddings → deterministic retrieval → Gemma → validation",
    )
    print("This is a separate v5.1 presentation mode.")
    print("The corrected full 509-page v4.1 demo remains installed and unchanged.")
    print(color("This run demonstrates the full process on exactly 10 original pages; it is not a full-corpus benchmark.", YELLOW))
    print("Private model chain-of-thought is not displayed. The auditable code decisions, evidence, model call, and validators are shown.")

    banner("PRE-DEMO CHECK")
    can_run = True
    if repo.is_dir():
        print(color(f"✓ Repository found: {repo}", GREEN))
    else:
        print(color(f"✗ Repository missing: {repo}", RED))
        can_run = False
    if source.is_file() and zipfile.is_zipfile(source):
        print(color(f"✓ Original TIFF ZIP found: {source}", GREEN))
        print(f"  Pages selected for this run: {args.start_page}–{args.start_page + 9}")
    else:
        print(color(f"✗ TIFF ZIP missing or invalid: {source}", RED))
        can_run = False
    if tesseract:
        print(color(f"✓ Tesseract found: {tesseract}", GREEN))
    else:
        print(color(f"✗ Tesseract missing: {args.tesseract_cmd}", RED))
        can_run = False

    try:
        deep = load_deep_module()
        if getattr(deep, "VERSION", "") not in {"v4.1", "v4.2"}:
            print(color(f"⚠ Deep module version is {getattr(deep, 'VERSION', 'unknown')}; v4.1 or later is recommended.", YELLOW))
        else:
            print(color(f"✓ Corrected deep classifier module found: {deep.VERSION}", GREEN))
    except Exception as exc:
        print(color(f"✗ Corrected v4.1 deep module could not be imported: {type(exc).__name__}: {exc}", RED))
        can_run = False
        deep = None

    ollama_ok, models, ollama_error = ollama_models(args.ollama_url)
    if ollama_ok:
        print(color("✓ Ollama is running", GREEN))
        print(f"  Gemma available: {args.llm_model in models}")
        print(f"  BGE-M3 available: {args.embedding_model in models}")
    else:
        print(color("⚠ Ollama is not responding", YELLOW))
        print(f"  Details: {ollama_error}")

    if not can_run or deep is None:
        banner("DEMO COULD NOT START")
        print("A required local file or program is missing. PuTTY remains open.")
        return

    manifest: dict[str, Any]
    if not args.skip_ingestion:
        banner("STEP 0 — CREATE A TEMPORARY 10-PAGE SOURCE PACKAGE")
        print(f"Selecting original pages {args.start_page} through {args.start_page + 9}.")
        print("The pages are copied into a new mini ZIP. The 509-page source ZIP is not changed.")
        try:
            manifest = create_subset_zip(source, paths.subset_zip, args.start_page)
        except Exception as exc:
            print(color(f"Could not create the ten-page package: {type(exc).__name__}: {exc}", RED))
            print("PuTTY remains open.")
            return
        write_json(paths.subset_manifest, manifest)
        print(color("✓ 10-PAGE SOURCE PACKAGE MADE", GREEN))
        for index, member in enumerate(manifest["selected_members"], start=1):
            print(f"  SOURCE PAGE {index:02d}/10 — original manual page {page_number_from_member(member)} — {member}")
    else:
        if not paths.subset_manifest.is_file():
            banner("EXISTING V5 RUN IS INCOMPLETE")
            print(f"Subset manifest not found: {paths.subset_manifest}")
            print("PuTTY remains open.")
            return
        manifest = read_json(paths.subset_manifest)
        banner("STEP 0 — REUSE THE EXISTING 10-PAGE SOURCE PACKAGE")
        print(f"Existing v5 run folder: {output_dir}")

    os.chdir(repo)
    current_pythonpath = os.environ.get("PYTHONPATH", "")
    os.environ["PYTHONPATH"] = f"{repo / 'scripts'}:{repo}" + (f":{current_pythonpath}" if current_pythonpath else "")
    python_bin = str(Path(os.environ.get("VIRTUAL_ENV", "/home/jwild/rag-workspace/.venv")) / "bin" / "python")
    if not Path(python_bin).is_file():
        python_bin = shutil.which("python") or "python"

    stage_results: list[tuple[StageCommand, StageResult]] = []
    if not args.skip_ingestion:
        banner("PART 1 — PROCESS ALL 10 PAGES IN CHRONOLOGICAL ORDER")
        print("Every build operation is immediately followed by its quality and safety check.")
        commands = build_stage_plan(
            repo=repo,
            paths=paths,
            python_bin=python_bin,
            tesseract_cmd=str(tesseract),
            psm_modes=args.psm_modes,
            request_timeout=args.ocr_timeout,
        )
        for command in commands:
            result = run_stage(command, paths, max(2, args.heartbeat_seconds))
            stage_results.append((command, result))
            print_stage_checkpoint(command.stage, command.report)
            if result.return_code != 0:
                print(color("Later stages were not started because this stage must pass first.", RED))
                break
    else:
        stage_results = [
            (StageCommand(stage, "build", [], path), StageResult(0, 0.0, path))
            for stage, path in paths.reports.items()
        ]
        # Two records per stage are expected by the summary's command count. Add
        # synthetic successful check entries only for reuse bookkeeping.
        stage_results = [
            pair
            for stage, path in paths.reports.items()
            for pair in (
                (StageCommand(stage, "build", [], path), StageResult(0, 0.0, path)),
                (StageCommand(stage, "check", [], path), StageResult(0, 0.0, path)),
            )
        ]

    ingestion = build_ingestion_summary(paths, stage_results)
    write_json(output_dir / "trace_net_fast10_deep_v5_ingestion_summary.json", ingestion)
    if ingestion["quality_status"] != "PASS":
        banner("10-PAGE INGESTION DID NOT PASS")
        for failure in ingestion["failures"]:
            print(f"  • {failure}")
        print("PuTTY remains open. The full v4.1 run was not changed.")
        return

    ocr_payload = read_json(paths.reports["ocr"])
    route_payload = read_json(paths.reports["retry"])
    storage_payload = read_json(paths.reports["storage"])
    retrieval_payload = read_json(paths.reports["retrieval_payload_audit"])
    ocr_records = deep.extract_page_records(ocr_payload)
    route_records = deep.extract_page_records(route_payload)
    storage_records = deep.extract_page_records(storage_payload)
    page_records = deep.merge_page_records(ocr_records, route_records, storage_records)

    deep.print_ocr_results(ocr_records or page_records, 10)
    gate = deep.classification_gate(page_records, 10)
    gate["status"] = "TRACE_NET_FAST10_DEEP_V5_CLASSIFICATION_GATE"
    write_json(output_dir / "trace_net_fast10_deep_v5_classification_gate.json", gate)
    if gate["quality_status"] != "PASS":
        banner("10-PAGE CLASSIFICATION GATE FAILED")
        print("The demo will not display UNKNOWN page types or build misleading graph/Engram output.")
        for failure in gate["failures"]:
            print(f"  • {failure}")
        print("PuTTY remains open. The corrected 509-page v4.1 run was not changed.")
        return

    print(color("✓ CLASSIFICATION GATE PASSED — 10/10 pages have one final route", GREEN))
    print(f"  Blank pages: {gate['route_counts']['blank']}")
    print(f"  Normal text pages: {gate['route_counts']['plain_text']}")
    print(f"  Table/IPL pages: {gate['route_counts']['table']}")
    print(f"  Image/diagram pages: {gate['route_counts']['image']}")
    graph_only_ids = validator_gated_page_ids(storage_payload)
    print_v5_classifications(deep, page_records, 10, graph_only_ids)
    if graph_only_ids:
        print()
        print(color("SAFETY EXPLANATION", BOLD + YELLOW))
        print("The page still receives a visible document type, but it remains graph-only because its retry confidence did not meet the retrieval threshold.")
        print("It is not embedded, not exact-indexed, and not allowed to act as direct answer evidence.")
        print(f"Graph-only page IDs: {sorted(graph_only_ids)}")

    graph = deep.build_graph_snapshot(output_dir, paths.subset_zip, page_records)
    copy_if_present(output_dir / "trace_net_demo_graph_nodes_v4.jsonl", output_dir / "trace_net_fast10_deep_v5_graph_nodes.jsonl")
    copy_if_present(output_dir / "trace_net_demo_graph_edges_v4.jsonl", output_dir / "trace_net_fast10_deep_v5_graph_edges.jsonl")
    copy_if_present(output_dir / "trace_net_demo_graph_summary_v4.json", output_dir / "trace_net_fast10_deep_v5_graph_summary.json")

    engram = deep.build_engram_layers(output_dir, page_records, graph, ingestion)
    copy_if_present(output_dir / "trace_net_demo_engram_layers_v4.json", output_dir / "trace_net_fast10_deep_v5_engram_layers.json")

    embedding_records: list[Any] = []
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
        embedding_records = build_v5_embeddings(
            deep,
            output_dir,
            page_records,
            graph_only_ids,
            args.ollama_url,
            args.embedding_model,
            args.request_timeout,
            args.embedding_max_chars,
        )
        embedding_summary = read_json(output_dir / "trace_net_demo_embedding_summary_v4.json")
        copy_if_present(output_dir / "trace_net_demo_page_embeddings_v4.jsonl", output_dir / "trace_net_fast10_deep_v5_page_embeddings.jsonl")
        copy_if_present(output_dir / "trace_net_demo_embedding_summary_v4.json", output_dir / "trace_net_fast10_deep_v5_embedding_summary.json")
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
        print("Every question uses only evidence created from these 10 selected pages.")
        for question_index, question in enumerate(questions, start=1):
            try:
                result = deep.print_question_process(
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
            write_json(output_dir / f"trace_net_fast10_deep_v5_question_{question_index:02d}.json", result)
            question_results.append(result)
    else:
        banner("QUESTION STAGE WAS NOT STARTED")
        if not ollama_ok:
            print("Reason: Ollama is not responding.")
        else:
            print(f"Reason: model {args.llm_model} is not installed.")

    html_path = output_dir / "trace_net_executive_fast10_deep_v5.html"
    try:
        write_v5_html(deep, html_path, paths.subset_zip, page_records, graph, engram, embedding_summary, question_results, ingestion)
    except Exception as exc:
        print(color(f"HTML report could not be created: {type(exc).__name__}: {exc}", YELLOW))

    overall_pass = (
        ingestion["quality_status"] == "PASS"
        and gate["quality_status"] == "PASS"
        and len(page_records) == 10
        and all(result.get("quality_status") == "PASS" for result in question_results)
        and bool(question_results)
    )
    final_manifest = {
        "status": STATUS,
        "version": VERSION,
        "quality_status": "PASS" if overall_pass else "FAIL",
        "mode": "fast10_deep",
        "subset": manifest,
        "ingestion_summary": str(output_dir / "trace_net_fast10_deep_v5_ingestion_summary.json"),
        "classification_gate": str(output_dir / "trace_net_fast10_deep_v5_classification_gate.json"),
        "graph_nodes": str(output_dir / "trace_net_fast10_deep_v5_graph_nodes.jsonl"),
        "graph_edges": str(output_dir / "trace_net_fast10_deep_v5_graph_edges.jsonl"),
        "engram_layers": str(output_dir / "trace_net_fast10_deep_v5_engram_layers.json"),
        "embedding_records": str(output_dir / "trace_net_fast10_deep_v5_page_embeddings.jsonl"),
        "html_report": str(html_path),
        "question_count": len(question_results),
        "question_pass_count": sum(1 for result in question_results if result.get("quality_status") == "PASS"),
        "page_count": len(page_records),
        "unknown_page_count": gate["unclassified_page_count"],
        "fully_validated_route_count": ingestion.get("fully_validated_route_count"),
        "validator_gated_graph_only_count": ingestion.get("validator_gated_graph_only_count"),
        "production_database_writes": False,
        "original_source_modified": False,
        "full_v4_1_demo_modified": False,
    }
    write_json(output_dir / "trace_net_executive_fast10_deep_v5_manifest.json", final_manifest)

    banner("DEEP 10-PAGE DEMONSTRATION COMPLETE")
    print(f"Overall result: {final_manifest['quality_status']}")
    print(f"Pages processed: {len(page_records)}/10")
    print(f"Unknown page types: {gate['unclassified_page_count']}")
    print(f"Fully validated retrieval routes: {ingestion.get('fully_validated_route_count')}/10")
    print(f"Graph-only safety holds: {ingestion.get('validator_gated_graph_only_count')}")
    print(f"Graph nodes: {graph.get('node_count')}")
    print(f"Graph edges: {graph.get('edge_count')}")
    print(f"Engram layers made: {len(engram.get('layers') or [])}/6")
    print(f"Page embeddings made: {embedding_summary.get('embedded_count')}")
    print(f"Questions passed: {final_manifest['question_pass_count']}/{final_manifest['question_count']}")
    print(f"Output folder: {output_dir}")
    print(f"HTML report: {html_path}")
    print("Corrected full 509-page v4.1 demo modified: false")
    print("Production database writes: 0")
    print("PuTTY remains open.")


if __name__ == "__main__":
    main()
