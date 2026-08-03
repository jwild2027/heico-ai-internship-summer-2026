import importlib.util
import json
import sys
from pathlib import Path


SHADOW_PATH = Path("tiff/trace_net_engram_skill_shadow_v1.py")
INSTALLER_PATH = Path("src/trace_net/engram/trace_net_h30_engram_skill_shadow_v1.py")
LIBRARY_PATH = Path(
    "local_data/organization/trace_net/engram_skill_cards_v1/"
    "trace_net_engram_skill_cards_v1.json"
)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def q001_result():
    return {
        "query": "I only know the part starts with 123",
        "route": "guided_part_discovery",
        "route_plan": {
            "retrieval_tunnels": [
                "guided_candidate_discovery",
                "normal_source_resolution",
                "phase4_3_candidate_source_resolution",
                "qdrant_guidance",
            ]
        },
        "query_atoms": {
            "part_prefix": "123",
            "explicit_partial_wording": True,
        },
        "evidence_envelope": {
            "retrieval_tunnels_used": [
                "guided_candidate_discovery",
                "normal_source_resolution",
                "phase4_3_candidate_source_resolution",
            ],
            "candidate_evidence": [{"candidate_value": "1234567"}],
        },
        "content": (
            "## Answer\n\n"
            "TRACE-Net found candidate evidence, not a final identification:\n"
            "- 1234567 — ATA 25-21-00\n"
            "Candidate, visual, graph, summary, and semantic results are guidance only "
            "until resolved to direct source evidence.\n\n"
            "## Evidence\n\nOnly guidance-level matches were found.\n\n"
            "## Engineering confidence\n\nGuidance only.\n\n"
            "## Limits\n\n- A source-resolved record is still required."
        ),
        "follow_up_questions": [
            "What additional part number characters do you remember after the prefix 123?",
            "Do you know the manufacturer, vendor, or supplier?",
            "What component, function, assembly, or installation location is the part associated with?",
            "What does the part look like, including its shape, color, size, markings, and nearby hardware?",
            "Do you know the ATA chapter, aircraft system, figure, diagram, IPL item, table, manual, or page?",
        ],
        "citation_count": 0,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }


def test_q001_shadow_selects_partial_skill_and_flags_generic_answer():
    module = load(SHADOW_PATH, "shadow_q001")
    shadow = module.build_engram_skill_shadow(
        q001_result(),
        stage="offline_final_record",
        library_path=LIBRARY_PATH,
    )
    assert shadow["quality_status"] == "PASS"
    assert shadow["selected_skill_ids"][0] == "partial_identifier_discovery"
    assert "generic_candidate_boilerplate" in shadow["current_answer_flags"]
    assert (
        shadow["follow_up_assessment"]
        ["all_five_standard_discovery_questions_present"]
        is True
    )
    assert shadow["expected_answer_modes"] == ["candidate_discovery"]
    assert shadow["answer_permission"] is False


def test_guidance_contains_old_reliable_playbook_without_becoming_proof():
    module = load(SHADOW_PATH, "shadow_guidance")
    shadow = module.build_engram_skill_shadow(
        q001_result(),
        stage="offline_final_record",
        library_path=LIBRARY_PATH,
    )
    text = shadow["guidance_text"]
    assert "Search exact identifier indexes" in text
    assert "Deduplicate candidate identities" in text
    assert "BEHAVIOR GUIDANCE ONLY; NOT PROOF" in text
    assert shadow["can_be_used_as_proof"] is False
    assert shadow["retrieval_execution_allowed"] is False


def test_attach_preserves_current_behavior_fingerprint():
    module = load(SHADOW_PATH, "shadow_attach")
    original = q001_result()
    before = module.immutable_output_fingerprint(original)
    output = module.attach_engram_skill_shadow(
        original,
        query=original["query"],
        stage="final_answer_writer",
        library_path=LIBRARY_PATH,
    )
    after = module.immutable_output_fingerprint(output)
    assert before == after
    assert output["content"] == original["content"]
    assert output["route"] == original["route"]
    assert output["evidence_envelope"] == original["evidence_envelope"]
    assert output["engram_skill_shadow_behavior_preserved"] is True
    assert output["engram_skill_shadow_applied_to_answer"] is False


def test_exact_query_selects_exact_skill():
    module = load(SHADOW_PATH, "shadow_exact")
    result = {
        "query": "Where is P/N 120-41824-003 listed?",
        "route": "document_page_navigation",
        "content": "Best indexed location: page t_p_120_1176_p000084",
        "route_plan": {"retrieval_tunnels": ["document_page_navigation"]},
        "evidence_envelope": {"retrieval_tunnels_used": ["document_page_navigation"]},
        "follow_up_questions": [],
    }
    shadow = module.build_engram_skill_shadow(
        result,
        stage="offline_final_record",
        library_path=LIBRARY_PATH,
    )
    assert shadow["selected_skill_ids"][0] == "exact_identifier_lookup"
    assert shadow["expected_answer_modes"][0] == "direct_answer"


def test_runtime_installer_wraps_process_and_health_without_answer_change(monkeypatch):
    installer = load(INSTALLER_PATH, "shadow_installer")
    monkeypatch.setenv(
        "TRACE_NET_H30_ENGRAM_SKILL_CARDS_PATH",
        str(LIBRARY_PATH),
    )
    monkeypatch.setenv(
        "TRACE_NET_H30_ENGRAM_SKILL_SHADOW_ENABLED",
        "1",
    )

    class Runtime:
        def process(self, payload):
            return q001_result()

        def health(self):
            return {"quality_status": "PASS", "module": "fake_runtime"}

    namespace = {
        "Runtime": Runtime,
        "MODULE": "trace_net_full_gemma_cognitive_v1",
        "extract_latest_user": lambda payload: payload["query"],
    }
    installer.install_engram_skill_shadow(namespace)
    runtime = Runtime()
    output = runtime.process({"query": "I only know the part starts with 123"})
    assert output["content"] == q001_result()["content"]
    assert output["engram_skill_shadow"]["stage"] == "final_answer_writer"
    assert output["engram_skill_shadow_behavior_preserved"] is True
    health = runtime.health()
    assert health["quality_status"] == "PASS"
    assert health["engram_skill_shadow"]["quality_status"] == "PASS"
    assert health["engram_skill_shadow_changes_current_answer"] is False


def test_runtime_shadow_failure_is_fail_open(monkeypatch, tmp_path):
    installer = load(INSTALLER_PATH, "shadow_installer_fail")
    monkeypatch.setenv(
        "TRACE_NET_H30_ENGRAM_SKILL_CARDS_PATH",
        str(tmp_path / "missing.json"),
    )

    class CognitiveRuntime:
        def process(self, payload):
            return q001_result()

        def health(self):
            return {"quality_status": "PASS"}

    namespace = {
        "CognitiveRuntime": CognitiveRuntime,
        "MODULE": "trace_net_cognitive_router_v1",
        "extract_latest_user": lambda payload: payload["query"],
    }
    installer.install_engram_skill_shadow(namespace)
    output = CognitiveRuntime().process(
        {"query": "I only know the part starts with 123"}
    )
    assert output["content"] == q001_result()["content"]
    assert output["engram_skill_shadow"]["quality_status"] == "FAIL"
    assert output["engram_skill_shadow_behavior_preserved"] is True


def test_offline_report_builds_files(tmp_path):
    records = tmp_path / "records.jsonl"
    row = {
        "question_id": "q001",
        "category": "partial_part_prefix",
        "query": "I only know the part starts with 123",
        "actual_route": "guided_part_discovery",
        "answer": q001_result()["content"],
        "planned_tunnels": q001_result()["route_plan"]["retrieval_tunnels"],
        "used_tunnels": q001_result()["evidence_envelope"]["retrieval_tunnels_used"],
        "follow_up_questions": q001_result()["follow_up_questions"],
        "trace_net": q001_result(),
    }
    records.write_text(json.dumps(row) + "\n", encoding="utf-8")

    report = load(
        Path("scripts/build/engram/build_trace_net_engram_skill_shadow_report_v1.py"),
        "shadow_report",
    )
    output_dir = tmp_path / "out"
    code = report.main([
        str(records),
        "--skills",
        str(LIBRARY_PATH),
        "--output-dir",
        str(output_dir),
    ])
    assert code == 0
    text = (output_dir / "engram_skill_shadow_report.md").read_text(
        encoding="utf-8"
    )
    assert "partial_identifier_discovery" in text
    assert "generic_candidate_boilerplate" in text
    summary = json.loads(
        (output_dir / "engram_skill_shadow_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["quality_status"] == "PASS"
    assert summary["record_count"] == 1
