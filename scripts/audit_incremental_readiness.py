#!/usr/bin/env python3
"""Print a read-only incremental pipeline readiness audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.incremental_readiness import (  # noqa: E402
    audit_incremental_readiness,
    format_incremental_readiness_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit whether the local incremental TIFF pipeline is ready for changed-page backend mode."
    )
    parser.add_argument("--config", default="local_config.yaml")
    parser.add_argument("--backend-mode", default="changed-pages")
    parser.add_argument("--allow-stale-quality", action="store_true", help="Do not require latest quality gate/manifest to be OK.")
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--json-output", default="local_data/pipeline_runs/incremental_readiness.json")
    args = parser.parse_args(argv)

    report = audit_incremental_readiness(
        config_path=args.config,
        backend_mode=args.backend_mode,
        require_clean_quality=not args.allow_stale_quality,
    )
    print(format_incremental_readiness_report(report))

    if args.write_json:
        output = Path(args.json_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        print()
        print(f"JSON: {output}")

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
