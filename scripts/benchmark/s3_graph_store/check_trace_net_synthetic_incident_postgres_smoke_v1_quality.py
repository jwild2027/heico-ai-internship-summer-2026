from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_synthetic_incident_postgres_smoke_v1 import check_quality_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net synthetic incident Postgres smoke quality v1")
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--min-inserted-incidents", type=int, default=1)
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()

    quality = check_quality_file(
        args.report_path,
        min_inserted_incidents=args.min_inserted_incidents,
        write_json_report=args.write_json,
    )
    print("TRACE-Net synthetic incident Postgres smoke v1 quality")
    print(f" Status: {quality['status']}")
    for key in [
        "storage_mode",
        "postgres_table",
        "inserted_incident_count",
        "created_incident_found_count",
        "unsafe_incident_count",
        "source_truth_mutation_allowed_count",
        "raw_feedback_direct_to_llm_count",
    ]:
        print(f" {key}: {quality.get(key)}")
    if args.write_json:
        print(f" quality_path: {args.report_path.with_name('trace_net_synthetic_incident_postgres_smoke_v1_quality.json')}")
    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
