from pathlib import Path

TARGET = Path("tiff/storage_adapters.py")
MARKER = "# compatibility: allow page-id strings when resolving page source"


def main() -> int:
    if not TARGET.exists():
        raise SystemExit(f"Missing {TARGET}; run this from the repository root.")

    text = TARGET.read_text(encoding="utf-8")
    if MARKER in text:
        print(f"{TARGET} already contains ATA/source compatibility fix.")
        return 0

    needle = "    def _page_source_from_page(self, page"
    idx = text.find(needle)
    if idx < 0:
        raise SystemExit("Could not find _page_source_from_page method in tiff/storage_adapters.py")

    # Find the end of the def line, whatever its signature is.
    line_end = text.find("\n", idx)
    if line_end < 0:
        raise SystemExit("Malformed _page_source_from_page definition")

    insert = """\n        # compatibility: allow page-id strings when resolving page source\n        # Some ATA tree/page references are stored as page_id strings instead\n        # of full page dictionaries. Resolve those through get_page() before\n        # reading source_url/rescarta_url/tiff/ocr fields.\n        if page is None:\n            return None\n        if not isinstance(page, Mapping):\n            page_id = str(page)\n            resolved = None\n            try:\n                resolved = self.get_page(page_id)\n            except Exception:\n                resolved = None\n            if isinstance(resolved, Mapping):\n                # Some stores return the page fields directly; others wrap the\n                # page under a `page` key. Support both shapes.\n                nested_page = resolved.get(\"page\")\n                if isinstance(nested_page, Mapping):\n                    page = nested_page\n                else:\n                    page = resolved\n            else:\n                return {\"page_id\": page_id}\n"""

    text = text[:line_end+1] + insert + text[line_end+1:]
    TARGET.write_text(text, encoding="utf-8")
    print(f"Applied ATA/source compatibility fix to {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
