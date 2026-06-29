import json
from pathlib import Path

from tiff.trace_net_answer_quality_gate_v1 import build_answer_quality_gate, audit_answer_quality


def _context():
    return {
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
                "page_id": "t_p_120_1176_p000343",
            },
            {
                "citation_label": "E2",
                "anchor_aware_role": "same_anchor_community_variant",
                "proof_strength": "related_variant",
                "anchor_relation_type": "same_anchor_leiden_community_variant",
                "page_number": 346,
                "page_id": "t_p_120_1176_p000346",
            },
        ],
    }


def test_audit_passes_safe_cited_answer():
    answer = (
        "Part 120-29073-001 is found as STRUCTURE, LATERAL LEG on the direct exact anchor page [E1]. "
        "A nearby family variant shown in the provided context is 120-29073-005 [E2]. "
        "The variant is related evidence only, not proof of interchangeability [E2]."
    )
    payload = audit_answer_quality(answer_text=answer, context_payload=_context())
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["direct_proof_citation_count"] == 1
    assert payload["summary"]["invalid_answer_citation_count"] == 0


def test_audit_fails_invalid_citation():
    answer = "Part 120-29073-001 is found [E99]."
    payload = audit_answer_quality(answer_text=answer, context_payload=_context())
    assert payload["quality_status"] == "FAIL"
    assert payload["summary"]["invalid_answer_citation_count"] == 1
    assert any(v["violation_type"] == "invalid_citation_label" for v in payload["violations"])


def test_audit_fails_interchangeability_claim_without_proof():
    answer = "Part 120-29073-005 is an interchangeable replacement for 120-29073-001 [E1] [E2]."
    payload = audit_answer_quality(answer_text=answer, context_payload=_context())
    assert payload["quality_status"] == "FAIL"
    assert any(v["violation_type"] == "unsupported_interchangeability_claim" for v in payload["violations"])


def test_build_writes_outputs(tmp_path):
    context_path = tmp_path / "context.json"
    answer_path = tmp_path / "answer.md"
    out_dir = tmp_path / "out"
    context_path.write_text(json.dumps(_context()), encoding="utf-8")
    answer_path.write_text(
        "Part 120-29073-001 is found as STRUCTURE, LATERAL LEG [E1]. Nearby variant 120-29073-005 is related only [E2].",
        encoding="utf-8",
    )
    payload = build_answer_quality_gate(
        context_pack=str(context_path),
        answer_file=str(answer_path),
        output_dir=str(out_dir),
        require_source_quality_pass=True,
        quality=True,
    )
    assert payload["quality_status"] == "PASS"
    assert (out_dir / "trace_net_answer_quality_gate_v1.json").exists()
    assert (out_dir / "trace_net_answer_quality_gate_v1_records.csv").exists()
    assert (out_dir / "trace_net_answer_quality_gate_v1_violations.csv").exists()
    assert (out_dir / "trace_net_answer_quality_gate_v1_quality_check.json").exists()
