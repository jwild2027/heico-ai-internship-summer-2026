import json
from pathlib import Path

from tiff.trace_net_retrieval_payload_audit_v1 import build_retrieval_payload_audit


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _contract_payload():
    records = [
        {
            "page_id": "p1",
            "page_number": 1,
            "route": "plain_text",
            "source_member": "0001.tif",
            "raw_tiff_reference": "0001.tif",
            "source_image_sha256": "a" * 64,
            "lineage_ready": True,
            "contract_ready_targets": ["postgres_graph", "qdrant"],
            "embedding_scope": "validated_page_or_evidence_summary",
            "evidence_policy": "graph_source_map_plus_validated_evidence_links",
            "storage_decision": "validated_graph_and_semantic_index",
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        },
        {
            "page_id": "p2",
            "page_number": 2,
            "route": "blank",
            "source_member": "0002.tif",
            "raw_tiff_reference": "0002.tif",
            "source_image_sha256": "b" * 64,
            "lineage_ready": True,
            "contract_ready_targets": ["postgres_graph"],
            "evidence_policy": "graph_source_map_only",
            "final_do_not_embed": True,
            "storage_decision": "graph_only_blank",
        },
        {
            "page_id": "p3",
            "page_number": 3,
            "route": "table",
            "source_member": "0003.tif",
            "raw_tiff_reference": "0003.tif",
            "source_image_sha256": "c" * 64,
            "lineage_ready": True,
            "contract_ready_targets": ["postgres_graph", "qdrant", "opensearch"],
            "embedding_scope": "validated_page_or_evidence_summary",
            "exact_index_scope": "validated_table_or_exact_evidence",
            "evidence_policy": "graph_source_map_plus_validated_evidence_links",
            "storage_decision": "validated_graph_semantic_and_exact_index",
        },
    ]
    return {"quality_status": "PASS", "summary": {}, "records": records}


def _ocr_payload():
    return {
        "quality_status": "PASS",
        "records": [
            {"page_id": "p1", "page_number": 1, "ocr_text": "Description and operation for passenger seat maintenance."},
            {"page_id": "p2", "page_number": 2, "ocr_text": ""},
            {"page_id": "p3", "page_number": 3, "ocr_text": "ITEM FIG PART NUMBER 120-29073-001 NOMENCLATURE QTY", "part_number_count": 1},
        ],
    }


def test_build_retrieval_payload_audit_passes(tmp_path):
    contract = _write(tmp_path / "contract.json", _contract_payload())
    ocr = _write(tmp_path / "ocr.json", _ocr_payload())
    payload = build_retrieval_payload_audit(
        loader_contract_audit_path=contract,
        ocr_route_scan_pack_path=ocr,
        output_dir=tmp_path / "out",
        quality=True,
    )
    summary = payload["summary"]
    assert payload["quality_status"] == "PASS"
    assert summary["retrieval_payload_audit_record_count"] == 3
    assert summary["qdrant_payload_count"] == 2
    assert summary["opensearch_payload_count"] == 1
    assert summary["blank_payload_violation_count"] == 0
    assert summary["blocked_payload_violation_count"] == 0
    assert (tmp_path / "out" / "trace_net_retrieval_payload_audit_v1_qdrant_payload_audit.jsonl").exists()
    assert (tmp_path / "out" / "trace_net_retrieval_payload_audit_v1_opensearch_payload_audit.jsonl").exists()


def test_blank_qdrant_target_is_violation(tmp_path):
    contract_payload = _contract_payload()
    contract_payload["records"][1]["contract_ready_targets"] = ["postgres_graph", "qdrant"]
    contract_payload["records"][1]["embedding_scope"] = "bad_blank_embedding"
    contract = _write(tmp_path / "contract.json", contract_payload)
    ocr = _write(tmp_path / "ocr.json", _ocr_payload())
    payload = build_retrieval_payload_audit(
        loader_contract_audit_path=contract,
        ocr_route_scan_pack_path=ocr,
        output_dir=tmp_path / "out",
    )
    assert payload["quality_status"] == "FAIL"
    assert payload["summary"]["blank_payload_violation_count"] == 1
    assert payload["summary"]["violation_record_count"] >= 1
