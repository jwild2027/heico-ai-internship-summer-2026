import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24 import (
    MODEL_ID,
    attach_quality,
    build_endpoint_state,
    evaluate_quality,
    write_endpoint_files,
)


def parse_args():
    p = argparse.ArgumentParser(description="Build TRACE-Net E2E Live WebUI Final-Gated Gemma Endpoint v24 artifact.")
    p.add_argument("--live-llm-final-gate", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8020)
    p.add_argument("--model-id", default=MODEL_ID)
    p.add_argument("--min-final-gates", type=int, default=5)
    p.add_argument("--min-ready-final-answers", type=int, default=5)
    p.add_argument("--min-endpoint-routes", type=int, default=4)
    p.add_argument("--min-final-answers-with-source-truth-citations", type=int, default=5)
    p.add_argument("--min-cap-disclosures-in-final-answers", type=int, default=3)
    p.add_argument("--max-unsupported-claim-count", type=int, default=0)
    p.add_argument("--max-final-non-direct-citation-marker-count", type=int, default=0)
    p.add_argument("--max-graph-proof-authority-violations", type=int, default=0)
    p.add_argument("--max-summary-proof-authority-violations", type=int, default=0)
    p.add_argument("--max-answer-permission-count", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--quality", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    state = build_endpoint_state(Path(args.live_llm_final_gate), host=args.host, port=args.port, model_id=args.model_id)
    quality_status, checks = evaluate_quality(
        state,
        min_final_gates=args.min_final_gates,
        min_ready_final_answers=args.min_ready_final_answers,
        min_endpoint_routes=args.min_endpoint_routes,
        min_final_answers_with_source_truth_citations=args.min_final_answers_with_source_truth_citations,
        min_cap_disclosures_in_final_answers=args.min_cap_disclosures_in_final_answers,
        max_unsupported_claim_count=args.max_unsupported_claim_count,
        max_final_non_direct_citation_marker_count=args.max_final_non_direct_citation_marker_count,
        max_graph_proof_authority_violations=args.max_graph_proof_authority_violations,
        max_summary_proof_authority_violations=args.max_summary_proof_authority_violations,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    attach_quality(state, quality_status, checks)
    paths = write_endpoint_files(state, Path(args.output_dir))

    print("TRACE-Net E2E Live WebUI Final-Gated Gemma Endpoint v24")
    print(f" Status: {state['status']}")
    print(f" Quality status: {state['quality_status']}")
    for key in [
        "final_gate_count",
        "final_answer_count",
        "ready_final_answer_count",
        "endpoint_route_count",
        "final_answers_with_source_truth_citations_count",
        "cap_disclosures_in_final_answers_count",
        "unsupported_claim_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
        "base_url_windows",
        "base_url_open_webui_docker",
    ]:
        print(f" {key}: {state.get(key)}")
    print(f" report_path: {paths['report_path']}")
    print(f" responses_jsonl_path: {paths['responses_jsonl_path']}")
    print(f" inspect_md_path: {paths['inspect_md_path']}")
    return 0 if quality_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
