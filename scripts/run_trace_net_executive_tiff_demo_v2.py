#!/usr/bin/env python3
"""Executive-friendly TRACE-Net raw TIFF -> answer demo.

This wrapper does not modify TRACE-Net logic. It runs the repository's canonical
pipeline in chronological order and translates each technical stage into plain
English while it is running.

It never calls shell `exit`, never enables `set -e`/`set -u`, and does not touch
live Postgres, Qdrant, or OpenSearch databases.
"""
from __future__ import annotations

import argparse
import html
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
from typing import Any, Iterable

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
BLUE = "\033[34m"

PIPELINE_STEPS = {
    ("ocr", "build"): (
        "1A",
        "Read every raw TIFF page and run OCR",
        "The server opens the scanned pages and converts visible text into searchable text.",
    ),
    ("ocr", "check"): (
        "1B",
        "Check the OCR results",
        "TRACE-Net verifies page count, image hashes, and safety flags before continuing.",
    ),
    ("resolver", "build"): (
        "2A",
        "Measure what each page looks like",
        "The system uses ink, layout, OCR, table, and figure clues to estimate the page type.",
    ),
    ("resolver", "check"): (
        "2B",
        "Check the first page-type decisions",
        "TRACE-Net verifies that the confidence rules behaved safely and consistently.",
    ),
    ("four_route", "build"): (
        "3A",
        "Place each page into a simple route",
        "Each page becomes blank, normal text, table, or image/diagram so the right tools handle it.",
    ),
    ("four_route", "check"): (
        "3B",
        "Check the route assignments",
        "The system confirms that all 509 pages received an allowed route.",
    ),
    ("validator", "build"): (
        "4A",
        "Validate uncertain pages",
        "Extra rules examine pages that were not obvious on the first pass.",
    ),
    ("validator", "check"): (
        "4B",
        "Check the validated decisions",
        "TRACE-Net confirms that the page decisions are usable without human review.",
    ),
    ("retry", "build"): (
        "5A",
        "Retry the difficult pages",
        "Only unresolved pages receive a bounded second look; clear pages are not reprocessed.",
    ),
    ("retry", "check"): (
        "5B",
        "Check the retry results",
        "The system verifies that the retry step did not weaken safety or lineage.",
    ),
    ("storage", "build"): (
        "6A",
        "Decide where each page record belongs",
        "TRACE-Net prepares graph records, vector-search records, and exact-search records.",
    ),
    ("storage", "check"): (
        "6B",
        "Check the storage decisions",
        "This demo validates the records but does not write to production databases.",
    ),
    ("loader", "build"): (
        "7A",
        "Create a safe loading plan",
        "The system shows what would be sent to Postgres, Qdrant, and OpenSearch.",
    ),
    ("loader", "check"): (
        "7B",
        "Check the loading plan",
        "TRACE-Net confirms there are no accidental database writes or unsafe records.",
    ),
    ("contract", "build"): (
        "8A",
        "Verify source lineage",
        "Every prepared record must still point back to the original manual page.",
    ),
    ("contract", "check"): (
        "8B",
        "Check the source-lineage contracts",
        "The system confirms the records are traceable before they may support retrieval.",
    ),
    ("retrieval_payload_audit", "build"): (
        "9A",
        "Build the searchable evidence packages",
        "TRACE-Net creates the exact payloads the Discovery Machine can search later.",
    ),
    ("retrieval_payload_audit", "check"): (
        "9B",
        "Check the searchable evidence packages",
        "The final ingestion gate verifies counts, routes, lineage, and zero write attempts.",
    ),
}

STAGE_LINE = re.compile(r"^\[([a-zA-Z0-9_]+)\]\s+(build|check):")


@dataclass
class RunResult:
    return_code: int
    elapsed_seconds: float
    current_step: str


def color(text: str, code: str) -> str:
    return f"{code}{text}{RESET}"


def line(char: str = "=", width: int = 88) -> None:
    print(color(char * width, DIM), flush=True)


def banner(title: str, subtitle: str = "") -> None:
    print()
    line()
    print(color(title, BOLD + CYAN), flush=True)
    if subtitle:
        print(subtitle, flush=True)
    line()


def plain_step(number: str, title: str, explanation: str) -> None:
    print()
    print(color(f"STEP {number} — {title}", BOLD + BLUE), flush=True)
    print(f"What this means: {explanation}", flush=True)


def format_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    return f"{minutes}m {seconds:02d}s"


def _reader(stream: Any, output_queue: queue.Queue[str | None], log_handle: Any) -> None:
    try:
        for raw in iter(stream.readline, ""):
            log_handle.write(raw)
            log_handle.flush()
            output_queue.put(raw.rstrip("\n"))
    finally:
        output_queue.put(None)


def run_pipeline_with_narration(command: list[str], log_path: Path, heartbeat_seconds: int = 15) -> RunResult:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    current_key: tuple[str, str] | None = None
    current_title = "Starting the pipeline"
    last_event = started

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
        thread = threading.Thread(
            target=_reader,
            args=(process.stdout, output_queue, log_handle),
            daemon=True,
        )
        thread.start()

        reader_finished = False
        while process.poll() is None or not reader_finished:
            try:
                item = output_queue.get(timeout=1)
            except queue.Empty:
                item = "__NO_OUTPUT__"

            now = time.monotonic()
            if item is None:
                reader_finished = True
                continue

            if item != "__NO_OUTPUT__":
                match = STAGE_LINE.match(item)
                if match:
                    if current_key is not None:
                        previous = PIPELINE_STEPS.get(current_key)
                        if previous:
                            print(
                                color(
                                    f"✓ Finished STEP {previous[0]} in {format_elapsed(now - last_event)}",
                                    GREEN,
                                ),
                                flush=True,
                            )
                    current_key = (match.group(1), match.group(2))
                    mapped = PIPELINE_STEPS.get(current_key)
                    if mapped:
                        current_title = mapped[1]
                        plain_step(*mapped)
                        print(color("Working now...", YELLOW), flush=True)
                    else:
                        current_title = item
                        print(item, flush=True)
                    last_event = now
                elif item.startswith("Status:") or item.startswith("Quality status:"):
                    print(color(item, GREEN if "PASS" in item else YELLOW), flush=True)
                elif item.startswith("Summary:"):
                    print(color("The pipeline created its final technical summary.", DIM), flush=True)

            if now - last_event >= heartbeat_seconds:
                print(
                    color(
                        f"Still working: {current_title} | total time {format_elapsed(now - started)}",
                        YELLOW,
                    ),
                    flush=True,
                )
                last_event = now

        thread.join(timeout=2)
        return_code = int(process.returncode or 0)

    if current_key is not None and return_code == 0:
        previous = PIPELINE_STEPS.get(current_key)
        if previous:
            print(color(f"✓ Finished STEP {previous[0]}", GREEN), flush=True)

    return RunResult(
        return_code=return_code,
        elapsed_seconds=time.monotonic() - started,
        current_step=current_title,
    )


def run_simple_with_heartbeat(
    command: list[str],
    log_path: Path,
    label: str,
    heartbeat_seconds: int = 15,
) -> RunResult:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            command,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        last_message = started
        while process.poll() is None:
            time.sleep(1)
            now = time.monotonic()
            if now - last_message >= heartbeat_seconds:
                print(
                    color(
                        f"Still working: {label} | total time {format_elapsed(now - started)}",
                        YELLOW,
                    ),
                    flush=True,
                )
                last_message = now
        return_code = int(process.returncode or 0)
    return RunResult(return_code, time.monotonic() - started, label)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def count_tiffs(source: Path) -> tuple[int, int]:
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            names = [
                name
                for name in archive.namelist()
                if name.lower().endswith((".tif", ".tiff"))
            ]
            total_bytes = sum(
                info.file_size
                for info in archive.infolist()
                if info.filename in set(names)
            )
            return len(names), total_bytes
    if source.suffix.lower() in {".tif", ".tiff"}:
        return 1, source.stat().st_size
    return 0, 0


def ollama_models(base_url: str) -> tuple[bool, list[str], str]:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/api/tags", timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        models = [str(row.get("name") or "") for row in payload.get("models") or []]
        return True, models, ""
    except Exception as exc:
        return False, [], f"{type(exc).__name__}: {exc}"


def human_route_name(name: str) -> str:
    return {
        "blank": "Blank or nearly blank pages",
        "plain_text": "Normal text and procedure pages",
        "table": "Tables and illustrated-parts-list pages",
        "image": "Figures and diagram pages",
    }.get(name, name)


def show_pipeline_summary(report_path: Path) -> dict[str, Any]:
    payload = read_json(report_path)
    summary = payload.get("summary") or {}
    banner("WHAT THE INGESTION PIPELINE PRODUCED")
    print(f"Overall ingestion result: {payload.get('quality_status')}")
    print(f"Completed stage reports: {summary.get('stage_report_count')} of {summary.get('stage_count')}")
    print(f"Original pages with complete lineage: {summary.get('lineage_ready_count')}")
    print(f"Pages missing source lineage: {summary.get('missing_lineage_count')}")
    print()
    print(color("How the pages were classified:", BOLD))
    for route, count in (summary.get("final_validated_route_counts") or {}).items():
        print(f"  • {human_route_name(str(route))}: {count}")
    print()
    print(color("Prepared searchable records:", BOLD))
    print(f"  • Graph-ready page records: {summary.get('postgres_graph_record_count')}")
    print(f"  • Vector-search payloads: {summary.get('qdrant_payload_count')}")
    print(f"  • Exact-search payloads: {summary.get('opensearch_payload_count')}")
    print()
    print(color("Safety check:", BOLD))
    print(f"  • Database write attempts: {summary.get('write_attempt_count')}")
    print(f"  • Human-review requirement: {summary.get('human_review_required_count')}")
    print(f"  • Unsafe records: {summary.get('unsafe_record_count')}")
    return payload


def show_answer_summary(report_path: Path) -> dict[str, Any]:
    payload = read_json(report_path)
    summary = payload.get("summary") or {}
    evidence = payload.get("retrieval_evidence_records") or []
    answer = str((payload.get("answer_draft") or {}).get("answer_text") or "")

    banner("THE DISCOVERY MACHINE FOUND THE EVIDENCE")
    print(f"Evidence records selected: {summary.get('retrieval_evidence_count')}")
    print(f"Citations prepared: {summary.get('citation_count')}")
    for index, row in enumerate(evidence[:5], start=1):
        citation = row.get("citation") or {}
        reasons = ", ".join(row.get("retrieval_reasons") or [])
        print()
        print(color(f"Evidence {index}", BOLD))
        print(f"  Page: {citation.get('page_id') or citation.get('page_number')}")
        print(f"  Route: {human_route_name(str(row.get('route') or 'unknown'))}")
        print(f"  Why selected: {reasons or 'matched the question'}")
        excerpt = re.sub(r"\s+", " ", str(row.get("ocr_excerpt") or "")).strip()
        if excerpt:
            print(f"  OCR preview: {excerpt[:240]}{'…' if len(excerpt) > 240 else ''}")

    banner("GEMMA EXPLAINS THE EVIDENCE")
    print(f"Gemma called: {summary.get('llm_called')}")
    print(f"Gemma result: {summary.get('llm_status')}")
    print(f"Model: {summary.get('llm_model')}")
    print(f"Generated answer characters: {summary.get('llm_answer_char_count')}")

    banner("FINAL USER-FACING ANSWER")
    print(answer or "No final answer was produced.")
    print()
    print(color("Final safety facts", BOLD))
    print(f"  • Postgres writes: {summary.get('postgres_write_attempt_count')}")
    print(f"  • Qdrant writes: {summary.get('qdrant_write_attempt_count')}")
    print(f"  • OpenSearch writes: {summary.get('opensearch_write_attempt_count')}")
    print(f"  • Source-truth mutation allowed: {summary.get('source_truth_mutation_allowed_count')}")
    return payload


def make_html_report(
    path: Path,
    source: Path,
    question: str,
    pipeline: dict[str, Any] | None,
    answer_payload: dict[str, Any] | None,
) -> None:
    pipeline_summary = (pipeline or {}).get("summary") or {}
    answer_summary = (answer_payload or {}).get("summary") or {}
    answer_text = str(((answer_payload or {}).get("answer_draft") or {}).get("answer_text") or "")
    evidence = (answer_payload or {}).get("retrieval_evidence_records") or []
    route_counts = pipeline_summary.get("final_validated_route_counts") or {}

    stage_cards = []
    for (stage, kind), (number, title, explanation) in PIPELINE_STEPS.items():
        stage_cards.append(
            f"<div class='stage'><div class='num'>{html.escape(number)}</div>"
            f"<div><h3>{html.escape(title)}</h3><p>{html.escape(explanation)}</p></div></div>"
        )

    evidence_cards = []
    for index, row in enumerate(evidence[:5], start=1):
        citation = row.get("citation") or {}
        evidence_cards.append(
            "<div class='evidence'>"
            f"<h3>Evidence {index}</h3>"
            f"<p><strong>Page:</strong> {html.escape(str(citation.get('page_id') or citation.get('page_number') or 'unknown'))}</p>"
            f"<p><strong>Route:</strong> {html.escape(human_route_name(str(row.get('route') or 'unknown')))}</p>"
            f"<p><strong>Why selected:</strong> {html.escape(', '.join(row.get('retrieval_reasons') or []) or 'Matched the question')}</p>"
            f"<p>{html.escape(str(row.get('ocr_excerpt') or '')[:500])}</p>"
            "</div>"
        )

    route_rows = "".join(
        f"<tr><td>{html.escape(human_route_name(str(route)))}</td><td>{count}</td></tr>"
        for route, count in route_counts.items()
    )

    document = f"""<!doctype html>
<html><head><meta charset='utf-8'><title>TRACE-Net Executive TIFF Demo</title>
<style>
body{{font-family:Arial,sans-serif;margin:0;background:#f4f6f8;color:#18202a}}
header{{background:#152938;color:white;padding:32px 6vw}}
main{{max-width:1180px;margin:auto;padding:28px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}}
.card,.stage,.evidence{{background:white;border-radius:12px;padding:18px;box-shadow:0 3px 16px #0001}}
.stage{{display:flex;gap:14px;align-items:flex-start}}
.num{{background:#0b7285;color:white;border-radius:999px;min-width:46px;height:46px;display:grid;place-items:center;font-weight:bold}}
h1,h2,h3{{margin-top:0}} .good{{color:#17803d;font-weight:bold}} .answer{{white-space:pre-wrap;font-size:18px;line-height:1.5}}
table{{width:100%;border-collapse:collapse}} td,th{{padding:8px;border-bottom:1px solid #ddd;text-align:left}}
footer{{padding:30px;text-align:center;color:#667}}
</style></head>
<body><header><h1>TRACE-Net: Raw TIFF to Final Answer</h1>
<p>A plain-English, end-to-end server demonstration</p></header><main>
<div class='grid'>
<div class='card'><h2>Input</h2><p><strong>Source:</strong> {html.escape(str(source))}</p><p><strong>Question:</strong> {html.escape(question)}</p></div>
<div class='card'><h2>Result</h2><p class='good'>Ingestion: {html.escape(str((pipeline or {}).get('quality_status') or 'unknown'))}</p><p class='good'>Answer: {html.escape(str((answer_payload or {}).get('quality_status') or 'unknown'))}</p><p>Gemma calls: {html.escape(str(answer_summary.get('llm_called')))}</p><p>Citations: {html.escape(str(answer_summary.get('citation_count')))}</p></div>
</div>
<h2>What the server did, in order</h2><div class='grid'>{''.join(stage_cards)}</div>
<h2>Page classification</h2><div class='card'><table><tr><th>Page type</th><th>Count</th></tr>{route_rows}</table></div>
<h2>Discovery Machine evidence</h2><div class='grid'>{''.join(evidence_cards) or '<div class="card">No evidence records were produced.</div>'}</div>
<h2>Final answer</h2><div class='card answer'>{html.escape(answer_text or 'No answer was produced.')}</div>
<h2>Safety</h2><div class='card'><p>Postgres writes: {html.escape(str(answer_summary.get('postgres_write_attempt_count', 0)))}</p><p>Qdrant writes: {html.escape(str(answer_summary.get('qdrant_write_attempt_count', 0)))}</p><p>OpenSearch writes: {html.escape(str(answer_summary.get('opensearch_write_attempt_count', 0)))}</p><p>Source-truth mutation allowed: {html.escape(str(answer_summary.get('source_truth_mutation_allowed_count', 0)))}</p></div>
</main><footer>Generated by TRACE-Net executive demo wrapper v2</footer></body></html>"""
    path.write_text(document, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="/data/trace_net/repos/heico-ai-internship-summer-2026")
    parser.add_argument("--source-package", default="/data/trace_net/inputs/metadata.zip")
    parser.add_argument("--tesseract-cmd", default="/usr/bin/tesseract")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="gemma4:26b")
    parser.add_argument(
        "--question",
        default="Find part number 120-29073-001 and nearby similar parts. Use TRACE-Net evidence and cite pages.",
    )
    parser.add_argument("--output-dir")
    parser.add_argument("--heartbeat-seconds", type=int, default=15)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    repo = Path(args.repo).resolve()
    source = Path(args.source_package).resolve()
    tesseract = Path(args.tesseract_cmd)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir or f"/data/trace_net_runs/executive_raw_tiff_demo_{stamp}").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    banner("TRACE-NET EXECUTIVE DEMONSTRATION", "Raw scanned manual pages → searchable evidence → Gemma answer")
    print("This display uses plain English so a non-coder can follow every major decision.")
    print("The production databases are not modified during this demonstration.")

    banner("PRE-DEMO CHECK")
    can_run = True
    if repo.is_dir():
        print(color(f"✓ Repository found: {repo}", GREEN))
    else:
        print(color(f"✗ Repository not found: {repo}", RED))
        can_run = False
    if source.is_file():
        page_count, raw_bytes = count_tiffs(source)
        print(color(f"✓ Raw source found: {source}", GREEN))
        print(f"  TIFF pages detected: {page_count}")
        print(f"  Uncompressed TIFF data: {raw_bytes / (1024 * 1024):.1f} MB")
    else:
        print(color(f"✗ Raw source not found: {source}", RED))
        can_run = False
    executable = shutil.which(str(tesseract)) or (str(tesseract) if tesseract.is_file() else "")
    if executable:
        print(color(f"✓ OCR engine found: {executable}", GREEN))
    else:
        print(color(f"✗ OCR engine not found: {tesseract}", RED))
        can_run = False

    ollama_ok, models, ollama_error = ollama_models(args.ollama_url)
    if ollama_ok:
        print(color("✓ Ollama is running", GREEN))
        print(f"  Requested model available: {args.model in models}")
        print(f"  Models: {', '.join(models)}")
    else:
        print(color("⚠ Ollama is not responding", YELLOW))
        print(f"  Details: {ollama_error}")
        print("  The TIFF pipeline can run, but the final Gemma answer will be skipped.")

    if not can_run:
        banner("DEMO COULD NOT START")
        print("A required local file or program is missing. The PuTTY session remains open.")
        print(f"Output folder: {output_dir}")
        return

    os.chdir(repo)
    existing_pythonpath = os.environ.get("PYTHONPATH", "")
    os.environ["PYTHONPATH"] = f"{repo / 'scripts'}:{repo}" + (f":{existing_pythonpath}" if existing_pythonpath else "")
    python_bin = str(Path(os.environ.get("VIRTUAL_ENV", "/home/jwild/rag-workspace/.venv")) / "bin" / "python")
    if not Path(python_bin).is_file():
        python_bin = shutil.which("python") or "python"

    pipeline_command = [
        python_bin,
        "-u",
        "-B",
        "scripts/run_trace_net_ocr_classifier_pipeline_v1.py",
        "--source-package",
        str(source),
        "--tesseract-cmd",
        executable,
        "--output-dir",
        str(output_dir),
        "--quality",
    ]

    banner("PART 1 OF 2 — TURN THE RAW TIFFS INTO SEARCHABLE, TRACEABLE EVIDENCE")
    print("This is the longest part because the server reads and checks every scanned page.")
    pipeline_run = run_pipeline_with_narration(
        pipeline_command,
        output_dir / "01_full_ingestion.log",
        heartbeat_seconds=max(5, args.heartbeat_seconds),
    )
    print()
    print(f"Ingestion command finished in {format_elapsed(pipeline_run.elapsed_seconds)}")
    print(f"Ingestion return code: {pipeline_run.return_code}")

    pipeline_report = output_dir / "trace_net_ocr_classifier_pipeline_runner_v1.json"
    pipeline_payload: dict[str, Any] | None = None
    if pipeline_report.is_file():
        try:
            pipeline_payload = show_pipeline_summary(pipeline_report)
        except Exception as exc:
            print(color(f"Could not read the pipeline summary: {exc}", RED))
    else:
        print(color("The pipeline report was not created.", RED))

    answer_payload: dict[str, Any] | None = None
    answer_report = output_dir / "trace_net_raw_to_answer_e2e_smoke_v1.json"

    pipeline_pass = bool(
        pipeline_payload
        and pipeline_payload.get("quality_status") == "PASS"
        and pipeline_run.return_code == 0
    )

    if pipeline_pass and ollama_ok and args.model in models:
        banner("PART 2 OF 2 — ASK A QUESTION AND BUILD THE FINAL ANSWER")
        plain_step("10", "Read the user's question", "TRACE-Net extracts exact part numbers and useful search clues.")
        print(color(f"Question: {args.question}", BOLD))
        plain_step("11", "Search the prepared evidence", "The Discovery Machine scores the validated page records and keeps only the best matches.")
        plain_step("12", "Build a small evidence packet", "Only source-traced evidence and citations are sent forward.")
        plain_step("13", "Ask Gemma to explain", "Gemma writes the answer using only the evidence packet.")
        plain_step("14", "Check and save the result", "TRACE-Net records citations, safety flags, and the final answer files.")
        print()
        print(color("The four answer steps above are now running as one controlled operation...", YELLOW))

        answer_command = [
            python_bin,
            "-u",
            "-B",
            "scripts/run_trace_net_raw_to_answer_e2e_smoke_v1.py",
            "--source-package",
            str(source),
            "--tesseract-cmd",
            executable,
            "--output-dir",
            str(output_dir),
            "--question",
            args.question,
            "--top-k",
            "8",
            "--skip-pipeline",
            "--quality",
            "--llm-mode",
            "ollama_openai",
            "--llm-base-url",
            args.ollama_url.rstrip("/") + "/v1",
            "--llm-model",
            args.model,
            "--llm-api-key",
            "ollama",
            "--request-timeout",
            "1200",
            "--llm-max-tokens",
            "8192",
            "--require-llm-success",
        ]
        answer_run = run_simple_with_heartbeat(
            answer_command,
            output_dir / "02_retrieval_gemma_answer.log",
            "Discovery Machine retrieval, Gemma writing, and final validation",
            heartbeat_seconds=max(5, args.heartbeat_seconds),
        )
        print(color(f"✓ Answer operation finished in {format_elapsed(answer_run.elapsed_seconds)}", GREEN if answer_run.return_code == 0 else YELLOW))
        print(f"Answer return code: {answer_run.return_code}")

        if answer_report.is_file():
            try:
                answer_payload = show_answer_summary(answer_report)
            except Exception as exc:
                print(color(f"Could not read the answer report: {exc}", RED))
        else:
            print(color("The answer report was not created.", RED))
    else:
        banner("ANSWER STAGE WAS NOT STARTED")
        if not pipeline_pass:
            print("Reason: the ingestion quality gate did not pass.")
        elif not ollama_ok:
            print("Reason: Ollama was not responding.")
        else:
            print(f"Reason: model {args.model} was not listed by Ollama.")

    html_path = output_dir / "trace_net_executive_demo_v2.html"
    try:
        make_html_report(html_path, source, args.question, pipeline_payload, answer_payload)
    except Exception as exc:
        print(color(f"Could not create the HTML summary: {exc}", YELLOW))

    banner("DEMONSTRATION COMPLETE")
    print(f"Output folder: {output_dir}")
    print(f"Easy-English HTML summary: {html_path}")
    print(f"Full ingestion log: {output_dir / '01_full_ingestion.log'}")
    print(f"Answer log: {output_dir / '02_retrieval_gemma_answer.log'}")
    print(f"Final answer file: {output_dir / 'trace_net_raw_to_answer_e2e_smoke_v1_answer.md'}")
    print("PuTTY remains open. No production database was modified by this wrapper.")


if __name__ == "__main__":
    main()
