from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> int:
    print("$ " + " ".join(cmd))
    completed = subprocess.run(cmd, cwd=ROOT)
    return int(completed.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run pipeline quality plus API/adapter quality checks.")
    parser.add_argument("--require-incremental-smoke", action="store_true")
    parser.add_argument("--require-user-query-tests", action="store_true")
    parser.add_argument("--require-realistic-query-trace", action="store_true")
    parser.add_argument("--require-slow-realistic-query-trace", action="store_true")
    parser.add_argument("--require-source-package-traceability", action="store_true")
    parser.add_argument("--skip-refresh", action="store_true", help="Do not refresh API/storage/API-adapter JSON first.")
    args = parser.parse_args()

    if not args.skip_refresh:
        for cmd in [
            [sys.executable, "scripts/check_tiff_api_ready.py", "--write-json"],
            [sys.executable, "scripts/check_tiff_storage_adapters.py", "--write-json"],
            [sys.executable, "scripts/check_api_adapter_quality.py", "--write-json"],
            [sys.executable, "scripts/refresh_api_adapter_quality_summary.py"],
        ]:
            rc = run(cmd)
            if rc != 0:
                return rc

    pipeline_cmd = [sys.executable, "scripts/check_pipeline_quality.py"]
    for flag in [
        "require_incremental_smoke",
        "require_user_query_tests",
        "require_realistic_query_trace",
        "require_slow_realistic_query_trace",
        "require_source_package_traceability",
    ]:
        if getattr(args, flag):
            pipeline_cmd.append("--" + flag.replace("_", "-"))
    return run(pipeline_cmd)


if __name__ == "__main__":
    raise SystemExit(main())
