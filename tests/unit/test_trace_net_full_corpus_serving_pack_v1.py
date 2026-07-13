import json
from pathlib import Path
from scripts.build_trace_net_full_corpus_serving_pack_v1 import parser, build

def test_build_full_corpus_pack_from_fixture(tmp_path: Path):
    source = tmp_path / "artifact.json"
    source.write_text(json.dumps({
        "records": [
            {
                "page_id": "p000001",
                "document_id": "manual-a",
                "part_numbers": ["120-41824-003"],
                "table_text": "LOCKING RING",
                "v2_summary": "Illustrated parts list page for a locking ring.",
                "community_id": "community_1",
            },
            {
                "page_id": "p000002",
                "manual_reference": "25-21-00",
                "ocr_text": "Removal procedure and caution text.",
                "page_summary": "Procedure page with removal steps and caution.",
            },
        ]
    }), encoding="utf-8")
    out = tmp_path / "out"
    args = parser().parse_args([
        "--artifact-root", str(tmp_path),
        "--input", str(source),
        "--output-dir", str(out),
        "--min-exact-documents", "1",
        "--min-page-summaries", "1",
        "--min-page-memberships", "1",
    ])
    result = build(args)
    assert result["quality_status"] == "PASS"
    assert result["exact_search_document_count"] >= 4
    assert result["page_summary_count"] == 2
    assert result["leiden_page_membership_count"] == 2
    assert Path(result["paths"]["v27_manifest"]).exists()
    manifest = json.loads(Path(result["paths"]["v27_manifest"]).read_text())
    assert manifest["exact_search_document_count"] >= 4
    assert manifest["page_summary_count"] == 2
    assert manifest["leiden_page_membership_count"] == 2
