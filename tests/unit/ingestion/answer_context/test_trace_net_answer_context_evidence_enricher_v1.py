from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json
from pathlib import Path

from tiff.trace_net_answer_context_evidence_enricher_v1 import build_answer_context_evidence_enricher


def test_enricher_joins_ocr_and_marks_direct_match(tmp_path):
    context = tmp_path / "context.json"
    context.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {
            "question": "Find part number 120-29073-001 and nearby similar parts.",
            "query_part_numbers": ["120-29073-001"],
        },
        "records": [
            {
                "citation_label": "E1",
                "context_role": "direct_evidence_candidate",
                "page_id": "p1",
                "page_number": 5,
                "route": "table",
                "retrieval_score": 100.0,
                "targets": ["qdrant", "opensearch"],
            }
        ],
    }), encoding="utf-8")
    ocr = tmp_path / "ocr.json"
    ocr.write_text(json.dumps({
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "p1",
                "page_number": 5,
                "source_member": "00000005.tif",
                "source_image_sha256": "abc",
                "ocr_text": "ITEM 12 PART NO 120-29073-001 DESCRIPTION TEST BRACKET QTY 1",
            }
        ],
    }), encoding="utf-8")
    payload = build_answer_context_evidence_enricher(
        context_pack=context,
        ocr_route_scan_pack=ocr,
        output_dir=tmp_path / "out",
        require_source_quality_pass=True,
        quality=True,
    )
    assert payload["quality_status"] == "PASS"
    record = payload["records"][0]
    assert record["direct_text_match"] is True
    assert record["enriched_context_role"] == "direct_exact_match_proven"
    assert "120-29073-001" in record["enriched_excerpt"]
    assert payload["summary"]["enriched_excerpt_count"] == 1
    assert (tmp_path / "out" / "trace_net_answer_context_evidence_enricher_v1_prompt.txt").exists()


def test_enricher_uses_table_artifact_before_ocr(tmp_path):
    context = tmp_path / "context.json"
    context.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {"question": "Find 120-29073-001", "query_part_numbers": ["120-29073-001"]},
        "records": [{"citation_label": "E1", "page_id": "p1", "page_number": 5, "route": "table", "context_role": "direct_evidence_candidate"}],
    }), encoding="utf-8")
    ocr = tmp_path / "ocr.json"
    ocr.write_text(json.dumps({"quality_status": "PASS", "records": [{"page_id": "p1", "page_number": 5, "source_member": "5.tif", "source_image_sha256": "hash", "ocr_text": "no exact text here"}]}), encoding="utf-8")
    table = tmp_path / "table.json"
    table.write_text(json.dumps({"quality_status": "PASS", "records": [{"page_id": "p1", "evidence_text": "ROW PART 120-29073-001 DESCRIPTION TABLE SOURCE"}]}), encoding="utf-8")
    payload = build_answer_context_evidence_enricher(context_pack=context, ocr_route_scan_pack=ocr, table_exact_search_adapter=table, output_dir=tmp_path / "out", quality=True)
    assert payload["records"][0]["enriched_excerpt_source"] == "table_exact_or_table_artifact"
    assert payload["summary"]["direct_text_match_count"] == 1


def test_enricher_warns_without_excerpt_but_keeps_dry_run_safe(tmp_path):
    context = tmp_path / "context.json"
    context.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {"question": "Find 120-29073-001"},
        "records": [{"citation_label": "E1", "page_id": "p1", "page_number": 5, "route": "table", "context_role": "direct_evidence_candidate"}],
    }), encoding="utf-8")
    ocr = tmp_path / "ocr.json"
    ocr.write_text(json.dumps({"quality_status": "PASS", "records": [{"page_id": "p1", "page_number": 5, "source_member": "5.tif", "source_image_sha256": "hash"}]}), encoding="utf-8")
    payload = build_answer_context_evidence_enricher(context_pack=context, ocr_route_scan_pack=ocr, output_dir=tmp_path / "out")
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["enrichment_warning_count"] == 1
    assert payload["summary"]["answer_permission_count"] == 0
    assert payload["summary"]["write_attempt_count"] == 0
