from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_engineering_real_answer_smoke_test_v1 import check_real_answer_smoke_test


def main() -> int:
    p = argparse.ArgumentParser(description="Check TRACE-Net engineering real-answer smoke test v1")
    p.add_argument("--smoke-test", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--min-smoke-questions", type=int, default=1)
    p.add_argument("--min-good-answers", type=int, default=1)
    p.add_argument("--min-good-or-partial-answers", type=int, default=1)
    p.add_argument("--max-bad-answers", type=int, default=0)
    p.add_argument("--max-unsupported-claims", type=int, default=0)
    p.add_argument("--max-summary-used-as-proof", type=int, default=0)
    p.add_argument("--max-invalid-citations", type=int, default=0)
    p.add_argument("--max-llava-only-part-identity-claims", type=int, default=0)
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-answer-permission", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    a = p.parse_args()
    result = check_real_answer_smoke_test(
        manifest=a.smoke_test,
        output=a.output,
        require_quality_pass=a.require_quality_pass,
        min_smoke_questions=a.min_smoke_questions,
        min_good_answers=a.min_good_answers,
        min_good_or_partial_answers=a.min_good_or_partial_answers,
        max_bad_answers=a.max_bad_answers,
        max_unsupported_claims=a.max_unsupported_claims,
        max_summary_used_as_proof=a.max_summary_used_as_proof,
        max_invalid_citations=a.max_invalid_citations,
        max_llava_only_part_identity_claims=a.max_llava_only_part_identity_claims,
        max_unsafe=a.max_unsafe,
        max_answer_permission=a.max_answer_permission,
        max_source_truth_mutation_allowed=a.max_source_truth_mutation_allowed,
        max_write_attempts=a.max_write_attempts,
    )
    s = result.get("summary", {})
    print("status=" + result["status"])
    print("quality_status=" + result["quality_status"])
    for k in ["smoke_question_count", "good_answer_count", "partial_answer_count", "bad_answer_count", "blocked_answer_count", "unsupported_claim_count", "summary_used_as_proof_count"]:
        print(f"{k}={s.get(k)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
