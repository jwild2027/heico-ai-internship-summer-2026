from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: List[str]) -> int:
    completed = subprocess.run(cmd, cwd=str(ROOT))
    return int(completed.returncode)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _print_extra_requirement(title: str, path: Path, status_key: str = "status") -> int:
    print(f"\n{title}")
    if not path.exists():
        print("  Status: FAIL")
        print(f"  Missing: {path}")
        return 1
    data = _load_json(path)
    status = str(data.get(status_key, "fail")).lower()
    print(f"  Status: {status.upper()}")
    for check in data.get("checks", []):
        if "ok" in check:
            ok = bool(check.get("ok"))
        else:
            ok = str(check.get("status", "")).strip().lower() in {"ok", "pass", "passed", "success"}
        label = "OK" if ok else "FAIL"
        print(f"  {label} {check.get('name')}: {check.get('message')}")
    return 0 if status == "ok" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run full local TIFF system quality checks.")
    parser.add_argument("--require-api-adapter-quality", action="store_true")
    parser.add_argument("--require-api-contract-tests", action="store_true")
    parser.add_argument("--require-slow-api-contract-tests", action="store_true")
    parser.add_argument("--require-incremental-smoke", action="store_true")
    parser.add_argument("--require-user-query-tests", action="store_true")
    parser.add_argument("--require-realistic-query-trace", action="store_true")
    parser.add_argument("--require-slow-realistic-query-trace", action="store_true")
    parser.add_argument("--require-source-package-traceability", action="store_true")
    args = parser.parse_args()

    pipeline_args = [sys.executable, "scripts/check_pipeline_quality.py"]
    for flag in (
        "require_incremental_smoke",
        "require_user_query_tests",
        "require_realistic_query_trace",
        "require_slow_realistic_query_trace",
        "require_source_package_traceability",
    ):
        if getattr(args, flag):
            pipeline_args.append("--" + flag.replace("_", "-"))

    exit_code = _run(pipeline_args)

    if args.require_api_adapter_quality:
        exit_code = max(exit_code, _print_extra_requirement("API/adapter quality requirement", ROOT / "local_data/api/api_adapter_quality.json"))

    if args.require_api_contract_tests:
        # If the user asks for slow API contract tests, enforce it at the contract quality layer too.
        contract_quality_path = ROOT / "local_data/api/api_contract_quality.json"
        if args.require_slow_api_contract_tests:
            contract_cmd = [sys.executable, "scripts/check_api_contract_quality.py", "--write-json", "--require-slow"]
            exit_code = max(exit_code, _run(contract_cmd))
        exit_code = max(exit_code, _print_extra_requirement("API contract quality requirement", contract_quality_path))

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
