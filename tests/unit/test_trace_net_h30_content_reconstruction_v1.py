from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path("src/trace_net/writing/trace_net_h30_content_reconstruction_v1.py")


def load(name="trace_net_h30_content_reconstruction_test"):
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_table_relationship_extracts_explicit_same_row_fields():
    mod = load("phase3_table")
    text = "25-21-00-92  -51  120-26948-003  SUPPORT ASSY  QTY 1"
    row = mod.extract_table_relationship(text, "120-26948-003")
    assert row["table_reference"] == "25-21-00-92"
    assert row["item"] == "-51"
    assert row["quantity"] == "1"
    assert "Support" in row["nomenclature"]


def test_table_relationship_does_not_invent_missing_fields():
    mod = load("phase3_table_missing")
    row = mod.extract_table_relationship("120-26948-003", "120-26948-003")
    assert row == {}


def test_procedure_sequence_reset_is_detected():
    mod = load("phase3_procedure")
    text = (
        "c. Adjust the baggage protector. d. Install P/N 120-29074-005. "
        "e. Install seal PE13076-1. f. Torque the fasteners. "
        "a. Remove P/N 120-29073-006. b. Install P/N 120-29919-001."
    )
    steps = mod.extract_procedure_steps(text)
    groups = mod.reconstruct_procedure_sequences(steps)
    assert [group["title"] for group in groups] == ["Continuation", "Sequence 2"]
    assert groups[0]["steps"][0][0] == "c"
    assert groups[1]["steps"][0][0] == "a"


def test_visual_callout_requires_explicit_callout_and_part():
    mod = load("phase3_visual")
    assert mod.extract_explicit_callout_mappings("Figure 2 shows a seat", "[1]") == []
    rows = mod.extract_explicit_callout_mappings(
        "Callout 12: P/N 120-41824-003 - SEAT BACKREST",
        "[1]",
    )
    assert rows[0]["callout"] == "12"
    assert rows[0]["part_number"] == "120-41824-003"


def test_ata_renderer_labels_source_location_leads():
    mod = load("phase3_ata")
    registry = [
        {
            "citation_id": 1,
            "class": "source_resolution",
            "page_id": "t_p_demo_p000047",
            "value": "route-scoped page lead",
            "can_prove_claims": False,
        }
    ]
    text, metrics = mod.render_ata_reconstruction(
        {"route": "ata_system_discovery"},
        "Find ATA 51-25-00.",
        registry,
    )
    assert "ATA `51-25-00`" in text
    assert "source-location lead" in text
    assert "source-location leads" in text
    assert metrics["ata_navigation_only"] is True


def test_table_renderer_preserves_public_contract_phrases():
    mod = load("phase3_table_render")
    result = {
        "route": "exact_table_ipl_lookup",
        "evidence_envelope": {
            "coverage": {
                "page_content": {
                    "available": True,
                    "pages": [
                        {
                            "page_id": "t_p_demo_p30",
                            "found": True,
                            "tables": [
                                {
                                    "citation_id": 1,
                                    "text": "25-21-00-92 -51 120-26948-003 SUPPORT QTY 1",
                                }
                            ],
                        }
                    ],
                }
            }
        },
    }
    registry = [
        {
            "citation_id": 1,
            "class": "direct_source",
            "can_prove_claims": True,
            "candidate_value": "120-26948-003",
            "page_id": "t_p_demo_p30",
            "value": "120-26948-003",
        }
    ]
    text, metrics = mod.render_table_reconstruction(
        result,
        "Locate part 120-26948-003 in the IPL table.",
        registry,
    )
    assert "IPL/table evidence" in text
    assert "Source-backed record" in text
    assert "Reconstructed same-row relationship" in text
    assert metrics["table_part_page_match"] is True


def test_procedure_renderer_uses_continuation_and_sequence_two():
    mod = load("phase3_procedure_render")
    result = {
        "route": "procedure_task_lookup",
        "evidence_envelope": {
            "coverage": {
                "page_content": {
                    "available": True,
                    "pages": [
                        {
                            "page_id": "t_p_demo_p482",
                            "found": True,
                            "ocr": [
                                {
                                    "citation_id": 1,
                                    "text": (
                                        "c. Adjust the baggage protector. d. Install P/N 120-29074-005. "
                                        "e. Install seal PE13076-1. f. Torque fasteners. "
                                        "a. Remove P/N 120-29073-006 as described in item 2. "
                                        "b. Install P/N 120-29919-001."
                                    ),
                                }
                            ],
                        }
                    ],
                }
            }
        },
    }
    text, metrics = mod.render_procedure_reconstruction(
        result,
        "What procedure is described on page t_p_demo_p482?",
    )
    assert "Continuation — c." in text
    assert "Sequence 2 — a." in text
    assert "not reproduced on this page" in text
    assert metrics["procedure_sequence_count"] == 2


def test_runtime_falls_back_to_prior_valid_answer_when_reconstruction_fails(monkeypatch):
    mod = load("phase3_runtime")
    monkeypatch.setenv("TRACE_NET_H30_CONTENT_RECONSTRUCTION_ENABLED", "1")

    class FakeRuntime:
        def process(self, payload):
            return {
                "route": "ata_system_discovery",
                "content": "## Answer\n\nOld valid answer [1].\n\n## Evidence\n\n- Old [1]",
                "post_answer_validation": {"accepted": True, "failures": []},
                "citation_registry": [{"citation_id": 1, "page_id": "t_p_demo"}],
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
            }

        def health(self):
            return {"quality_status": "PASS"}

    module = {
        "Runtime": FakeRuntime,
        "citation_registry": lambda result: list(result["citation_registry"]),
        "citation_registry_digest": lambda registry: "digest",
        "validate_answer": lambda *args, **kwargs: {"accepted": False, "failures": ["bad"]},
        "extract_latest_user": lambda payload: "ATA 51-25-00",
        "synthesis_allowed_identifiers": lambda query, result: {},
    }
    mod.install_content_reconstruction(module)
    out = FakeRuntime().process({})
    assert out["content"].startswith("## Answer\n\nOld valid answer")
    assert out["content_reconstruction"]["fallback_used"] is True
    assert out["source_truth_mutation_allowed"] is False


def test_health_has_no_llm_or_retrieval_changes():
    mod = load("phase3_health")
    health = mod.content_reconstruction_health({})
    assert health["quality_status"] == "PASS"
    assert health["llm_call_added"] is False
    assert health["retrieval_changed"] is False
    assert health["source_truth_mutation_allowed"] is False
