from __future__ import annotations
import json
from pathlib import Path

from tiff.trace_net_engineering_engram_prompt_retrieval_smoke_v1 import (
    build_integration_records,
    build_prompt_retrieval_smoke_manifest,
    check_prompt_retrieval_smoke_manifest,
)


def _sample_prompt_injector():
    text = (
        "TRACE-NET ENGRAM RETRIEVAL GUIDANCE — BEHAVIOR ONLY, NOT PROOF\n"
        "Use these retrieved Engram atoms to shape answer behavior only. "
        "Do not use Engram memory as manual evidence. "
        "Manual/source claims still require current proof_context citations from TRACE-Net."
    )
    return {
        "quality_status": "PASS",
        "summary": {
            "answer_permission_count": 0,
            "write_attempt_count": 0,
            "unsafe_finding_count": 0,
            "qdrant_read_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
        },
        "prompt_bundles": [
            {
                "query_id": "q1",
                "task_type": "interchangeability_boundary",
                "selected_atom_count": 2,
                "selected_layers": ["procedural_memory", "trait_memory"],
                "selected_proof_roles": ["guidance_only"],
                "prompt_guidance_text": text,
            },
            {
                "query_id": "q2",
                "task_type": "unknown_part",
                "selected_atom_count": 1,
                "selected_layers": ["working_memory"],
                "selected_proof_roles": ["current_proof_context_only"],
                "prompt_guidance_text": text,
            },
        ],
    }


def test_build_records_preserves_boundaries():
    records = build_integration_records(_sample_prompt_injector(), max_prompt_chars=2000)
    assert len(records) == 2
    assert all(r["contains_behavior_only_boundary"] for r in records)
    assert all(not r["answer_permission"] for r in records)
    assert all(not r["write_attempt"] for r in records)
    assert all(not r["unsafe"] for r in records)


def test_manifest_passes_quality(tmp_path: Path):
    p = tmp_path / "h20.json"
    p.write_text(json.dumps(_sample_prompt_injector()), encoding="utf-8")
    manifest = build_prompt_retrieval_smoke_manifest(
        prompt_injector_path=p,
        output_dir=tmp_path / "out",
        min_queries=2,
        min_injected_atoms=3,
        require_quality_pass=True,
        require_guidance_only=True,
        require_no_answer_permission=True,
    )
    assert manifest["quality_status"] == "PASS"
    assert manifest["summary"]["selected_atom_count"] == 3
    assert Path(manifest["records_path"]).exists()


def test_checker_fails_disallowed_role(tmp_path: Path):
    src = _sample_prompt_injector()
    src["prompt_bundles"][0]["selected_proof_roles"] = ["manual_proof"]
    p = tmp_path / "h20.json"
    p.write_text(json.dumps(src), encoding="utf-8")
    manifest = build_prompt_retrieval_smoke_manifest(
        prompt_injector_path=p,
        output_dir=tmp_path / "out",
        min_queries=2,
        min_injected_atoms=3,
        require_quality_pass=True,
        require_guidance_only=True,
        require_no_answer_permission=True,
    )
    assert manifest["quality_status"] == "FAIL"
    result = check_prompt_retrieval_smoke_manifest(manifest, min_queries=2, min_injected_atoms=3, require_quality_pass=False)
    assert result["quality_status"] == "FAIL"


def test_prompt_compaction_keeps_budget(tmp_path: Path):
    src = _sample_prompt_injector()
    src["prompt_bundles"][0]["prompt_guidance_text"] += " X" * 1000
    p = tmp_path / "h20.json"
    p.write_text(json.dumps(src), encoding="utf-8")
    manifest = build_prompt_retrieval_smoke_manifest(
        prompt_injector_path=p,
        output_dir=tmp_path / "out",
        max_prompt_chars=600,
        min_queries=2,
        min_injected_atoms=3,
        require_quality_pass=True,
        require_guidance_only=True,
        require_no_answer_permission=True,
    )
    assert manifest["summary"]["max_observed_prompt_chars"] <= 600
