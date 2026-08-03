import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/build/visual/build_trace_net_visual_question_context_adapter_v1_1.py"


def load_module():
    spec = importlib.util.spec_from_file_location("adapter_v1_1", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_canonical_page_id_rejects_bare_integer():
    m = load_module()
    assert m.CANONICAL_PAGE_ID_RE.fullmatch("t_p_120_1176_p000315")
    assert not m.CANONICAL_PAGE_ID_RE.fullmatch("315")
    assert not m.CANONICAL_PAGE_ID_RE.fullmatch("20")


def test_route_seed_blocks_unrelated_artifacts(tmp_path):
    m = load_module()
    artifact_root = tmp_path / "trace_net"
    route_dir = artifact_root / "page_route_manifest"
    route_dir.mkdir(parents=True)
    route_file = route_dir / "trace_net_page_route_manifest_v1_cards.jsonl"
    route_file.write_text(json.dumps({
        "page_id": "t_p_120_1176_p000315",
        "primary_route": "image_visual",
    }) + "\n", encoding="utf-8")

    good_dir = artifact_root / "llava_visual_summary_batch_v1"
    good_dir.mkdir()
    (good_dir / "good.jsonl").write_text(json.dumps({
        "page_id": "t_p_120_1176_p000315",
        "visual_id": "visual_1",
        "primary_object": "seat structure",
        "part_numbers": ["120-36833-001"],
    }) + "\n", encoding="utf-8")

    bad_dir = artifact_root / "page_context_v2"
    bad_dir.mkdir()
    (bad_dir / "bad.jsonl").write_text(
        json.dumps({"page_id": "315", "functional_description": "planner contamination"}) + "\n",
        encoding="utf-8",
    )

    pages, _ = m.discover_image_pages(artifact_root, route_file)
    contexts, metrics = m.build_contexts(artifact_root, tmp_path / "out", pages, None)
    assert pages == {"t_p_120_1176_p000315"}
    assert len(contexts) == 1
    assert contexts[0]["page_id"] == "t_p_120_1176_p000315"
    assert contexts[0]["object_description"]["primary_object"] == "seat structure"
    assert "planner contamination" not in json.dumps(contexts[0])
    assert metrics["rejected_noncanonical_page_id_count"] >= 1


def test_output_stays_candidate_only(tmp_path):
    m = load_module()
    artifact_root = tmp_path / "trace_net"
    route_dir = artifact_root / "page_route_manifest"
    route_dir.mkdir(parents=True)
    route_file = route_dir / "trace_net_page_route_manifest_v1_cards.jsonl"
    route_file.write_text(json.dumps({
        "page_id": "t_p_120_1176_p000001",
        "route": "image_visual",
    }) + "\n", encoding="utf-8")
    visual_dir = artifact_root / "image_visual_evidence_pack_v1"
    visual_dir.mkdir()
    (visual_dir / "record.json").write_text(json.dumps({
        "page_id": "t_p_120_1176_p000001",
        "visual_id": "v1",
        "citation_ready": True,
        "source_trace_ready": True,
    }), encoding="utf-8")

    pages, _ = m.discover_image_pages(artifact_root, route_file)
    contexts, _ = m.build_contexts(artifact_root, tmp_path / "out", pages, None)
    assert contexts[0]["evidence_status"]["final_answer_allowed"] is False
    assert contexts[0]["safety_contract"]["source_truth_mutation_allowed_count"] == 0
