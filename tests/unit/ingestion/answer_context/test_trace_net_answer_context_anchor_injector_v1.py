import json
from pathlib import Path

from tiff.trace_net_answer_context_anchor_injector_v1 import build_answer_context_anchor_injector


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _probe_payload() -> dict:
    return {
        "quality_status": "PASS",
        "summary": {
            "question": "Find part number 120-29073-001 and nearby similar parts.",
            "query_part_numbers": ["120-29073-001"],
            "exact_direct_hit_count": 2,
            "exact_hit_count": 4,
            "family_variant_hit_count": 1,
            "direct_exact_page_numbers": [343, 346],
        },
        "direct_evidence_records": [
            {
                "proof_role": "direct_exact_match_proven",
                "source_name": "ocr_route_scan_pack",
                "hit_class": "trusted_ocr_text_hit",
                "page_id": "p343",
                "page_number": 343,
                "source_member": "00000343.tif",
                "matched_part_number": "120-29073-001",
                "field_path": "ocr_sample_text",
                "excerpt": "1 | 120-29073-001 . STRUCTURE, LATERAL LEG VS4956 1",
            },
            {
                "proof_role": "direct_exact_match_proven",
                "source_name": "ocr_route_scan_pack",
                "hit_class": "trusted_ocr_text_hit",
                "page_id": "p346",
                "page_number": 346,
                "source_member": "00000346.tif",
                "matched_part_number": "120-29073-001",
                "field_path": "ocr_sample_text",
                "excerpt": "1 | 120-29073-001 . STRUCTURE, LATERAL LEG VS4956 A 1",
            },
            {
                "proof_role": "direct_exact_match_proven",
                "source_name": "table_exact_search_adapter",
                "hit_class": "trusted_table_exact_hit",
                "page_id": "p32",
                "field_path": "raw_value",
                "excerpt": "120-29073-001",
            },
        ],
        "reference_hit_records": [
            {
                "proof_role": "exact_metadata_candidate",
                "source_name": "ocr_route_scan_pack",
                "hit_class": "trusted_metadata_hit",
                "page_id": "p32",
                "page_number": 32,
                "source_member": "00000032.tif",
                "excerpt": "120-29073-001",
            }
        ],
        "family_variant_records": [
            {
                "source_name": "ocr_route_scan_pack",
                "hit_class": "family_variant_hit",
                "page_id": "p346",
                "page_number": 346,
                "source_member": "00000346.tif",
                "excerpt": "120-29073-005",
            }
        ],
    }


def test_anchor_injector_puts_direct_exact_pages_first(tmp_path):
    probe = _write(tmp_path / "probe.json", _probe_payload())
    payload = build_answer_context_anchor_injector(
        part_number_exact_retrieval_probe=probe,
        output_dir=tmp_path / "out",
        require_source_quality_pass=True,
        quality=True,
    )
    assert payload["quality_status"] == "PASS"
    summary = payload["summary"]
    assert summary["direct_exact_anchor_count"] == 2
    assert summary["direct_exact_anchor_page_numbers"] == [343, 346]
    assert summary["exact_reference_anchor_count"] == 1
    assert summary["family_variant_anchor_count"] == 1
    assert payload["records"][0]["anchor_role"] == "direct_exact_match_anchor"
    assert "DIRECT EXACT ANCHORS" in payload["llm_context_prompt"]
    assert "120-29073-001 . STRUCTURE, LATERAL LEG" in payload["llm_context_prompt"]


def test_anchor_injector_retains_existing_context_but_dedupes_direct_pages(tmp_path):
    probe = _write(tmp_path / "probe.json", _probe_payload())
    graph = _write(
        tmp_path / "graph.json",
        {
            "quality_status": "PASS",
            "records": [
                {"page_id": "p343", "page_number": 343, "graph_context_role": "similar_table_candidate", "enriched_excerpt": "old duplicate"},
                {"page_id": "p45", "page_number": 45, "graph_context_role": "similar_table_candidate", "enriched_excerpt": "support page"},
            ],
        },
    )
    payload = build_answer_context_anchor_injector(
        part_number_exact_retrieval_probe=probe,
        graph_leiden_expander=graph,
        output_dir=tmp_path / "out",
        require_source_quality_pass=True,
    )
    assert payload["summary"]["retained_support_context_count"] == 1
    assert any(r.get("page_number") == 45 and r.get("anchor_status") == "RETAINED_SUPPORT_CONTEXT" for r in payload["records"])
    assert not any(r.get("page_number") == 343 and r.get("anchor_status") == "RETAINED_SUPPORT_CONTEXT" for r in payload["records"])


def test_anchor_injector_fails_without_direct_anchor(tmp_path):
    probe_payload = _probe_payload()
    probe_payload["direct_evidence_records"] = []
    probe = _write(tmp_path / "probe.json", probe_payload)
    payload = build_answer_context_anchor_injector(
        part_number_exact_retrieval_probe=probe,
        output_dir=tmp_path / "out",
    )
    assert payload["quality_status"] == "FAIL"
    assert payload["summary"]["anchor_injection_ready"] is False


def test_anchor_injector_records_safety_contract(tmp_path):
    probe = _write(tmp_path / "probe.json", _probe_payload())
    payload = build_answer_context_anchor_injector(
        part_number_exact_retrieval_probe=probe,
        output_dir=tmp_path / "out",
    )
    summary = payload["summary"]
    assert summary["answer_permission_count"] == 0
    assert summary["source_truth_mutation_allowed_count"] == 0
    assert summary["write_attempt_count"] == 0
    assert summary["dry_run_only"] is True
