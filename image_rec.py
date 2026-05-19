import os
from pathlib import Path

import ollama


MODEL = os.getenv("OLLAMA_IMAGE_MODEL", "gemma3:4b")
IMAGE_PATH = Path(__file__).with_name("images.jpg")


if not IMAGE_PATH.exists():
	raise FileNotFoundError(f"Image not found: {IMAGE_PATH}")


try:
	res = ollama.chat(
		model=MODEL,
		messages=[
			{
				"role": "user",
				"content": "Describe this image and find what the specific part is called online:",
				"images": [str(IMAGE_PATH)],
			}
		],
	)
except ollama.ResponseError as error:
	raise RuntimeError(
		f"Ollama could not load model '{MODEL}'. Run `ollama pull {MODEL}` first, or set OLLAMA_IMAGE_MODEL to an installed multimodal model."
	) from error


print(res["message"]["content"])