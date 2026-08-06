#!/usr/bin/env python3
"""
TRACE-Net repository stage inventory v2.

Read-only, dependency-aware scanner. It does not move, rename, delete, stage,
commit, or edit project files.

Key improvements over v1:
- linear/inverted reference indexing instead of all-files-against-all-files
- Python AST analysis
- shell/PowerShell command and environment-variable analysis
- producer/consumer path extraction
- protected runtime entrypoint detection
- version-family lineage analysis
- evidence-backed primary and secondary stage classifications
- progress output during every phase
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
import zipfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterable, Iterator

SCHEMA_VERSION = "trace_net_repo_stage_inventory_v2"

STAGES = (
    "shared",
    "ingestion",
    "ocr",
    "visual",
    "tables",
    "graph",
    "embeddings",
    "retrieval",
    "router",
    "brain_engram",
    "context",
    "llm_writing",
    "validation",
    "serving",
    "feedback",
    "benchmarks",
    "operations",
    "legacy",
    "unclassified",
)

# Terms are intentionally project-specific. A match contributes evidence but
# never alone authorizes a physical move.
STAGE_TERMS: dict[str, tuple[str, ...]] = {
    "shared": (
        "schema", "common", "shared", "utility", "utilities", "helper",
        "constants", "identifier", "source_id", "dublin_core", "trust_tier",
        "source_trace_id", "contract",
    ),
    "ingestion": (
        "tiff", "pdf", "ingest", "inventory", "extract_page", "page_extract",
        "preprocess", "raster", "convert", "source_manifest", "document_source",
        "scan_pack", "page_image",
    ),
    "ocr": (
        "ocr", "tesseract", "fishnet", "paddleocr", "easyocr", "abbyy",
        "text_recognition", "layout_aware", "scan_recovery", "psm",
    ),
    "visual": (
        "visual", "vision", "llava", "image_route", "image_visual", "diagram",
        "callout", "figure_link", "visual_region", "visual_understanding",
        "whole_page_vision", "gemma_visual",
    ),
    "tables": (
        "table", "ipl", "table_cell", "table_row", "table_element", "tabula",
        "camelot", "parts_list", "detailed_parts_list", "column",
    ),
    "graph": (
        "graph", "neo4j", "postgres_age", "apache_age", "leiden", "community",
        "nha", "hierarchy", "edge_bundle", "node_bundle", "relationship",
        "has_context", "part_on_page", "mentions_part", "has_nomenclature",
    ),
    "embeddings": (
        "embedding", "bge_m3", "qdrant", "vector_index", "candidate_chunk",
        "rag_candidate", "vector_store", "embedding_candidate",
    ),
    "retrieval": (
        "retriev", "hybrid_search", "opensearch", "exact_identifier",
        "semantic_search", "candidate_discovery", "source_resolution",
        "high_degree", "graph_search", "tunnel", "ranking_policy",
    ),
    "router": (
        "router", "routing", "query_atom", "guided_discovery", "normal_ask",
        "fastpath", "intent_classifier", "route_confidence", "route_scan",
        "planner_execution", "front_door",
    ),
    "brain_engram": (
        "engram", "memory_atom", "memory_layer", "skill_card", "critic_memory",
        "working_memory", "semantic_memory", "procedural_memory",
        "episodic_memory", "trait_memory", "brain", "planner_guidance",
        "memory_taxonomy",
    ),
    "context": (
        "context_pack", "page_context", "context_bridge", "evidence_envelope",
        "claim_ready", "source_trace", "citation_pack", "evidence_pack",
        "page_intelligence", "v2_summary", "v3_page", "proof_context",
    ),
    "llm_writing": (
        "llm_answer", "gemma", "writer", "answer_draft", "answer_renderer",
        "answer_presentation", "constrained_writer", "final_answer",
        "answer_contract", "content_reconstruction", "response_composer",
    ),
    "validation": (
        "self_rag", "crag", "validator", "validation", "quality_gate",
        "evidence_sufficiency", "citation_validation", "claim_gate",
        "safety_gate", "critic", "repair_quality", "consensus", "fallback",
    ),
    "serving": (
        "serve", "server", "endpoint", "openwebui", "open_webui", "proxy",
        "api", "chat_completions", "sse", "http", "bridge", "public_model",
    ),
    "feedback": (
        "feedback", "thumbs_up", "thumbs_down", "rating", "user_signal",
        "policy_signal", "feedback_event",
    ),
    "benchmarks": (
        "benchmark", "smoke", "question_bank", "same10", "regression",
        "quality_check", "evaluation", "eval", "latency", "question_count",
        "test_bank",
    ),
    "operations": (
        "launch", "deploy", "deployment", "systemd", "docker", "migration",
        "migrate", "loader", "install", "watchdog", "health", "preflight",
        "cleanup", "organize", "inventory", "runbook", "runtime", "tmux",
    ),
}

GENERIC_STAGES = {"shared", "operations", "benchmarks"}
TEXT_EXTENSIONS = {
    ".py", ".pyi", ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd",
    ".md", ".rst", ".txt", ".json", ".jsonl", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".csv", ".tsv", ".html", ".css", ".js", ".ts", ".tsx",
    ".jsx", ".sql", ".env", ".properties",
}
PYTHON_EXTENSIONS = {".py", ".pyi"}
SHELL_EXTENSIONS = {".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd"}

SKIP_CONTENT_PREFIXES = (
    ".git/",
    "repo_stage_inventory_",
    "trace_net_repo_stage_inventory_",
)
SKIP_LARGE_CONTENT_BYTES = 5_000_000

PROTECTED_NAME_PATTERNS = (
    r"^serve_trace_net_",
    r"^launch_trace_net_",
    r"^load_trace_net_",
    r"trace_net_h30_gemma_residency_watchdog",
    r"run_trace_net_gemma_residency_same10",
    r"serve_trace_net_full_gemma_cognitive",
    r"serve_trace_net_nha_phase16_gemma_proxy",
    r"serve_trace_net_guided_discovery_router_proxy",
    r"launch_trace_net_router_stack",
)

LEGACY_PATH_MARKERS = (
    "/legacy/", "/archive/", "/deprecated/", "/obsolete/",
)

PATH_LITERAL_RE = re.compile(
    r"""(?:
        (?:[A-Za-z]:[\\/][^\s"'`<>|]+) |
        (?:/(?:data|home|opt|var|mnt|c)/[^\s"'`<>|]+) |
        (?:(?:scripts|tests|docs|tiff|local_data|release_data|patches)/
           [A-Za-z0-9_./-]+)
    )""",
    re.VERBOSE,
)
ENV_RE = re.compile(r"\bTRACE_NET_[A-Z0-9_]+\b")
PORT_RE = re.compile(r"(?<!\d)(8\d{3}|11\d{3})(?!\d)")
VERSION_RE = re.compile(r"(?P<prefix>.*?)(?:_v(?P<version>\d+(?:_\d+)*))(?P<suffix>(?:_[a-z0-9]+)*)$", re.I)
WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")

@dataclass
class ParsedSignals:
    imports: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    string_literals: list[str] = field(default_factory=list)
    env_vars: list[str] = field(default_factory=list)
    ports: list[int] = field(default_factory=list)
    path_literals: list[str] = field(default_factory=list)
    executed_scripts: list[str] = field(default_factory=list)
    parse_error: str = ""

@dataclass
class FileRecord:
    path: str
    tracked: bool
    size_bytes: int
    extension: str
    content_scanned: bool
    primary_stage: str
    secondary_stages: list[str]
    confidence: float
    status: str
    protected_entrypoint: bool
    safe_to_move: bool
    suggested_destination: str
    legacy_reason: str
    newer_version_candidates: list[str]
    imported_modules: list[str]
    imported_by: list[str]
    referenced_by: list[str]
    path_literals: list[str]
    artifact_producers_or_consumers: list[str]
    env_vars: list[str]
    ports: list[int]
    evidence: list[str]
    notes: list[str]

def log(message: str) -> None:
    now = time.strftime("%H:%M:%S")
    print(f"[{now}] {message}", flush=True)

def run_git(repo: Path, args: list[str]) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout

def normalize_path(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")

def list_repo_files(repo: Path) -> tuple[list[str], set[str]]:
    tracked = {
        normalize_path(line.strip())
        for line in run_git(repo, ["ls-files"]).splitlines()
        if line.strip()
    }
    visible = {
        normalize_path(line.strip())
        for line in run_git(repo, ["ls-files", "--cached", "--others", "--exclude-standard"]).splitlines()
        if line.strip()
    }
    files = sorted(
        path for path in visible
        if path and (repo / path).is_file() and not path.startswith(".git/")
    )
    return files, tracked

def should_scan_content(path: str, size_bytes: int) -> bool:
    if size_bytes > SKIP_LARGE_CONTENT_BYTES:
        return False
    if Path(path).suffix.lower() not in TEXT_EXTENSIONS:
        return False
    return not any(path.startswith(prefix) for prefix in SKIP_CONTENT_PREFIXES)

def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""

def dotted_module_for_path(path: str) -> str | None:
    p = PurePosixPath(path)
    if p.suffix not in PYTHON_EXTENSIONS:
        return None
    parts = list(p.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return None
    return ".".join(parts)

def extract_python_signals(text: str, path: str) -> ParsedSignals:
    signals = ParsedSignals()
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as exc:
        signals.parse_error = f"{exc.__class__.__name__}: {exc.msg} line={exc.lineno}"
        return extract_text_signals(text, signals)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            signals.imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            signals.imports.append("." * node.level + module)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            signals.symbols.append(node.name)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip()
            if value:
                signals.string_literals.append(value[:1000])

    return extract_text_signals(text, signals)

def extract_text_signals(text: str, signals: ParsedSignals | None = None) -> ParsedSignals:
    signals = signals or ParsedSignals()
    signals.env_vars = sorted(set(ENV_RE.findall(text)))
    signals.ports = sorted({int(p) for p in PORT_RE.findall(text)})
    path_literals = {normalize_path(match.group(0).rstrip(".,;:)]}")) for match in PATH_LITERAL_RE.finditer(text)}
    signals.path_literals = sorted(path_literals)

    executed = set()
    for match in re.finditer(
        r"(?:python(?:3)?|bash|sh)\s+(?:-B\s+)?(?:-m\s+\S+\s+)?([A-Za-z0-9_./-]+\.(?:py|sh))",
        text,
        flags=re.I,
    ):
        executed.add(normalize_path(match.group(1)))
    signals.executed_scripts = sorted(executed)
    return signals

def extract_shell_signals(text: str) -> ParsedSignals:
    signals = extract_text_signals(text)
    symbols = set()
    for line in text.splitlines():
        stripped = line.strip()
        m = re.match(r"(?:function\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\(\)", stripped)
        if m:
            symbols.add(m.group(1))
        m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)=", stripped)
        if m:
            symbols.add(m.group(1))
    signals.symbols = sorted(symbols)
    return signals

def parse_file(repo: Path, path: str) -> tuple[ParsedSignals, bool]:
    full = repo / path
    size = full.stat().st_size
    if not should_scan_content(path, size):
        return ParsedSignals(), False
    text = read_text(full)
    suffix = full.suffix.lower()
    if suffix in PYTHON_EXTENSIONS:
        return extract_python_signals(text, path), True
    if suffix in SHELL_EXTENSIONS:
        return extract_shell_signals(text), True
    return extract_text_signals(text), True

def tokenized(value: str) -> set[str]:
    norm = value.lower().replace("-", "_").replace(".", "_").replace("/", "_")
    return {word.lower() for word in WORD_RE.findall(norm)}

def score_stages(path: str, signals: ParsedSignals) -> tuple[Counter[str], list[str]]:
    scores: Counter[str] = Counter()
    evidence: list[str] = []

    path_text = normalize_path(path).lower().replace("-", "_")
    symbol_text = " ".join(signals.symbols).lower().replace("-", "_")
    import_text = " ".join(signals.imports).lower().replace("-", "_")
    string_text = " ".join(signals.string_literals[:200]).lower().replace("-", "_")
    env_text = " ".join(signals.env_vars).lower()

    sources = (
        ("path", path_text, 5),
        ("symbol", symbol_text, 3),
        ("import", import_text, 3),
        ("string", string_text, 1),
        ("environment", env_text, 2),
    )

    for stage, terms in STAGE_TERMS.items():
        matched: list[str] = []
        for source_name, source_text, weight in sources:
            source_matches = sorted({
                term for term in terms
                if term.lower().replace("-", "_") in source_text
            })
            if source_matches:
                scores[stage] += weight * min(len(source_matches), 4)
                matched.extend(f"{source_name}:{term}" for term in source_matches[:4])
        if matched:
            evidence.append(f"{stage} <= " + ", ".join(matched[:8]))

    name = Path(path).name.lower()
    if re.match(r"^serve_.*\.(py|sh)$", name):
        scores["serving"] += 12
        evidence.append("serving <= active serve_* filename")
    if re.match(r"^launch_.*\.(sh|py)$", name):
        scores["operations"] += 12
        evidence.append("operations <= launch_* filename")
    if re.match(r"^load_.*\.py$", name):
        scores["operations"] += 8
        evidence.append("operations <= load_* filename")
    if re.match(r"^(run|check)_.*(benchmark|smoke|quality|regression).*\.py$", name):
        scores["benchmarks"] += 10
        evidence.append("benchmarks <= run/check benchmark filename")
    if path.startswith("tests/"):
        scores["benchmarks"] += 4
        evidence.append("benchmarks <= tests/ path")
    if path.startswith("docs/"):
        # Docs inherit their domain but receive no standalone stage.
        evidence.append("documentation file; domain inferred from subject")
    if any(marker in f"/{normalize_path(path).lower()}/" for marker in LEGACY_PATH_MARKERS):
        scores["legacy"] += 100
        evidence.append("legacy <= existing archive/legacy path")

    return scores, evidence

def choose_stages(scores: Counter[str]) -> tuple[str, list[str], float]:
    if not scores:
        return "unclassified", [], 0.0
    ranked = scores.most_common()
    top_stage, top_score = ranked[0]

    # On ties, prefer a domain stage over generic lifecycle categories.
    tied = [stage for stage, score in ranked if score == top_score]
    domain_tied = [stage for stage in tied if stage not in GENERIC_STAGES]
    if domain_tied:
        top_stage = domain_tied[0]

    total = sum(max(v, 0) for v in scores.values())
    confidence = 0.0 if total == 0 else top_score / total

    # Secondary stages need meaningful independent support.
    secondary = [
        stage for stage, score in ranked
        if stage != top_stage and score >= max(4, top_score * 0.30)
    ][:4]
    return top_stage, secondary, round(min(confidence, 1.0), 4)

def is_protected(path: str, signals: ParsedSignals, referenced_by: list[str]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    name = Path(path).name.lower()
    for pattern in PROTECTED_NAME_PATTERNS:
        if re.search(pattern, name):
            reasons.append(f"protected filename pattern: {pattern}")
    if signals.ports:
        reasons.append(f"declares runtime ports: {signals.ports}")
    if any(ref.startswith("scripts/launch_") for ref in referenced_by):
        reasons.append("referenced by launcher")
    if any(ref.startswith(("docs/", "scripts/")) and "runbook" in ref.lower() for ref in referenced_by):
        reasons.append("referenced by runbook")
    return bool(reasons), reasons

def version_key(text: str) -> tuple[int, ...]:
    return tuple(int(x) for x in text.split("_"))

def version_family(path: str) -> tuple[str, tuple[int, ...]] | None:
    p = PurePosixPath(path)
    stem = p.stem.lower()
    match = VERSION_RE.match(stem)
    if not match:
        return None
    prefix = re.sub(r"_(?:fix|patched|runtime_fixed|final|latest)$", "", match.group("prefix"))
    suffix = match.group("suffix") or ""
    # Preserve meaningful route/phase suffixes, remove generic repair suffixes.
    suffix = re.sub(r"_(?:fix|patched|runtime_fixed|final|latest)", "", suffix)
    family = f"{p.parent}/{prefix}{suffix}{p.suffix}".lower()
    return family, version_key(match.group("version"))

def build_version_lineage(files: list[str]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    families: dict[str, list[tuple[tuple[int, ...], str]]] = defaultdict(list)
    for path in files:
        parsed = version_family(path)
        if parsed:
            family, version = parsed
            families[family].append((version, path))

    newer: dict[str, list[str]] = defaultdict(list)
    family_members: dict[str, list[str]] = {}
    for family, members in families.items():
        members.sort()
        family_members[family] = [path for _, path in members]
        for idx, (_, path) in enumerate(members):
            newer[path] = [p for _, p in members[idx + 1:]]
    return newer, family_members

def probable_artifact_paths(signals: ParsedSignals) -> list[str]:
    return sorted({
        path for path in signals.path_literals
        if path.startswith(("local_data/", "release_data/", "/data/", "data/"))
        or path.endswith((".json", ".jsonl", ".csv", ".tsv", ".png", ".jpg", ".tif", ".tiff"))
    })

def status_for(
    path: str,
    protected: bool,
    referenced_by: list[str],
    imported_by: list[str],
    newer_versions: list[str],
) -> tuple[str, str, bool]:
    norm = f"/{normalize_path(path).lower()}/"
    name = Path(path).name.lower()

    if protected:
        return "active_protected", "", False
    if any(marker in norm for marker in LEGACY_PATH_MARKERS):
        return "legacy_existing", "already stored under archive/legacy", False
    if "/__pycache__/" in norm or name.endswith(".pyc"):
        return "generated_ignore", "Python cache", False
    if name.startswith(("tmp_", "temp_")) or name.endswith((".bak", ".old", ".orig")):
        return "legacy_high_confidence", "temporary or backup filename", True

    one_time_patch = (
        path.startswith("patches/")
        or re.match(r"^(?:trace_net|patch)_.*_patch/", path)
        or name == "apply_me.py"
    )
    if one_time_patch and not referenced_by and not imported_by:
        return "legacy_candidate", "unreferenced one-time patch/application material", True

    if newer_versions and not referenced_by and not imported_by:
        return (
            "legacy_candidate",
            "newer version-family member exists and no repository caller was found",
            True,
        )

    return "active_or_review", "", False

def destination_for(path: str, primary_stage: str, status: str) -> str:
    name = Path(path).name
    if status.startswith("legacy"):
        if path.startswith("docs/"):
            return f"docs/trace_net/archive/{name}"
        if path.startswith("tests/"):
            return f"tests/legacy/{name}"
        if path.startswith("scripts/"):
            return f"scripts/legacy/{name}"
        if path.startswith(("patches/", "trace_net_", "patch_")):
            return f"tools/patch_archive/{path}"
        return f"legacy/{path}"

    if primary_stage == "unclassified":
        return path
    if path.startswith(("local_data/", "release_data/")):
        return path
    if path.startswith("scripts/"):
        return f"scripts/{primary_stage}/{name}"
    if path.startswith("docs/"):
        return f"docs/trace_net/{primary_stage}/{name}"
    if path.startswith("tests/unit/"):
        return f"tests/unit/{primary_stage}/{name}"
    if path.startswith("tests/integration/"):
        return f"tests/integration/{primary_stage}/{name}"
    if path.startswith("tests/"):
        return f"tests/{primary_stage}/{name}"
    if path.startswith("tiff/"):
        return f"tiff/trace_net/{primary_stage}/{name}"
    return path

def resolve_import(
    source_path: str,
    import_name: str,
    module_to_path: dict[str, str],
) -> str | None:
    if not import_name:
        return None
    if import_name.startswith("."):
        # Conservative relative import handling.
        dots = len(import_name) - len(import_name.lstrip("."))
        suffix = import_name.lstrip(".")
        source_module = dotted_module_for_path(source_path) or ""
        base_parts = source_module.split(".")[:-1]
        if dots > 1:
            base_parts = base_parts[: max(0, len(base_parts) - (dots - 1))]
        absolute = ".".join([*base_parts, suffix] if suffix else base_parts)
        return module_to_path.get(absolute)
    if import_name in module_to_path:
        return module_to_path[import_name]
    # Importing a symbol from a module or package.
    parts = import_name.split(".")
    while parts:
        candidate = ".".join(parts)
        if candidate in module_to_path:
            return module_to_path[candidate]
        parts.pop()
    return None

def build_reference_maps(
    files: list[str],
    signals_by_file: dict[str, ParsedSignals],
) -> tuple[
    dict[str, list[str]],
    dict[str, list[str]],
    dict[str, list[str]],
]:
    path_set = set(files)
    basename_map: dict[str, list[str]] = defaultdict(list)
    for path in files:
        basename_map[Path(path).name].append(path)

    module_to_path = {
        module: path
        for path in files
        if (module := dotted_module_for_path(path))
    }

    referenced_by: dict[str, set[str]] = defaultdict(set)
    imported_by: dict[str, set[str]] = defaultdict(set)
    artifact_links: dict[str, set[str]] = defaultdict(set)

    for source, signals in signals_by_file.items():
        for imported in signals.imports:
            target = resolve_import(source, imported, module_to_path)
            if target and target != source:
                imported_by[target].add(source)

        for raw in [*signals.path_literals, *signals.executed_scripts]:
            normalized = normalize_path(raw)
            candidates: list[str] = []
            if normalized in path_set:
                candidates = [normalized]
            else:
                basename = Path(normalized).name
                if basename in basename_map and len(basename_map[basename]) == 1:
                    candidates = basename_map[basename]
            for target in candidates:
                if target != source:
                    referenced_by[target].add(source)

            if normalized.startswith(("local_data/", "release_data/", "/data/", "data/")):
                artifact_links[source].add(normalized)

    return (
        {k: sorted(v) for k, v in referenced_by.items()},
        {k: sorted(v) for k, v in imported_by.items()},
        {k: sorted(v) for k, v in artifact_links.items()},
    )

def propagate_stage_evidence(
    scores_by_file: dict[str, Counter[str]],
    imported_by: dict[str, list[str]],
    referenced_by: dict[str, list[str]],
) -> None:
    # Two bounded passes: callers can lend weak evidence to generic helpers,
    # but cannot overpower strong direct evidence.
    for _ in range(2):
        snapshot = {path: scores.copy() for path, scores in scores_by_file.items()}
        for target, callers in imported_by.items():
            if target not in scores_by_file:
                continue
            for caller in callers:
                for stage, score in snapshot.get(caller, {}).most_common(2):
                    if score >= 6:
                        scores_by_file[target][stage] += 1
        for target, callers in referenced_by.items():
            if target not in scores_by_file:
                continue
            for caller in callers:
                for stage, score in snapshot.get(caller, {}).most_common(1):
                    if score >= 8:
                        scores_by_file[target][stage] += 1

def write_csv(path: Path, records: list[FileRecord]) -> None:
    fields = list(asdict(records[0]).keys()) if records else [f.name for f in FileRecord.__dataclass_fields__.values()]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            row = asdict(record)
            for key, value in row.items():
                if isinstance(value, list):
                    row[key] = json.dumps(value, ensure_ascii=False)
            writer.writerow(row)

def write_outputs(
    repo: Path,
    output_dir: Path,
    records: list[FileRecord],
    family_members: dict[str, list[str]],
    package: bool,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    stage_counts = Counter(r.primary_stage for r in records)
    status_counts = Counter(r.status for r in records)

    write_csv(output_dir / "repo_stage_map.csv", records)

    inventory = {
        "schema_version": SCHEMA_VERSION,
        "repository": str(repo),
        "generated_at_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "file_count": len(records),
        "stage_counts": dict(stage_counts),
        "status_counts": dict(status_counts),
        "records": [asdict(r) for r in records],
    }
    (output_dir / "repo_stage_inventory.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    dependency_graph = {
        r.path: {
            "imports": r.imported_modules,
            "imported_by": r.imported_by,
            "referenced_by": r.referenced_by,
            "artifact_paths": r.artifact_producers_or_consumers,
        }
        for r in records
        if r.imported_modules or r.imported_by or r.referenced_by or r.artifact_producers_or_consumers
    }
    (output_dir / "repo_dependency_graph.json").write_text(
        json.dumps(dependency_graph, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    protected = [asdict(r) for r in records if r.protected_entrypoint]
    legacy = [asdict(r) for r in records if r.status.startswith("legacy")]
    unresolved = [
        asdict(r) for r in records
        if r.primary_stage == "unclassified" or r.confidence < 0.45
    ]
    move_manifest = [
        {
            "source": r.path,
            "destination": r.suggested_destination,
            "primary_stage": r.primary_stage,
            "secondary_stages": r.secondary_stages,
            "status": r.status,
            "confidence": r.confidence,
            "safe_to_move": r.safe_to_move,
            "protected_entrypoint": r.protected_entrypoint,
            "evidence": r.evidence,
        }
        for r in records
        if r.suggested_destination != r.path
    ]

    for name, payload in (
        ("repo_active_entrypoints.json", protected),
        ("repo_legacy_candidates.json", legacy),
        ("repo_unresolved_files.json", unresolved),
        ("repo_move_manifest_draft.json", move_manifest),
        ("repo_version_families.json", family_members),
    ):
        (output_dir / name).write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    lines = [
        "# TRACE-Net repository stage inventory v2",
        "",
        f"- Repository: `{repo}`",
        f"- Files inventoried: **{len(records)}**",
        f"- Tracked: **{sum(r.tracked for r in records)}**",
        f"- Untracked: **{sum(not r.tracked for r in records)}**",
        f"- Protected entrypoints: **{len(protected)}**",
        f"- Legacy candidates/existing legacy: **{len(legacy)}**",
        f"- Low-confidence or unclassified: **{len(unresolved)}**",
        "",
        "No project file was moved, renamed, deleted, staged, committed, or edited.",
        "",
        "## Stage totals",
        "",
        "| Stage | Files |",
        "|---|---:|",
    ]
    for stage in STAGES:
        lines.append(f"| `{stage}` | {stage_counts.get(stage, 0)} |")

    lines += [
        "",
        "## Status totals",
        "",
        "| Status | Files |",
        "|---|---:|",
    ]
    for status, count in status_counts.most_common():
        lines.append(f"| `{status}` | {count} |")

    lines += [
        "",
        "## Protected runtime entrypoints",
        "",
    ]
    for item in sorted((r for r in records if r.protected_entrypoint), key=lambda x: x.path):
        lines.append(
            f"- `{item.path}` — stage `{item.primary_stage}`; "
            f"ports `{item.ports}`; callers `{len(item.referenced_by) + len(item.imported_by)}`"
        )

    lines += [
        "",
        "## Legacy candidates",
        "",
        "These are review candidates only. No deletion or movement is authorized by this report.",
        "",
    ]
    for item in sorted((r for r in records if r.status.startswith("legacy")), key=lambda x: x.path):
        lines.append(
            f"- `{item.path}` — `{item.status}` — {item.legacy_reason or 'existing legacy location'}"
        )

    lines += [
        "",
        "## Safety policy for the later move phase",
        "",
        "- Do not move protected entrypoints without compatibility wrappers.",
        "- Do not move `local_data/` or `release_data/` until every producer and consumer is updated.",
        "- Do not declare an older version legacy based only on its version number.",
        "- Require dependency checks, compile checks, tests, and launcher health checks after each stage.",
        "- Keep ambiguous files in review rather than forcing a category.",
        "",
    ]

    (output_dir / "repo_organization_report.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    if package:
        archive = output_dir.with_suffix(".zip")
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for child in sorted(output_dir.rglob("*")):
                if child.is_file():
                    zf.write(child, child.relative_to(output_dir.parent))
        log(f"packaged_result={archive}")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--output-dir", default="repo_stage_inventory_v2")
    parser.add_argument("--package", action="store_true")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if not (repo / ".git").exists():
        raise SystemExit(f"not_git_repo={repo}")
    output_dir = (repo / args.output_dir).resolve()

    log("phase=1 action=list_tracked_and_untracked_files")
    files, tracked = list_repo_files(repo)
    log(f"phase=1 file_count={len(files)} tracked={len(tracked)} untracked={len(files)-len(tracked)}")

    log("phase=2 action=parse_python_shell_and_text_signals")
    signals_by_file: dict[str, ParsedSignals] = {}
    scanned_count = 0
    for index, path in enumerate(files, start=1):
        signals, scanned = parse_file(repo, path)
        signals_by_file[path] = signals
        scanned_count += int(scanned)
        if index == 1 or index % 250 == 0 or index == len(files):
            log(f"phase=2 progress={index}/{len(files)} content_scanned={scanned_count}")

    log("phase=3 action=build_linear_dependency_and_reference_indexes")
    referenced_by, imported_by, artifact_links = build_reference_maps(files, signals_by_file)
    log(
        "phase=3 "
        f"referenced_targets={len(referenced_by)} "
        f"imported_targets={len(imported_by)} "
        f"artifact_consumers_or_producers={len(artifact_links)}"
    )

    log("phase=4 action=score_project_stages")
    scores_by_file: dict[str, Counter[str]] = {}
    evidence_by_file: dict[str, list[str]] = {}
    for index, path in enumerate(files, start=1):
        scores, evidence = score_stages(path, signals_by_file[path])
        scores_by_file[path] = scores
        evidence_by_file[path] = evidence
        if index == 1 or index % 500 == 0 or index == len(files):
            log(f"phase=4 progress={index}/{len(files)}")

    log("phase=5 action=propagate_weak_caller_evidence")
    propagate_stage_evidence(scores_by_file, imported_by, referenced_by)

    log("phase=6 action=build_version_families_and_legacy_evidence")
    newer_versions, family_members = build_version_lineage(files)
    log(f"phase=6 version_family_count={len(family_members)}")

    log("phase=7 action=build_evidence_backed_records")
    records: list[FileRecord] = []
    for index, path in enumerate(files, start=1):
        signals = signals_by_file[path]
        primary, secondary, confidence = choose_stages(scores_by_file[path])
        refs = referenced_by.get(path, [])
        importers = imported_by.get(path, [])
        protected, protected_reasons = is_protected(path, signals, refs)
        status, legacy_reason, legacy_safe = status_for(
            path,
            protected,
            refs,
            importers,
            newer_versions.get(path, []),
        )
        suggested = destination_for(path, primary, status)
        safe_to_move = (
            suggested != path
            and not protected
            and status in {"legacy_high_confidence"}
            and not refs
            and not importers
        )
        notes: list[str] = []
        if path.startswith(("local_data/", "release_data/")):
            notes.append("artifact tree retained in place during physical organization phase 1")
        if signals.parse_error:
            notes.append(signals.parse_error)
        if status == "legacy_candidate":
            notes.append("review required; not automatically safe to move")
        if legacy_safe and not safe_to_move:
            notes.append("legacy evidence exists but dependency or policy gate blocks automatic move")

        evidence = [*evidence_by_file[path], *protected_reasons]
        if refs:
            evidence.append(f"referenced_by_count={len(refs)}")
        if importers:
            evidence.append(f"imported_by_count={len(importers)}")
        if newer_versions.get(path):
            evidence.append(f"newer_version_candidates={newer_versions[path][:5]}")

        records.append(
            FileRecord(
                path=path,
                tracked=path in tracked,
                size_bytes=(repo / path).stat().st_size,
                extension=(repo / path).suffix.lower(),
                content_scanned=should_scan_content(path, (repo / path).stat().st_size),
                primary_stage=primary,
                secondary_stages=secondary,
                confidence=confidence,
                status=status,
                protected_entrypoint=protected,
                safe_to_move=safe_to_move,
                suggested_destination=suggested,
                legacy_reason=legacy_reason,
                newer_version_candidates=newer_versions.get(path, []),
                imported_modules=signals.imports,
                imported_by=importers,
                referenced_by=refs,
                path_literals=signals.path_literals,
                artifact_producers_or_consumers=artifact_links.get(path, []),
                env_vars=signals.env_vars,
                ports=signals.ports,
                evidence=evidence,
                notes=notes,
            )
        )
        if index == 1 or index % 500 == 0 or index == len(files):
            log(f"phase=7 progress={index}/{len(files)}")

    log("phase=8 action=write_reports")
    write_outputs(repo, output_dir, records, family_members, args.package)

    summary = {
        "schema_version": SCHEMA_VERSION,
        "file_count": len(records),
        "tracked_count": sum(r.tracked for r in records),
        "untracked_count": sum(not r.tracked for r in records),
        "protected_entrypoint_count": sum(r.protected_entrypoint for r in records),
        "legacy_candidate_count": sum(r.status.startswith("legacy") for r in records),
        "safe_to_move_count": sum(r.safe_to_move for r in records),
        "unresolved_count": sum(r.primary_stage == "unclassified" or r.confidence < 0.45 for r in records),
        "output_dir": str(output_dir),
    }
    for key, value in summary.items():
        print(f"{key}={value}")
    print("TRACE_NET_REPO_STAGE_INVENTORY_V2=PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
