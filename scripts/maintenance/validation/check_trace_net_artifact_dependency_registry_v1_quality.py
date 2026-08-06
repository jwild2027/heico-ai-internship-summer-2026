from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_artifact_dependency_registry_v1 import check_artifact_dependency_registry_quality


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Artifact Dependency Registry v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-artifacts", type=int, default=1)
    parser.add_argument("--min-dependency-edges", type=int, default=0)
    parser.add_argument("--allow-cycles", action="store_true")
    parser.add_argument("--require-quality-status", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)
    quality = check_artifact_dependency_registry_quality(
        args.report_path,
        min_artifacts=args.min_artifacts,
        min_dependency_edges=args.min_dependency_edges,
        require_no_cycles=not args.allow_cycles,
        require_quality_status=args.require_quality_status,
        write_json_report=args.write_json,
    )
    print("TRACE-Net artifact dependency registry v1 quality")
    print(f" Status: {quality['status']}")
    print(f" issue_count: {quality['issue_count']}")
    if quality.get("issues"):
        for issue in quality["issues"]:
            print(f" issue: {issue}")
    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
