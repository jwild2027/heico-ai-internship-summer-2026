"""TRACE-Net E2E codebase checklist v1.

Local, read-only checklist for the current TRACE-Net E2E RAG path.
It inspects source files and local artifact reports, then prints a terminal-friendly
PASS/WARN/MISSING checklist.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

PASS = "PASS"
WARN = "WARN"
MISSING = "MISSING"
FAIL = "FAIL"

ZERO_COUNTER_KEYS = (
    "unsafe_total_count",
    "unsafe_record_count",
    "unsafe_runtime_record_count",
    "unsafe_context_record_count",
    "unsafe_evidence_sufficiency_record_count",
    "unsafe_final_gate_smoke_record_count",
    "unsafe_api_wrapper_record_count",
    "answer_permission_count",
    "can_answer_directly_count",
    "can_prove_claims_count",
    "source_truth_mutation_allowed_count",
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
    "opensearch_write_attempt_count",
    "opensearch_upload_attempt_count",
)


@dataclass(frozen=True)
class ChecklistItem:
    category: str
    name: str
    status: str
    path: str = ""
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FileRequirement:
    category: str
    name: str
    path: str
    required: bool = True


@dataclass(frozen=True)
class ArtifactRequirement:
    category: str
    name: str
    path: str
    required_quality_status: str = PASS
    required_status_substring: str = ""
    min_summary_values: Mapping[str, int] | None = None
    expected_zero_counters: Sequence[str] = ZERO_COUNTER_KEYS
    required: bool = True


def _read_json(path: Path) -> Tuple[Optional[Dict[str, Any]], str]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except FileNotFoundError:
        return None, "file not found"
    except json.JSONDecodeError as exc:
        return None, f"invalid json: {exc}"


def _summary(data: Mapping[str, Any]) -> Mapping[str, Any]:
    value = data.get("summary")
    return value if isinstance(value, Mapping) else {}


def _quality_status(data: Mapping[str, Any]) -> str:
    return str(data.get("quality_status") or _summary(data).get("quality_status") or "")


def _status_values(data: Mapping[str, Any]) -> List[str]:
    values: List[str] = []
    for key, value in data.items():
        if key.endswith("status") or key.endswith("_status") or key == "status":
            if isinstance(value, (str, int, float, bool)):
                values.append(str(value))
    for key, value in _summary(data).items():
        if key.endswith("status") or key.endswith("_status") or key == "status":
            if isinstance(value, (str, int, float, bool)):
                values.append(str(value))
    return values


def _get_counter(data: Mapping[str, Any], key: str) -> Optional[int]:
    candidates = [data, _summary(data)]
    for mapping in candidates:
        if key in mapping:
            value = mapping.get(key)
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str) and value.strip().isdigit():
                return int(value.strip())
    return None


def source_file_requirements() -> List[FileRequirement]:
    return [
        FileRequirement("source", "E2E query input harness", "tiff/trace_net_e2e_query_input_v1.py"),
        FileRequirement("source", "E2E query planning/routing tunnels", "tiff/trace_net_e2e_query_planning_routing_v1.py"),
        FileRequirement("source", "E2E hybrid retrieval runtime", "tiff/trace_net_e2e_hybrid_retrieval_runtime_v1.py"),
        FileRequirement("source", "E2E context pack builder", "tiff/trace_net_e2e_context_pack_builder_v1.py"),
        FileRequirement("source", "E2E evidence sufficiency gate", "tiff/trace_net_e2e_evidence_sufficiency_gate_v1.py"),
        FileRequirement("source", "E2E final gate smoke", "tiff/trace_net_e2e_final_gate_smoke_v1.py"),
        FileRequirement("source", "E2E RAG demo report", "tiff/trace_net_e2e_rag_demo_report_v1.py"),
        FileRequirement("source", "E2E API wrapper smoke", "tiff/trace_net_e2e_api_wrapper_smoke_v1.py"),
        FileRequirement("source", "E2E local endpoint module", "tiff/trace_net_e2e_local_endpoint_v1.py"),
        FileRequirement("source", "E2E local endpoint server", "scripts/operations/serving/serve_trace_net_e2e_local_endpoint_v1.py"),
        FileRequirement("source", "Codebase checklist", "tiff/trace_net_e2e_codebase_checklist_v1.py"),
    ]


def artifact_requirements() -> List[ArtifactRequirement]:
    z = ZERO_COUNTER_KEYS
    return [
        ArtifactRequirement(
            "table_route",
            "Table exact-search adapter",
            "local_data/organization/trace_net/table_exact_search_adapter/trace_net_table_exact_search_adapter_v1.json",
            min_summary_values={"table_exact_search_document_count": 1000},
            expected_zero_counters=z,
        ),
        ArtifactRequirement(
            "table_route",
            "Table exact-search smoke",
            "local_data/organization/trace_net/table_exact_search_smoke/trace_net_table_exact_search_smoke_v1.json",
            min_summary_values={"successful_smoke_query_count": 3, "total_match_count": 3},
            expected_zero_counters=z,
        ),
        ArtifactRequirement(
            "table_route",
            "Table hybrid retrieval bridge",
            "local_data/organization/trace_net/table_hybrid_retrieval_bridge/trace_net_table_hybrid_retrieval_bridge_v1.json",
            min_summary_values={"table_hybrid_bridge_record_count": 1000},
            expected_zero_counters=z,
        ),
        ArtifactRequirement(
            "e2e_chain",
            "E2E query input",
            "local_data/organization/trace_net/e2e_query_input/trace_net_e2e_query_input_v1.json",
            required_status_substring="READY_FOR_RETRIEVAL_RUNTIME",
            min_summary_values={"e2e_query_input_record_count": 5},
            expected_zero_counters=z,
        ),
        ArtifactRequirement(
            "e2e_chain",
            "E2E query planning/routing tunnels",
            "local_data/organization/trace_net/e2e_query_planning_routing/trace_net_e2e_query_planning_routing_v1.json",
            required_status_substring="READY_FOR_HYBRID_RETRIEVAL_RUNTIME",
            min_summary_values={"query_route_plan_count": 5, "total_query_tunnel_count": 15},
            expected_zero_counters=z,
        ),
        ArtifactRequirement(
            "e2e_chain",
            "Planned hybrid retrieval runtime",
            "local_data/organization/trace_net/e2e_hybrid_retrieval_runtime_planned/trace_net_e2e_hybrid_retrieval_runtime_v1.json",
            required_status_substring="READY_FOR_CONTEXT_PACK",
            min_summary_values={"successful_retrieval_query_count": 4, "total_retrieval_hit_count": 10},
            expected_zero_counters=z,
        ),
        ArtifactRequirement(
            "e2e_chain",
            "Planned context pack builder",
            "local_data/organization/trace_net/e2e_context_pack_builder_planned/trace_net_e2e_context_pack_builder_v1.json",
            required_status_substring="READY_FOR_FINAL_GATE",
            min_summary_values={"context_pack_count": 5, "citation_ready_context_item_count": 20},
            expected_zero_counters=z,
        ),
        ArtifactRequirement(
            "e2e_chain",
            "Planned evidence sufficiency gate",
            "local_data/organization/trace_net/e2e_evidence_sufficiency_gate_planned/trace_net_e2e_evidence_sufficiency_gate_v1.json",
            required_status_substring="READY_FOR_FINAL_GATE_SMOKE",
            min_summary_values={"final_gate_review_ready_pack_count": 4},
            expected_zero_counters=z,
        ),
        ArtifactRequirement(
            "e2e_chain",
            "Planned final gate smoke",
            "local_data/organization/trace_net/e2e_final_gate_smoke_planned/trace_net_e2e_final_gate_smoke_v1.json",
            required_status_substring="READY_FOR_API_OR_AUDIT_RESPONSE",
            min_summary_values={"safe_response_draft_count": 4, "total_citation_count": 10},
            expected_zero_counters=z,
        ),
        ArtifactRequirement(
            "e2e_chain",
            "E2E RAG demo report",
            "local_data/organization/trace_net/e2e_rag_demo_report/trace_net_e2e_rag_demo_report_v1.json",
            required_status_substring="READY_FOR_API_WRAPPER",
            min_summary_values={"complete_demo_flow_count": 5, "citation_backed_response_draft_count": 4},
            expected_zero_counters=z,
        ),
        ArtifactRequirement(
            "endpoint",
            "E2E API wrapper smoke",
            "local_data/organization/trace_net/e2e_api_wrapper_smoke/trace_net_e2e_api_wrapper_smoke_v1.json",
            required_status_substring="READY_FOR_LOCAL_ENDPOINT",
            min_summary_values={"api_wrapper_response_count": 5, "citation_backed_api_response_count": 4},
            expected_zero_counters=z,
        ),
        ArtifactRequirement(
            "endpoint",
            "E2E local endpoint manifest",
            "local_data/organization/trace_net/e2e_local_endpoint/trace_net_e2e_local_endpoint_v1.json",
            required_status_substring="READY_FOR_OPEN_WEBUI_SMOKE",
            min_summary_values={"endpoint_route_count": 4, "api_response_count": 5},
            expected_zero_counters=z,
        ),
    ]


def check_file_requirement(root: Path, requirement: FileRequirement) -> ChecklistItem:
    path = root / requirement.path
    if path.exists():
        return ChecklistItem(requirement.category, requirement.name, PASS, requirement.path, "present")
    return ChecklistItem(requirement.category, requirement.name, MISSING if requirement.required else WARN, requirement.path, "missing")


def check_artifact_requirement(root: Path, requirement: ArtifactRequirement) -> List[ChecklistItem]:
    items: List[ChecklistItem] = []
    path = root / requirement.path
    data, error = _read_json(path)
    if data is None:
        items.append(ChecklistItem(requirement.category, requirement.name, MISSING if requirement.required else WARN, requirement.path, error))
        return items

    quality = _quality_status(data)
    if quality == requirement.required_quality_status:
        items.append(ChecklistItem(requirement.category, requirement.name, PASS, requirement.path, f"quality_status={quality}"))
    else:
        items.append(ChecklistItem(requirement.category, requirement.name, FAIL, requirement.path, f"quality_status={quality!r}"))

    if requirement.required_status_substring:
        status_blob = " | ".join(_status_values(data))
        if requirement.required_status_substring in status_blob:
            items.append(ChecklistItem(requirement.category, f"{requirement.name} status", PASS, requirement.path, requirement.required_status_substring))
        else:
            items.append(ChecklistItem(requirement.category, f"{requirement.name} status", FAIL, requirement.path, f"missing {requirement.required_status_substring}; found {status_blob}"))

    for key, minimum in (requirement.min_summary_values or {}).items():
        observed = _get_counter(data, key)
        if observed is None:
            items.append(ChecklistItem(requirement.category, f"{requirement.name} {key}", FAIL, requirement.path, "missing counter"))
        elif observed >= minimum:
            items.append(ChecklistItem(requirement.category, f"{requirement.name} {key}", PASS, requirement.path, f"observed={observed} expected>={minimum}"))
        else:
            items.append(ChecklistItem(requirement.category, f"{requirement.name} {key}", FAIL, requirement.path, f"observed={observed} expected>={minimum}"))

    nonzero: List[str] = []
    for key in requirement.expected_zero_counters:
        observed = _get_counter(data, key)
        if observed is not None and observed != 0:
            nonzero.append(f"{key}={observed}")
    if nonzero:
        items.append(ChecklistItem(requirement.category, f"{requirement.name} safety/write counters", FAIL, requirement.path, ", ".join(nonzero)))
    else:
        items.append(ChecklistItem(requirement.category, f"{requirement.name} safety/write counters", PASS, requirement.path, "all observed authority/write counters are zero"))

    return items


def build_checklist(root: Path | str = ".") -> Dict[str, Any]:
    root = Path(root)
    items: List[ChecklistItem] = []
    for req in source_file_requirements():
        items.append(check_file_requirement(root, req))
    for req in artifact_requirements():
        items.extend(check_artifact_requirement(root, req))

    status_counts: Dict[str, int] = {}
    for item in items:
        status_counts[item.status] = status_counts.get(item.status, 0) + 1

    blocking_count = status_counts.get(FAIL, 0) + status_counts.get(MISSING, 0)
    overall_status = PASS if blocking_count == 0 else FAIL
    if overall_status == PASS and status_counts.get(WARN, 0):
        overall_status = WARN

    hybrid_note = (
        "Current WebUI endpoint uses artifact-backed planned hybrid retrieval outputs. "
        "The planned runtime includes query planning/routing tunnels, table bridge signals, exact/table evidence, "
        "and context/final-gate artifacts, but it is not yet a fully dynamic per-query live retrieval runner."
    )

    return {
        "module": "trace_net_e2e_codebase_checklist_v1",
        "overall_status": overall_status,
        "status_counts": status_counts,
        "blocking_count": blocking_count,
        "hybrid_search_assessment": hybrid_note,
        "items": [item.to_dict() for item in items],
    }


def render_terminal_checklist(report: Mapping[str, Any]) -> str:
    lines: List[str] = []
    lines.append("TRACE-Net E2E Codebase Checklist v1")
    lines.append(f"Overall status: {report.get('overall_status')}")
    lines.append(f"Blocking items: {report.get('blocking_count')}")
    lines.append("")
    lines.append("Hybrid search assessment:")
    lines.append(f"- {report.get('hybrid_search_assessment')}")
    lines.append("")

    categories: Dict[str, List[Mapping[str, Any]]] = {}
    for item in report.get("items", []):
        if not isinstance(item, Mapping):
            continue
        categories.setdefault(str(item.get("category", "other")), []).append(item)

    for category in sorted(categories):
        lines.append(f"[{category}]")
        for item in categories[category]:
            status = str(item.get("status", ""))
            mark = {PASS: "[PASS]", WARN: "[WARN]", FAIL: "[FAIL]", MISSING: "[MISS]"}.get(status, f"[{status}]")
            name = item.get("name", "")
            detail = item.get("detail", "")
            path = item.get("path", "")
            suffix = f" — {detail}" if detail else ""
            path_suffix = f" ({path})" if path else ""
            lines.append(f"  {mark} {name}{suffix}{path_suffix}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_report_files(report: Mapping[str, Any], output_dir: Path | str) -> Dict[str, str]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "trace_net_e2e_codebase_checklist_v1.json"
    md_path = output_dir / "trace_net_e2e_codebase_checklist_v1.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text("```text\n" + render_terminal_checklist(report) + "```\n", encoding="utf-8")
    return {"json_path": str(json_path), "md_path": str(md_path)}
