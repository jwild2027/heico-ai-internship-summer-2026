from pathlib import Path
import argparse
import json
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_ask_api_hybrid_v3_routing_v1 import quality_report, write_json


def main() -> int:
    p = argparse.ArgumentParser(description="Check TRACE-Net Ask API Hybrid v3 Routing v1 quality")
    p.add_argument("--report-path", type=Path, required=True)
    p.add_argument("--require-hybrid-v3-quality-pass", action="store_true")
    p.add_argument("--require-final-answer-quality-pass", action="store_true")
    p.add_argument("--write-json", action="store_true")
    args = p.parse_args()
    report = json.loads(args.report_path.read_text(encoding="utf-8"))
    quality = quality_report(
        report,
        require_hybrid_v3_quality_pass=args.require_hybrid_v3_quality_pass,
        require_final_answer_quality_pass=args.require_final_answer_quality_pass,
    )
    if args.write_json:
        write_json(args.report_path.with_name("trace_net_ask_api_hybrid_v3_routing_v1_quality.json"), quality)
    print(json.dumps(quality, indent=2, sort_keys=True))
    return 0 if quality.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
