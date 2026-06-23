#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_e2e_dynamic_query_endpoint_v1 import build_manifest


def main() -> int:
    ap = argparse.ArgumentParser(description="Build TRACE-Net E2E dynamic query endpoint manifest v1")
    ap.add_argument("--table-exact-search-adapter", type=Path, required=True)
    ap.add_argument("--table-hybrid-retrieval-bridge", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--min-exact-search-documents", type=int, default=1000)
    ap.add_argument("--min-bridge-records", type=int, default=1000)
    ap.add_argument("--min-field-count", type=int, default=3)
    ap.add_argument("--quality", action="store_true")
    args = ap.parse_args()
    manifest = build_manifest(
        args.table_exact_search_adapter,
        args.table_hybrid_retrieval_bridge,
        args.output_dir,
        min_exact_search_documents=args.min_exact_search_documents,
        min_bridge_records=args.min_bridge_records,
        min_field_count=args.min_field_count,
        quality=args.quality,
    )
    s = manifest["summary"]
    print("TRACE-Net E2E Dynamic Query Endpoint v1")
    print(" Status:", manifest["status"])
    print(" Quality status:", manifest["quality_status"])
    print(" e2e_dynamic_query_endpoint_status:", manifest["e2e_dynamic_query_endpoint_status"])
    for key in [
        "table_exact_search_document_count",
        "table_hybrid_bridge_record_count",
        "dynamic_search_document_count",
        "page_with_dynamic_search_document_count",
        "field_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "opensearch_upload_attempt_count",
    ]:
        print(f" {key}:", s.get(key))
    print(" report_path:", manifest.get("report_path"))
    print(" inspect_md_path:", manifest.get("inspect_md_path"))
    return 0 if manifest["quality_status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
