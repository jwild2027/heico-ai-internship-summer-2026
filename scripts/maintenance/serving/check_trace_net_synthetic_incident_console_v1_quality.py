from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_synthetic_incident_console_v1 import quality_report, write_json


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net synthetic incident console v1 quality")
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--min-incidents", type=int, default=0)
    parser.add_argument("--max-unsafe-incidents", type=int, default=0)
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    payload = json.loads(args.report_path.read_text(encoding="utf-8"))
    quality = quality_report(payload, min_incidents=args.min_incidents, max_unsafe_incidents=args.max_unsafe_incidents)
    if args.write_json:
        quality_path = args.report_path.with_name("trace_net_synthetic_incident_console_v1_quality.json")
        write_json(quality_path, quality)
    print("TRACE-Net synthetic incident console v1 quality")
    print(f" Status: {quality['status']}")
    print(f" incident_count: {quality['incident_count']}")
    print(f" unsafe_incident_count: {quality['unsafe_incident_count']}")
    print(f" source_truth_mutation_allowed_count: {quality['source_truth_mutation_allowed_count']}")
    print(f" raw_feedback_direct_to_llm_count: {quality['raw_feedback_direct_to_llm_count']}")
    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
