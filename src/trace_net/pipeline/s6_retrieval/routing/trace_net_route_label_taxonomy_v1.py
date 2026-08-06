"""TRACE-Net route label taxonomy v1.

This module defines the page-route labels used by the OCR/router accuracy loop.
It is intentionally non-mutating: it only writes local JSON/JSONL/Markdown artifacts.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

MODULE = "trace_net_route_label_taxonomy_v1"
VERSION = "v1"
STATUS = "TRACE_NET_ROUTE_LABEL_TAXONOMY_BUILT"


@dataclass(frozen=True)
class RouteLabel:
    label: str
    display_name: str
    family: str
    definition: str
    positive_signals: List[str]
    negative_signals: List[str]
    required_validator_checks: List[str]
    default_processor_contract: str
    qdrant_embedding_policy: str
    postgres_graph_policy: str
    exact_search_policy: str
    review_policy: str
    answer_permission: bool = False
    source_truth_mutation_allowed: bool = False
    can_answer_directly: bool = False
    can_prove_claims: bool = False


ROUTE_LABELS: List[RouteLabel] = [
    RouteLabel(
        label="blank_candidate",
        display_name="Blank candidate",
        family="blank_or_sparse",
        definition="A page with empty or near-empty OCR and low visual/ink signal. It is not source-truth blank until confirmed.",
        positive_signals=["empty_ocr", "low_ink_density", "few_connected_components", "no_part_numbers", "no_table_headers"],
        negative_signals=["paragraph_text", "part_number_tokens", "figure_caption", "table_headers", "dense_ink"],
        required_validator_checks=["ocr_empty_or_near_empty", "low_ink_or_sparse_layout", "no_critical_entities_detected"],
        default_processor_contract="blank_candidate_confirmation_scan",
        qdrant_embedding_policy="do_not_embed_blank_candidates",
        postgres_graph_policy="store_page_node_with_blank_candidate_status_and_review_flag",
        exact_search_policy="do_not_index_as_evidence",
        review_policy="human_confirm_blank_before_source_truth_blank",
    ),
    RouteLabel(
        label="cover_or_title_page",
        display_name="Cover or title page",
        family="front_matter",
        definition="A cover, title, revision title, or publication identity page. Usually dense text but not a table/evidence table.",
        positive_signals=["manual_title", "publication_number", "revision_date", "manufacturer_name", "cover_layout"],
        negative_signals=["many_part_numbers", "row_column_grid", "vendor_code_column", "figure_callouts", "procedure_steps"],
        required_validator_checks=["publication_identity_present", "low_table_row_repetition", "not_many_part_numbers"],
        default_processor_contract="front_matter_identity_scan",
        qdrant_embedding_policy="embed_short_publication_identity_summary_only",
        postgres_graph_policy="store_document_identity_edges_and_page_node",
        exact_search_policy="index_publication_ids_dates_and_revision_identifiers",
        review_policy="review_if_confused_with_table_or_revision_record",
    ),
    RouteLabel(
        label="normal_text",
        display_name="Normal text",
        family="text",
        definition="Narrative, explanatory, introductory, service, maintenance, or ordinary manual prose without dominant procedure or table structure.",
        positive_signals=["paragraph_density", "section_headings", "sentences", "low_part_number_density"],
        negative_signals=["many_column_headers", "many_part_numbers", "figure_caption_with_labels", "blank_ocr"],
        required_validator_checks=["paragraph_text_present", "not_table_dominant", "not_visual_diagram_dominant"],
        default_processor_contract="normal_text_page_context_scan",
        qdrant_embedding_policy="embed_ocr_chunks_and_page_context_summary",
        postgres_graph_policy="store_page_text_node_entities_and_section_edges",
        exact_search_policy="index_named_entities_section_titles_and_page_refs",
        review_policy="review_if_table_or_figure_signals_tie_with_text_signals",
    ),
    RouteLabel(
        label="procedure_or_description",
        display_name="Procedure or description",
        family="text",
        definition="Description, operation, removal, installation, cleaning, inspection, repair, or other procedural/prose page.",
        positive_signals=["description_and_operation", "general_heading", "removal", "installation", "inspection", "repair", "step_numbering"],
        negative_signals=["many_part_numbers", "detailed_parts_list_headers", "mostly_diagram_labels", "blank_ocr"],
        required_validator_checks=["procedure_or_description_heading_present", "paragraph_or_step_text_present", "not_detailed_parts_list"],
        default_processor_contract="procedure_description_context_scan",
        qdrant_embedding_policy="embed_procedure_chunks_with_strong_page_trace",
        postgres_graph_policy="store_procedure_nodes_steps_warnings_and_page_edges",
        exact_search_policy="index_task_titles_warnings_cautions_and_references",
        review_policy="review_if_safety_warning_or_table_like_layout_is_uncertain",
    ),
    RouteLabel(
        label="table_or_index",
        display_name="Table or index",
        family="structured_text",
        definition="Structured list, index, LEP, contents, vendor list, numerical index, or repeated row/column table that is not specifically a detailed parts list.",
        positive_signals=["row_column_layout", "table_headers", "page_date_columns", "index_sequence", "vendor_code", "repeated_rows"],
        negative_signals=["cover_title_only", "paragraph_dominant", "diagram_callouts", "blank_ocr"],
        required_validator_checks=["repeated_row_or_column_structure", "table_header_or_index_signal", "not_header_only_illustrated_parts_list"],
        default_processor_contract="table_ocr_table_candidate_scan",
        qdrant_embedding_policy="embed_table_summary_or_evidence_cards_only_not_raw_table_blob",
        postgres_graph_policy="store_table_node_rows_columns_cells_and_page_edges",
        exact_search_policy="index_exact_table_values_identifiers_and_page_refs",
        review_policy="review_if_header_only_or_prose_dominant",
    ),
    RouteLabel(
        label="detailed_parts_list",
        display_name="Detailed parts list",
        family="structured_text",
        definition="Illustrated/detailed parts list page with item numbers, part numbers, nomenclature, units-per-assembly, figure-item references, or equivalent IPL structure.",
        positive_signals=["part_number_density", "fig_item_column", "nomenclature_column", "units_per_assy", "vendor_code", "airline_part_number", "detailed_parts_list"],
        negative_signals=["few_or_no_part_numbers", "description_operation_prose", "figure_diagram_only", "blank_ocr"],
        required_validator_checks=["part_number_or_ipl_column_signal", "structured_row_signal", "nomenclature_or_units_signal"],
        default_processor_contract="detailed_parts_list_extraction_scan",
        qdrant_embedding_policy="embed_extracted_part_evidence_cards_and_summaries",
        postgres_graph_policy="store_part_nodes_item_edges_table_cells_and_source_page_edges",
        exact_search_policy="index_part_numbers_item_numbers_nomenclature_and_source_refs",
        review_policy="review_if_part_numbers_missing_or_column_boundaries_uncertain",
    ),
    RouteLabel(
        label="image_visual_diagram",
        display_name="Image visual diagram",
        family="visual",
        definition="Diagram, figure, callout illustration, exploded view, or labeled technical drawing requiring image/vision handling plus OCR support.",
        positive_signals=["figure_caption", "callout_labels", "leader_lines", "visual_label_text", "limited_paragraph_text", "diagram_ink_distribution"],
        negative_signals=["dense_table_rows", "many_part_numbers_in_table", "paragraph_dominant", "blank_ocr"],
        required_validator_checks=["figure_or_diagram_signal", "visual_layout_signal", "ocr_label_or_callout_support"],
        default_processor_contract="image_visual_ocr_and_vision_queue_scan",
        qdrant_embedding_policy="embed_only_ocr_supported_visual_context_cards",
        postgres_graph_policy="store_visual_card_nodes_callouts_labels_and_page_edges",
        exact_search_policy="index_ocr_supported_figure_numbers_labels_and_callouts",
        review_policy="review_raw_vision_output_before_webui_use_unless_ocr_supported",
    ),
    RouteLabel(
        label="mixed_text_and_figure",
        display_name="Mixed text and figure",
        family="mixed",
        definition="Page containing both meaningful prose/procedure content and a figure/diagram or visual region where both routes may be useful.",
        positive_signals=["paragraph_text_present", "figure_caption_present", "diagram_or_callout_region", "moderate_ocr_text"],
        negative_signals=["blank_ocr", "pure_table_rows", "pure_cover_title"],
        required_validator_checks=["text_signal_present", "visual_signal_present", "route_split_recommended"],
        default_processor_contract="mixed_text_visual_split_scan",
        qdrant_embedding_policy="embed_text_summary_and_ocr_supported_visual_context_separately",
        postgres_graph_policy="store_page_node_with_text_region_and_visual_region_edges",
        exact_search_policy="index_source_refs_figure_labels_and_text_entities",
        review_policy="review_region_split_if_downstream_evidence_depends_on_visual_claims",
    ),
    RouteLabel(
        label="review_required",
        display_name="Review required",
        family="review",
        definition="Fallback for low-confidence, conflicting, corrupted, OCR-failed, route-tied, or safety-sensitive pages.",
        positive_signals=["conflicting_route_scores", "ocr_error", "low_confidence", "high_value_uncertainty", "corrupt_image"],
        negative_signals=["high_confidence_single_route"],
        required_validator_checks=["review_reason_present", "no_answer_permission", "source_trace_present"],
        default_processor_contract="human_review_route_resolution_scan",
        qdrant_embedding_policy="do_not_embed_as_normal_context_until_reviewed",
        postgres_graph_policy="store_review_task_edges_and_source_page_node",
        exact_search_policy="index_only_review_metadata_not_claim_evidence",
        review_policy="human_or_policy_review_required_before_downstream_route_commit",
    ),
]

LEGACY_ROUTE_ALIASES: Dict[str, Dict[str, Any]] = {
    "blank_candidate": {"canonical_candidates": ["blank_candidate"], "migration_policy": "direct"},
    "normal_text": {"canonical_candidates": ["normal_text", "procedure_or_description", "cover_or_title_page"], "migration_policy": "split_by_text_features"},
    "table": {"canonical_candidates": ["table_or_index", "detailed_parts_list", "procedure_or_description", "cover_or_title_page"], "migration_policy": "split_by_table_and_prose_validators"},
    "image_visual": {"canonical_candidates": ["image_visual_diagram", "mixed_text_and_figure"], "migration_policy": "split_by_visual_and_text_region_validators"},
    "review_required": {"canonical_candidates": ["review_required"], "migration_policy": "direct"},
}

ROUTE_FAMILIES: Dict[str, str] = {label.label: label.family for label in ROUTE_LABELS}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = payload.get("summary") or {}
    labels = payload.get("records") or []
    lines = [
        "# TRACE-Net Route Label Taxonomy v1",
        "",
        "This artifact locks the canonical page route labels used by OCR/router accuracy work.",
        "",
        "## Summary",
        "",
    ]
    for key in sorted(summary):
        lines.append(f"- **{key}**: {summary[key]}")
    lines.extend(["", "## Labels", ""])
    for label in labels:
        lines.append(f"### {label['label']}")
        lines.append("")
        lines.append(label["definition"])
        lines.append("")
        lines.append(f"- family: `{label['family']}`")
        lines.append(f"- processor: `{label['default_processor_contract']}`")
        lines.append(f"- qdrant policy: `{label['qdrant_embedding_policy']}`")
        lines.append(f"- review policy: `{label['review_policy']}`")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _summarize(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    families: Dict[str, int] = {}
    for record in records:
        families[record["family"]] = families.get(record["family"], 0) + 1
    return {
        "module": MODULE,
        "version": VERSION,
        "canonical_route_label_count": len(records),
        "route_family_counts": families,
        "legacy_route_alias_count": len(LEGACY_ROUTE_ALIASES),
        "answer_permission_count": sum(1 for record in records if record.get("answer_permission")),
        "can_answer_directly_count": sum(1 for record in records if record.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for record in records if record.get("can_prove_claims")),
        "source_truth_mutation_allowed_count": sum(1 for record in records if record.get("source_truth_mutation_allowed")),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "unsafe_record_count": 0,
        "ready_for_gold_label_review_workbook": True,
    }


def _quality_status(summary: Mapping[str, Any]) -> str:
    if summary.get("canonical_route_label_count", 0) < 9:
        return "FAIL"
    safety_keys = [
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "unsafe_record_count",
    ]
    if any(summary.get(key, 0) != 0 for key in safety_keys):
        return "FAIL"
    return "PASS"


def build_route_label_taxonomy(output_dir: Path | str, *, quality: bool = False) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    records = [asdict(route) for route in ROUTE_LABELS]
    summary = _summarize(records)
    payload: Dict[str, Any] = {
        "status": STATUS,
        "quality_status": _quality_status(summary),
        "module": MODULE,
        "version": VERSION,
        "summary": summary,
        "records": records,
        "legacy_route_aliases": LEGACY_ROUTE_ALIASES,
        "route_families": ROUTE_FAMILIES,
        "safety_contract": {
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "postgres_write_allowed": False,
            "qdrant_write_allowed": False,
            "opensearch_write_allowed": False,
        },
    }

    report_path = output_dir / "trace_net_route_label_taxonomy_v1.json"
    _write_json(report_path, payload)
    _write_jsonl(output_dir / "trace_net_route_label_taxonomy_v1_records.jsonl", records)
    _write_json(output_dir / "trace_net_route_label_taxonomy_v1_summary.json", summary)
    _write_markdown(output_dir / "trace_net_route_label_taxonomy_v1.md", payload)
    if quality:
        _write_json(output_dir / "trace_net_route_label_taxonomy_v1_quality_check.json", payload)
    return payload


def main_build(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Build TRACE-Net route label taxonomy v1")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    payload = build_route_label_taxonomy(args.output_dir, quality=args.quality)
    print(f"Status: {payload['status']}")
    print(f"Quality status: {payload['quality_status']}")
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    return payload


if __name__ == "__main__":
    main_build()
