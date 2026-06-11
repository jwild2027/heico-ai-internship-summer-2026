"""TRACE-Net IT issue-origin test matrix v1.

This module stress-tests the TRACE-Net IT Operations Console with synthetic
quality artifacts. It does not mutate real TRACE-Net artifacts, Postgres,
Qdrant, OpenSearch, or source truth.

The goal is to test issue origins/categories rather than one-off issue strings:
source ingest, OCR, table, visual, graph, trust, retrieval, feedback, answer,
incremental operations, storage/writeback, model advisory output, leakage, and
human-review signals.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import html
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from tiff.trace_net_it_operations_console_v1 import (
    EXPECTED_STAGE_PATHS,
    build_it_operations_console,
    read_json,
    write_json,
    write_jsonl,
)

SCHEMA_VERSION = "trace_net_it_issue_origin_test_matrix_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/it_issue_origin_test_matrix")


@dataclass(frozen=True)
class IssueScenario:
    scenario_id: str
    origin_category: str
    source_layer: str
    stage_id: str
    expected_severity: str
    expected_category: str
    summary_key: str | None
    summary_value: int | float | None
    status: str = "PASS"
    description: str = ""
    recommended_action: str = ""

    def artifact_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": f"{SCHEMA_VERSION}_synthetic_quality",
            "status": self.status,
            "quality_status": self.status,
            "scenario_id": self.scenario_id,
            "origin_category": self.origin_category,
            "source_layer": self.source_layer,
            "description": self.description,
            "summary": {
                "scenario_id": self.scenario_id,
                "origin_category": self.origin_category,
                "source_layer": self.source_layer,
            },
        }
        if self.summary_key and self.summary_value is not None:
            payload["summary"][self.summary_key] = self.summary_value
        return payload


# These scenarios are intentionally broad. They test where problems originate,
# not a single hard-coded real artifact issue.
SCENARIOS: tuple[IssueScenario, ...] = (
    # Source and ingest lineage.
    IssueScenario("src_unsafe_package", "source_ingest", "source_package", "issue_source_ingest_unsafe_package", "critical", "safety_count_nonzero", "unsafe_source_package_count", 1, description="A source package has unsafe records."),
    IssueScenario("src_mutation_risk", "source_ingest", "source_package", "issue_source_ingest_mutation", "critical", "safety_count_nonzero", "source_truth_mutation_allowed_count", 1, description="A source-stage artifact would allow source truth mutation."),
    IssueScenario("src_missing_trace", "source_ingest", "source_links", "issue_source_ingest_missing_trace", "warning", "operational_warning", "missing_source_trace_count", 4, description="Source trace records are missing."),
    IssueScenario("src_changed_arrivals", "source_ingest", "incremental_source_scan", "issue_source_ingest_changed_sources", "warning", "operational_warning", "changed_source_count", 2, description="Changed source files require incremental work."),
    IssueScenario("src_new_arrivals", "source_ingest", "incremental_source_scan", "issue_source_ingest_new_sources", "warning", "operational_warning", "new_source_count", 3, description="New source arrivals are detected."),

    # OCR and text extraction.
    IssueScenario("ocr_unsafe_text", "ocr_text", "ocr_extractor", "issue_ocr_unsafe_text", "critical", "safety_count_nonzero", "unsafe_ocr_record_count", 1, description="OCR output was flagged unsafe."),
    IssueScenario("ocr_raw_index_risk", "ocr_text", "ocr_indexing", "issue_ocr_raw_index_risk", "critical", "safety_count_nonzero", "unsafe_raw_ocr_index_document_count", 1, description="Raw OCR would be indexed without filtering."),
    IssueScenario("ocr_needs_retry", "ocr_text", "ocr_retry", "issue_ocr_needs_retry", "warning", "operational_warning", "needs_ocr_page_count", 7, description="Pages need OCR retry."),
    IssueScenario("ocr_missing_clean_text", "ocr_text", "ocr_cleaning", "issue_ocr_missing_clean_text", "warning", "operational_warning", "missing_clean_ocr_text_count", 5, description="Clean OCR artifacts are missing."),

    # Page registry and routing.
    IssueScenario("registry_failed_stage", "page_registry", "page_element_registry", "issue_page_registry_failed", "critical", "stage_quality_failed", None, None, status="FAIL", description="The page registry quality artifact failed."),
    IssueScenario("registry_missing_routes", "page_registry", "extraction_router", "issue_page_registry_missing_routes", "warning", "operational_warning", "missing_extraction_route_count", 9, description="Pages are missing extraction routes."),
    IssueScenario("registry_needs_table", "page_registry", "route_planner", "issue_page_registry_needs_table", "warning", "operational_warning", "needs_table_page_count", 12, description="Pages need table route work."),
    IssueScenario("registry_review", "page_registry", "route_planner", "issue_page_registry_review", "review", "review_backlog", "needs_human_review_count", 6, description="Registry flags pages for human review."),

    # Table extraction and normalization.
    IssueScenario("table_unsafe_evidence", "table_extraction", "table_understanding", "issue_table_unsafe", "critical", "safety_count_nonzero", "unsafe_table_evidence_count", 1, description="Unsafe table evidence appeared."),
    IssueScenario("table_uncited_answer", "table_extraction", "table_answer_support", "issue_table_uncited_answer", "critical", "safety_count_nonzero", "answer_capable_without_citation_count", 2, description="Answer-capable table rows lack citations."),
    IssueScenario("table_missing_source", "table_extraction", "table_source_trace", "issue_table_missing_source", "warning", "operational_warning", "missing_source_trace_count", 10, description="Table records lack source trace."),
    IssueScenario("table_unverified_rows", "table_extraction", "table_cells", "issue_table_unverified_rows", "warning", "operational_warning", "candidate_unverified_table_row_count", 14, description="Table rows remain unverified."),
    IssueScenario("table_repair_review", "table_extraction", "table_cell_normalizer", "issue_table_repair_review", "review", "review_backlog", "review_required_table_repair_count", 3, description="Table cell repairs require review."),

    # Visual / figure / chart / callout.
    IssueScenario("visual_unsafe", "visual_diagram", "figure_chart_understanding", "issue_visual_unsafe", "critical", "safety_count_nonzero", "unsafe_visual_evidence_count", 1, description="Visual evidence was unsafe."),
    IssueScenario("visual_direct_answer", "visual_diagram", "visual_authority", "issue_visual_direct_answer", "critical", "safety_count_nonzero", "direct_answer_allowed_visual_count", 1, description="Visual records were incorrectly allowed to answer."),
    IssueScenario("visual_unverified_claim", "visual_diagram", "callout_detection", "issue_visual_unverified_claim", "warning", "operational_warning", "unverified_visual_claim_count", 11, description="Visual claims remain unverified."),
    IssueScenario("visual_needs_model", "visual_diagram", "vision_model_pilot", "issue_visual_needs_model", "warning", "operational_warning", "needs_vision_model_count", 17, description="Pages need vision model inspection."),
    IssueScenario("visual_human_review", "visual_diagram", "diagram_review", "issue_visual_human_review", "review", "review_backlog", "records_needing_human_review_count", 23, description="Diagrams need human review."),
    IssueScenario("callout_review", "visual_diagram", "callout_visual_part_verifier", "issue_callout_review", "review", "review_backlog", "needs_human_review_callout_count", 5, description="Callout candidates require human review."),

    # Graph integrity and writeback.
    IssueScenario("graph_orphan_edge", "graph_integrity", "graph_overlay", "issue_graph_orphan_edge", "critical", "safety_count_nonzero", "orphan_edge_count", 1, description="Graph overlay has orphan edges."),
    IssueScenario("graph_missing_lineage", "graph_integrity", "part_lineage", "issue_graph_missing_lineage", "warning", "operational_warning", "missing_part_candidate_lineage_count", 8, description="Cross-page graph nodes lack lineage."),
    IssueScenario("graph_postgres_write", "graph_integrity", "graph_writeback", "issue_graph_postgres_write", "critical", "safety_count_nonzero", "postgres_write_attempt_count", 1, description="A dry-run stage attempted Postgres writeback."),
    IssueScenario("graph_review_cluster", "graph_integrity", "leiden_review", "issue_graph_review_cluster", "review", "review_backlog", "review_required_community_count", 3, description="Communities require review."),

    # Trust, authority, and evidence consensus.
    IssueScenario("trust_direct_answer", "trust_authority", "trust_authority", "issue_trust_direct_answer", "critical", "safety_count_nonzero", "direct_answer_allowed_count", 1, description="A trust record allows direct answering unexpectedly."),
    IssueScenario("trust_claim_proof", "trust_authority", "trust_authority", "issue_trust_claim_proof", "critical", "safety_count_nonzero", "claim_proof_allowed_count", 1, description="A trust record allows proof without gate."),
    IssueScenario("trust_claim_without_authority", "trust_authority", "authority_gate", "issue_trust_claim_without_authority", "critical", "safety_count_nonzero", "claim_proof_without_authority_count", 1, description="A claim proof lacks authority."),
    IssueScenario("trust_missing_authority", "trust_authority", "authority_gate", "issue_trust_missing_authority", "warning", "operational_warning", "missing_authority_count", 2, description="Trust authority records are missing."),
    IssueScenario("consensus_unsafe_include", "evidence_consensus", "evidence_consensus", "issue_consensus_unsafe_include", "critical", "safety_count_nonzero", "unsafe_rag_include_records_count", 1, description="Unsafe evidence would enter RAG."),
    IssueScenario("consensus_review_needed", "evidence_consensus", "evidence_consensus", "issue_consensus_review_needed", "review", "review_backlog", "human_review_candidate_count", 4, description="Evidence consensus created review candidates."),

    # Embeddings / vector / Qdrant.
    IssueScenario("embed_unsafe_candidate", "semantic_vector", "embedding_candidates", "issue_embed_unsafe_candidate", "critical", "safety_count_nonzero", "unsafe_embedding_candidate_count", 1, description="Unsafe candidate reached embedding stage."),
    IssueScenario("embed_missing_page", "semantic_vector", "embedding_candidates", "issue_embed_missing_page", "warning", "operational_warning", "missing_embedding_page_id_count", 4, description="Embedding records are missing page IDs."),
    IssueScenario("qdrant_direct_answer", "semantic_vector", "qdrant_payload", "issue_qdrant_direct_answer", "critical", "safety_count_nonzero", "direct_answer_allowed_payload_count", 1, description="A Qdrant payload allows direct answering."),
    IssueScenario("qdrant_needs_upsert", "semantic_vector", "qdrant_incremental", "issue_qdrant_needs_upsert", "warning", "operational_warning", "needs_qdrant_page_count", 12, description="Changed pages need Qdrant upsert."),

    # Retrieval / ranking / communities.
    IssueScenario("retrieval_unsafe", "retrieval", "hybrid_retrieval", "issue_retrieval_unsafe", "critical", "safety_count_nonzero", "unsafe_result_count", 1, description="Unsafe retrieval result appeared."),
    IssueScenario("retrieval_only_answer", "retrieval", "hybrid_retrieval", "issue_retrieval_only_answer", "critical", "safety_count_nonzero", "retrieval_only_answer_allowed_count", 1, description="Retrieval-only record was answer allowed."),
    IssueScenario("retrieval_missing_citation", "retrieval", "hybrid_retrieval", "issue_retrieval_missing_citation", "warning", "operational_warning", "missing_citation_count", 6, description="Retrieval results lack citations."),
    IssueScenario("community_as_proof", "graph_community", "leiden_communities", "issue_community_as_proof", "critical", "safety_count_nonzero", "community_as_proof_count", 1, description="Community signal was used as proof."),
    IssueScenario("community_missing_membership", "graph_community", "leiden_communities", "issue_community_missing_membership", "warning", "operational_warning", "missing_community_membership_count", 5, description="Community membership is missing."),

    # Feedback / prompt safety.
    IssueScenario("feedback_raw_to_llm", "feedback_memory", "feedback_memory", "issue_feedback_raw_to_llm", "critical", "safety_count_nonzero", "raw_feedback_direct_to_llm_count", 1, description="Raw feedback would be sent to LLM."),
    IssueScenario("feedback_as_proof", "feedback_memory", "feedback_memory", "issue_feedback_as_proof", "critical", "safety_count_nonzero", "feedback_as_proof_count", 1, description="Feedback was treated as proof."),
    IssueScenario("feedback_prompt_injection", "feedback_memory", "feedback_sanitizer", "issue_feedback_prompt_injection", "review", "review_backlog", "prompt_injection_flagged_count", 2, description="Feedback sanitizer detected prompt injection."),
    IssueScenario("feedback_missing_target", "feedback_memory", "feedback_events", "issue_feedback_missing_target", "warning", "operational_warning", "missing_feedback_target_count", 3, description="Feedback records are missing targets."),

    # Answer and final gate.
    IssueScenario("answer_uncited_claim", "answer_gate", "citation_draft", "issue_answer_uncited_claim", "critical", "safety_count_nonzero", "uncited_final_claim_count", 1, description="A final claim lacks citation."),
    IssueScenario("answer_claim_without_citation", "answer_gate", "final_answer_gate", "issue_answer_claim_without_citation", "critical", "safety_count_nonzero", "claim_without_citation_count", 1, description="A claim lacks citation."),
    IssueScenario("answer_local_path_leak", "answer_gate", "snippet_cleaner", "issue_answer_local_path_leak", "critical", "safety_count_nonzero", "local_path_leak_count", 1, description="Answer/snippet leaks local path."),
    IssueScenario("answer_raw_bytes", "answer_gate", "snippet_cleaner", "issue_answer_raw_bytes", "critical", "safety_count_nonzero", "raw_bytes_repr_count", 1, description="Answer/snippet leaks raw byte wrapper."),
    IssueScenario("answer_boilerplate", "answer_gate", "snippet_cleaner", "issue_answer_boilerplate", "critical", "safety_count_nonzero", "boilerplate_leak_count", 1, description="Answer/snippet leaks boilerplate."),
    IssueScenario("answer_nonstandard_status", "answer_gate", "final_answer_gate", "issue_answer_nonstandard_status", "warning", "stage_quality_nonstandard", None, None, status="PARTIAL", description="Final answer stage has nonstandard status."),

    # Incremental operations.
    IssueScenario("incremental_dirty", "incremental_ops", "corpus_manifest", "issue_incremental_dirty", "warning", "operational_warning", "dirty_page_count", 5, description="Incremental manifest has dirty pages."),
    IssueScenario("incremental_needs_embedding", "incremental_ops", "corpus_manifest", "issue_incremental_needs_embedding", "warning", "operational_warning", "needs_embedding_page_count", 5, description="Pages need embedding refresh."),
    IssueScenario("incremental_needs_graph", "incremental_ops", "corpus_manifest", "issue_incremental_needs_graph", "warning", "operational_warning", "needs_graph_update_page_count", 5, description="Pages need graph updates."),
    IssueScenario("incremental_needs_leiden", "incremental_ops", "corpus_manifest", "issue_incremental_needs_leiden", "warning", "operational_warning", "needs_leiden_refresh_page_count", 5, description="Graph change requires community refresh."),
    IssueScenario("orchestrator_unsafe_job", "incremental_ops", "incremental_orchestrator", "issue_orchestrator_unsafe_job", "critical", "safety_count_nonzero", "unsafe_job_count", 1, description="Incremental planner created unsafe job."),

    # OpenSearch / production index.
    IssueScenario("opensearch_unsafe_doc", "keyword_search", "opensearch_adapter", "issue_opensearch_unsafe_doc", "critical", "safety_count_nonzero", "unsafe_index_document_count", 1, description="Unsafe document would be indexed."),
    IssueScenario("opensearch_raw_visual", "keyword_search", "opensearch_adapter", "issue_opensearch_raw_visual", "critical", "safety_count_nonzero", "unsafe_raw_visual_output_indexed_count", 1, description="Raw visual output would be indexed."),
    IssueScenario("opensearch_missing_page", "keyword_search", "opensearch_adapter", "issue_opensearch_missing_page", "warning", "operational_warning", "missing_index_page_id_count", 4, description="OpenSearch docs lack page IDs."),
    IssueScenario("opensearch_needs_docs", "keyword_search", "opensearch_incremental", "issue_opensearch_needs_docs", "warning", "operational_warning", "needs_opensearch_page_count", 9, description="Changed pages need OpenSearch upsert."),

    # LLM / model advisory boundaries.
    IssueScenario("llm_freeform_allowed", "llm_advisory", "answer_composer", "issue_llm_freeform_allowed", "critical", "safety_count_nonzero", "direct_answer_allowed_llm_freeform_count", 1, description="LLM freeform answer was allowed directly."),
    IssueScenario("llm_claim_proof", "llm_advisory", "answer_composer", "issue_llm_claim_proof", "critical", "safety_count_nonzero", "claim_proof_allowed_llm_count", 1, description="LLM advisory output was allowed as proof."),
    IssueScenario("llm_needs_model", "llm_advisory", "model_runtime", "issue_llm_needs_model", "warning", "operational_warning", "needs_model_download_count", 1, description="Model runtime dependency is missing or pending."),

    # Security and leakage.
    IssueScenario("security_prompt_leak", "security_leakage", "prompt_boundary", "issue_security_prompt_leak", "critical", "safety_count_nonzero", "unsafe_prompt_leak_count", 1, description="Prompt/debug leakage detected."),
    IssueScenario("security_debug_leak", "security_leakage", "debug_boundary", "issue_security_debug_leak", "critical", "safety_count_nonzero", "unsafe_debug_record_count", 1, description="Debug/internal record leaked into a publishable layer."),
    IssueScenario("security_missing_redaction", "security_leakage", "redaction", "issue_security_missing_redaction", "warning", "operational_warning", "missing_redaction_count", 3, description="Expected redaction was missing."),
)


def utc_now_iso() -> str:
    return _dt.datetime.now(tz=_dt.UTC).replace(microsecond=0).isoformat()


def safe_stage_id(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", text).strip("_").lower()


def scenario_artifact_path(root: Path, scenario: IssueScenario) -> Path:
    stage = safe_stage_id(scenario.stage_id)
    return root / stage / f"{stage}_quality.json"


def seed_expected_pass_artifacts(root: Path) -> None:
    for stage_id, rel_path in EXPECTED_STAGE_PATHS.items():
        path = root / rel_path
        write_json(
            path,
            {
                "schema_version": f"{SCHEMA_VERSION}_expected_stage_stub",
                "status": "PASS",
                "quality_status": "PASS",
                "summary": {
                    "stage_id": stage_id,
                    "stubbed_for_issue_origin_matrix": True,
                },
            },
        )


def write_scenario_artifacts(root: Path, scenarios: Iterable[IssueScenario]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        path = scenario_artifact_path(root, scenario)
        payload = scenario.artifact_payload()
        write_json(path, payload)
        rows.append(
            {
                "scenario_id": scenario.scenario_id,
                "origin_category": scenario.origin_category,
                "source_layer": scenario.source_layer,
                "stage_id": safe_stage_id(scenario.stage_id),
                "expected_severity": scenario.expected_severity,
                "expected_category": scenario.expected_category,
                "expected_key": scenario.summary_key,
                "artifact_path": path.as_posix(),
                "description": scenario.description,
            }
        )
    return rows


def issue_matches_scenario(issue: dict[str, Any], scenario: IssueScenario) -> bool:
    if issue.get("stage_id") != safe_stage_id(scenario.stage_id):
        return False
    if issue.get("severity") != scenario.expected_severity:
        return False
    if issue.get("category") != scenario.expected_category:
        return False
    if scenario.summary_key is None:
        return True
    key = str(issue.get("key") or "")
    return key == scenario.summary_key or key.endswith(f".{scenario.summary_key}")


def summarize_by_origin(scenario_results: list[dict[str, Any]]) -> dict[str, Any]:
    by_origin: dict[str, dict[str, Any]] = {}
    for result in scenario_results:
        origin = result["origin_category"]
        row = by_origin.setdefault(
            origin,
            {
                "origin_category": origin,
                "scenario_count": 0,
                "detected_count": 0,
                "critical_count": 0,
                "warning_count": 0,
                "review_count": 0,
            },
        )
        row["scenario_count"] += 1
        if result["detected"]:
            row["detected_count"] += 1
        sev = result["expected_severity"]
        if sev == "critical":
            row["critical_count"] += 1
        elif sev == "warning":
            row["warning_count"] += 1
        elif sev == "review":
            row["review_count"] += 1
    return {origin: by_origin[origin] for origin in sorted(by_origin)}


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# TRACE-Net IT Issue-Origin Test Matrix v1",
        "",
        f"**Status:** {report['quality_status']}",
        f"**Generated:** {report['generated_at']}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "scenario_count",
        "origin_category_count",
        "detected_scenario_count",
        "undetected_scenario_count",
        "critical_scenario_count",
        "warning_scenario_count",
        "review_scenario_count",
        "synthetic_console_critical_issue_count",
        "synthetic_console_warning_issue_count",
        "synthetic_console_review_issue_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Origin Coverage", ""])
    lines.append("| Origin | Scenarios | Detected | Critical | Warning | Review |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for origin in report.get("origin_coverage", {}).values():
        lines.append(
            f"| {origin['origin_category']} | {origin['scenario_count']} | {origin['detected_count']} | "
            f"{origin['critical_count']} | {origin['warning_count']} | {origin['review_count']} |"
        )
    lines.extend(["", "## Undetected Scenarios", ""])
    misses = [r for r in report["scenario_results"] if not r["detected"]]
    if not misses:
        lines.append("All synthetic issue-origin scenarios were detected.")
    else:
        for result in misses:
            lines.append(f"- {result['scenario_id']} ({result['origin_category']}): {result['description']}")
    lines.append("")
    return "\n".join(lines)


def render_html(report: dict[str, Any]) -> str:
    escaped = html.escape(render_markdown(report))
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>TRACE-Net IT Issue-Origin Test Matrix v1</title>"
        "<style>body{font-family:Arial,sans-serif;margin:32px;}"
        "pre{white-space:pre-wrap;background:#f7f7f7;padding:16px;border:1px solid #ddd;}"
        "</style></head><body><h1>TRACE-Net IT Issue-Origin Test Matrix v1</h1>"
        f"<pre>{escaped}</pre></body></html>"
    )


def build_it_issue_origin_test_matrix(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    min_scenarios: int = 60,
    min_origin_categories: int = 15,
    require_all_scenarios_detected: bool = True,
    keep_synthetic_root: bool = True,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    synthetic_root = output_dir / "synthetic_trace_net_root"
    synthetic_console_dir = output_dir / "synthetic_console_report"
    if synthetic_root.exists():
        shutil.rmtree(synthetic_root)
    if synthetic_console_dir.exists():
        shutil.rmtree(synthetic_console_dir)
    synthetic_root.mkdir(parents=True, exist_ok=True)

    seed_expected_pass_artifacts(synthetic_root)
    scenario_catalog = write_scenario_artifacts(synthetic_root, SCENARIOS)

    console_report = build_it_operations_console(
        trace_net_root=synthetic_root,
        output_dir=synthetic_console_dir,
        include_all_quality_files=True,
        max_critical_issues=999999,
        allow_missing_expected_stages=True,
    )
    issues = console_report["issues"]

    scenario_results: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        matching = [issue for issue in issues if issue_matches_scenario(issue, scenario)]
        scenario_results.append(
            {
                "scenario_id": scenario.scenario_id,
                "origin_category": scenario.origin_category,
                "source_layer": scenario.source_layer,
                "stage_id": safe_stage_id(scenario.stage_id),
                "expected_severity": scenario.expected_severity,
                "expected_category": scenario.expected_category,
                "expected_key": scenario.summary_key,
                "description": scenario.description,
                "detected": bool(matching),
                "matched_issue_count": len(matching),
                "matched_issue_ids": [issue["issue_id"] for issue in matching],
            }
        )

    origin_coverage = summarize_by_origin(scenario_results)
    detected_count = sum(1 for r in scenario_results if r["detected"])
    scenario_count = len(scenario_results)
    origin_category_count = len(origin_coverage)
    critical_scenario_count = sum(1 for s in SCENARIOS if s.expected_severity == "critical")
    warning_scenario_count = sum(1 for s in SCENARIOS if s.expected_severity == "warning")
    review_scenario_count = sum(1 for s in SCENARIOS if s.expected_severity == "review")

    checks = {
        "scenario_count_meets_minimum": scenario_count >= min_scenarios,
        "origin_category_count_meets_minimum": origin_category_count >= min_origin_categories,
        "all_scenarios_detected_if_required": (detected_count == scenario_count) if require_all_scenarios_detected else detected_count > 0,
        "critical_scenarios_present": critical_scenario_count > 0,
        "warning_scenarios_present": warning_scenario_count > 0,
        "review_scenarios_present": review_scenario_count > 0,
        "synthetic_console_generated": bool(console_report.get("report_path")),
    }
    quality_status = "PASS" if all(checks.values()) else "FAIL"
    generated_at = utc_now_iso()
    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": quality_status,
        "scenario_count": scenario_count,
        "origin_category_count": origin_category_count,
        "detected_scenario_count": detected_count,
        "undetected_scenario_count": scenario_count - detected_count,
        "critical_scenario_count": critical_scenario_count,
        "warning_scenario_count": warning_scenario_count,
        "review_scenario_count": review_scenario_count,
        "synthetic_console_quality_status": console_report.get("quality_status"),
        "synthetic_console_issue_count": console_report.get("summary", {}).get("issue_count"),
        "synthetic_console_critical_issue_count": console_report.get("summary", {}).get("critical_issue_count"),
        "synthetic_console_warning_issue_count": console_report.get("summary", {}).get("warning_issue_count"),
        "synthetic_console_review_issue_count": console_report.get("summary", {}).get("review_issue_count"),
        "synthetic_trace_net_root": synthetic_root.as_posix(),
        "synthetic_console_report_path": console_report.get("report_path"),
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "IT_ISSUE_ORIGIN_TEST_MATRIX_BUILT",
        "quality_status": quality_status,
        "generated_at": generated_at,
        "output_dir": output_dir.as_posix(),
        "summary": summary,
        "quality": {
            "schema_version": f"{SCHEMA_VERSION}_quality",
            "status": quality_status,
            "checks": checks,
            "min_scenarios": min_scenarios,
            "min_origin_categories": min_origin_categories,
            "require_all_scenarios_detected": require_all_scenarios_detected,
        },
        "scenario_catalog": scenario_catalog,
        "scenario_results": scenario_results,
        "origin_coverage": origin_coverage,
    }

    report_path = output_dir / "trace_net_it_issue_origin_test_matrix_v1.json"
    scenarios_path = output_dir / "trace_net_it_issue_origin_test_matrix_v1_scenarios.jsonl"
    results_path = output_dir / "trace_net_it_issue_origin_test_matrix_v1_results.jsonl"
    origins_path = output_dir / "trace_net_it_issue_origin_test_matrix_v1_origins.jsonl"
    summary_path = output_dir / "trace_net_it_issue_origin_test_matrix_v1_summary.json"
    quality_path = output_dir / "trace_net_it_issue_origin_test_matrix_v1_quality.json"
    md_path = output_dir / "trace_net_it_issue_origin_test_matrix_v1.md"
    html_path = output_dir / "trace_net_it_issue_origin_test_matrix_v1.html"
    manifest_path = output_dir / "trace_net_it_issue_origin_test_matrix_v1_manifest.json"

    write_json(report_path, report)
    write_jsonl(scenarios_path, scenario_catalog)
    write_jsonl(results_path, scenario_results)
    write_jsonl(origins_path, origin_coverage.values())
    write_json(summary_path, summary)
    write_json(quality_path, report["quality"])
    md_path.write_text(render_markdown(report), encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")
    manifest = {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": generated_at,
        "report_path": report_path.as_posix(),
        "scenarios_path": scenarios_path.as_posix(),
        "results_path": results_path.as_posix(),
        "origins_path": origins_path.as_posix(),
        "summary_path": summary_path.as_posix(),
        "quality_path": quality_path.as_posix(),
        "markdown_path": md_path.as_posix(),
        "html_path": html_path.as_posix(),
        "synthetic_trace_net_root": synthetic_root.as_posix() if keep_synthetic_root else None,
        "synthetic_console_report_path": console_report.get("report_path"),
    }
    write_json(manifest_path, manifest)

    report.update(
        {
            "report_path": report_path.as_posix(),
            "scenarios_path": scenarios_path.as_posix(),
            "results_path": results_path.as_posix(),
            "origins_path": origins_path.as_posix(),
            "summary_path": summary_path.as_posix(),
            "quality_path": quality_path.as_posix(),
            "markdown_path": md_path.as_posix(),
            "html_path": html_path.as_posix(),
            "manifest_path": manifest_path.as_posix(),
        }
    )
    write_json(report_path, report)
    return report


def check_it_issue_origin_test_matrix_quality(
    report_path: Path,
    min_scenarios: int = 60,
    min_origin_categories: int = 15,
    require_all_scenarios_detected: bool = True,
    write_json_report: bool = False,
) -> dict[str, Any]:
    payload = read_json(report_path)
    summary = payload.get("summary", {})
    scenario_count = int(summary.get("scenario_count", 0) or 0)
    origin_count = int(summary.get("origin_category_count", 0) or 0)
    detected_count = int(summary.get("detected_scenario_count", 0) or 0)
    checks = {
        "scenario_count_meets_minimum": scenario_count >= min_scenarios,
        "origin_category_count_meets_minimum": origin_count >= min_origin_categories,
        "all_scenarios_detected_if_required": (detected_count == scenario_count) if require_all_scenarios_detected else detected_count > 0,
        "critical_scenarios_present": int(summary.get("critical_scenario_count", 0) or 0) > 0,
        "warning_scenarios_present": int(summary.get("warning_scenario_count", 0) or 0) > 0,
        "review_scenarios_present": int(summary.get("review_scenario_count", 0) or 0) > 0,
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    quality = {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": status,
        "report_path": report_path.as_posix(),
        "summary": summary,
        "checks": checks,
        "min_scenarios": min_scenarios,
        "min_origin_categories": min_origin_categories,
        "require_all_scenarios_detected": require_all_scenarios_detected,
    }
    if write_json_report:
        quality_path = report_path.with_name("trace_net_it_issue_origin_test_matrix_v1_quality.json")
        write_json(quality_path, quality)
        quality["quality_path"] = quality_path.as_posix()
    return quality


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run TRACE-Net IT issue-origin test matrix v1")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--min-scenarios", type=int, default=60)
    parser.add_argument("--min-origin-categories", type=int, default=15)
    parser.add_argument("--allow-undetected-scenarios", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = build_it_issue_origin_test_matrix(
        output_dir=args.output_dir,
        min_scenarios=args.min_scenarios,
        min_origin_categories=args.min_origin_categories,
        require_all_scenarios_detected=not args.allow_undetected_scenarios,
    )
    print("TRACE-Net IT issue-origin test matrix v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    summary = report["summary"]
    for key in [
        "scenario_count",
        "origin_category_count",
        "detected_scenario_count",
        "undetected_scenario_count",
        "critical_scenario_count",
        "warning_scenario_count",
        "review_scenario_count",
        "synthetic_console_critical_issue_count",
        "synthetic_console_warning_issue_count",
        "synthetic_console_review_issue_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report['report_path']}")
    print(f" quality_path: {report['quality_path']}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
