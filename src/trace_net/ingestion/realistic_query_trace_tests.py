"""Realistic prompt-to-retrieval-to-graph trace regression tests.

These tests are higher level than the fast user-query smoke suite.  Each case
models a user-facing prompt or retrieval event, then checks that the result can
be traced back through the graph to source links and AI page context.

The intended coverage is:

    user prompt -> deterministic/RAG retrieval -> page/chunk id -> graph ->
    document/ATA/source/context/part/nomenclature

For the local MVP, Qdrant is simulated by a vector payload containing a page_id
and chunk_id.  In production, Qdrant should return the same kind of payload so
PostgreSQL/graph traversal can resolve source context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import subprocess
import sys
import time
from typing import Any, Iterable


@dataclass(frozen=True)
class CommandCheck:
    """One command in a realistic query trace case."""

    label: str
    command: tuple[str, ...]
    expected_contains: tuple[str, ...] = ()
    expected_not_contains: tuple[str, ...] = ()
    timeout_seconds: int = 120

    def resolved_command(self, config: str) -> list[str]:
        return [part.format(config=config) for part in self.command]


@dataclass(frozen=True)
class RealisticTraceCase:
    """A user-like prompt plus one or more traceability checks."""

    id: str
    category: str
    description: str
    user_prompt: str
    checks: tuple[CommandCheck, ...]
    slow: bool = False


@dataclass
class CommandCheckResult:
    label: str
    command: list[str]
    status: str
    elapsed_seconds: float
    returncode: int | None
    missing_expected: list[str] = field(default_factory=list)
    forbidden_found: list[str] = field(default_factory=list)
    stdout_preview: str = ""
    stderr_preview: str = ""

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "command": self.command,
            "status": self.status,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "returncode": self.returncode,
            "missing_expected": self.missing_expected,
            "forbidden_found": self.forbidden_found,
            "stdout_preview": self.stdout_preview,
            "stderr_preview": self.stderr_preview,
        }


@dataclass
class RealisticTraceResult:
    id: str
    category: str
    description: str
    user_prompt: str
    status: str
    elapsed_seconds: float
    checks: list[CommandCheckResult]

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "description": self.description,
            "user_prompt": self.user_prompt,
            "status": self.status,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "checks": [check.to_jsonable() for check in self.checks],
        }


def default_realistic_trace_cases(include_slow: bool = False) -> list[RealisticTraceCase]:
    """Return realistic end-to-end prompt/trace regression cases."""

    cases = [
        RealisticTraceCase(
            id="part_prompt_120_37313_001_to_graph",
            category="part_prompt_to_graph",
            description="User asks for a part, answer must be exact and trace through graph to source/context.",
            user_prompt="I have part number 120-37313-001. What is it and where is the source evidence?",
            checks=(
                CommandCheck(
                    label="rag_exact_part_prompt",
                    command=(
                        "scripts/operations/ingestion/ask_tiff_rag.py",
                        "--config",
                        "{config}",
                        "I have part number 120-37313-001. What is it and where is the source evidence?",
                    ),
                    expected_contains=(
                        "LLM used: False",
                        "Embeddings used: False",
                        "120-37313-001 is listed as HOLDER, MAGAZINE",
                        "Sources:",
                    ),
                ),
                CommandCheck(
                    label="graph_part_trace",
                    command=("scripts/maintenance/graph/trace_document_graph.py", "--part", "120-37313-001", "--strict"),
                    expected_contains=(
                        "Trace: part_to_sources",
                        "Status: OK",
                        "HOLDER, MAGAZINE",
                        "sample_pages_with_source_links: 8",
                        "sample_pages_with_context: 8",
                        "HAS_CONTEXT",
                        "HAS_SOURCE_LINK",
                    ),
                ),
            ),
        ),
        RealisticTraceCase(
            id="part_prompt_am03078_22_to_graph",
            category="part_prompt_to_graph",
            description="User asks for AM03078-22, exact answer must trace to pages/source/context.",
            user_prompt="Can you identify AM03078-22 and show me where it appears?",
            checks=(
                CommandCheck(
                    label="rag_exact_part_prompt",
                    command=(
                        "scripts/operations/ingestion/ask_tiff_rag.py",
                        "--config",
                        "{config}",
                        "Can you identify AM03078-22 and show me where it appears?",
                    ),
                    expected_contains=("LLM used: False", "AM03078-22 is listed as", "ASHTRAY", "Sources:"),
                ),
                CommandCheck(
                    label="graph_part_trace",
                    command=("scripts/maintenance/graph/trace_document_graph.py", "--part", "AM03078-22", "--strict"),
                    expected_contains=("Trace: part_to_sources", "Status: OK", "source_link", "AI context"),
                ),
            ),
        ),
        RealisticTraceCase(
            id="nomenclature_prompt_holder_magazine_to_parts",
            category="nomenclature_to_graph",
            description="User searches by part name, system should find matching parts and graph evidence.",
            user_prompt="Where is HOLDER, MAGAZINE mentioned?",
            checks=(
                CommandCheck(
                    label="rag_nomenclature_lookup",
                    command=("scripts/operations/ingestion/ask_tiff_rag.py", "--config", "{config}", "Where is HOLDER, MAGAZINE mentioned?"),
                    expected_contains=("LLM used: False", "120-36843-001", "120-37313-001", "120-37313-535"),
                    timeout_seconds=150,
                ),
                CommandCheck(
                    label="graph_part_trace_one_match",
                    command=("scripts/maintenance/graph/trace_document_graph.py", "--part", "120-37313-001", "--strict"),
                    expected_contains=("HOLDER, MAGAZINE", "sample_pages_with_context", "HAS_SOURCE_LINK"),
                ),
            ),
        ),
        RealisticTraceCase(
            id="ata_prompt_25_21_00_to_sources",
            category="ata_to_graph",
            description="User asks for ATA evidence; organization route and graph trace should agree.",
            user_prompt="Find evidence for ATA 25-21-00 and show source pages.",
            checks=(
                CommandCheck(
                    label="rag_ata_lookup",
                    command=("scripts/operations/ingestion/ask_tiff_rag.py", "--config", "{config}", "Find evidence for ATA 25-21-00 and show source pages."),
                    expected_contains=("LLM used: False", "ATA 25-21-00 is present in the local organization tree", "Sample source pages"),
                ),
                CommandCheck(
                    label="graph_ata_trace",
                    command=("scripts/maintenance/graph/trace_document_graph.py", "--ata", "25-21-00", "--max-pages", "8", "--strict"),
                    expected_contains=("Trace: ata_to_sources", "Status: OK", "ATA 25-21-00", "HAS_SOURCE_LINK"),
                ),
            ),
        ),
        RealisticTraceCase(
            id="page_prompt_000083_to_part_context_source",
            category="page_to_graph",
            description="Known source page should traverse to document, ATA, source, context, part, and nomenclature.",
            user_prompt="For page t_p_120_1176_p000083, what document, section, source, and part context do we have?",
            checks=(
                CommandCheck(
                    label="graph_page_trace",
                    command=("scripts/maintenance/graph/trace_document_graph.py", "--page", "t_p_120_1176_p000083", "--strict"),
                    expected_contains=(
                        "Trace: page_trace",
                        "Status: OK",
                        "document: T.P. 120/1176",
                        "ata: ATA 25-21-00",
                        "source_link_present: True",
                        "context_present: True",
                        "HOLDER, MAGAZINE",
                    ),
                ),
            ),
        ),
        RealisticTraceCase(
            id="vector_payload_page_000495_to_graph_context",
            category="vector_to_graph",
            description="Simulated Qdrant payload must resolve to graph document/source/context.",
            user_prompt="Vector retrieval found page t_p_120_1176_p000495 for a seat-back repair question. Can we trace it?",
            checks=(
                CommandCheck(
                    label="simulated_qdrant_payload_trace",
                    command=(
                        "scripts/maintenance/graph/trace_document_graph.py",
                        "--vector-page",
                        "t_p_120_1176_p000495",
                        "--vector-chunk",
                        "chunk_t_p_120_1176_p000495_001",
                        "--vector-score",
                        "0.635",
                        "--strict",
                    ),
                    expected_contains=(
                        "Trace: vector_candidate_to_graph",
                        "Status: OK",
                        "vector_payload_page_id: t_p_120_1176_p000495",
                        "source_link_present: True",
                        "context_present: True",
                    ),
                    expected_not_contains=("Page has no AI context yet",),
                ),
            ),
        ),
        RealisticTraceCase(
            id="context_prompt_page_000495",
            category="context_to_graph",
            description="User asks about AI context for a vector-retrieved page.",
            user_prompt="What is page t_p_120_1176_p000495 about?",
            checks=(
                CommandCheck(
                    label="context_inspection",
                    command=("scripts/maintenance/context/inspect_page_contexts.py", "--page", "t_p_120_1176_p000495", "--limit", "5"),
                    expected_contains=("Page context inspection", "t_p_120_1176_p000495", "role=", "confidence="),
                ),
                CommandCheck(
                    label="graph_vector_trace",
                    command=(
                        "scripts/maintenance/graph/trace_document_graph.py",
                        "--vector-page",
                        "t_p_120_1176_p000495",
                        "--vector-chunk",
                        "chunk_t_p_120_1176_p000495_001",
                        "--vector-score",
                        "0.635",
                        "--strict",
                    ),
                    expected_contains=("context_present: True", "source_link_present: True", "ATA 25-21-00"),
                ),
            ),
        ),
    ]
    if include_slow:
        cases.append(
            RealisticTraceCase(
                id="slow_rag_summary_passenger_seat_back_to_graph",
                category="rag_vector_to_graph_slow",
                description="Broad RAG prompt should use embeddings/LLM and trace a known vector candidate to source/context.",
                user_prompt="Summarize passenger seat back crack reinforcement using source evidence.",
                slow=True,
                checks=(
                    CommandCheck(
                        label="rag_broad_summary",
                        command=(
                            "scripts/operations/ingestion/ask_tiff_rag.py",
                            "--config",
                            "{config}",
                            "Summarize passenger seat back crack reinforcement using source evidence.",
                        ),
                        expected_contains=("LLM used: True", "Embeddings used: True", "Sources:"),
                        timeout_seconds=300,
                    ),
                    CommandCheck(
                        label="known_vector_source_trace",
                        command=(
                            "scripts/maintenance/graph/trace_document_graph.py",
                            "--vector-page",
                            "t_p_120_1176_p000495",
                            "--vector-chunk",
                            "chunk_t_p_120_1176_p000495_001",
                            "--vector-score",
                            "0.635",
                            "--strict",
                        ),
                        expected_contains=("Trace: vector_candidate_to_graph", "source_link_present: True", "context_present: True"),
                    ),
                ),
            )
        )
    return cases


def select_cases(cases: Iterable[RealisticTraceCase], selected_ids: Iterable[str] | None = None) -> list[RealisticTraceCase]:
    selected = set(selected_ids or [])
    if not selected:
        return list(cases)
    by_id = {case.id: case for case in cases}
    missing = sorted(selected - set(by_id))
    if missing:
        raise KeyError(f"unknown realistic query trace case id(s): {', '.join(missing)}")
    return [by_id[case_id] for case_id in selected]


def run_realistic_trace_case(case: RealisticTraceCase, repo_root: str | Path = ".", config: str = "local_config.yaml") -> RealisticTraceResult:
    start = time.perf_counter()
    check_results = [run_command_check(check, repo_root=repo_root, config=config) for check in case.checks]
    elapsed = time.perf_counter() - start
    status = "pass" if all(result.status == "pass" for result in check_results) else "fail"
    return RealisticTraceResult(
        id=case.id,
        category=case.category,
        description=case.description,
        user_prompt=case.user_prompt,
        status=status,
        elapsed_seconds=elapsed,
        checks=check_results,
    )


def run_command_check(check: CommandCheck, repo_root: str | Path = ".", config: str = "local_config.yaml") -> CommandCheckResult:
    repo_root = Path(repo_root)
    command_parts = check.resolved_command(config=config)
    full_command = [sys.executable, *command_parts]
    start = time.perf_counter()
    try:
        completed = subprocess.run(
            full_command,
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=check.timeout_seconds,
            check=False,
        )
        elapsed = time.perf_counter() - start
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        missing = [text for text in check.expected_contains if text not in stdout]
        forbidden = [text for text in check.expected_not_contains if text in stdout]
        status = "pass" if completed.returncode == 0 and not missing and not forbidden else "fail"
        return CommandCheckResult(
            label=check.label,
            command=full_command,
            status=status,
            elapsed_seconds=elapsed,
            returncode=completed.returncode,
            missing_expected=missing,
            forbidden_found=forbidden,
            stdout_preview=_preview(stdout),
            stderr_preview=_preview(stderr),
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - start
        return CommandCheckResult(
            label=check.label,
            command=full_command,
            status="timeout",
            elapsed_seconds=elapsed,
            returncode=None,
            missing_expected=list(check.expected_contains),
            stdout_preview=_preview(exc.stdout or ""),
            stderr_preview=_preview(exc.stderr or ""),
        )


def summarize_realistic_trace_results(results: list[RealisticTraceResult]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    category_counts: dict[str, dict[str, int]] = {}
    check_total = 0
    check_pass = 0
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
        cat = category_counts.setdefault(result.category, {})
        cat[result.status] = cat.get(result.status, 0) + 1
        for check in result.checks:
            check_total += 1
            if check.status == "pass":
                check_pass += 1
    return {
        "total": len(results),
        "status_counts": counts,
        "pass": counts.get("pass", 0),
        "fail": counts.get("fail", 0),
        "check_total": check_total,
        "check_pass": check_pass,
        "check_fail": check_total - check_pass,
        "category_status_counts": category_counts,
        "elapsed_seconds": round(sum(result.elapsed_seconds for result in results), 3),
    }


def write_realistic_trace_results_json(results: list[RealisticTraceResult], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": summarize_realistic_trace_results(results),
        "results": [result.to_jsonable() for result in results],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _preview(text: str, max_chars: int = 2500) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...<truncated>"
