import json
from pathlib import Path

from tiff.trace_net_figure_item_fast_answer_composer_v1 import build_figure_item_fast_answer_composer


def _context(tmp_path: Path) -> Path:
    payload = {
        "module": "trace_net_anchor_aware_graph_leiden_expander_v1",
        "quality_status": "PASS",
        "summary": {"module": "trace_net_anchor_aware_graph_leiden_expander_v1"},
        "records": [
            {
                "citation_label": "E7",
                "anchor_aware_role": "direct_exact_match_anchor",
                "proof_strength": "direct_exact_proof",
                "anchor_relation_type": "exact_anchor",
                "page_number": 361,
                "page_id": "p361",
                "excerpt": "FIG. ITEM PART NUMBER FROM TO ASSY 85 - | 120-29067-017 STRUCTURE ASSY REF 1 | 120-29073-001 . STRUCTURE, LATERAL LEG............. VS4956 | 035/171 1 -2 | 120-29073-005 . STRUCTURE, LATERAL LEG",
            },
            {
                "citation_label": "E1",
                "anchor_aware_role": "direct_exact_match_anchor",
                "proof_strength": "direct_exact_proof",
                "page_number": 343,
                "page_id": "p343",
                "excerpt": "ASSY 79 - | 120-29067-001 STRUCTURE ASSY REF 1 | 120-29073-001 . STRUCTURE, LATERAL LEG",
            },
        ],
    }
    path = tmp_path / "context.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_figure_item_answer(tmp_path):
    context = _context(tmp_path)
    payload = build_figure_item_fast_answer_composer(
        context_pack=context,
        output_dir=tmp_path / "out",
        question="Show figure 85 item 1.",
        require_source_quality_pass=True,
        quality=True,
    )
    assert payload["quality_status"] == "PASS"
    summary = payload["summary"]
    assert summary["figure"] == "85"
    assert summary["item"] == "1"
    assert summary["figure_item_answer_record_count"] == 1
    assert summary["figure_item_part_numbers"] == ["120-29073-001"]
    assert summary["valid_answer_citation_count"] >= 1
    answer = (tmp_path / "out" / "trace_net_figure_item_fast_answer_composer_v1_answer.md").read_text(encoding="utf-8")
    assert "Figure" in answer or "figure" in answer
    assert "120-29073-001" in answer
    assert "[E7]" in answer
