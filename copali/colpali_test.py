"""colpali_test.py

Simple test harness to check whether a `colpali` Python package or executable
is installed and callable. Useful for quick manual debugging.

Usage examples:
  python colpali_test.py --module colpali
  python colpali_test.py --exec-path "C:\\path\\to\\colpali.exe" --input sample.pdf
  python colpali_test.py --module colpali --exec-path colpali --input sample.pdf
"""

import argparse
import importlib
import subprocess
import shutil
import sys
import os


def test_import(module_name: str) -> bool:
    try:
        mod = importlib.import_module(module_name)
        ver = getattr(mod, "__version__", None)
        print(f"Imported module '{module_name}' (version={ver})")
        attrs = [a for a in dir(mod) if not a.startswith("_")]
        print("Top attributes:", attrs[:40])
        return True
    except Exception as e:
        print(f"Import failed for '{module_name}': {e}")
        return False


def test_exec(exec_path: str, input_file: str | None = None) -> bool:
    # If exec_path is just a name, try to resolve it via PATH
    resolved = shutil.which(exec_path) or exec_path
    cmd = [resolved, "--version"]
    if input_file:
        cmd = [resolved, input_file, "--help"]
    try:
        print(f"Running: {cmd}")
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        print("Return code:", proc.returncode)
        print("Stdout:\n", proc.stdout.strip()[:2000])
        print("Stderr:\n", proc.stderr.strip()[:2000])
        return proc.returncode == 0
    except FileNotFoundError:
        print(f"Executable not found: {resolved}")
        return False
    except subprocess.TimeoutExpired:
        print("Executable timed out")
        return False
    except Exception as e:
        print(f"Error running executable: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Probe colpali installation")
    parser.add_argument("--module", type=str, help="Python module name to import (e.g., colpali)")
    parser.add_argument("--exec-path", type=str, help="Executable name or full path to run")
    parser.add_argument("--input", type=str, help="Optional input file to pass to executable")
    args = parser.parse_args()

    ok = True
    if args.module:
        ok = test_import(args.module) or ok

    if args.exec_path:
        ok = test_exec(args.exec_path, args.input) or ok
    else:
        # If module provided but no exec, try to find an executable with same name
        if args.module:
            name = args.module
            path = shutil.which(name)
            if path:
                print(f"Found executable for '{name}' at: {path}")
                ok = test_exec(path, args.input) or ok

    if not (args.module or args.exec_path):
        parser.print_help()
        sys.exit(1)

    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
