#!/usr/bin/env python3
"""TRACE-Net NHA N6: deterministic read-only query engine and benchmark runner.

N6 consumes the real N4 hierarchy artifacts and the isolated N5 synthetic
benchmark overlay. Synthetic data is usable only when explicitly enabled. The
module performs no LLM calls and no Postgres, Qdrant, OpenSearch, TIFF, OCR, or
source-truth writes.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

MODULE = "trace_net_nha_phase6_query_benchmark_v1"
STATUS = "TRACE_NET_NHA_PHASE6_QUERY_BENCHMARK_V1"
SCHEMA_VERSION = "trace_net_nha_phase6_query_benchmark_v1"

SYNTHETIC_PART_RE = re.compile(r"\b990-\d{5}-\d{3}\b", re.I)
REAL_PART_RE = re.compile(r"\b(?:\d{2,4}-\d{4,6}-\d{3}|[A-Z]{2,}\d{3,}[A-Z0-9-]*)\b", re.I)
PROJECT_RE = re.compile(r"\bSYN-PROJECT-\d{2}[A-Z]\b", re.I)
CONFIG_RE = re.compile(r"\bSYN-CONFIG-\d{2}[A-Z]\b", re.I)
REVISION_RE = re.compile(r"\bSYN-REV-\d{2}[A-Z]\b", re.I)

DIRECT_CATEGORIES = {
    "direct_nha",
    "attaching_direct_nha",
    "project_scoped_nha",
    "revision_scoped_nha",
}
CHAIN_CATEGORIES = {
    "ancestor_chain",
    "attaching_chain",
    "attaching_ancestor_chain",
}


def _compact(value: Any, limit: int = 20000) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _stable_id(prefix: str, *values: Any) -> str:
    blob = "|".join(_compact(value, 5000) for value in values)
    return f"{prefix}:{hashlib.sha256(blob.encode('utf-8')).hexdigest()[:20]}"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("records", "items", "rows", "cases", "questions"):
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(row) for row in value if isinstance(row, Mapping)]
    return []


def _dedupe(values: Iterable[Any]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))


def _item_sort(value: Any) -> tuple[int, str]:
    text = str(value or "")
    match = re.search(r"\d+", text)
    return (int(match.group(0)) if match else 10**9, text)


def _extract_part(query: str, *, synthetic: bool) -> str:
    pattern = SYNTHETIC_PART_RE if synthetic else REAL_PART_RE
    match = pattern.search(str(query or ""))
    return match.group(0).upper() if match else ""


def _extract_scope(query: str) -> dict[str, str]:
    text = str(query or "")
    project = PROJECT_RE.search(text)
    config = CONFIG_RE.search(text)
    revision = REVISION_RE.search(text)
    return {
        "project_id": project.group(0).upper() if project else "",
        "configuration_id": config.group(0).upper() if config else "",
        "revision_id": revision.group(0).upper() if revision else "",
    }


def load_phase6_inputs(
    phase4_dir: str | Path,
    phase5_dir: str | Path,
    *,
    enable_synthetic_benchmark: bool,
) -> dict[str, Any]:
    phase4 = Path(phase4_dir).resolve()
    phase5 = Path(phase5_dir).resolve()
    required = {
        "real_relationships": phase4 / "trace_net_nha_hierarchy_relationships_v1.json",
        "real_answer_key": phase4 / "trace_net_nha_phase4_answer_key_v1.json",
        "phase4_quality": phase4 / "trace_net_nha_phase4_quality_v1.json",
        "synthetic_relationships": phase5 / "trace_net_nha_synthetic_relationships_v1.json",
        "synthetic_assignments": phase5 / "trace_net_nha_synthetic_page_assignments_v1.json",
        "synthetic_questions": phase5 / "trace_net_nha_synthetic_question_bank_v1.json",
        "synthetic_scenarios": phase5 / "trace_net_nha_synthetic_scenarios_v1.json",
        "phase5_quality": phase5 / "trace_net_nha_phase5_quality_v1.json",
    }
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("missing_nha_phase6_inputs: " + ", ".join(missing))
    if not enable_synthetic_benchmark:
        raise PermissionError("synthetic_benchmark_requires_explicit_enable_flag")
    phase4_quality = _read_json(required["phase4_quality"])
    phase5_quality = _read_json(required["phase5_quality"])
    if str(phase4_quality.get("quality_status") or "") != "PASS":
        raise ValueError("phase4_quality_status_not_pass")
    if str(phase5_quality.get("quality_status") or "") != "PASS":
        raise ValueError("phase5_quality_status_not_pass")
    return {
        "phase4_dir": str(phase4),
        "phase5_dir": str(phase5),
        "paths": {key: str(path) for key, path in required.items()},
        "sha256": {key: _sha256_file(path) for key, path in required.items()},
        "real_relationships": _records(_read_json(required["real_relationships"])),
        "real_answer_key": _records(_read_json(required["real_answer_key"])),
        "synthetic_relationships": _records(_read_json(required["synthetic_relationships"])),
        "synthetic_assignments": _records(_read_json(required["synthetic_assignments"])),
        "synthetic_questions": _records(_read_json(required["synthetic_questions"])),
        "synthetic_scenarios": _records(_read_json(required["synthetic_scenarios"])),
    }


class NHAQueryEngine:
    """Bounded deterministic queries over real or explicitly enabled synthetic relations."""

    def __init__(
        self,
        relationships: Sequence[Mapping[str, Any]],
        *,
        truth_mode: str,
        assignments: Sequence[Mapping[str, Any]] | None = None,
        scenarios: Sequence[Mapping[str, Any]] | None = None,
        synthetic_enabled: bool = False,
        max_depth: int = 8,
    ) -> None:
        self.truth_mode = truth_mode
        self.synthetic_enabled = bool(synthetic_enabled)
        self.max_depth = max(1, min(int(max_depth), 32))
        if truth_mode == "synthetic_benchmark" and not self.synthetic_enabled:
            raise PermissionError("synthetic_query_engine_disabled")
        self.relationships = [dict(row) for row in relationships]
        self.assignments = [dict(row) for row in assignments or []]
        self.scenarios = [dict(row) for row in scenarios or []]
        self.by_child: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.assignment_by_relationship: dict[str, dict[str, Any]] = {}
        self.assignment_by_scenario: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.isolated_parts: dict[str, dict[str, Any]] = {}

        for assignment in self.assignments:
            rid = str(assignment.get("relationship_id") or "")
            if rid:
                self.assignment_by_relationship[rid] = assignment
            self.assignment_by_scenario[str(assignment.get("scenario_id") or "")].append(assignment)
        for scenario in self.scenarios:
            isolated = str(scenario.get("isolated_part") or "").upper()
            if isolated:
                self.isolated_parts[isolated] = scenario

        for row in self.relationships:
            child = str(row.get("child_part") or "").upper()
            if child:
                self.by_child[child].append(row)
            for parent in row.get("parent_candidates") or []:
                parent_text = str(parent).upper()
                if parent_text:
                    self.by_parent[parent_text].append(row)
        for mapping in (self.by_child, self.by_parent):
            for key in mapping:
                mapping[key].sort(key=lambda row: (
                    str(row.get("project_id") or ""),
                    str(row.get("configuration_id") or ""),
                    str(row.get("revision_id") or ""),
                    _item_sort(row.get("item_number")),
                    str(row.get("child_part") or ""),
                ))

    def _is_confirmed(self, row: Mapping[str, Any]) -> bool:
        if self.truth_mode == "synthetic_benchmark":
            return str(row.get("benchmark_truth_status") or "") == "confirmed" and bool(row.get("direct_nha"))
        return str(row.get("relationship_status") or "") == "source_supported" and bool(row.get("direct_nha"))

    def _is_conflict(self, row: Mapping[str, Any]) -> bool:
        if self.truth_mode == "synthetic_benchmark":
            return str(row.get("benchmark_truth_status") or "") == "conflict"
        return str(row.get("relationship_status") or "") == "ambiguous"

    @staticmethod
    def _matches_scope(row: Mapping[str, Any], scope: Mapping[str, str]) -> bool:
        for key in ("project_id", "configuration_id", "revision_id"):
            expected = str(scope.get(key) or "")
            if expected and str(row.get(key) or "") != expected:
                return False
        return True

    def _rows_for_child(self, child: str, scope: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
        rows = list(self.by_child.get(str(child).upper(), []))
        if scope:
            rows = [row for row in rows if self._matches_scope(row, scope)]
        return rows

    def _pages_for_rows(self, rows: Sequence[Mapping[str, Any]]) -> list[str]:
        pages: list[str] = []
        for row in rows:
            if self.truth_mode == "synthetic_benchmark":
                page = str(row.get("assigned_page_id") or "")
                if page:
                    pages.append(page)
            else:
                pages.extend([
                    str(row.get("row_page_id") or ""),
                    *[str(value) for value in row.get("anchor_page_ids") or []],
                ])
        return _dedupe(pages)

    @staticmethod
    def _contexts(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
        return {
            "project_ids": _dedupe(row.get("project_id") for row in rows),
            "configuration_ids": _dedupe(row.get("configuration_id") for row in rows),
            "revision_ids": _dedupe(row.get("revision_id") for row in rows),
        }

    def direct_nha(self, child: str, scope: Mapping[str, str] | None = None) -> dict[str, Any]:
        child = str(child).upper()
        rows = self._rows_for_child(child, scope)
        confirmed = [row for row in rows if self._is_confirmed(row)]
        conflicts = [row for row in rows if self._is_conflict(row)]
        if conflicts:
            candidates = _dedupe(parent for row in conflicts for parent in row.get("parent_candidates") or [])
            return self._result(
                "conflict_limited", child=child, parent_candidates=candidates,
                pages=self._pages_for_rows(conflicts), rows=conflicts, scope=scope,
                item_order=[str(row.get("item_number") or "") for row in conflicts],
                **self._contexts(conflicts),
            )
        parent_values = _dedupe(row.get("direct_nha") for row in confirmed)
        if len(parent_values) == 1:
            selected = [row for row in confirmed if str(row.get("direct_nha") or "") == parent_values[0]]
            return self._result(
                "direct_answer", child=child, direct_nha=parent_values[0],
                parent_candidates=parent_values, pages=self._pages_for_rows(selected),
                item_order=[str(row.get("item_number") or "") for row in selected],
                rows=selected, scope=scope, **self._contexts(selected),
            )
        if len(parent_values) > 1:
            return self._result(
                "candidate_or_clarification", child=child, parent_candidates=parent_values,
                pages=self._pages_for_rows(confirmed), rows=confirmed, scope=scope,
                item_order=[str(row.get("item_number") or "") for row in confirmed],
                limits=["Multiple context-specific parents remain; add project, configuration, or revision."],
                **self._contexts(confirmed),
            )
        if child in self.isolated_parts:
            scenario = self.isolated_parts[child]
            assignments = self.assignment_by_scenario.get(str(scenario.get("scenario_id") or ""), [])
            return self._result(
                "no_relationship", child=child,
                pages=_dedupe(row.get("page_id") for row in assignments), rows=[], scope=scope,
                project_ids=[str(value) for value in scenario.get("project_ids") or []],
                configuration_ids=[str(value) for value in scenario.get("configuration_ids") or []],
                revision_ids=[str(value) for value in scenario.get("revision_ids") or []],
            )
        candidates = _dedupe(parent for row in rows for parent in row.get("parent_candidates") or [])
        if candidates:
            return self._result(
                "candidate_or_clarification", child=child, parent_candidates=candidates,
                pages=self._pages_for_rows(rows), rows=rows, scope=scope,
                item_order=[str(row.get("item_number") or "") for row in rows],
                **self._contexts(rows),
            )
        return self._result("no_relationship", child=child, rows=[], pages=[], scope=scope)

    def ancestor_chain(self, child: str, scope: Mapping[str, str] | None = None) -> dict[str, Any]:
        child = str(child).upper()
        chain = [child]
        pages: list[str] = []
        items: list[str] = []
        used_rows: list[dict[str, Any]] = []
        visited = {child}
        current = child
        for _ in range(self.max_depth):
            direct = self.direct_nha(current, scope)
            if direct["behavior"] == "no_relationship":
                break
            if direct["behavior"] != "direct_answer":
                return self._result(
                    direct["behavior"], child=child, chain=chain,
                    parent_candidates=direct.get("parent_candidates") or [],
                    pages=_dedupe([*pages, *direct.get("pages", [])]),
                    item_order=items, rows=[*used_rows, *direct.get("rows", [])], scope=scope,
                    limits=direct.get("limits") or [],
                    **self._contexts([*used_rows, *direct.get("rows", [])]),
                )
            parent = str(direct.get("direct_nha") or "")
            if not parent:
                break
            if parent in visited:
                return self._result(
                    "cycle_blocked", child=child, chain=[*chain, parent],
                    pages=_dedupe([*pages, *direct.get("pages", [])]),
                    rows=[*used_rows, *direct.get("rows", [])], scope=scope,
                    limits=["A cycle was detected; no chain conclusion is released."],
                )
            relation_rows = list(direct.get("rows") or [])
            pages.extend(direct.get("pages") or [])
            if relation_rows:
                items.append(str(relation_rows[0].get("item_number") or ""))
            used_rows.extend(relation_rows)
            chain.append(parent)
            visited.add(parent)
            current = parent
        behavior = "ordered_chain_answer" if len(chain) > 1 else "no_relationship"
        return self._result(
            behavior, child=child, direct_nha=chain[1] if len(chain) > 1 else "",
            chain=chain, pages=_dedupe(pages), item_order=items, rows=used_rows, scope=scope,
            **self._contexts(used_rows),
        )

    def direct_children(self, parent: str, scope: Mapping[str, str] | None = None) -> dict[str, Any]:
        parent = str(parent).upper()
        rows = [row for row in self.by_parent.get(parent, []) if self._is_confirmed(row)]
        if scope:
            rows = [row for row in rows if self._matches_scope(row, scope)]
        rows.sort(key=lambda row: (_item_sort(row.get("item_number")), str(row.get("child_part") or "")))
        children = _dedupe(row.get("child_part") for row in rows if str(row.get("direct_nha") or "").upper() == parent)
        return self._result(
            "direct_children_answer" if children else "no_relationship",
            parent=parent, direct_children=children, pages=self._pages_for_rows(rows),
            item_order=[str(row.get("item_number") or "") for row in rows], rows=rows, scope=scope,
            **self._contexts(rows),
        )

    def descendants(self, parent: str, scope: Mapping[str, str] | None = None) -> dict[str, Any]:
        parent = str(parent).upper()
        queue: deque[tuple[str, int]] = deque([(parent, 0)])
        visited = {parent}
        direct_children: list[str] = []
        descendants: list[str] = []
        pages: list[str] = []
        rows_used: list[dict[str, Any]] = []
        deepest_chain: list[str] = [parent]
        parent_path: dict[str, list[str]] = {parent: [parent]}
        while queue:
            current, depth = queue.popleft()
            if depth >= self.max_depth:
                continue
            result = self.direct_children(current, scope)
            child_rows = list(result.get("rows") or [])
            for row in child_rows:
                child = str(row.get("child_part") or "").upper()
                if not child or child in visited:
                    continue
                visited.add(child)
                rows_used.append(row)
                pages.extend(self._pages_for_rows([row]))
                path = [*parent_path[current], child]
                parent_path[child] = path
                if len(path) > len(deepest_chain):
                    deepest_chain = path
                if depth == 0:
                    direct_children.append(child)
                else:
                    descendants.append(child)
                queue.append((child, depth + 1))
        bottom_up_chain = list(reversed(deepest_chain)) if len(deepest_chain) > 1 else []
        return self._result(
            "tree_answer" if direct_children else "no_relationship", parent=parent,
            direct_children=direct_children, descendants=descendants, chain=bottom_up_chain,
            pages=_dedupe(pages), rows=rows_used, scope=scope,
            **self._contexts(rows_used),
        )

    def compare_by_scope(self, child: str, dimension: str) -> dict[str, Any]:
        child = str(child).upper()
        rows = [row for row in self._rows_for_child(child) if self._is_confirmed(row)]
        rows.sort(key=lambda row: (str(row.get(dimension) or ""), _item_sort(row.get("item_number"))))
        comparisons = [
            {
                dimension: str(row.get(dimension) or ""),
                "direct_nha": str(row.get("direct_nha") or ""),
                "project_id": str(row.get("project_id") or ""),
                "configuration_id": str(row.get("configuration_id") or ""),
                "revision_id": str(row.get("revision_id") or ""),
                "page_id": str(row.get("assigned_page_id") or row.get("row_page_id") or ""),
            }
            for row in rows
        ]
        return self._result(
            "scoped_comparison_answer" if comparisons else "no_relationship",
            child=child, parent_candidates=_dedupe(row["direct_nha"] for row in comparisons),
            pages=_dedupe(row["page_id"] for row in comparisons), comparisons=comparisons, rows=rows,
            **self._contexts(rows),
        )

    def page_evidence(self, child: str, scope: Mapping[str, str] | None = None) -> dict[str, Any]:
        direct = self.direct_nha(child, scope)
        behavior = "page_and_trait_answer" if direct.get("pages") else direct["behavior"]
        return {**direct, "behavior": behavior}

    def no_relationship_page(self, child: str) -> dict[str, Any]:
        direct = self.direct_nha(child)
        behavior = "page_and_negative_answer" if direct["behavior"] == "no_relationship" and direct.get("pages") else direct["behavior"]
        return {**direct, "behavior": behavior}

    def execute_question(self, question: Mapping[str, Any]) -> dict[str, Any]:
        category = str(question.get("category") or "")
        query = str(question.get("query") or "")
        synthetic = self.truth_mode == "synthetic_benchmark"
        part = _extract_part(query, synthetic=synthetic)
        scope = _extract_scope(query)
        if category in DIRECT_CATEGORIES:
            result = self.direct_nha(part, scope)
            if result.get("behavior") == "direct_answer":
                chain_result = self.ancestor_chain(part, scope)
                if chain_result.get("behavior") == "ordered_chain_answer":
                    result["chain"] = list(chain_result.get("chain") or [])
        elif category == "relationship_evidence_page":
            result = self.page_evidence(part, scope)
        elif category in CHAIN_CATEGORIES:
            result = self.ancestor_chain(part, scope)
        elif category in {"direct_children", "direct_child_count"}:
            result = self.direct_children(part, scope)
            if category == "direct_child_count" and result["behavior"] != "no_relationship":
                result["behavior"] = "count_answer"
                result["count"] = len(result.get("direct_children") or [])
        elif category == "direct_vs_descendant":
            result = self.descendants(part, scope)
        elif category == "project_comparison":
            result = self.compare_by_scope(part, "project_id")
        elif category == "revision_change":
            result = self.compare_by_scope(part, "revision_id")
        elif category in {"contradiction_resolution", "conflict_evidence"}:
            result = self.direct_nha(part, scope)
            if category == "conflict_evidence" and result["behavior"] == "conflict_limited":
                result["behavior"] = "conflict_evidence_answer"
        elif category == "no_nha":
            result = self.direct_nha(part, scope)
        elif category == "negative_page_retrieval":
            result = self.no_relationship_page(part)
        else:
            result = self._result("unsupported_query", child=part, limits=[f"Unsupported category: {category}"])
        result["category"] = category
        result["query"] = query
        result["public_answer"] = render_public_answer(result, synthetic=synthetic)
        return result

    def _result(self, behavior: str, **kwargs: Any) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "module": MODULE,
            "status": STATUS,
            "truth_mode": self.truth_mode,
            "behavior": behavior,
            "child": "",
            "parent": "",
            "direct_nha": "",
            "parent_candidates": [],
            "chain": [],
            "direct_children": [],
            "descendants": [],
            "pages": [],
            "item_order": [],
            "rows": [],
            "comparisons": [],
            "project_ids": [],
            "configuration_ids": [],
            "revision_ids": [],
            "limits": [],
            "read_only": True,
            "source_truth_mutation_allowed": False,
            "production_graph_write_count": 0,
            **kwargs,
        }


def render_public_answer(result: Mapping[str, Any], *, synthetic: bool) -> str:
    label = "Synthetic benchmark only. " if synthetic else ""
    behavior = str(result.get("behavior") or "")
    child = str(result.get("child") or "")
    parent = str(result.get("parent") or "")
    direct = str(result.get("direct_nha") or "")
    chain = [str(value) for value in result.get("chain") or []]
    children = [str(value) for value in result.get("direct_children") or []]
    descendants = [str(value) for value in result.get("descendants") or []]
    candidates = [str(value) for value in result.get("parent_candidates") or []]
    pages = [str(value) for value in result.get("pages") or []]
    comparisons = [dict(row) for row in result.get("comparisons") or []]

    if behavior == "direct_answer":
        answer = f"{label}The direct NHA of `{child}` is `{direct}`."
    elif behavior == "ordered_chain_answer":
        answer = f"{label}The ordered assembly chain is: " + " → ".join(f"`{value}`" for value in chain) + "."
    elif behavior in {"direct_children_answer", "count_answer"}:
        answer = f"{label}Assembly `{parent}` has {len(children)} direct child relationship(s): " + ", ".join(f"`{value}`" for value in children) + "."
    elif behavior == "tree_answer":
        answer = f"{label}Direct children of `{parent}`: " + (", ".join(f"`{value}`" for value in children) or "none") + ". Lower descendants: " + (", ".join(f"`{value}`" for value in descendants) or "none") + "."
    elif behavior == "scoped_comparison_answer":
        parts = [f"{row.get('project_id') or row.get('revision_id')}: `{row.get('direct_nha')}`" for row in comparisons]
        answer = f"{label}Context-specific parents are: " + "; ".join(parts) + "."
    elif behavior in {"conflict_limited", "conflict_evidence_answer"}:
        answer = f"{label}The parent relationship is conflicting; no direct NHA is confirmed. Candidates: " + ", ".join(f"`{value}`" for value in candidates) + "."
    elif behavior in {"page_and_trait_answer", "page_and_negative_answer"}:
        answer = f"{label}The benchmark relationship record is carried by: " + ", ".join(f"`{value}`" for value in pages) + "."
    elif behavior in {"candidate_or_clarification", "no_relationship"}:
        answer = f"{label}No single confirmed direct NHA is available for `{child}`."
    elif behavior == "cycle_blocked":
        answer = f"{label}A relationship cycle was detected, so no chain conclusion is released."
    else:
        answer = f"{label}No supported query result was produced."

    evidence_lines = [f"- Relationship page reference: `{page}`." for page in pages]
    if not evidence_lines:
        evidence_lines = ["- No relationship page reference was returned."]
    limits = list(result.get("limits") or [])
    if synthetic:
        limits.insert(0, "Synthetic traits are benchmark overlays; the physical TIFF and OCR were not modified.")
    if not limits:
        limits.append("Only direct, source-supported relationships are treated as confirmed.")
    return "\n".join([
        "## Answer", "", answer, "", "## Evidence", "", *evidence_lines,
        "", "## Limits", "", *[f"- {value}" for value in limits],
    ])


def evaluate_synthetic_question(question: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    expected_behavior = str(question.get("expected_behavior") or "")
    if str(result.get("behavior") or "") != expected_behavior:
        failures.append(f"behavior expected={expected_behavior} actual={result.get('behavior')}")
    for field in ("expected_direct_nha",):
        expected = str(question.get(field) or "")
        actual = str(result.get("direct_nha") or "")
        if expected and actual != expected:
            failures.append(f"direct_nha expected={expected} actual={actual}")
    list_checks = (
        ("expected_chain", "chain", True),
        ("expected_direct_children", "direct_children", True),
        ("expected_parent_candidates", "parent_candidates", True),
        ("expected_pages", "pages", False),
        ("expected_item_order", "item_order", True),
    )
    for expected_field, actual_field, ordered in list_checks:
        expected = [str(value) for value in question.get(expected_field) or []]
        if not expected:
            continue
        actual = [str(value) for value in result.get(actual_field) or []]
        mismatch = actual != expected if ordered else set(actual) != set(expected)
        if mismatch:
            failures.append(f"{actual_field} expected={expected} actual={actual}")
    for expected_field, actual_field in (
        ("expected_project_id", "project_ids"),
        ("expected_configuration_id", "configuration_ids"),
        ("expected_revision_id", "revision_ids"),
    ):
        expected = str(question.get(expected_field) or "")
        actual = [str(value) for value in result.get(actual_field) or []]
        if expected and expected not in actual:
            failures.append(f"{actual_field} missing={expected} actual={actual}")
    answer = str(result.get("public_answer") or "")
    if "Synthetic benchmark only" not in answer:
        failures.append("synthetic_label_missing")
    if "physical TIFF itself contains" in answer or "physical TIFF contains" in answer:
        failures.append("physical_tiff_synthetic_claim")
    if result.get("truth_mode") != "synthetic_benchmark":
        failures.append("truth_mode_not_synthetic")
    if result.get("production_graph_write_count") != 0:
        failures.append("production_graph_write_attempt")
    return {
        "question_id": question.get("question_id") or "",
        "scenario_id": question.get("scenario_id") or "",
        "category": question.get("category") or "",
        "query": question.get("query") or "",
        "expected_behavior": expected_behavior,
        "actual_behavior": result.get("behavior") or "",
        "passed": not failures,
        "failures": failures,
        "result": dict(result),
    }


def build_real_smoke_cases(answer_key_cases: Sequence[Mapping[str, Any]], maximum: int = 20) -> list[dict[str, Any]]:
    """Build a balanced real-source smoke set without contradictory expectations.

    A child may have one source-supported parent in one figure and additional
    ambiguous parent candidates elsewhere. Such a child must be evaluated as a
    context-required case; it must never also appear as a context-free direct
    answer merely because one supported row exists.
    """
    cases_by_child: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in answer_key_cases:
        child = str(row.get("child_part") or "")
        if child:
            cases_by_child[child].append(dict(row))

    supported: list[dict[str, Any]] = []
    limited: list[dict[str, Any]] = []

    for child, rows in cases_by_child.items():
        direct_rows = [
            row for row in rows
            if str(row.get("expected_behavior") or "") == "direct_answer"
        ]
        limited_rows = [
            row for row in rows
            if str(row.get("expected_behavior") or "") != "direct_answer"
        ]
        supported_parents = _dedupe(
            row.get("expected_direct_nha") for row in direct_rows
        )
        parent_candidates = _dedupe(
            value
            for row in rows
            for value in [
                row.get("expected_direct_nha"),
                *(row.get("expected_parent_candidates") or []),
            ]
        )
        expected_pages = _dedupe(
            page for row in rows for page in row.get("expected_pages") or []
        )
        depths = [
            int(row.get("expected_hierarchy_depth") or 0)
            for row in rows
            if int(row.get("expected_hierarchy_depth") or 0) > 0
        ]

        context_required = bool(limited_rows) or len(supported_parents) != 1
        if context_required:
            base = dict((limited_rows or direct_rows or rows)[0])
            base.update({
                "case_id": _stable_id(
                    "nha_phase6_real_context_case",
                    child,
                    parent_candidates,
                    expected_pages,
                ),
                "child_part": child,
                "expected_behavior": "candidate_or_clarification",
                "expected_direct_nha": "",
                "expected_parent_candidates": parent_candidates,
                "expected_pages": expected_pages,
                "expected_hierarchy_depth": min(depths) if depths else 1,
            })
            limited.append(base)
        elif direct_rows:
            supported.append(direct_rows[0])

    supported.sort(key=lambda row: (
        int(row.get("expected_hierarchy_depth") or 0),
        str(row.get("child_part") or ""),
    ))
    limited.sort(key=lambda row: str(row.get("child_part") or ""))
    limited_target = min(5, len(limited), maximum)
    supported_target = min(len(supported), max(0, maximum - limited_target))
    selected = supported[:supported_target]
    selected.extend(limited[: max(0, maximum - len(selected))])
    if len(selected) < maximum:
        selected.extend(
            supported[
                supported_target : supported_target + (maximum - len(selected))
            ]
        )
    return selected[:maximum]


def evaluate_real_smoke_case(case: Mapping[str, Any], engine: NHAQueryEngine) -> dict[str, Any]:
    child = str(case.get("child_part") or "")
    result = engine.direct_nha(child)
    failures: list[str] = []
    expected_behavior = str(case.get("expected_behavior") or "")
    if expected_behavior == "direct_answer":
        if result.get("behavior") != "direct_answer":
            failures.append(f"behavior expected=direct_answer actual={result.get('behavior')}")
        if str(result.get("direct_nha") or "") != str(case.get("expected_direct_nha") or ""):
            failures.append("direct_nha_mismatch")
    else:
        if result.get("behavior") not in {"candidate_or_clarification", "conflict_limited"}:
            failures.append(f"ambiguous_case_not_limited:{result.get('behavior')}")
        if result.get("direct_nha"):
            failures.append("ambiguous_case_positive_direct_nha")
    expected_pages = [str(value) for value in case.get("expected_pages") or []]
    if expected_pages and not set(result.get("pages") or []).intersection(expected_pages):
        failures.append("expected_page_not_recovered")
    return {
        "case_id": case.get("case_id") or "",
        "child_part": child,
        "expected_behavior": expected_behavior,
        "actual_behavior": result.get("behavior") or "",
        "passed": not failures,
        "failures": failures,
        "result": {**result, "public_answer": render_public_answer(result, synthetic=False)},
    }


def validate_phase6(
    synthetic_results: Sequence[Mapping[str, Any]],
    real_results: Sequence[Mapping[str, Any]],
    *,
    expected_synthetic_questions: int = 60,
    expected_real_questions: int = 20,
) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    if len(synthetic_results) != expected_synthetic_questions:
        failures.append(f"synthetic_question_count expected={expected_synthetic_questions} actual={len(synthetic_results)}")
    if len(real_results) != expected_real_questions:
        failures.append(f"real_question_count expected={expected_real_questions} actual={len(real_results)}")
    synthetic_pass = sum(bool(row.get("passed")) for row in synthetic_results)
    real_pass = sum(bool(row.get("passed")) for row in real_results)
    if synthetic_pass != len(synthetic_results):
        failures.append(f"synthetic_fail_count:{len(synthetic_results) - synthetic_pass}")
    if real_pass != len(real_results):
        failures.append(f"real_fail_count:{len(real_results) - real_pass}")
    if any((row.get("result") or {}).get("production_graph_write_count") != 0 for row in [*synthetic_results, *real_results]):
        failures.append("production_graph_write_attempt")
    if any((row.get("result") or {}).get("truth_mode") != "synthetic_benchmark" for row in synthetic_results):
        failures.append("synthetic_truth_mode_leak")
    if any((row.get("result") or {}).get("truth_mode") != "real_source" for row in real_results):
        failures.append("real_truth_mode_leak")
    if not synthetic_results:
        warnings.append("no_synthetic_results")
    if not real_results:
        warnings.append("no_real_results")
    return {
        "schema_version": SCHEMA_VERSION,
        "module": MODULE,
        "status": STATUS,
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "warnings": warnings,
        "counts": {
            "synthetic_question_count": len(synthetic_results),
            "synthetic_pass_count": synthetic_pass,
            "synthetic_fail_count": len(synthetic_results) - synthetic_pass,
            "real_smoke_question_count": len(real_results),
            "real_smoke_pass_count": real_pass,
            "real_smoke_fail_count": len(real_results) - real_pass,
            "llm_call_count": 0,
            "production_graph_write_count": 0,
            "source_artifact_mutation_count": 0,
        },
        "safety_contract": {
            "read_only": True,
            "synthetic_requires_explicit_enable": True,
            "synthetic_never_supports_production_claims": True,
            "physical_tiff_modified": False,
            "ocr_source_modified": False,
            "phase4_artifacts_mutated": False,
            "phase5_artifacts_mutated": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "llm_call_count": 0,
        },
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def build_phase6(
    *,
    phase4_dir: str | Path,
    phase5_dir: str | Path,
    output_dir: str | Path,
    enable_synthetic_benchmark: bool,
    expected_synthetic_questions: int = 60,
    expected_real_questions: int = 20,
    max_depth: int = 8,
) -> dict[str, Any]:
    source = load_phase6_inputs(
        phase4_dir,
        phase5_dir,
        enable_synthetic_benchmark=enable_synthetic_benchmark,
    )
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    synthetic_engine = NHAQueryEngine(
        source["synthetic_relationships"],
        truth_mode="synthetic_benchmark",
        assignments=source["synthetic_assignments"],
        scenarios=source["synthetic_scenarios"],
        synthetic_enabled=True,
        max_depth=max_depth,
    )
    real_engine = NHAQueryEngine(
        source["real_relationships"], truth_mode="real_source", max_depth=max_depth,
    )

    synthetic_results: list[dict[str, Any]] = []
    for question in source["synthetic_questions"]:
        started = time.perf_counter()
        result = synthetic_engine.execute_question(question)
        evaluation = evaluate_synthetic_question(question, result)
        evaluation["latency_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
        synthetic_results.append(evaluation)

    real_cases = build_real_smoke_cases(source["real_answer_key"], maximum=expected_real_questions)
    real_results: list[dict[str, Any]] = []
    for case in real_cases:
        started = time.perf_counter()
        evaluation = evaluate_real_smoke_case(case, real_engine)
        evaluation["latency_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
        real_results.append(evaluation)

    validation = validate_phase6(
        synthetic_results,
        real_results,
        expected_synthetic_questions=expected_synthetic_questions,
        expected_real_questions=expected_real_questions,
    )
    write_json(output / "trace_net_nha_phase6_synthetic_results_v1.json", {"records": synthetic_results})
    write_jsonl(output / "trace_net_nha_phase6_synthetic_results_v1.jsonl", synthetic_results)
    write_json(output / "trace_net_nha_phase6_real_smoke_results_v1.json", {"records": real_results})
    write_jsonl(output / "trace_net_nha_phase6_real_smoke_results_v1.jsonl", real_results)
    write_json(output / "trace_net_nha_phase6_quality_v1.json", validation)

    report_lines = [
        "# TRACE-Net NHA Phase N6 Query Benchmark",
        "",
        f"- Quality status: **{validation['quality_status']}**",
        f"- Synthetic: {validation['counts']['synthetic_pass_count']}/{validation['counts']['synthetic_question_count']}",
        f"- Real smoke: {validation['counts']['real_smoke_pass_count']}/{validation['counts']['real_smoke_question_count']}",
        "- LLM calls: 0",
        "- Production graph writes: 0",
        "",
        "## Synthetic failures",
    ]
    synthetic_failures = [row for row in synthetic_results if not row.get("passed")]
    report_lines.extend([f"- {row['question_id']}: {', '.join(row['failures'])}" for row in synthetic_failures] or ["- None"])
    report_lines.extend(["", "## Real smoke failures"])
    real_failures = [row for row in real_results if not row.get("passed")]
    report_lines.extend([f"- {row['case_id']}: {', '.join(row['failures'])}" for row in real_failures] or ["- None"])
    (output / "report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    summary = {
        "schema_version": SCHEMA_VERSION,
        "module": MODULE,
        "status": STATUS,
        "quality_status": validation["quality_status"],
        "phase4_dir": source["phase4_dir"],
        "phase5_dir": source["phase5_dir"],
        "output_dir": str(output),
        "input_sha256": source["sha256"],
        "counts": validation["counts"],
        "failures": validation["failures"],
        "warnings": validation["warnings"],
        "artifacts": [
            "trace_net_nha_phase6_synthetic_results_v1.json",
            "trace_net_nha_phase6_synthetic_results_v1.jsonl",
            "trace_net_nha_phase6_real_smoke_results_v1.json",
            "trace_net_nha_phase6_real_smoke_results_v1.jsonl",
            "trace_net_nha_phase6_quality_v1.json",
            "report.md",
        ],
    }
    write_json(output / "trace_net_nha_phase6_summary_v1.json", summary)
    return summary
