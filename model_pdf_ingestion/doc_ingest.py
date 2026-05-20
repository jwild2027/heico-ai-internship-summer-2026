#!/usr/bin/env python3
"""Extract text from a PDF with pypdf, chunk it, and summarize each chunk with Ollama.

This script is a small PDF ingestion pipeline for the current AI setup:
- choose a PDF with `--pdf` or a file picker
- extract text with pypdf
- chunk the text into manageable pieces
- ask the vision/text model to summarize each chunk into JSON
- save the structured result to a JSON file for later search, RAG, or Chroma ingestion
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import ollama
from pypdf import PdfReader

MODEL = os.getenv("OLLAMA_DOC_MODEL", "gemma3:4b")
DEFAULT_PROMPT = (
    "Summarize this document chunk for later retrieval. "
    "Return only valid JSON with keys: title, summary, keywords, entities, page_notes. "
    "Keep the summary concise and specific."
)
DEFAULT_CHUNK_WORDS = 900
DEFAULT_CHUNK_OVERLAP = 40
DEFAULT_MIN_SCORE = 1
NOISE_LINE_MIN_OCCURRENCES = 3
NOISE_LINE_MAX_LEN = 80

PAGE_MARKER_RE = re.compile(r"^\s*(page\s*)?\d+(\s*/\s*\d+)?\s*$", re.IGNORECASE)
HEADING_RE = re.compile(
    r"^(\d+(?:\.\d+)*\.?\s+.+|[A-Z][A-Z0-9\s,;:\-()]{4,}|[A-Z][\w\s\-]{3,}:\s*)$"
)


@dataclass
class ChunkRecord:
    chunk_id: int
    page_start: int
    page_end: int
    heading: str
    score: int
    text: str


@dataclass
class SummaryRecord:
    chunk_id: int
    page_start: int
    page_end: int
    heading: str
    score: int
    text: str
    summary: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest a PDF with pypdf and summarize it with Ollama.")
    parser.add_argument("--pdf", "-p", type=Path, help="Path to the PDF file to ingest.")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("doc_ingest_output.json"),
        help="Where to save the structured JSON output.",
    )
    parser.add_argument(
        "--chunk-words",
        type=int,
        default=DEFAULT_CHUNK_WORDS,
        help="Approximate number of words per chunk.",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=DEFAULT_CHUNK_OVERLAP,
        help="Number of words to overlap between chunks.",
    )
    parser.add_argument(
        "--prompt",
        "-t",
        default=DEFAULT_PROMPT,
        help="Prompt used when asking Ollama to summarize each chunk.",
    )
    parser.add_argument(
        "--model",
        default=MODEL,
        help="Ollama model to use for document ingestion.",
    )
    return parser.parse_args()


def pick_pdf_file() -> Path:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as error:
        raise RuntimeError(
            "No --pdf path was provided and the file picker is unavailable. "
            "Run again with --pdf PATH_TO_FILE.pdf."
        ) from error

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    file_path = filedialog.askopenfilename(
        title="Select a PDF to ingest",
        filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
    )
    root.destroy()

    if not file_path:
        raise RuntimeError("No PDF selected.")

    return Path(file_path)


def resolve_pdf_path(pdf_arg: Path | None) -> Path:
    pdf_path = pdf_arg or pick_pdf_file()
    pdf_path = pdf_path.expanduser().resolve()

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF path is not a file: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Unsupported file type: {pdf_path.suffix}. Expected a PDF.")

    return pdf_path


def extract_pages(pdf_path: Path) -> list[dict[str, Any]]:
    reader = PdfReader(str(pdf_path))
    pages: list[dict[str, Any]] = []

    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append({"page": index, "text": text})

    return pages


def normalize_line(line: str) -> str:
    line = re.sub(r"\s+", " ", line).strip()
    line = re.sub(r"^\d+\s*$", "", line).strip()
    return line


def find_repeated_noise_lines(pages: list[dict[str, Any]]) -> set[str]:
    counts: dict[str, int] = {}
    page_count = len(pages)

    for page in pages:
        seen_on_page: set[str] = set()
        for raw_line in str(page["text"]).splitlines():
            line = normalize_line(raw_line)
            if not line:
                continue
            if len(line) > NOISE_LINE_MAX_LEN:
                continue
            if PAGE_MARKER_RE.match(line):
                continue
            seen_on_page.add(line)
        for line in seen_on_page:
            counts[line] = counts.get(line, 0) + 1

    repeated_threshold = max(NOISE_LINE_MIN_OCCURRENCES, int(page_count * 0.30))
    return {line for line, count in counts.items() if count >= repeated_threshold}


def clean_page_text(page_text: str, repeated_noise: set[str]) -> str:
    cleaned_lines: list[str] = []
    for raw_line in page_text.splitlines():
        line = normalize_line(raw_line)
        if not line:
            continue
        if PAGE_MARKER_RE.match(line):
            continue
        if line in repeated_noise:
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def split_into_paragraphs(page_text: str) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", page_text) if part.strip()]
    if len(paragraphs) == 1:
        # Preserve line-based structure when PDFs do not include blank lines.
        paragraphs = [line.strip() for line in page_text.splitlines() if line.strip()]
    return paragraphs


def is_heading(line: str) -> bool:
    line = normalize_line(line)
    if not line:
        return False
    if len(line.split()) <= 10 and HEADING_RE.match(line):
        return True
    return False


def build_structure_aware_sections(pages: list[dict[str, Any]], repeated_noise: set[str]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current_section: dict[str, Any] | None = None

    for page in pages:
        page_number = int(page["page"])
        cleaned_text = clean_page_text(str(page["text"]), repeated_noise)
        if not cleaned_text.strip():
            continue

        for block in split_into_paragraphs(cleaned_text):
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            heading = ""
            content_lines = lines

            if lines and is_heading(lines[0]):
                heading = lines[0]
                content_lines = lines[1:]

            block_text = " ".join(content_lines).strip()
            if not block_text:
                continue

            if heading:
                if current_section and current_section["text"]:
                    sections.append(current_section)
                current_section = {
                    "heading": heading,
                    "page_start": page_number,
                    "page_end": page_number,
                    "text": block_text,
                }
                continue

            if current_section is None:
                current_section = {
                    "heading": f"Page {page_number}",
                    "page_start": page_number,
                    "page_end": page_number,
                    "text": block_text,
                }
            else:
                current_section["text"] = f"{current_section['text']} {block_text}".strip()
                current_section["page_end"] = page_number

    if current_section and current_section["text"]:
        sections.append(current_section)

    return sections


def split_words(text: str) -> list[str]:
    return re.findall(r"\S+", text)


def score_section_text(text: str, query_terms: list[str]) -> int:
    lowered = text.lower()
    score = 0
    for term in query_terms:
        score += lowered.count(term.lower())
    return score


def build_query_terms(prompt: str) -> list[str]:
    terms = [term.lower() for term in re.findall(r"[A-Za-z0-9_][A-Za-z0-9_\-]+", prompt)]
    stopwords = {
        "this", "that", "with", "from", "into", "only", "valid", "json", "keys",
        "summary", "keep", "concise", "specific", "document", "chunk", "later", "retrieval",
        "return", "page", "pages", "ollama", "keys",
    }
    filtered = [term for term in terms if term not in stopwords and len(term) > 2]
    # keep order while deduplicating
    seen = set()
    ordered: list[str] = []
    for term in filtered:
        if term not in seen:
            seen.add(term)
            ordered.append(term)
    return ordered


def chunk_sections(
    sections: list[dict[str, Any]],
    chunk_words: int,
    overlap: int,
    query_terms: list[str],
    min_score: int,
) -> list[ChunkRecord]:
    records: list[ChunkRecord] = []
    chunk_id = 1

    for section in sections:
        text = str(section["text"]).strip()
        if not text:
            continue

        score = score_section_text(text, query_terms)
        if query_terms and score < min_score:
            continue

        words = split_words(text)
        if not words:
            continue

        if len(words) <= chunk_words:
            records.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    page_start=int(section["page_start"]),
                    page_end=int(section["page_end"]),
                    heading=str(section["heading"]),
                    score=score,
                    text=text,
                )
            )
            chunk_id += 1
            continue

        step = max(chunk_words - overlap, 1)
        start = 0
        while start < len(words):
            window = words[start : start + chunk_words]
            if not window:
                break
            window_text = " ".join(window).strip()
            records.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    page_start=int(section["page_start"]),
                    page_end=int(section["page_end"]),
                    heading=str(section["heading"]),
                    score=score,
                    text=window_text,
                )
            )
            chunk_id += 1
            start += step

    return records


def extract_json_text(content: str) -> str:
    text = content.strip()

    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1].strip()

    return text


def summarize_chunk(chunk: ChunkRecord, prompt: str, model: str) -> dict[str, Any]:
    response = ollama.chat(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You summarize PDF text for retrieval. Return only JSON.",
            },
            {
                "role": "user",
                "content": (
                    f"Section heading: {chunk.heading}. Pages {chunk.page_start}-{chunk.page_end}. "
                    f"Section relevance score: {chunk.score}. "
                    f"{prompt}\n\nTEXT:\n{chunk.text}"
                ),
            },
        ],
        stream=False,
    )

    content = response["message"]["content"]
    json_text = extract_json_text(content)

    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError:
        payload = {
            "title": f"Chunk {chunk.chunk_id}",
            "summary": content.strip(),
            "keywords": [],
            "entities": [],
            "page_notes": [],
            "raw_output": content,
        }

    if not isinstance(payload, dict):
        payload = {
            "title": f"Chunk {chunk.chunk_id}",
            "summary": content.strip(),
            "keywords": [],
            "entities": [],
            "page_notes": [],
            "raw_output": content,
        }

    payload.setdefault("title", f"Chunk {chunk.chunk_id}")
    payload.setdefault("summary", content.strip())
    payload.setdefault("keywords", [])
    payload.setdefault("entities", [])
    payload.setdefault("page_notes", [])
    return payload


def deduplicate_chunks(chunks: list[ChunkRecord]) -> list[ChunkRecord]:
    seen: set[str] = set()
    deduped: list[ChunkRecord] = []
    for chunk in chunks:
        normalized = re.sub(r"\s+", " ", chunk.text.lower()).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(chunk)
    return deduped


def main() -> None:
    args = parse_args()
    run_ingest(
        resolve_pdf_path(args.pdf),
        args.output,
        args.model,
        args.chunk_words,
        args.overlap,
        args.prompt,
    )


if __name__ == "__main__":
    main()


def run_ingest(
    pdf_path: Path,
    output: Path | str,
    model: str,
    chunk_words: int = DEFAULT_CHUNK_WORDS,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    prompt: str = DEFAULT_PROMPT,
) -> None:
    """Programmatic ingest entrypoint.

    This mirrors the behavior of the CLI `main()` but can be imported and
    called by thin wrappers that fix a particular `model`.
    """

    pages = extract_pages(pdf_path)
    repeated_noise = find_repeated_noise_lines(pages)
    sections = build_structure_aware_sections(pages, repeated_noise)
    query_terms = build_query_terms(prompt)
    chunks = chunk_sections(sections, chunk_words, overlap, query_terms, DEFAULT_MIN_SCORE)
    chunks = deduplicate_chunks(chunks)

    if not chunks:
        raise RuntimeError(f"No extractable text found in {pdf_path}")

    print(f"Using model: {model}")
    print(f"PDF: {pdf_path}")
    print(f"Pages extracted: {len(pages)}")
    print(f"Repeated noise lines removed: {len(repeated_noise)}")
    print(f"Structure-aware sections found: {len(sections)}")
    print(f"Chunks created after filtering: {len(chunks)}")
    if query_terms:
        print(f"Query terms used for first-pass filtering: {', '.join(query_terms)}")

    summaries: list[SummaryRecord] = []
    for chunk in chunks:
        print(f"Summarizing chunk {chunk.chunk_id} (pages {chunk.page_start}-{chunk.page_end})...")
        summary = summarize_chunk(chunk, prompt, model)
        summaries.append(
            SummaryRecord(
                chunk_id=chunk.chunk_id,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                heading=chunk.heading,
                score=chunk.score,
                text=chunk.text,
                summary=summary,
            )
        )

    output_data = {
        "source_pdf": str(pdf_path),
        "model": model,
        "pages": pages,
        "chunks": [asdict(item) for item in summaries],
    }

    Path(output).write_text(json.dumps(output_data, indent=2), encoding="utf-8")
    print(f"Saved structured output to {Path(output).resolve()}")
