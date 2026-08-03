"""User-style query test cases for the TIFF/RAG local MVP.

These tests are intentionally black-box-ish: they run the same command-line
entrypoints a user/demo operator would run, then check for expected strings in
stdout.  They are not meant to replace unit tests or RAG evals; they are a
smoke/regression suite for end-to-end user behavior.
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
class UserQueryCase:
    id: str
    description: str
    command: list[str]
    expected_contains: tuple[str, ...] = ()
    expected_not_contains: tuple[str, ...] = ()
    timeout_seconds: int = 90
    slow: bool = False
    category: str = "general"

    def resolved_command(self, config: str) -> list[str]:
        return [part.format(config=config) for part in self.command]


@dataclass
class UserQueryResult:
    id: str
    category: str
    description: str
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
            "id": self.id,
            "category": self.category,
            "description": self.description,
            "command": self.command,
            "status": self.status,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "returncode": self.returncode,
            "missing_expected": self.missing_expected,
            "forbidden_found": self.forbidden_found,
            "stdout_preview": self.stdout_preview,
            "stderr_preview": self.stderr_preview,
        }


def default_user_query_cases(include_slow: bool = False) -> list[UserQueryCase]:
    cases = [
        UserQueryCase(
            id="org_part_120_37313_001",
            category="organization",
            description="Organization export part lookup for 120-37313-001.",
            command=["scripts/operations/ingestion/query_document_organization.py", "--part", "120-37313-001", "--strict"],
            expected_contains=("120-37313-001 | HOLDER, MAGAZINE", "pages=28", "source=http://localhost:8080"),
        ),
        UserQueryCase(
            id="org_part_am03078_22",
            category="organization",
            description="Organization export part lookup for AM03078-22.",
            command=["scripts/operations/ingestion/query_document_organization.py", "--part", "AM03078-22", "--strict"],
            expected_contains=("AM03078-22", "ASHTRAY", "source=http://localhost:8080"),
        ),
        UserQueryCase(
            id="org_ata_25_21_00",
            category="organization",
            description="Organization export ATA browse for ATA 25-21-00.",
            command=["scripts/operations/ingestion/query_document_organization.py", "--ata", "25-21-00", "--strict"],
            expected_contains=("ATA 25-21-00", "manual=T.P. 120/1176", "pages=501"),
        ),
        UserQueryCase(
            id="org_page_source_000042",
            category="organization",
            description="Organization export page/source lookup for p000042.",
            command=["scripts/operations/ingestion/query_document_organization.py", "--page", "t_p_120_1176_p000042", "--strict"],
            expected_contains=("t_p_120_1176_p000042", "ATA 11-00-66", "TIFF:", "OCR:"),
        ),
        UserQueryCase(
            id="graph_part_to_context",
            category="graph",
            description="Graph traversal from part to page, nomenclature, context, and source link.",
            command=["tests/integration/test_document_graph_traversal.py", "--part", "120-37313-001", "--strict"],
            expected_contains=("Status: OK", "HAS_CONTEXT", "HOLDER, MAGAZINE", "source_link=True"),
        ),
        UserQueryCase(
            id="context_page_000042",
            category="context",
            description="Page context inspection for a known part-list page.",
            command=["scripts/maintenance/context/inspect_page_contexts.py", "--page", "t_p_120_1176_p000042", "--limit", "5"],
            expected_contains=("Page context inspection", "t_p_120_1176_p000042", "role=parts_list"),
        ),
        UserQueryCase(
            id="rag_exact_part_120_37313_001",
            category="rag",
            description="Deterministic RAG exact part lookup for 120-37313-001.",
            command=["scripts/operations/ingestion/ask_tiff_rag.py", "--config", "{config}", "What is part number 120-37313-001?"],
            expected_contains=("LLM used: False", "Embeddings used: False", "120-37313-001 is listed as HOLDER, MAGAZINE", "Sources:"),
        ),
        UserQueryCase(
            id="rag_exact_part_am03078_22",
            category="rag",
            description="Deterministic RAG exact part lookup for AM03078-22.",
            command=["scripts/operations/ingestion/ask_tiff_rag.py", "--config", "{config}", "What is part number AM03078-22?"],
            expected_contains=("LLM used: False", "Embeddings used: False", "AM03078-22 is listed as", "ASHTRAY"),
        ),
        UserQueryCase(
            id="rag_nomenclature_holder_magazine",
            category="rag",
            description="Reverse nomenclature lookup for HOLDER, MAGAZINE.",
            command=["scripts/operations/ingestion/ask_tiff_rag.py", "--config", "{config}", "Where is HOLDER, MAGAZINE mentioned?"],
            expected_contains=("LLM used: False", "120-36843-001", "120-37313-001", "120-37313-535"),
            timeout_seconds=120,
        ),
        UserQueryCase(
            id="rag_ata_25_21_00",
            category="rag",
            description="ATA evidence lookup through organization-tree routing.",
            command=["scripts/operations/ingestion/ask_tiff_rag.py", "--config", "{config}", "Find evidence for ATA 25-21-00."],
            expected_contains=("LLM used: False", "ATA 25-21-00 is present in the local organization tree", "Logical parts in section"),
        ),
    ]
    if include_slow:
        cases.append(
            UserQueryCase(
                id="rag_broad_summary_passenger_seat_back",
                category="rag_slow",
                description="Broad RAG summary that should use Gemma and embeddings.",
                command=[
                    "scripts/operations/ingestion/ask_tiff_rag.py",
                    "--config",
                    "{config}",
                    "Summarize passenger seat back crack reinforcement using source evidence.",
                ],
                expected_contains=("LLM used: True", "Embeddings used: True", "Sources:"),
                timeout_seconds=240,
                slow=True,
            )
        )
    return cases


def select_cases(cases: Iterable[UserQueryCase], selected_ids: Iterable[str] | None = None) -> list[UserQueryCase]:
    selected = set(selected_ids or [])
    if not selected:
        return list(cases)
    by_id = {case.id: case for case in cases}
    missing = sorted(selected - set(by_id))
    if missing:
        raise KeyError(f"unknown user query case id(s): {', '.join(missing)}")
    return [by_id[case_id] for case_id in selected]


def run_user_query_case(case: UserQueryCase, repo_root: str | Path = ".", config: str = "local_config.yaml") -> UserQueryResult:
    repo_root = Path(repo_root)
    command_parts = case.resolved_command(config=config)
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
            timeout=case.timeout_seconds,
            check=False,
        )
        elapsed = time.perf_counter() - start
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        missing = [text for text in case.expected_contains if text not in stdout]
        forbidden = [text for text in case.expected_not_contains if text in stdout]
        status = "pass" if completed.returncode == 0 and not missing and not forbidden else "fail"
        return UserQueryResult(
            id=case.id,
            category=case.category,
            description=case.description,
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
        return UserQueryResult(
            id=case.id,
            category=case.category,
            description=case.description,
            command=full_command,
            status="timeout",
            elapsed_seconds=elapsed,
            returncode=None,
            missing_expected=list(case.expected_contains),
            stdout_preview=_preview(exc.stdout or ""),
            stderr_preview=_preview(exc.stderr or ""),
        )


def summarize_results(results: list[UserQueryResult]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    return {
        "total": len(results),
        "status_counts": counts,
        "pass": counts.get("pass", 0),
        "fail": counts.get("fail", 0),
        "timeout": counts.get("timeout", 0),
        "elapsed_seconds": round(sum(r.elapsed_seconds for r in results), 3),
    }


def write_results_json(results: list[UserQueryResult], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": summarize_results(results),
        "results": [result.to_jsonable() for result in results],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _preview(text: str, max_chars: int = 2000) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...<truncated>"
