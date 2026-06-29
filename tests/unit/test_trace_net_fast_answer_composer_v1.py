from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_fast_answer_composer_v1 import build_fast_answer_composer


def _context(tmp_path: Path) -> Path:
    payload = {
        "quality_status": "PASS",
        "summary": {
            "module": "trace_net_anchor_aware_graph_leiden_expander_v1",
            "question": "Find part number 120-29073-001 and nearby similar parts.",
            "query_part_numbers": ["120-29073-001"],
        },
        "records": [
            {
                "citation_label": "E1",
                "anchor_aware_role": "direct_exact_match_anchor",
                "proof_strength": "direct_exact_proof",
                "anchor_relation_type": "exact_anchor",
                "page_number": 343,
                "page_id": "p343",
                "excerpt": "FIG 79 ITEM 1 | 120-29073-001 . STRUCTURE, LATERAL LEG ........ VS4956 1",
            },
            {
                "citation_label": "E2",
                "anchor_aware_role": "direct_exact_match_anchor",
                "proof_strength": "direct_exact_proof",
                "anchor_relation_type": "exact_anchor",
                "page_number": 346,
                "page_id": "p346",
                "excerpt": "FIG 80 ITEM 1 | 120-29073-001 . STRUCTURE, LATERAL LEG ........ VS4956 1",
            },
            {
                "citation_label": "E25",
                "anchor_aware_role": "same_anchor_community_variant",
                "proof_strength": "related_variant",
                "anchor_relation_type": "same_anchor_leiden_community_variant",
                "page_number": 346,
                "page_id": "p346",
                "excerpt": "120-29073-005",
            },
            {
                "citation_label": "E18",
                "anchor_aware_role": "family_variant_anchor",
                "proof_strength": "related_variant",
                "anchor_relation_type": "part_family_variant",
                "page_number": 32,
                "page_id": "p32",
                "excerpt": "120-29073-007",
            },
            {
                "citation_label": "E31",
                "anchor_aware_role": "same_anchor_leiden_community_neighbor",
                "proof_strength": "weak_candidate",
                "anchor_relation_type": "same_anchor_leiden_community",
                "page_number": 55,
                "page_id": "p55",
                "excerpt": "weak related context",
            },
        ],
    }
    p = tmp_path / "context.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_build_fast_answer_composer_passes(tmp_path: Path) -> None:
    context = _context(tmp_path)
    payload = build_fast_answer_composer(
        context_pack=context,
        output_dir=tmp_path / "out",
        require_source_quality_pass=True,
        quality=True,
    )
    assert payload["quality_status"] == "PASS"
    answer = payload["answer_text"]
    assert "120-29073-001" in answer
    assert "STRUCTURE, LATERAL LEG" in answer
    assert "[E1]" in answer and "[E2]" in answer
    assert "120-29073-005" in answer
    assert "120-29073-007" in answer
    assert "interchangeable" not in answer.lower()
    assert "replacement" not in answer.lower()
    assert (tmp_path / "out" / "trace_net_fast_answer_composer_v1_answer.md").exists()


def test_missing_source_quality_fails_when_required(tmp_path: Path) -> None:
    context = _context(tmp_path)
    data = json.loads(context.read_text())
    data["quality_status"] = "FAIL"
    context.write_text(json.dumps(data), encoding="utf-8")
    try:
        build_fast_answer_composer(context_pack=context, output_dir=tmp_path / "out", require_source_quality_pass=True)
    except Exception as exc:
        assert "source context quality" in str(exc)
    else:
        raise AssertionError("expected source quality failure")
