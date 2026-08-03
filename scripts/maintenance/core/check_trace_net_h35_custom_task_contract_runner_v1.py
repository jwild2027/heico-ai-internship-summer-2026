from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_h35_custom_task_contract_runner_v1 import check_custom_task_contract_run


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--contract-run", required=True)
    p.add_argument("--min-records", type=int, default=5)
    p.add_argument("--min-good-answers", type=int, default=5)
    p.add_argument("--min-contract-pass", type=int, default=5)
    p.add_argument("--max-fallback-used", type=int, default=0)
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    args = p.parse_args(argv)
    result = check_custom_task_contract_run(**vars(args))
    return 0 if result["quality_status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
