from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_page_element_registry_v1 import build_registry_report, read_json


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def sample_artifacts(tmp_path: Path) -> dict[str, Path]:
    page_profiles = {
        "quality_status": "PASS",
        "records": [
            {
                "profile_id": "profile_p1",
                "page_id": "t_p_120_1176_p000001",
                "page_number": 1,
                "document_id": "doc",
                "ata_code": "25-21-00",
                "context_v2_present": True,
                "embedding_text": "Revision 4 title manual supersedes technical publication table",
                "query_tunnel_terms": ["manual revision history"],
            },
            {
                "profile_id": "profile_p2",
                "page_id": "t_p_120_1176_p000002",
                "page_number": 2,
                "document_id": "doc",
                "embedding_text": "figure diagram callout parts list",
            },
        ],
    }
    embedding_candidates = {
        "quality_status": "PASS",
        "records": [
            {
                "embedding_candidate_id": "e1",
                "source_candidate_id": "rag_candidate:source_evidence:p1",
                "page_id": "t_p_120_1176_p000001",
                "rag_bucket": "source_evidence",
                "citation_id": "cite:source:p1",
                "can_answer_directly": False,
                "can_prove_claims": False,
            },
            {
                "embedding_candidate_id": "e2",
                "source_candidate_id": "rag_candidate:source_text:p1",
                "page_id": "t_p_120_1176_p000001",
                "rag_bucket": "source_text_evidence",
                "citation_id": "cite:source_text:p1",
                "authority": "ocr_text_claim_with_citation",
                "text_for_embedding": "Revision 4 - 10 April 2006",
                "can_answer_directly": False,
                "can_prove_claims": False,
            },
            {
                "embedding_candidate_id": "e3",
                "source_candidate_id": "rag_candidate:part:p1",
                "page_id": "t_p_120_1176_p000001",
                "rag_bucket": "verified_part_evidence",
                "citation_id": "cite:part:p1",
                "authority": "part_page_relationship",
                "can_answer_directly": False,
                "can_prove_claims": False,
            },
            {
                "embedding_candidate_id": "e4",
                "source_candidate_id": "rag_candidate:source_evidence:p2",
                "page_id": "t_p_120_1176_p000002",
                "rag_bucket": "source_evidence",
                "citation_id": "cite:source:p2",
                "can_answer_directly": False,
                "can_prove_claims": False,
            },
        ],
    }
    context_helpers = {
        "quality_status": "PASS",
        "records": [
            {
                "helper_id": "ctx1",
                "page_id": "t_p_120_1176_p000001",
                "authority": "retrieval_helper_only",
                "can_answer_directly": False,
            }
        ],
    }
    baseline = {"quality_status": "PASS", "summary": {"page_count": 2}}

    paths = {
        "page_profiles": tmp_path / "page_profiles.json",
        "embedding_candidates": tmp_path / "embedding_candidates.json",
        "context_helpers": tmp_path / "context_helpers.json",
        "baseline": tmp_path / "baseline.json",
    }
    write_json(paths["page_profiles"], page_profiles)
    write_json(paths["embedding_candidates"], embedding_candidates)
    write_json(paths["context_helpers"], context_helpers)
    write_json(paths["baseline"], baseline)
    return paths


def test_build_registry_report_creates_per_page_records(tmp_path: Path) -> None:
    paths = sample_artifacts(tmp_path)
    report = build_registry_report(
        page_profiles_path=paths["page_profiles"],
        embedding_candidates_path=paths["embedding_candidates"],
        context_helpers_path=paths["context_helpers"],
        baseline_checkpoint_path=paths["baseline"],
        output_dir=tmp_path / "out",
        quality_config={
            "require_page_count": 2,
            "min_page_records": 2,
            "min_pages_with_detected_elements": 2,
            "min_pages_with_recommended_routes": 2,
            "min_pages_with_fishnet": 2,
            "min_pages_with_comparison_targets": 2,
            "min_pages_with_graph_attachment_plan": 2,
            "min_pages_with_trust_policy": 2,
            "min_pages_with_source_trace": 2,
            "min_pages_with_ocr": 1,
        },
        write_quality=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["record_count"] == 2
    assert Path(report["report_path"]).exists()
    assert Path(report["records_path"]).exists()
    assert Path(report["matrix_markdown_path"]).exists()

    records = report["records"]
    p1 = next(r for r in records if r["page_id"] == "t_p_120_1176_p000001")
    assert "revision_or_effectivity_signal" in p1["page_traits"]
    assert "source_text" in {e["element_type"] for e in p1["detected_elements"]}
    assert "context_v2" in {e["element_type"] for e in p1["detected_elements"]}
    assert p1["answer_support_candidate_count"] == 2
    assert p1["can_answer_directly"] is False
    assert p1["can_mutate_source_truth"] is False

    p2 = next(r for r in records if r["page_id"] == "t_p_120_1176_p000002")
    assert "figure_chart_or_diagram_signal" in p2["page_traits"]
    assert any("visual" in route or "figure" in route for route in p2["recommended_extraction_routes"])


def test_registry_writes_graph_attachment_plan(tmp_path: Path) -> None:
    paths = sample_artifacts(tmp_path)
    report = build_registry_report(
        page_profiles_path=paths["page_profiles"],
        embedding_candidates_path=paths["embedding_candidates"],
        context_helpers_path=paths["context_helpers"],
        output_dir=tmp_path / "out",
        quality_config={"require_page_count": 2},
    )

    p1 = report["records"][0]
    plan = p1["graph_attachment_plan"]
    assert plan["mode"] == "plan_only_no_postgres_mutation"
    assert plan["can_mutate_source_truth"] is False
    assert plan["planned_edges"]


def test_registry_summary_counts_are_safe(tmp_path: Path) -> None:
    paths = sample_artifacts(tmp_path)
    report = build_registry_report(
        page_profiles_path=paths["page_profiles"],
        embedding_candidates_path=paths["embedding_candidates"],
        context_helpers_path=paths["context_helpers"],
        output_dir=tmp_path / "out",
        quality_config={"require_page_count": 2},
    )
    summary = report["summary"]
    assert summary["direct_answer_allowed_count"] == 0
    assert summary["source_truth_mutation_allowed_count"] == 0
    assert summary["retrieval_only_answer_allowed_count"] == 0
    assert summary["pages_with_fishnet_plan_count"] == 2
    assert summary["pages_with_graph_attachment_plan_count"] == 2


def test_report_can_be_read_back(tmp_path: Path) -> None:
    paths = sample_artifacts(tmp_path)
    report = build_registry_report(
        page_profiles_path=paths["page_profiles"],
        embedding_candidates_path=paths["embedding_candidates"],
        context_helpers_path=paths["context_helpers"],
        output_dir=tmp_path / "out",
    )
    loaded = read_json(report["report_path"], required=True)
    assert loaded["schema_version"] == "trace_net_page_element_registry_v1"
    assert loaded["quality"]["status"] == report["quality_status"]
