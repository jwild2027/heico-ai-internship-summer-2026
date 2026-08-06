from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_engineering_engram_prompt_retrieval_llm_smoke_v1 import check_prompt_retrieval_llm_smoke

def main() -> int:
    p = argparse.ArgumentParser(description="Check TRACE-Net H22 Engram prompt retrieval LLM smoke.")
    p.add_argument("--llm-smoke", required=True)
    p.add_argument("--min-queries", type=int, default=1)
    p.add_argument("--min-llm-answered", type=int, default=1)
    p.add_argument("--min-good-answers", type=int, default=1)
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--max-bad-answers", type=int, default=0)
    p.add_argument("--max-unsupported-claims", type=int, default=0)
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    args = p.parse_args()
    result = check_prompt_retrieval_llm_smoke(**vars(args))
    s = result.get("summary", {})
    print(f"status={result.get('status')}")
    print(f"quality_status={result.get('quality_status')}")
    print(f"query_count={s.get('query_count')}")
    print(f"llm_answered_count={s.get('llm_answered_count')}")
    print(f"good_answer_count={s.get('good_answer_count')}")
    print(f"bad_answer_count={s.get('bad_answer_count')}")
    print(f"unsupported_claim_count={s.get('unsupported_claim_count')}")
    print(f"answer_permission_count={s.get('answer_permission_count')}")
    print(f"write_attempt_count={s.get('write_attempt_count')}")
    if result.get("quality_failures"):
        print("quality_failures=" + json.dumps(result.get("quality_failures")))
    return 0 if result.get("quality_status") == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
