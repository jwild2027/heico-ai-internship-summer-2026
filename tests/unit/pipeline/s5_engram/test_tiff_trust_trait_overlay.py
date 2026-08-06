import json
from pathlib import Path

from tiff.trust_trait_overlay import (
    TrustTraitOverlayPaths,
    build_trust_trait_overlay,
    export_trust_trait_overlay,
    read_jsonl,
)


def _clean_record(page_id: str, tier: str, **flags):
    cleanup = {
        "trust_tier": tier,
        "usable_for_rag": tier in {"A", "B"},
        "requires_human_review": tier in {"C", "D"},
        "trust_reasons": ["unit_test_reason"] if tier in {"C", "D"} else ["clean_useful_visual_context"],
        "cleanup_version": "visual_text_v2_3_1_cleanup",
    }
    cleanup.update(flags)
    return {
        "page_id": page_id,
        "status": "ok",
        "prompt_version": "visual_text_v2_2",
        "visual_text_markdown_clean": "# Page visual text\n\n## Page type\nfigure\n",
        "visual_text_cleanup_scores": cleanup,
        "visual_text_scores_clean": {
            "required_sections_present": True,
            "metadata_leakage_risk": False,
            "refusal_like": False,
            "hallucination_risk": bool(flags.get("hallucination_risk")),
            "too_summary_heavy": bool(flags.get("too_summary_heavy")),
        },
    }


def test_build_trust_trait_overlay_attaches_tier_to_visual_text_context():
    result = build_trust_trait_overlay([
        _clean_record("p001", "A"),
        _clean_record("p002", "C", hallucination_risk=True, table_expected_but_not_extracted=True),
    ])

    summary = result["summary"]
    assert result["status"] == "OK"
    assert summary["records"] == 2
    assert summary["pages"] == 2
    assert summary["trust_tier_counts"]["A"] == 1
    assert summary["trust_tier_counts"]["C"] == 1
    assert summary["rag_trait_counts"]["include_visual_text"] == 1
    assert summary["rag_trait_counts"]["exclude_visual_text"] == 1
    assert summary["review_trait_counts"]["needs_human_review"] == 1
    assert summary["review_trait_counts"]["hallucination_risk"] == 1
    assert summary["review_trait_counts"]["table_expected_but_not_extracted"] == 1

    trait_ids = {node["id"] for node in result["nodes"] if node["type"] == "trait"}
    assert "trait:trust:visual_text:a" in trait_ids
    assert "trait:trust:visual_text:c" in trait_ids
    assert "trait:rag:visual_text:include_visual_text" in trait_ids
    assert "trait:rag:visual_text:exclude_visual_text" in trait_ids
    assert "trait:review:visual_text:needs_human_review" in trait_ids

    edges = {(edge["type"], edge["from"], edge["to"]) for edge in result["edges"]}
    assert ("HAS_VISUAL_TEXT", "page:p001", "visual_text:p001") in edges
    assert ("HAS_VISUAL_TEXT", "page:p002", "visual_text:p002") in edges


def test_export_trust_trait_overlay_writes_files(tmp_path: Path):
    visual_dir = tmp_path / "visual_text"
    trust_dir = tmp_path / "trust_traits"
    visual_dir.mkdir()
    records_path = visual_dir / "visual_text_extraction_clean.jsonl"
    records = [_clean_record("page-one", "B"), _clean_record("page-two", "D", prompt_template_leakage_risk=True)]
    with records_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    paths = TrustTraitOverlayPaths(output_dir=trust_dir, clean_records_path=records_path)
    result = export_trust_trait_overlay(paths)

    assert result["status"] == "OK"
    assert paths.summary.exists()
    assert paths.graph_nodes.exists()
    assert paths.graph_edges.exists()
    assert paths.assertions.exists()
    assert paths.review_md.exists()
    summary = json.loads(paths.summary.read_text(encoding="utf-8"))
    assertions = read_jsonl(paths.assertions)
    assert summary["records"] == 2
    assert summary["trust_tier_counts"]["B"] == 1
    assert summary["trust_tier_counts"]["D"] == 1
    assert len(assertions) >= 2
