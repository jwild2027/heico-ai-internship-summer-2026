from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_opensearch_adapter_v1 import quality_report, write_json


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net OpenSearch Adapter v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-documents", type=int, default=1)
    parser.add_argument("--min-page-scoped-documents", type=int, default=1)
    parser.add_argument("--require-mapping", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    path = Path(args.report_path)
    report = json.loads(path.read_text(encoding="utf-8"))
    quality = quality_report(
        report,
        min_documents=args.min_documents,
        min_page_scoped_documents=args.min_page_scoped_documents,
        require_mapping=args.require_mapping,
    )
    if args.write_json:
        quality_path = path.with_name("trace_net_opensearch_adapter_v1_quality.json")
        write_json(quality_path, quality)
        report["quality"] = quality
        report["quality_status"] = quality["status"]
        write_json(path, report)
    summary = quality.get("summary") or {}
    print("TRACE-Net OpenSearch Adapter v1 quality")
    print(f" Status: {quality['status']}")
    for key in [
        "opensearch_document_count",
        "page_scoped_document_count",
        "missing_page_id_count",
        "missing_source_trace_count",
        "unsafe_index_document_count",
        "raw_feedback_indexed_count",
        "raw_visual_output_indexed_count",
        "raw_ocr_unfiltered_indexed_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    if args.write_json:
        print(f" quality_path: {path.with_name('trace_net_opensearch_adapter_v1_quality.json')}")
    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
