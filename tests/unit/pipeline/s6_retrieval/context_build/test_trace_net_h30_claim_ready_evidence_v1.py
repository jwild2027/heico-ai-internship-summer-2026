from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

CLAIM_PATH = Path("src/trace_net/pipeline/s6_retrieval/context_build/trace_net_h30_claim_ready_evidence_v1.py")
CHECK_PATH = Path("scripts/maintenance/s6_retrieval/check_trace_net_h30_claim_ready_evidence_v1.py")
MODE_PATH = Path("src/trace_net/writing/answer_modes/trace_net_h30_evidence_aware_answer_modes_v1.py")
WRITER_PATH = Path("scripts/operations/writing/serve_trace_net_full_gemma_cognitive_v1.py")


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def typed(
    record_id,
    bucket,
    index,
    *,
    candidate="",
    page="",
    claims=None,
    modality="textual_source",
    support=False,
    conflict=False,
    excerpt="",
):
    return {
        "record_id": record_id,
        "source_bucket": bucket,
        "source_index": index,
        "evidence_class": "direct_source" if bucket == "direct_evidence" else "candidate_guidance",
        "modality": modality,
        "authority_class": "direct_source_record" if support else "guidance_candidate",
        "proof_status": "claim_supporting_direct" if support else "guidance_only",
        "resolution_status": "resolved_source" if support else "candidate_unresolved",
        "claim_types": list(claims or []),
        "claim_support_allowed": support,
        "final_answer_eligible": support,
        "guidance_only": not support,
        "conflicted": conflict,
        "source_trace": {"page_id": page, "ready": support},
        "identity": {
            "candidate": candidate,
            "part_numbers": [candidate] if candidate else [],
            "ata": "",
            "figure_refs": [],
            "item": "",
        },
        "excerpt": excerpt or candidate,
    }


def result(route, atoms, envelope, records):
    return {
        "route": route,
        "query_atoms": copy.deepcopy(atoms),
        "evidence_envelope": copy.deepcopy(envelope),
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }, {
        "records": copy.deepcopy(records),
        "coverage": {},
        "validation": {"quality_status": "PASS"},
        "contract": {},
        "schema_version": "trace_net_typed_evidence_envelope_v1",
    }


def test_exact_part_drops_unrelated_typed_record():
    mod = load(CLAIM_PATH, "claim_ready_exact")
    envelope = {
        "direct_evidence": [],
        "candidate_evidence": [
            {"candidate_value": "120-20970-001", "nomenclature": ["STRUCTURE ARMREST"]},
            {"candidate_value": "120-29068-025", "nomenclature": ["STRUCTURE ASSEMBLY"]},
        ],
        "visual_guidance": [],
        "semantic_guidance": [],
        "contradictions": [],
        "source_resolution": [],
        "authority_evidence": [],
    }
    records = [
        typed("a", "candidate_evidence", 0, candidate="120-20970-001", claims=["part_identity"]),
        typed("b", "candidate_evidence", 1, candidate="120-29068-025", claims=["part_identity"]),
    ]
    sample, view = result(
        "exact_identifier_lookup",
        {"identifier_mode": "exact", "exact_part_numbers": ["120-20970-001"]},
        envelope,
        records,
    )
    out = mod.build_claim_ready_evidence(sample, typed_view=view)
    assert out["quality_status"] == "PASS"
    assert [row["record_id"] for row in out["records"]] == ["a"]
    assert out["by_bucket"]["candidate_evidence"] == [envelope["candidate_evidence"][0]]
    assert len(sample["evidence_envelope"]["candidate_evidence"]) == 2


def test_partial_contains_keeps_only_matching_candidates():
    mod = load(CLAIM_PATH, "claim_ready_partial")
    envelope = {
        "direct_evidence": [],
        "candidate_evidence": [
            {"candidate_value": "120-29067-001"},
            {"candidate_value": "120-48024-001"},
        ],
        "visual_guidance": [],
        "semantic_guidance": [],
        "contradictions": [],
        "source_resolution": [],
        "authority_evidence": [],
    }
    records = [
        typed("a", "candidate_evidence", 0, candidate="120-29067-001", claims=["part_identity"]),
        typed("b", "candidate_evidence", 1, candidate="120-48024-001", claims=["part_identity"]),
    ]
    sample, view = result(
        "guided_part_discovery",
        {"identifier_mode": "contains", "part_contains": "29067"},
        envelope,
        records,
    )
    out = mod.build_claim_ready_evidence(sample, typed_view=view)
    assert [row["record_id"] for row in out["records"]] == ["a"]
    assert out["coverage"]["rejected_reason_counts"]["partial_identifier_mismatch"] == 1


def test_nomenclature_requires_requested_noun():
    mod = load(CLAIM_PATH, "claim_ready_nomenclature")
    envelope = {
        "direct_evidence": [],
        "candidate_evidence": [
            {"candidate_value": "120-48024-001", "nomenclature": ["RING, LOCKING"]},
            {"candidate_value": "120-29068-025", "nomenclature": ["STRUCTURE, ASSY"]},
        ],
        "visual_guidance": [],
        "semantic_guidance": [],
        "contradictions": [],
        "source_resolution": [],
        "authority_evidence": [],
    }
    records = [
        typed("ring", "candidate_evidence", 0, candidate="120-48024-001", claims=["nomenclature"]),
        typed("assy", "candidate_evidence", 1, candidate="120-29068-025", claims=["nomenclature"]),
    ]
    sample, view = result(
        "nomenclature_function_search",
        {"nomenclature_terms": ["ring"]},
        envelope,
        records,
    )
    out = mod.build_claim_ready_evidence(sample, typed_view=view)
    assert [row["record_id"] for row in out["records"]] == ["ring"]
    assert out["coverage"]["rejected_reason_counts"]["nomenclature_term_mismatch"] == 1


def test_visual_route_requires_requested_page():
    mod = load(CLAIM_PATH, "claim_ready_visual")
    envelope = {
        "direct_evidence": [],
        "candidate_evidence": [],
        "visual_guidance": [
            {"page_id": "t_p_120_1176_p000018", "subject": "Seat backrest"},
            {"page_id": "t_p_120_1176_p000081", "subject": "Single passenger seat"},
        ],
        "semantic_guidance": [],
        "contradictions": [],
        "source_resolution": [],
        "authority_evidence": [],
    }
    records = [
        typed("p18", "visual_guidance", 0, page="t_p_120_1176_p000018", claims=["figure_callout"], modality="visual"),
        typed("p81", "visual_guidance", 1, page="t_p_120_1176_p000081", claims=["figure_callout"], modality="visual"),
    ]
    sample, view = result(
        "visual_figure_callout_lookup",
        {"page_ids": ["t_p_120_1176_p000081"]},
        envelope,
        records,
    )
    out = mod.build_claim_ready_evidence(sample, typed_view=view)
    assert [row["record_id"] for row in out["records"]] == ["p81"]


def test_graph_route_keeps_entity_but_does_not_promote_guidance():
    mod = load(CLAIM_PATH, "claim_ready_graph")
    envelope = {
        "direct_evidence": [],
        "candidate_evidence": [],
        "visual_guidance": [],
        "semantic_guidance": [
            {"candidate_value": "120-20970-001", "relationship": "APPEARS_ON"},
            {"candidate_value": "120-29068-025", "relationship": "APPEARS_ON"},
        ],
        "contradictions": [],
        "source_resolution": [],
        "authority_evidence": [],
    }
    records = [
        typed("wanted", "semantic_guidance", 0, candidate="120-20970-001", claims=["assembly_relationship"], modality="graph"),
        typed("other", "semantic_guidance", 1, candidate="120-29068-025", claims=["assembly_relationship"], modality="graph"),
    ]
    sample, view = result(
        "graph_relationship_reasoning",
        {"identifier_mode": "exact", "exact_part_numbers": ["120-20970-001"]},
        envelope,
        records,
    )
    out = mod.build_claim_ready_evidence(sample, typed_view=view)
    assert [row["record_id"] for row in out["records"]] == ["wanted"]
    assert out["records"][0]["guidance_only"] is True
    assert out["records"][0]["claim_support_allowed"] is False


def test_install_rebuilds_typed_view_after_final_enrichment(monkeypatch):
    mod = load(CLAIM_PATH, "claim_ready_install")
    monkeypatch.setenv("TRACE_NET_H30_CLAIM_READY_EVIDENCE_ENABLED", "1")
    base = {
        "route": "exact_identifier_lookup",
        "query_atoms": {"identifier_mode": "exact", "exact_part_numbers": ["120-20970-001"]},
        "evidence_envelope": {
            "direct_evidence": [],
            "candidate_evidence": [{"candidate_value": "120-20970-001"}],
            "visual_guidance": [],
            "semantic_guidance": [],
            "contradictions": [],
            "source_resolution": [],
            "authority_evidence": [],
            "typed_evidence": [{"record_id": "stale"}],
        },
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }
    fresh = {
        "records": [
            typed("fresh", "candidate_evidence", 0, candidate="120-20970-001", claims=["part_identity"])
        ],
        "coverage": {"typed_record_count": 1},
        "validation": {"quality_status": "PASS"},
        "contract": {},
    }
    monkeypatch.setattr(mod, "_rebuild_typed_view", lambda envelope, route: copy.deepcopy(fresh))

    class Runtime:
        def process(self, payload):
            return copy.deepcopy(base)

        def health(self):
            return {"quality_status": "PASS"}

    namespace = {"CognitiveRuntime": Runtime}
    mod.install_claim_ready_evidence(namespace)
    out = Runtime().process({})
    assert out["evidence_envelope"]["typed_evidence"][0]["record_id"] == "fresh"
    selected = out["evidence_envelope"]["claim_ready_evidence"]
    assert selected["typed_view_rebuilt_after_final_enrichment"]
    assert selected["validation"]["legacy_evidence_preserved"]
    assert out["evidence_envelope"]["candidate_evidence"] == base["evidence_envelope"]["candidate_evidence"]


def test_answer_modes_prefers_claim_ready_records():
    modes = load(MODE_PATH, "claim_ready_modes_consumer")
    legacy = typed("legacy", "candidate_evidence", 0, candidate="120-29068-025", claims=["part_identity"])
    selected = typed("selected", "candidate_evidence", 1, candidate="120-20970-001", claims=["part_identity"])
    sample = {
        "evidence_envelope": {
            "typed_evidence": [legacy, selected],
            "claim_ready_evidence": {
                "quality_status": "PASS",
                "records": [selected],
            },
        }
    }
    assert [row["record_id"] for row in modes.typed_records(sample)] == ["selected"]
    assert modes.typed_record_source(sample) == "claim_ready_evidence"


def test_writer_prefers_claim_ready_raw_buckets():
    writer = load(WRITER_PATH, "claim_ready_writer_consumer")
    sample = {
        "evidence_envelope": {
            "candidate_evidence": [
                {"candidate_value": "120-29068-025"},
                {"candidate_value": "120-20970-001"},
            ],
            "claim_ready_evidence": {
                "quality_status": "PASS",
                "by_bucket": {
                    "candidate_evidence": [{"candidate_value": "120-20970-001"}],
                    "direct_evidence": [],
                    "visual_guidance": [],
                    "semantic_guidance": [],
                    "source_resolution": [],
                    "authority_evidence": [],
                },
            },
        }
    }
    assert writer.candidate_evidence(sample) == [{"candidate_value": "120-20970-001"}]
    assert writer.claim_ready_evidence_available(sample) is True


def test_checker_accepts_clean_fake_run(tmp_path):
    checker = load(CHECK_PATH, "claim_ready_checker_clean")
    payload = {
        "evaluation": {
            "question_id": "q01",
            "post_validation_accepted": True,
        },
        "raw_response": {
            "trace_net": {
                "route": "exact_identifier_lookup",
                "answer_mode": {"typed_record_source": "claim_ready_evidence"},
                "evidence_envelope": {
                    "claim_ready_evidence": {
                        "quality_status": "PASS",
                        "typed_view_rebuilt_after_final_enrichment": True,
                        "coverage": {
                            "complete_typed_record_count": 3,
                            "selected_record_count": 1,
                            "complete_typed_audit_preserved": True,
                        },
                        "validation": {
                            "quality_status": "PASS",
                            "legacy_evidence_preserved": True,
                        },
                    }
                },
            }
        },
    }
    (tmp_path / "01_q01_exact_part.json").write_text(json.dumps(payload), encoding="utf-8")
    report = checker.inspect_run(tmp_path)
    assert report["quality_status"] == "PASS"
    assert report["passed_record_count"] == 1


def test_checker_rejects_missing_selector(tmp_path):
    checker = load(CHECK_PATH, "claim_ready_checker_bad")
    payload = {
        "evaluation": {
            "question_id": "q01",
            "post_validation_accepted": True,
        },
        "raw_response": {
            "trace_net": {
                "route": "exact_identifier_lookup",
                "answer_mode": {},
                "evidence_envelope": {},
            }
        },
    }
    (tmp_path / "01_q01_exact_part.json").write_text(json.dumps(payload), encoding="utf-8")
    report = checker.inspect_run(tmp_path)
    assert report["quality_status"] == "FAIL"
    assert report["missing_claim_ready_count"] == 1


def test_phase2_runtime_wiring_is_present():
    router = Path("scripts/operations/s6_retrieval/serve_trace_net_cognitive_router_v1.py").read_text(encoding="utf-8")
    modes = MODE_PATH.read_text(encoding="utf-8")
    writer = WRITER_PATH.read_text(encoding="utf-8")
    launcher = Path("scripts/operations/launch_trace_net_cognitive_openwebui_v1.sh").read_text(encoding="utf-8")
    assert "install_claim_ready_evidence" in router
    assert "typed_record_source" in modes
    assert "claim_ready_evidence_available" in writer
    assert "TRACE_NET_H30_CLAIM_READY_EVIDENCE_ENABLED" in launcher
    assert "test_trace_net_h30_claim_ready_evidence_v1.py" in launcher
