from __future__ import annotations

import argparse
import os
from pathlib import Path

import ollama


MODEL = os.getenv("OLLAMA_IMAGE_MODEL", "qwen3-vl")
DEFAULT_PROMPT = (
	"Describe this image and find what the specific part or manual is called online. "
	"Also list every callout."
)


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Send a local image to an Ollama multimodal model.")
	parser.add_argument(
		"--image",
		"-i",
		type=Path,
		help="Path to the image file to analyze.",
	)
	parser.add_argument(
		"--prompt",
		"-p",
		default=DEFAULT_PROMPT,
		help="Prompt to send alongside the image.",
	)
	return parser.parse_args()


def pick_image_file() -> Path:
	"""Open a file picker so the user can choose an image without moving files into GitHub."""
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
		title="Select an image for Ollama",
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

	return image_path


def main() -> None:
	args = parse_args()
	image_path = resolve_image_path(args.image)

	try:
		res = ollama.chat(
			model=MODEL,
			messages=[
				{
					"role": "user",
					"content": args.prompt,
					"images": [str(image_path)],
				}
			],
		)
	except ollama.ResponseError as error:
		raise RuntimeError(
			f"Ollama could not load model '{MODEL}'. Run `ollama pull {MODEL}` first, or set OLLAMA_IMAGE_MODEL to an installed multimodal model."
		) from error

	print(res["message"]["content"])


if __name__ == "__main__":
	main()