import json
from pathlib import Path

from tiff.trace_net_part_family_fast_answer_composer_v1 import build_part_family_fast_answer_composer


def _context(tmp_path: Path) -> Path:
    payload = {
        "module": "trace_net_anchor_aware_graph_leiden_expander_v1",
        "quality_status": "PASS",
        "summary": {"module": "trace_net_anchor_aware_graph_leiden_expander_v1"},
        "records": [
            {
                "citation_label": "E1",
                "anchor_aware_role": "direct_exact_match_anchor",
                "proof_strength": "direct_exact_proof",
                "anchor_relation_type": "exact_anchor",
                "page_number": 343,
                "page_id": "p343",
                "leiden_community_ids": ["4"],
                "excerpt": "FIG 79 ITEM 1 | 120-29073-001 . STRUCTURE, LATERAL LEG",
            },
            {
                "citation_label": "E25",
                "anchor_aware_role": "same_anchor_community_variant",
                "proof_strength": "related_variant",
                "anchor_relation_type": "same_anchor_leiden_community_variant",
                "page_number": 346,
                "page_id": "p346",
                "same_anchor_leiden_community_ids": ["50"],
                "excerpt": "120-29073-005 . STRUCTURE, LATERAL LEG",
            },
            {
                "citation_label": "E18",
                "anchor_aware_role": "family_variant_anchor",
                "proof_strength": "related_variant",
                "anchor_relation_type": "part_family_variant",
                "page_number": 32,
                "page_id": "p032",
                "excerpt": "120-29073-007",
            },
        ],
    }
    path = tmp_path / "context.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_part_family_composer_builds_cited_answer(tmp_path):
    context = _context(tmp_path)
    payload = build_part_family_fast_answer_composer(
        context_pack=context,
        output_dir=tmp_path / "out",
        question="Show the 120-29073 family.",
        part_family="120-29073",
        require_source_quality_pass=True,
        quality=True,
    )
    assert payload["quality_status"] == "PASS"
    summary = payload["summary"]
    assert summary["part_family_fast_answer_ready"] is True
    assert summary["part_family_part_number_count"] == 3
    answer = (tmp_path / "out" / "trace_net_part_family_fast_answer_composer_v1_answer.md").read_text(encoding="utf-8")
    assert "120-29073-001" in answer
    assert "120-29073-005" in answer
    assert "120-29073-007" in answer
    assert "[E1]" in answer
