from __future__ import annotations

import sys
import types

from scripts.trace_net_h30_phase19_preservation_writer_v1 import (
    answer_digest,
    build_preservation_prompt,
    canonical_answer_object,
    install_phase19_preservation_writer,
)


def packet():
    return {
        "route": "exact_identifier_lookup",
        "deterministic_sections": {
            "answer": ["`120-20970-001` appears in the indexed source records [1]."],
            "evidence": ["- Source-backed record [1]."],
            "limits": ["- Some associations remain guidance-level."],
        },
        "required_answer_phrases": ["appears in the indexed source records"],
    }


def test_canonical_object_and_digest_are_stable():
    value = canonical_answer_object(packet(), "schema-v1")
    assert value == {
        "schema_version": "schema-v1",
        "answer": ["`120-20970-001` appears in the indexed source records [1]."],
    }
    assert answer_digest(packet(), "schema-v1") == answer_digest(packet(), "schema-v1")


def test_prompt_contains_exact_output_and_no_rewrite_instruction():
    prompt = build_preservation_prompt(packet(), "schema-v1")
    assert "EXACT OUTPUT OBJECT" in prompt
    assert "character-for-character" in prompt
    assert "Do not paraphrase" in prompt
    assert "120-20970-001" in prompt


def test_install_monkeypatches_writer_and_attaches_telemetry(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_PHASE19_PRESERVATION_WRITER_ENABLED", "1")
    monkeypatch.setenv("TRACE_NET_H30_PHASE19_PRESERVATION_MAX_TOKENS", "256")

    fake_writer = types.ModuleType("scripts.trace_net_h30_constrained_gemma_writer_v1")
    fake_writer.OUTPUT_SCHEMA_VERSION = "schema-v1"
    fake_writer.build_writer_packet = lambda *a, **k: packet()
    fake_writer.render_writer_prompt = lambda value: "legacy"
    fake_writer.load_constrained_writer_config = lambda environ=None: {"max_tokens": 512}
    monkeypatch.setitem(sys.modules, fake_writer.__name__, fake_writer)

    class Runtime:
        def process(self, payload):
            built = fake_writer.build_writer_packet()
            return {
                "content": "ok",
                "built_packet": built,
                "constrained_gemma_writer": {
                    "call_attempted": True,
                    "call_count": 1,
                    "structured_output_accepted": True,
                    "phase3_fallback_used": False,
                },
            }

        def health(self):
            return {"quality_status": "PASS"}

    module = {"Runtime": Runtime}
    install_phase19_preservation_writer(module)
    built = fake_writer.build_writer_packet()
    assert built["phase19_preservation"]["enabled"] is True
    assert "EXACT OUTPUT OBJECT" in fake_writer.render_writer_prompt(built)
    assert fake_writer.load_constrained_writer_config()["max_tokens"] == 256
    result = Runtime().process({})
    assert result["phase19_preservation_writer"]["active"] is True
    assert result["phase19_preservation_writer"]["structured_output_accepted"] is True
    assert Runtime().health()["phase19_preservation_writer"]["enabled"] is True
