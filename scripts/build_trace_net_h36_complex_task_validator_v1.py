#!/usr/bin/env python3
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_h36_complex_task_validator_v1 import build_complex_task_validator


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--contract-run", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--min-records", type=int, default=5)
    p.add_argument("--min-contract-pass", type=int, default=4)
    p.add_argument("--max-bad", type=int, default=0)
    p.add_argument("--max-fallback-used", type=int, default=0)
    p.add_argument("--require-source-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    args = p.parse_args()
    manifest = build_complex_task_validator(**vars(args))
    s = manifest["summary"]
    print("status=TRACE_NET_H36_COMPLEX_TASK_VALIDATOR_BUILT")
    print(f"quality_status={manifest['quality_status']}")
    print(f"record_count={s['record_count']}")
    print(f"contract_pass_count={s['contract_pass_count']}")
    print(f"review_count={s['review_count']}")
    print(f"bad_count={s['bad_count']}")
    print(f"fallback_used_count={s['fallback_used_count']}")
    print(f"unsafe_finding_count={s['unsafe_finding_count']}")
    print(f"answer_permission_count={s['answer_permission_count']}")
    print(f"write_attempt_count={s['write_attempt_count']}")
    print(f"output={Path(args.output_dir) / 'trace_net_h36_complex_task_validator_v1.json'}")
    return 0 if manifest["quality_status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
