import json
from pathlib import Path

from tiff.trace_net_route_label_taxonomy_v1 import build_route_label_taxonomy


def test_build_route_label_taxonomy(tmp_path):
    payload = build_route_label_taxonomy(tmp_path, quality=True)
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["canonical_route_label_count"] >= 9
    labels = {record["label"] for record in payload["records"]}
    assert "blank_candidate" in labels
    assert "cover_or_title_page" in labels
    assert "normal_text" in labels
    assert "procedure_or_description" in labels
    assert "table_or_index" in labels
    assert "detailed_parts_list" in labels
    assert "image_visual_diagram" in labels
    assert "mixed_text_and_figure" in labels
    assert "review_required" in labels
    assert (tmp_path / "trace_net_route_label_taxonomy_v1.json").exists()
    assert (tmp_path / "trace_net_route_label_taxonomy_v1_records.jsonl").exists()
    assert (tmp_path / "trace_net_route_label_taxonomy_v1.md").exists()


def test_legacy_aliases_split_coarse_routes(tmp_path):
    payload = build_route_label_taxonomy(tmp_path)
    aliases = payload["legacy_route_aliases"]
    assert aliases["table"]["migration_policy"] == "split_by_table_and_prose_validators"
    assert "detailed_parts_list" in aliases["table"]["canonical_candidates"]
    assert "procedure_or_description" in aliases["table"]["canonical_candidates"]
    assert aliases["image_visual"]["canonical_candidates"] == ["image_visual_diagram", "mixed_text_and_figure"]


def test_all_labels_are_non_answering_and_non_mutating(tmp_path):
    payload = build_route_label_taxonomy(tmp_path)
    for record in payload["records"]:
        assert record["answer_permission"] is False
        assert record["can_answer_directly"] is False
        assert record["can_prove_claims"] is False
        assert record["source_truth_mutation_allowed"] is False
