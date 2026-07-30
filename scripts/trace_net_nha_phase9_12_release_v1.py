#!/usr/bin/env python3
"""TRACE-Net NHA N9-N12 release promotion and live endpoint benchmark helpers.

N9 promotes only validated real N4 artifacts into a small Git-tracked release.
N10 builds and evaluates a deterministic live 20-question endpoint bank.
N11/N12 use those contracts for server shadow diagnostics and gated release.
No synthetic N5 artifact is loaded or promoted by this module.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

MODULE = "trace_net_nha_phase9_12_release_v1"
STATUS = "TRACE_NET_NHA_PHASE9_12_RELEASE_V1"
SCHEMA_VERSION = "trace_net_nha_phase9_12_release_v1"
SYNTHETIC_PART_RE = re.compile(r"\b990-\d{5}-\d{3}\b", re.I)

RELEASE_FILES = (
    "trace_net_nha_hierarchy_relationships_v1.json",
    "trace_net_nha_phase4_answer_key_v1.json",
    "trace_net_nha_phase4_quality_v1.json",
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("records", "items", "rows", "cases", "questions"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [dict(row) for row in rows if isinstance(row, Mapping)]
    return []


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def _dedupe(values: Iterable[Any]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))


def validate_release_source(phase4_dir: str | Path) -> dict[str, Any]:
    root = Path(phase4_dir).resolve()
    paths = {name: root / name for name in RELEASE_FILES}
    missing = [str(path) for path in paths.values() if not path.exists()]
    failures: list[str] = []
    if missing:
        return {
            "quality_status": "FAIL",
            "failures": ["missing_release_source:" + ",".join(missing)],
            "warnings": [],
            "counts": {},
            "paths": {key: str(value) for key, value in paths.items()},
        }

    quality = _read_json(paths["trace_net_nha_phase4_quality_v1.json"])
    relationships_payload = _read_json(paths["trace_net_nha_hierarchy_relationships_v1.json"])
    answer_key_payload = _read_json(paths["trace_net_nha_phase4_answer_key_v1.json"])
    relationships = _records(relationships_payload)
    answer_cases = _records(answer_key_payload)
    serialized = json.dumps(
        {"relationships": relationships_payload, "answer_key": answer_key_payload},
        ensure_ascii=False,
    )

    if str(quality.get("quality_status") or "") != "PASS":
        failures.append("phase4_quality_not_pass")
    if not relationships:
        failures.append("no_real_relationships")
    if not answer_cases:
        failures.append("no_real_answer_key_cases")
    if SYNTHETIC_PART_RE.search(serialized) or "synthetic_benchmark" in serialized.casefold():
        failures.append("synthetic_content_in_real_release")
    for row in relationships:
        if str(row.get("truth_mode") or "") != "real_source" or not bool(row.get("source_truth")):
            failures.append(f"non_real_relationship:{row.get('relationship_id')}")
            break
    supported = sum(str(row.get("relationship_status") or "") == "source_supported" for row in relationships)
    ambiguous = sum(str(row.get("relationship_status") or "") == "ambiguous" for row in relationships)
    if supported < 1:
        failures.append("no_source_supported_relationships")
    if int(answer_key_payload.get("case_count") or len(answer_cases)) != len(answer_cases):
        failures.append("answer_key_case_count_mismatch")

    return {
        "schema_version": SCHEMA_VERSION,
        "module": MODULE,
        "status": STATUS,
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "warnings": [],
        "counts": {
            "relationship_count": len(relationships),
            "source_supported_relationship_count": supported,
            "ambiguous_relationship_count": ambiguous,
            "answer_key_case_count": len(answer_cases),
            "synthetic_record_count": 0,
            "production_graph_write_count": 0,
        },
        "paths": {key: str(value) for key, value in paths.items()},
        "sha256": {key: _sha256_file(value) for key, value in paths.items()},
        "safety_contract": {
            "real_source_only": True,
            "synthetic_phase5_loaded": False,
            "synthetic_records_promoted": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
        },
    }


def promote_real_release(phase4_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    validation = validate_release_source(phase4_dir)
    if validation["quality_status"] != "PASS":
        return validation
    source = Path(phase4_dir).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name in RELEASE_FILES:
        shutil.copy2(source / name, output / name)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "module": MODULE,
        "status": "TRACE_NET_NHA_PHASE9_REAL_RELEASE_V1",
        "quality_status": "PASS",
        "release_id": "trace_net_nha_real_release_v1",
        "source_phase": "N4",
        "source_dir": str(source),
        "release_dir": str(output),
        "files": [
            {
                "name": name,
                "sha256": _sha256_file(output / name),
                "bytes": (output / name).stat().st_size,
            }
            for name in RELEASE_FILES
        ],
        "counts": validation["counts"],
        "safety_contract": validation["safety_contract"],
    }
    _write_json(output / "trace_net_nha_real_release_manifest_v1.json", manifest)
    checked = check_promoted_release(output)
    return {
        **manifest,
        "quality_status": checked["quality_status"],
        "failures": checked["failures"],
        "warnings": checked["warnings"],
    }


def check_promoted_release(release_dir: str | Path) -> dict[str, Any]:
    root = Path(release_dir).resolve()
    manifest_path = root / "trace_net_nha_real_release_manifest_v1.json"
    failures: list[str] = []
    if not manifest_path.exists():
        return {
            "schema_version": SCHEMA_VERSION,
            "module": MODULE,
            "status": "TRACE_NET_NHA_PHASE9_RELEASE_CHECK_V1",
            "quality_status": "FAIL",
            "failures": ["missing_release_manifest"],
            "warnings": [],
        }
    manifest = _read_json(manifest_path)
    if str(manifest.get("quality_status") or "") != "PASS":
        failures.append("manifest_quality_not_pass")
    expected = {str(row.get("name") or ""): str(row.get("sha256") or "") for row in manifest.get("files") or []}
    for name in RELEASE_FILES:
        path = root / name
        if not path.exists():
            failures.append(f"missing_release_file:{name}")
        elif _sha256_file(path) != expected.get(name):
            failures.append(f"release_checksum_mismatch:{name}")
    validation = validate_release_source(root)
    failures.extend(validation.get("failures") or [])
    return {
        "schema_version": SCHEMA_VERSION,
        "module": MODULE,
        "status": "TRACE_NET_NHA_PHASE9_RELEASE_CHECK_V1",
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": _dedupe(failures),
        "warnings": [],
        "counts": validation.get("counts") or {},
        "release_dir": str(root),
        "manifest_sha256": _sha256_file(manifest_path),
        "safety_contract": validation.get("safety_contract") or {},
    }


def build_live20_bank(phase4_dir: str | Path, *, total: int = 20, max_depth: int = 8) -> list[dict[str, Any]]:
    from scripts.trace_net_nha_phase7_8_runtime_v1 import load_real_engine

    engine, source = load_real_engine(phase4_dir, max_depth=max_depth)
    relationships = [dict(row) for row in source["relationships"]]
    children = sorted(_dedupe(row.get("child_part") for row in relationships))
    direct: list[tuple[str, dict[str, Any]]] = []
    limited: list[tuple[str, dict[str, Any]]] = []
    for child in children:
        result = engine.direct_nha(child)
        if result.get("behavior") == "direct_answer" and result.get("pages"):
            direct.append((child, result))
        elif result.get("behavior") in {"conflict_limited", "candidate_or_clarification"} and result.get("pages"):
            limited.append((child, result))

    cases: list[dict[str, Any]] = []

    def add(kind: str, query: str, action: str, result: Mapping[str, Any] | None = None) -> None:
        result = dict(result or {})
        cases.append({
            "case_id": f"NHA-LIVE20-{len(cases) + 1:03d}",
            "kind": kind,
            "query": query,
            "expected_action": action,
            "expected_behavior": str(result.get("behavior") or ""),
            "expected_direct_nha": str(result.get("direct_nha") or ""),
            "expected_parent_candidates": _dedupe(result.get("parent_candidates") or []),
            "expected_chain": _dedupe(result.get("chain") or []),
            "expected_direct_children": _dedupe(result.get("direct_children") or []),
            "expected_descendants": _dedupe(result.get("descendants") or []),
            "expected_pages": _dedupe(result.get("pages") or []),
            "stream": len(cases) % 2 == 1,
        })

    for child, result in direct[:8]:
        add("direct_nha", f"What is the direct NHA of part {child}?", "override", result)
    for child, result in limited[:3]:
        add("limited_nha", f"What is the direct NHA of part {child}?", "override", result)

    supported = [row for row in relationships if row.get("relationship_status") == "source_supported" and row.get("direct_nha")]
    parents = sorted(_dedupe(row.get("direct_nha") for row in supported))
    parent_added = 0
    for parent in parents:
        result = engine.direct_children(parent)
        if result.get("behavior") == "direct_children_answer" and result.get("pages"):
            add("direct_children", f"List the direct children of assembly {parent}.", "override", result)
            parent_added += 1
            if parent_added >= 3:
                break

    chain_added = 0
    for row in sorted(supported, key=lambda value: (-int(value.get("hierarchy_depth") or 0), str(value.get("child_part") or ""))):
        child = str(row.get("child_part") or "")
        result = engine.ancestor_chain(child)
        if result.get("behavior") == "ordered_chain_answer" and len(result.get("chain") or []) > 2 and result.get("pages"):
            add("ancestor_chain", f"Show the complete assembly chain above {child}.", "override", result)
            chain_added += 1
            if chain_added >= 2:
                break

    tree_added = False
    for parent in parents:
        result = engine.descendants(parent)
        if result.get("behavior") == "tree_answer" and result.get("descendants") and result.get("pages"):
            add("direct_vs_descendant", f"Show direct versus lower descendants below assembly {parent}.", "override", result)
            tree_added = True
            break

    if direct:
        child, _ = direct[0]
        result = engine.page_evidence(child)
        add("relationship_evidence_page", f"Which page proves the NHA relationship for {child}?", "override", result)

    add("non_nha_control", "What can TRACE-Net do?", "passthrough")
    add("synthetic_block_control", "What is the direct NHA of synthetic part 990-91001-001?", "synthetic_blocked")

    if len(cases) != total or not tree_added:
        raise ValueError(f"unable_to_build_live20 expected={total} actual={len(cases)} tree_added={tree_added}")
    return cases


def _extract_answer(payload: Mapping[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
        return ""
    message = choices[0].get("message")
    return str(message.get("content") or "") if isinstance(message, Mapping) else ""


def _parse_stream_answer(raw: str) -> str:
    pieces: list[str] = []
    for line in raw.splitlines():
        if not line.startswith("data: "):
            continue
        value = line[6:].strip()
        if not value or value == "[DONE]":
            continue
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            continue
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
            continue
        delta = choices[0].get("delta")
        if isinstance(delta, Mapping) and isinstance(delta.get("content"), str):
            pieces.append(str(delta.get("content")))
    return "".join(pieces)


def post_chat(
    base_url: str,
    *,
    api_key: str,
    model: str,
    query: str,
    stream: bool,
    timeout: float,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": query}],
        "stream": bool(stream),
        "temperature": 0,
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            headers = {key.casefold(): value for key, value in response.headers.items()}
            if stream:
                answer = _parse_stream_answer(raw)
                body: dict[str, Any] = {}
            else:
                body = json.loads(raw)
                answer = _extract_answer(body)
            return {
                "http_status": int(response.status),
                "headers": headers,
                "answer": answer,
                "body": body,
                "raw": raw,
                "latency_seconds": round(time.perf_counter() - started, 3),
            }
    except urllib.error.HTTPError as exc:
        return {
            "http_status": int(exc.code),
            "headers": {key.casefold(): value for key, value in exc.headers.items()},
            "answer": "",
            "body": {},
            "raw": exc.read().decode("utf-8", errors="replace"),
            "latency_seconds": round(time.perf_counter() - started, 3),
        }
    except Exception as exc:
        return {
            "http_status": 599,
            "headers": {},
            "answer": "",
            "body": {},
            "raw": f"{type(exc).__name__}: {exc}",
            "latency_seconds": round(time.perf_counter() - started, 3),
        }


def evaluate_live_case(case: Mapping[str, Any], response: Mapping[str, Any], *, latency_hard_limit: float) -> dict[str, Any]:
    failures: list[str] = []
    answer = str(response.get("answer") or "")
    headers = {str(key).casefold(): str(value) for key, value in (response.get("headers") or {}).items()}
    expected_action = str(case.get("expected_action") or "")
    action = headers.get("x-trace-net-nha-action", "")
    behavior = headers.get("x-trace-net-nha-behavior", "")
    route = headers.get("x-trace-net-route", "")
    if int(response.get("http_status") or 0) != 200:
        failures.append(f"http_status:{response.get('http_status')}")
    if not answer.strip():
        failures.append("empty_answer")
    if action != expected_action:
        failures.append(f"action expected={expected_action} actual={action}")
    if float(response.get("latency_seconds") or 0.0) > latency_hard_limit:
        failures.append("latency_hard_limit_exceeded")

    if expected_action == "override":
        if route != "assembly_relationship_reasoning":
            failures.append(f"route_mismatch:{route}")
        expected_behavior = str(case.get("expected_behavior") or "")
        if behavior != expected_behavior:
            failures.append(f"behavior expected={expected_behavior} actual={behavior}")
        for heading in ("## Answer", "## Evidence", "## Limits"):
            if heading not in answer:
                failures.append(f"missing_heading:{heading}")
        for page in case.get("expected_pages") or []:
            if str(page) not in answer:
                failures.append(f"missing_page:{page}")
        if case.get("expected_pages") and "[1]" not in answer:
            failures.append("missing_citation_marker")
        evidence_only = str(case.get("kind") or "") == "relationship_evidence_page"
        expected_direct = str(case.get("expected_direct_nha") or "")
        if not evidence_only and expected_direct and expected_direct not in answer:
            failures.append("missing_expected_direct_nha")
        if not evidence_only:
            for value in case.get("expected_parent_candidates") or []:
                if str(value) not in answer:
                    failures.append(f"missing_parent_candidate:{value}")
            for value in case.get("expected_chain") or []:
                if str(value) not in answer:
                    failures.append(f"missing_chain_part:{value}")
            for value in case.get("expected_direct_children") or []:
                if str(value) not in answer:
                    failures.append(f"missing_direct_child:{value}")
        lowered = answer.casefold()
        for marker in ("synthetic benchmark", "relationship_id", "truth_mode", "benchmark_truth_status"):
            if marker in lowered:
                failures.append(f"public_internal_leak:{marker}")
    elif expected_action == "synthetic_blocked":
        if route != "synthetic_identifier_blocked":
            failures.append(f"synthetic_route_mismatch:{route}")
        lowered = answer.casefold()
        if "reserved benchmark identifier" not in lowered or "not available to production" not in lowered:
            failures.append("synthetic_block_message_missing")
        if "source page" in lowered or "[1]" in answer:
            failures.append("synthetic_block_fake_evidence")
    elif expected_action == "passthrough":
        if route != "upstream":
            failures.append(f"passthrough_route_mismatch:{route}")

    return {
        "case_id": case.get("case_id") or "",
        "kind": case.get("kind") or "",
        "query": case.get("query") or "",
        "stream": bool(case.get("stream")),
        "expected_action": expected_action,
        "actual_action": action,
        "expected_behavior": case.get("expected_behavior") or "",
        "actual_behavior": behavior,
        "route": route,
        "http_status": response.get("http_status"),
        "latency_seconds": response.get("latency_seconds"),
        "passed": not failures,
        "failures": failures,
        "answer": answer,
        "headers": headers,
    }


def validate_live20(results: Sequence[Mapping[str, Any]], *, expected_count: int = 20) -> dict[str, Any]:
    failures: list[str] = []
    if len(results) != expected_count:
        failures.append(f"question_count expected={expected_count} actual={len(results)}")
    pass_count = sum(bool(row.get("passed")) for row in results)
    if pass_count != len(results):
        failures.append(f"failed_question_count:{len(results) - pass_count}")
    http_200 = sum(int(row.get("http_status") or 0) == 200 for row in results)
    action_matches = sum(str(row.get("expected_action") or "") == str(row.get("actual_action") or "") for row in results)
    override_results = [row for row in results if row.get("expected_action") == "override"]
    synthetic_results = [row for row in results if row.get("expected_action") == "synthetic_blocked"]
    passthrough_results = [row for row in results if row.get("expected_action") == "passthrough"]
    latencies = [float(row.get("latency_seconds") or 0.0) for row in results]
    return {
        "schema_version": SCHEMA_VERSION,
        "module": MODULE,
        "status": "TRACE_NET_NHA_PHASE10_LIVE20_V1",
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "warnings": [],
        "counts": {
            "question_count": len(results),
            "pass_count": pass_count,
            "fail_count": len(results) - pass_count,
            "http_200_count": http_200,
            "action_match_count": action_matches,
            "override_count": len(override_results),
            "override_pass_count": sum(bool(row.get("passed")) for row in override_results),
            "synthetic_block_count": len(synthetic_results),
            "synthetic_block_pass_count": sum(bool(row.get("passed")) for row in synthetic_results),
            "passthrough_control_count": len(passthrough_results),
            "passthrough_control_pass_count": sum(bool(row.get("passed")) for row in passthrough_results),
            "stream_count": sum(bool(row.get("stream")) for row in results),
            "nonstream_count": sum(not bool(row.get("stream")) for row in results),
            "production_graph_write_count": 0,
            "source_artifact_mutation_count": 0,
            "synthetic_artifact_access_count": 0,
        },
        "latency": {
            "average_seconds": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
            "maximum_seconds": round(max(latencies), 3) if latencies else 0.0,
        },
        "safety_contract": {
            "real_release_only": True,
            "synthetic_identifier_returns_safe_block": True,
            "synthetic_identifier_upstream_passthrough": False,
            "non_nha_passthrough": True,
            "llm_calls_for_nha_overrides": 0,
            "source_truth_mutation_allowed": False,
        },
    }


def write_live20_artifacts(output_dir: str | Path, bank: Sequence[Mapping[str, Any]], results: Sequence[Mapping[str, Any]], quality: Mapping[str, Any]) -> dict[str, Any]:
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    _write_json(output / "trace_net_nha_phase10_live20_bank_v1.json", {"records": list(bank)})
    _write_json(output / "trace_net_nha_phase10_live20_results_v1.json", {"records": list(results)})
    _write_jsonl(output / "trace_net_nha_phase10_live20_results_v1.jsonl", results)
    _write_json(output / "trace_net_nha_phase10_live20_quality_v1.json", dict(quality))
    summary = {
        "schema_version": SCHEMA_VERSION,
        "module": MODULE,
        "status": "TRACE_NET_NHA_PHASE10_LIVE20_V1",
        "quality_status": quality.get("quality_status"),
        "output_dir": str(output),
        "counts": quality.get("counts") or {},
        "latency": quality.get("latency") or {},
        "failures": quality.get("failures") or [],
        "warnings": quality.get("warnings") or [],
        "artifacts": [
            "trace_net_nha_phase10_live20_bank_v1.json",
            "trace_net_nha_phase10_live20_results_v1.json",
            "trace_net_nha_phase10_live20_results_v1.jsonl",
            "trace_net_nha_phase10_live20_quality_v1.json",
        ],
    }
    _write_json(output / "trace_net_nha_phase10_live20_summary_v1.json", summary)
    return summary
