#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_opensearch_adapter_v1 import build_opensearch_documents
from tiff.trace_net_opensearch_adapter_lineage_guard_v1 import apply_lineage_guard


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild TRACE-Net OpenSearch Adapter v1, then apply lineage guard.")
    parser.add_argument("--embedding-candidates", required=True)
    parser.add_argument("--page-profiles")
    parser.add_argument("--table-cell-normalizer")
    parser.add_argument("--evidence-snippet-cleaner")
    parser.add_argument("--context-helpers")
    parser.add_argument("--leiden-communities")
    parser.add_argument("--graph-overlay-part-normalizer")
    parser.add_argument("--output-dir", default="local_data/organization/trace_net/opensearch_adapter")
    parser.add_argument("--index-name", default="trace_net_safe_search_v1")
    parser.add_argument("--min-documents", type=int, default=1)
    parser.add_argument("--min-page-scoped-documents", type=int, default=1)
    parser.add_argument("--require-mapping", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    initial = build_opensearch_documents(
        embedding_candidates_path=args.embedding_candidates,
        page_profiles_path=args.page_profiles,
        table_cell_normalizer_path=args.table_cell_normalizer,
        evidence_snippet_cleaner_path=args.evidence_snippet_cleaner,
        context_helpers_path=args.context_helpers,
        leiden_communities_path=args.leiden_communities,
        graph_overlay_part_normalizer_path=args.graph_overlay_part_normalizer,
        output_dir=args.output_dir,
        index_name=args.index_name,
        min_documents=args.min_documents,
        min_page_scoped_documents=args.min_page_scoped_documents,
        require_mapping=args.require_mapping or args.quality,
        write_quality=True,
    )
    report_path = Path(initial["paths"]["report_path"])
    guarded = apply_lineage_guard(
        adapter_report_path=report_path,
        output_dir=args.output_dir,
        min_documents=args.min_documents,
        min_page_scoped_documents=args.min_page_scoped_documents,
        require_mapping=args.require_mapping or args.quality,
    )
    s = guarded.get("summary") or {}
    print("TRACE-Net OpenSearch Adapter v1 lineage rebuild")
    print(" Quality status:", guarded.get("quality_status"))
    for key in (
        "opensearch_document_count",
        "page_scoped_document_count",
        "documents_with_search_text_count",
        "missing_page_id_count",
        "missing_source_trace_count",
        "lineage_guard_dropped_document_count",
        "unsafe_index_document_count",
        "raw_feedback_indexed_count",
        "raw_visual_output_indexed_count",
        "raw_ocr_unfiltered_indexed_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {s.get(key)}")
    print(" report_path:", guarded.get("paths", {}).get("report_path"))
    print(" quality_path:", guarded.get("paths", {}).get("quality_path"))
    return 0 if guarded.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
