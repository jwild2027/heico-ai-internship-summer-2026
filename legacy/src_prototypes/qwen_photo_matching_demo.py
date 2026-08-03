#!/usr/bin/env python3
"""Match a local image against images/ by asking an Ollama vision model to describe each image.

Flow:
1. Choose an image from the local filesystem (CLI path or file picker).
2. Ask the vision model to produce a compact JSON description of the upload.
3. Ask the same model to describe every candidate in the images/ folder.
4. Rank candidates by description similarity and print the best-looking match.

This is intentionally lightweight: the AI describes the image, and the script
uses those descriptions to choose the closest match.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import ollama

MODEL = os.getenv("OLLAMA_IMAGE_MODEL", "qwen3-vl")
DEFAULT_PROMPT = (
    "Describe this image for visual matching. "
    "Focus on the main subject, setting, colors, text, visible objects, and any unique features. "
    "Return a compact JSON object with keys: subject, scene, objects, colors, text, keywords, summary. "
    "Keep the summary to one or two sentences."
)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


@dataclass
class MatchResult:
    path: Path
    score: float
    description: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Match an uploaded image against files in the images folder.")
    parser.add_argument("--image", "-i", type=Path, help="Path to the image to analyze.")
    parser.add_argument(
        "--images-dir",
        type=Path,
        default=Path(__file__).with_name("images"),
        help="Folder containing candidate images to compare against.",
    )
    parser.add_argument(
        "--prompt",
        "-p",
        default=DEFAULT_PROMPT,
        help="Prompt used to ask the vision model for a matching-friendly description.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="How many matches to print.",
    )
    return parser.parse_args()


def pick_image_file() -> Path:
    """Open a Windows file picker when --image is not provided."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as error:
        raise RuntimeError(
            "No --image path was provided and the Windows file picker is unavailable. "
            "Run again with --image PATH_TO_IMAGE."
        ) from error

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    file_path = filedialog.askopenfilename(
        title="Select an image for photo_detect",
        filetypes=[
            ("Image files", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"),
            ("All files", "*.*"),
        ],
    )
    root.destroy()

    if not file_path:
        raise RuntimeError("No image selected.")

    return Path(file_path)


def resolve_image_path(image_arg: Path | None) -> Path:
    image_path = image_arg or pick_image_file()
    image_path = image_path.expanduser().resolve()

    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    if not image_path.is_file():
        raise FileNotFoundError(f"Image path is not a file: {image_path}")
    if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported image file type: {image_path.suffix}")

    return image_path


def list_candidate_images(images_dir: Path, source_image: Path) -> list[Path]:
    if not images_dir.exists():
        raise FileNotFoundError(f"Images folder not found: {images_dir}")
    if not images_dir.is_dir():
        raise NotADirectoryError(f"Images path is not a folder: {images_dir}")

    candidates = [
        path.resolve()
        for path in images_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS and path.resolve() != source_image
    ]
    return sorted(candidates)


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


def chat_describe_image(image_path: Path, prompt: str) -> dict[str, Any]:
    response = ollama.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a visual matching assistant. Return only JSON."},
            {
                "role": "user",
                "content": prompt,
                "images": [str(image_path)],
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
            "summary": content.strip(),
            "keywords": [],
            "raw_output": content,
        }

    if not isinstance(payload, dict):
        payload = {
            "summary": content.strip(),
            "keywords": [],
            "raw_output": content,
        }

    payload.setdefault("summary", content.strip())
    payload.setdefault("keywords", [])
    return payload


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(normalize_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(f"{key} {normalize_text(item)}" for key, item in value.items())
    return str(value)


def score_match(upload_desc: dict[str, Any], candidate_desc: dict[str, Any]) -> float:
    upload_summary = normalize_text(upload_desc.get("summary"))
    candidate_summary = normalize_text(candidate_desc.get("summary"))

    upload_keywords = {word.lower().strip() for word in upload_desc.get("keywords", []) if str(word).strip()}
    candidate_keywords = {word.lower().strip() for word in candidate_desc.get("keywords", []) if str(word).strip()}

    text_similarity = SequenceMatcher(None, upload_summary.lower(), candidate_summary.lower()).ratio()
    if upload_keywords and candidate_keywords:
        keyword_overlap = len(upload_keywords & candidate_keywords) / len(upload_keywords | candidate_keywords)
    else:
        keyword_overlap = 0.0

    # Weighted toward the AI-generated summaries, with keywords as a tie-breaker.
    return (0.75 * text_similarity) + (0.25 * keyword_overlap)


def describe_candidates(upload_desc: dict[str, Any], candidate_paths: list[Path], prompt: str) -> list[MatchResult]:
    results: list[MatchResult] = []

    for candidate_path in candidate_paths:
        candidate_desc = chat_describe_image(candidate_path, prompt)
        score = score_match(upload_desc, candidate_desc)
        results.append(MatchResult(path=candidate_path, score=score, description=candidate_desc))

    results.sort(key=lambda item: item.score, reverse=True)
    return results


def print_description(title: str, image_path: Path, description: dict[str, Any]) -> None:
    print(f"\n{title}: {image_path}")
    print(f"summary: {normalize_text(description.get('summary'))}")
    keywords = description.get("keywords", [])
    if keywords:
        print(f"keywords: {', '.join(normalize_text(keywords).split())}")
    if description.get("raw_output"):
        print("raw_output:")
        print(description["raw_output"])


def main() -> None:
    args = parse_args()
    source_image = resolve_image_path(args.image)
    candidates = list_candidate_images(args.images_dir, source_image)

    print(f"Using model: {MODEL}")
    print(f"Source image: {source_image}")
    print(f"Candidate folder: {args.images_dir.resolve()}")
    print(f"Candidates found: {len(candidates)}")

    if not candidates:
        raise RuntimeError(f"No candidate images found in {args.images_dir}")

    try:
        upload_desc = chat_describe_image(source_image, args.prompt)
    except ollama.ResponseError as error:
        raise RuntimeError(
            f"Ollama could not load model '{MODEL}'. Run `ollama pull {MODEL}` first, or set OLLAMA_IMAGE_MODEL to an installed multimodal model."
        ) from error

    print_description("Uploaded image description", source_image, upload_desc)

    try:
        matches = describe_candidates(upload_desc, candidates, args.prompt)
    except ollama.ResponseError as error:
        raise RuntimeError(
            f"Ollama failed while describing candidate images. Make sure '{MODEL}' is installed and running."
        ) from error

    print("\nTop matches:")
    for index, match in enumerate(matches[: max(args.top_k, 1)], start=1):
        print(f"{index}. {match.path.name}  score={match.score:.3f}")
        summary = normalize_text(match.description.get("summary"))
        if summary:
            print(f"   {summary}")

    best_match = matches[0]
    print("\nBest looking match:")
    print(f"{best_match.path}")
    print(f"score={best_match.score:.3f}")
    print(f"summary={normalize_text(best_match.description.get('summary'))}")

    print("\nBest match description:")
    print_description("Candidate", best_match.path, best_match.description)


if __name__ == "__main__":
    main()
