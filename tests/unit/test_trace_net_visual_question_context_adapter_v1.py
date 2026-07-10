from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build_trace_net_visual_question_context_adapter_v1.py"


def load_module():
    spec = importlib.util.spec_from_file_location("trace_net_visual_question_context_adapter_v1", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_context_joins_existing_artifacts_and_preserves_provenance(tmp_path):
    module = load_module()
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    (artifact_root / "llava.json").write_text(json.dumps({
        "page_id": "p001", "visual_id": "v1", "primary_object": "locking ring",
        "physical_description": "Circular retaining component", "vision_text": "120-48024-001",
        "part_numbers": ["120-48024-001"], "ata_number": "25-21-00"
    }), encoding="utf-8")
    (artifact_root / "ocr.json").write_text(json.dumps({
        "page_id": "p001", "ocr_text": "120-48024-001", "ocr_agreement": "exact_agreement",
        "citation_ready": True, "source_trace_ready": True
    }), encoding="utf-8")
    (artifact_root / "context.json").write_text(json.dumps({
        "page_id": "p001", "page_context_v2": "Illustrated parts page for a seat assembly"
    }), encoding="utf-8")

    grouped, _, _ = module.discover_records(artifact_root)
    context = module.build_context("p001", grouped["p001"])
    assert context["object_description"]["primary_object"] == "locking ring"
    assert context["identifiers"]["part_numbers"] == ["120-48024-001"]
    assert context["identifiers"]["ata_numbers"] == ["25-21-00"]
    assert context["ocr_vision_reconciliation"]["agreement_status"] == "exact_agreement"
    assert context["page_context_v2"].startswith("Illustrated parts page")
    assert len(context["source_artifact_refs"]) == 3
    assert context["field_provenance"]["part_numbers"]
    assert context["evidence_status"]["final_answer_allowed"] is False


def test_defaults_remain_candidate_only_and_read_only(tmp_path):
    module = load_module()
    source = module.SourceRecord("visual.json", 0, {"page_id": "p002", "description": "Unclear bracket"})
    context = module.build_context("p002", [source])
    assert context["evidence_status"]["proof_status"] == "candidate_only"
    assert context["evidence_status"]["candidate_only"] is True
    assert context["evidence_status"]["citation_ready"] is False
    assert context["safety_contract"]["read_only"] is True
    assert context["safety_contract"]["source_truth_mutation_allowed_count"] == 0
    assert context["safety_contract"]["answer_permission_count"] == 0
