#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.production_adapters import DEFAULT_OUTPUT, ProductionAdapterConfig, build_production_adapter_readiness, write_production_adapter_readiness


def main() -> int:
    parser = argparse.ArgumentParser(description="Check production storage adapter stub readiness.")
    parser.add_argument("--schema-dir", default="local_data/architecture/production_schema")
    parser.add_argument("--json-output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--require-configured", action="store_true", help="Require production service URLs/DSNs to be set. Use after services exist.")
    args = parser.parse_args()

    config = ProductionAdapterConfig.from_env(schema_dir=args.schema_dir)
    readiness = build_production_adapter_readiness(config, require_configured=args.require_configured)

    if args.write_json:
        write_production_adapter_readiness(args.json_output, config=config, require_configured=args.require_configured)

    print("Production adapter stub readiness")
    print(f"  Status: {readiness.status}")
    print(f"  Mode: {readiness.mode}")
    print(f"  Schema dir: {readiness.schema_dir}")
    print(f"  Schema artifacts present: {readiness.schema_artifacts_present}")
    print("\nProduction service configuration:")
    print(f"  PostgreSQL DSN configured: {readiness.postgres_configured}")
    print(f"  OpenSearch URL configured: {readiness.opensearch_configured}")
    print(f"  Qdrant URL configured: {readiness.qdrant_configured}")
    print(f"  ResCarta base URL configured: {readiness.rescarta_configured}")
    print("\nChecks:")
    for check in readiness.checks:
        print(f"  {'OK' if check.ok else 'INFO'} {check.name}: {check.message}")
    if args.write_json:
        print(f"\nJSON: {args.json_output}")

    return 0 if readiness.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
