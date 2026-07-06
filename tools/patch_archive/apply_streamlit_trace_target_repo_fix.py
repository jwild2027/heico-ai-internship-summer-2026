from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()
CANDIDATE_FILES = [
    Path("apps/streamlit/tiff_api_ui.py"),
    Path("tiff/streamlit_api_client.py"),
]

NEW_BODY_LINES = [
    "combined = f\"{question or ''}\\n{answer or ''}\"",
    "page_id = find_first_page_id(combined)",
    "if page_id:",
    "    return {\"type\": \"page\", \"value\": page_id}",
    "ata_code = find_first_ata(combined)",
    "if ata_code:",
    "    return {\"type\": \"ata\", \"value\": ata_code}",
    "part_number = find_first_part(combined)",
    "if part_number:",
    "    return {\"type\": \"part\", \"value\": part_number}",
    "return {\"type\": None, \"value\": None}",
]


def iter_python_files() -> list[Path]:
    files: list[Path] = []
    for candidate in CANDIDATE_FILES:
        p = ROOT / candidate
        if p.exists():
            files.append(p)
    for p in sorted((ROOT / "tiff").glob("*.py")) if (ROOT / "tiff").exists() else []:
        if p not in files:
            files.append(p)
    for p in sorted((ROOT / "apps" / "streamlit").glob("*.py")) if (ROOT / "apps" / "streamlit").exists() else []:
        if p not in files:
            files.append(p)
    return files


def find_function_bounds(lines: list[str], name: str) -> tuple[int, int, str] | None:
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped.startswith(f"def {name}("):
            continue
        indent = line[: len(line) - len(stripped)]
        # Skip decorators immediately above by keeping the def line as start.
        start = i
        end = len(lines)
        for j in range(i + 1, len(lines)):
            next_line = lines[j]
            next_stripped = next_line.lstrip()
            if not next_stripped.strip():
                continue
            next_indent = next_line[: len(next_line) - len(next_stripped)]
            if len(next_indent) <= len(indent) and (
                next_stripped.startswith("def ")
                or next_stripped.startswith("class ")
                or next_stripped.startswith("@")
            ):
                end = j
                break
        return start, end, indent
    return None


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    bounds = find_function_bounds(lines, "infer_trace_target")
    if bounds is None:
        return False
    start, end, indent = bounds
    body_indent = indent + "    "
    def_line = lines[start]
    new_lines = [def_line]
    for line in NEW_BODY_LINES:
        new_lines.append(body_indent + line)
    updated_lines = lines[:start] + new_lines + lines[end:]
    path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    return True


def main() -> int:
    patched: list[Path] = []
    for path in iter_python_files():
        if patch_file(path):
            patched.append(path.relative_to(ROOT))
    if not patched:
        print("Could not find infer_trace_target in known Python files.")
        return 1
    print("Patched infer_trace_target in:")
    for path in patched:
        print(f"  {path}")
    print("Trace target priority is now: page -> ATA -> part.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
