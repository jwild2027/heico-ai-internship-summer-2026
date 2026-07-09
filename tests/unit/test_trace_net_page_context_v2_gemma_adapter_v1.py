import json
from pathlib import Path

from tiff.trace_net_page_context_v2_gemma_adapter_v1 import (
    GRAPH_EDGES_JSON,
    GRAPH_NODES_JSON,
    MANIFEST_JSON,
    RECORDS_JSON,
    build_adapter,
    check_quality,
)


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def sample_gemma_report():
    return {
        "quality_status": "PASS",
        "failure_reasons": [],
        "summary": {
            "sample_record_count": 2,
            "gemma_success_count": 2,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
        "records": [
            {
                "page_id": "t_p_120_1176_p000001",
                "generation_model": "gemma4:26b",
                "llm_status": "GEMMA_JSON_SUMMARY_SUCCEEDED",
                "role": "front_matter",
                "subrole": "title_page",
                "confidence": "high",
                "short_summary": "Title page for the manual.",
                "retrieval_summary": "Useful for identifying the manual title and document identity.",
                "retrieval_cues": ["title page", "manual identity"],
                "important_entities": ["T.P. 120/1176"],
                "source_grounding": {"ocr_text_used": True},
                "authority": {"guidance_only": True},
            },
            {
                "page_id": "t_p_120_1176_p000042",
                "generation_model": "gemma4:26b",
                "llm_status": "GEMMA_JSON_SUMMARY_SUCCEEDED",
                "role": "parts_list",
                "subrole": "assembly_number_index",
                "confidence": "high",
                "short_summary": "Parts list/index page.",
                "retrieval_summary": "Useful for matching part and assembly references.",
                "retrieval_cues": ["parts list", "assembly number"],
                "important_entities": ["ATA 25-21-00-42"],
                "source_grounding": {"ocr_text_used": True},
                "authority": {"guidance_only": True},
            },
        ],
    }


def test_adapter_writes_old_page_context_v2_graph_contract(tmp_path):
    input_path = tmp_path / "gemma_v2.json"
    output_dir = tmp_path / "page_context_v2"
    write_json(input_path, sample_gemma_report())

    manifest = build_adapter(input_path, output_dir, min_records=2, expected_records=2)

    assert manifest["quality_status"] == "PASS"
    assert manifest["summary"]["record_count"] == 2
    assert manifest["summary"]["page_context_v2_node_count"] == 2
    assert manifest["summary"]["has_context_v2_edge_count"] == 2
    assert manifest["summary"]["answer_permission_count"] == 0
    assert manifest["summary"]["source_truth_mutation_allowed_count"] == 0

    records = json.loads((output_dir / RECORDS_JSON).read_text(encoding="utf-8"))
    nodes = json.loads((output_dir / GRAPH_NODES_JSON).read_text(encoding="utf-8"))
    edges = json.loads((output_dir / GRAPH_EDGES_JSON).read_text(encoding="utf-8"))

    assert records[1]["id"] == "page_context_v2:t_p_120_1176_p000042"
    assert records[1]["record_type"] == "page_context_v2"
    assert records[1]["guidance_only"] is True
    assert records[1]["canonical_source_truth"] is False
    assert records[1]["can_answer_directly"] is False

    assert nodes[1]["id"] == "page_context_v2:t_p_120_1176_p000042"
    assert nodes[1]["node_type"] == "page_context_v2"

    matching_edges = [e for e in edges if e["target"] == "page_context_v2:t_p_120_1176_p000042"]
    assert len(matching_edges) == 1
    assert matching_edges[0]["source"] == "page:t_p_120_1176_p000042"
    assert matching_edges[0]["edge_type"] == "HAS_CONTEXT_V2"


def test_quality_checker_enforces_old_contract(tmp_path):
    input_path = tmp_path / "gemma_v2.json"
    output_dir = tmp_path / "page_context_v2"
    write_json(input_path, sample_gemma_report())
    build_adapter(input_path, output_dir, min_records=2, expected_records=2)

    result = check_quality(
        output_dir / MANIFEST_JSON,
        min_records=2,
        expected_records=2,
        require_quality_pass=True,
        require_old_v2_graph_contract=True,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        max_unsafe=0,
    )

    assert result["quality_status"] == "PASS"
    assert result["failure_reasons"] == []
    assert result["summary"]["graph_node_count"] == 2
    assert result["summary"]["graph_edge_count"] == 2
