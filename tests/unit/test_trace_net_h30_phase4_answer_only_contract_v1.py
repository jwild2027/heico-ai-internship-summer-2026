import json

from src.trace_net.writing import trace_net_h30_constrained_gemma_writer_v1 as writer


CONTENT = """## Answer

`120-26948-003` appears in the available IPL/table evidence on page `t_p_120_1176_p000030` [1].

## Evidence

- Source-backed record: `120-26948-003` — page `t_p_120_1176_p000030` [1]

## Limits

- This record does not establish effectivity or installation suitability [1]."""

REGISTRY = [{
    "citation_id": 1,
    "class": "direct_source",
    "authority": "proof",
    "can_prove_claims": True,
    "claim_scope": "confirmed",
    "candidate_value": "120-26948-003",
    "page_id": "t_p_120_1176_p000030",
    "nomenclature": ["Support"],
    "value": "120-26948-003",
}]


def packet():
    return writer.build_writer_packet(
        query="Locate part 120-26948-003 in the IPL table.",
        result={
            "route": "exact_table_ipl_lookup",
            "content": CONTENT,
            "answer_mode": {"mode": "confirmed_direct"},
        },
        registry=REGISTRY,
    )


def test_prompt_requests_answer_only_and_safe_exact_copy():
    prompt = writer.render_writer_prompt(packet())
    assert "Return only schema_version and answer" in prompt
    assert "safest valid response is to copy ORIGINAL ANSWER LINES exactly" in prompt
    assert "TRACE-Net, not the model" in prompt


def test_answer_only_output_uses_deterministic_support_sections():
    p = packet()
    output = json.dumps({
        "schema_version": writer.OUTPUT_SCHEMA_VERSION,
        "answer": p["deterministic_sections"]["answer"],
    })
    parsed = writer.parse_structured_writer_output(output)
    validation = writer.validate_structured_output(parsed, packet=p)
    assert validation["accepted"], validation
    assert validation["support_sections_source"] == "phase3_deterministic"
    assert p["deterministic_sections"]["evidence"][0] in validation["rendered"]
    assert p["deterministic_sections"]["limits"][0] in validation["rendered"]


def test_model_support_fields_are_ignored_not_rendered():
    p = packet()
    output = json.dumps({
        "schema_version": writer.OUTPUT_SCHEMA_VERSION,
        "answer": p["deterministic_sections"]["answer"],
        "evidence": ["Invented evidence [1]"],
        "limits": ["Invented limit [1]"],
    })
    validation = writer.validate_structured_output(
        writer.parse_structured_writer_output(output),
        packet=p,
    )
    assert validation["accepted"], validation
    assert "Invented evidence" not in validation["rendered"]
    assert "Invented limit" not in validation["rendered"]
    assert validation["model_supplied_evidence_ignored"]
    assert validation["model_supplied_limits_ignored"]


def test_full_markdown_answer_wrapper_is_normalized():
    p = packet()
    wrapped = "## Answer\n\n" + p["deterministic_sections"]["answer"][0] + "\n\n## Evidence\n\nIgnore this"
    output = json.dumps({
        "schema_version": writer.OUTPUT_SCHEMA_VERSION,
        "answer": wrapped,
    })
    parsed = writer.parse_structured_writer_output(output)
    assert parsed["answer"] == p["deterministic_sections"]["answer"]
    validation = writer.validate_structured_output(parsed, packet=p)
    assert validation["accepted"], validation


def test_answer_only_contract_still_rejects_new_identifier():
    p = packet()
    output = json.dumps({
        "schema_version": writer.OUTPUT_SCHEMA_VERSION,
        "answer": ["Part `999-99999-999` appears in the available IPL/table evidence [1]."],
    })
    validation = writer.validate_structured_output(
        writer.parse_structured_writer_output(output),
        packet=p,
    )
    assert not validation["accepted"]
    assert "structured_output_added_parts" in validation["failures"]
