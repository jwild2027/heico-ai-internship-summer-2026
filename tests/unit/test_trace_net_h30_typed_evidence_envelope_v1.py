import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(
    "src/trace_net/context/trace_net_h30_typed_evidence_envelope_v1.py"
)
ROUTER_PATH = Path(
    "scripts/operations/router/serve_trace_net_cognitive_router_v1.py"
)
LAUNCHER_PATH = Path(
    "scripts/operations/launch_trace_net_cognitive_openwebui_v1.sh"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "trace_net_phase4_typed_evidence_test",
        MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def sample_envelope():
    return {
        "route": "guided_part_discovery",
        "direct_evidence": [
            {
                "page_id": "t_p_demo_p000001",
                "field_name": "part_number",
                "value": "120-41824-003",
                "citation_ready": True,
                "source_trace_ready": True,
                "direct_proof_authority": True,
            },
            {
                "page_id": "",
                "field_name": "ocr_text",
                "value": "unresolved OCR",
                "citation_ready": False,
                "source_trace_ready": False,
            },
        ],
        "candidate_evidence": [
            {
                "candidate_value": "120-41824-007",
                "guidance_only": True,
                "source_truth": False,
            }
        ],
        "visual_guidance": [
            {
                "page_id": "t_p_demo_p000003",
                "figure_refs": ["2"],
                "guidance_only": True,
            }
        ],
        "semantic_guidance": [
            {
                "candidate_type": "v3_page_intelligence",
                "page_id": "t_p_demo_p000004",
                "guidance_only": True,
            },
            {
                "candidate_type": "leiden_graph_relationship",
                "page_id": "t_p_demo_p000005",
                "guidance_only": True,
            },
        ],
        "contradictions": [
            {
                "type": "ata_document_mismatch",
                "candidate": "120-41824-297",
            }
        ],
        "source_resolution": [
            {
                "candidate_value": "120-41824-003",
                "resolution_status": "attempted",
            }
        ],
        "authority_evidence": [],
    }


def test_disabled_by_default():
    module = load_module()
    config = module.load_typed_evidence_config({})
    assert config["enabled"] is False


def test_direct_source_with_trace_can_support_claim():
    module = load_module()
    typed = module.build_typed_evidence_view(sample_envelope())
    direct = typed["records"][0]
    assert direct["source_bucket"] == "direct_evidence"
    assert direct["claim_support_allowed"] is True
    assert direct["final_answer_eligible"] is True
    assert direct["source_trace"]["ready"] is True


def test_incomplete_direct_source_cannot_support_claim():
    module = load_module()
    typed = module.build_typed_evidence_view(sample_envelope())
    direct = typed["records"][1]
    assert direct["proof_status"] == "direct_source_trace_incomplete"
    assert direct["claim_support_allowed"] is False


def test_all_guidance_classes_are_non_proof():
    module = load_module()
    typed = module.build_typed_evidence_view(sample_envelope())
    rows = [
        row for row in typed["records"]
        if row["source_bucket"] in {
            "candidate_evidence",
            "visual_guidance",
            "semantic_guidance",
            "source_resolution",
        }
    ]
    assert rows
    assert all(row["guidance_only"] for row in rows)
    assert not any(row["claim_support_allowed"] for row in rows)


def test_conflict_blocks_claim_support():
    module = load_module()
    typed = module.build_typed_evidence_view(sample_envelope())
    conflict = [
        row for row in typed["records"]
        if row["source_bucket"] == "contradictions"
    ][0]
    assert conflict["conflicted"] is True
    assert conflict["proof_status"] == "conflict_unresolved"
    assert conflict["claim_support_allowed"] is False


def test_graph_and_summary_modalities_are_explicit():
    module = load_module()
    typed = module.build_typed_evidence_view(sample_envelope())
    modalities = {
        row["modality"]
        for row in typed["records"]
    }
    assert "graph" in modalities
    assert "summary" in modalities


def test_legacy_rows_have_one_to_one_typed_records():
    module = load_module()
    source = sample_envelope()
    typed = module.build_typed_evidence_view(source)
    expected = sum(
        len(source.get(bucket) or [])
        for bucket in module.SOURCE_BUCKETS
    )
    assert len(typed["records"]) == expected
    assert typed["validation"]["quality_status"] == "PASS"


def test_stable_record_ids():
    module = load_module()
    first = module.build_typed_evidence_view(sample_envelope())
    second = module.build_typed_evidence_view(sample_envelope())
    assert [
        row["record_id"] for row in first["records"]
    ] == [
        row["record_id"] for row in second["records"]
    ]


def test_safety_contract_is_fail_closed():
    module = load_module()
    typed = module.build_typed_evidence_view(sample_envelope())
    safety = typed["safety_contract"]
    assert safety["answer_permission"] is False
    assert safety["source_truth_mutation_allowed"] is False
    assert safety["postgres_write_attempt"] is False
    assert safety["qdrant_write_attempt"] is False
    assert safety["opensearch_write_attempt"] is False


def test_runtime_files_are_wired():
    router = ROUTER_PATH.read_text(encoding="utf-8")
    launcher = LAUNCHER_PATH.read_text(encoding="utf-8")
    assert "install_typed_evidence_envelope" in router
    assert "TRACE_NET_H30_TYPED_EVIDENCE_ENABLED" in launcher
    assert (
        "test_trace_net_h30_typed_evidence_envelope_v1.py"
        in launcher
    )
