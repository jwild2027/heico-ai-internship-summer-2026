from pathlib import Path
import argparse
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_synthetic_incident_console_v1 import (
    DEFAULT_INCIDENT_TABLE,
    DEFAULT_OUTPUT_DIR,
    build_console_report,
    init_postgres_storage,
    write_postgres_schema_file,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Initialize TRACE-Net synthetic incident console Postgres storage")
    parser.add_argument("--database-url", default=os.environ.get("TRACE_NET_DATABASE_URL"), required=False)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--postgres-table", default=DEFAULT_INCIDENT_TABLE)
    args = parser.parse_args(argv)

    if not args.database_url:
        raise SystemExit("--database-url or TRACE_NET_DATABASE_URL is required")

    init_postgres_storage(args.database_url, table_name=args.postgres_table)
    schema_path = write_postgres_schema_file(args.output_dir, args.postgres_table)
    report = build_console_report(
        args.output_dir,
        storage_mode="postgres",
        database_url=args.database_url,
        table_name=args.postgres_table,
    )

    print("TRACE-Net synthetic incident console Postgres storage v1")
    print(" Status: POSTGRES_SCHEMA_READY")
    print(f" storage_mode: postgres")
    print(f" postgres_table: {args.postgres_table}")
    print(f" incident_count: {report['summary']['incident_count']}")
    print(f" schema_path: {schema_path}")
    print(f" report_path: {args.output_dir / 'trace_net_synthetic_incident_console_v1.json'}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
