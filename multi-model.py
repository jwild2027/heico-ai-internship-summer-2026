"""Run the same prompt against multiple local Ollama models and measure timings.

Usage:
  python multi-model.py --prompt "Tell me a joke"

Defaults models: `gemma3:4b`, `llama3.1:8b`, `phi3:mini` (adjust names to your local models).
"""

import argparse
import json
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import perf_counter

try:
	import ollama
except Exception as e:
	raise RuntimeError("Missing `ollama` Python package or failed to import it. Install via `pip install ollama`.") from e


def parse_model_timings(raw_str: str):
	"""Parse numeric timing fields from raw model response and return ms values.

	Looks for fields like total_duration=54702474300 (assumed nanoseconds) and converts to ms.
	Returns a dict of {field: value_in_ms}.
	"""
	if not raw_str:
		return {}
	# find key=value pairs where value is an integer
	pairs = re.findall(r"([a-zA-Z_]+)=([0-9]+)", raw_str)
	out = {}
	for k, v in pairs:
		try:
			iv = int(v)
		except Exception:
			continue
		# assume durations are in nanoseconds if large; convert to ms
		# heuristic: values > 1e6 are probably nanoseconds
		if iv > 1_000_000:
			out[k] = iv / 1_000_000.0
		else:
			out[k] = iv
	return out


def call_model(model: str, prompt: str):
	"""Call an Ollama model synchronously and measure elapsed time in milliseconds.

	Returns a dict with keys: model, ms, text, error
	"""
	start = perf_counter()
	try:
		# Basic chat call — include a single user message
		res = ollama.chat(model=model, messages=[{"role":"user","content": prompt}])
		end = perf_counter()
		ms = (end - start) * 1000.0

		# response content shape may vary; try common keys
		raw = res
		raw_str = str(res)
		text = None
		if isinstance(res, dict):
			msg = res.get("message") or {}
			# message may be a mapping or an object with 'content'
			if isinstance(msg, dict):
				text = msg.get("content")
			else:
				# fallback - stringify
				try:
					text = getattr(msg, "content", None)
				except Exception:
					text = None
			if text is None:
				text = res.get("content") or res.get("results") or raw_str
		else:
			# not a dict - stringify the object
			# some ollama clients return objects with nested Message
			try:
				text = getattr(res, "message", None)
				if text is not None:
					text = getattr(text, "content", str(text))
				else:
					text = raw_str
			except Exception:
				text = raw_str

		timings = parse_model_timings(raw_str)
		return {"model": model, "ms": ms, "text": text, "raw": raw_str, "model_timings": timings, "error": None}
	except Exception as e:
		end = perf_counter()
		ms = (end - start) * 1000.0
		return {"model": model, "ms": ms, "text": None, "raw": None, "model_timings": {}, "error": str(e)}


def run_all(models, prompt, max_workers=None):
	results = []
	with ThreadPoolExecutor(max_workers=max_workers or len(models)) as ex:
		futures = {ex.submit(call_model, m, prompt): m for m in models}
		for fut in as_completed(futures):
			results.append(fut.result())
	# preserve given model order
	ordered = [next((r for r in results if r["model"] == m), None) for m in models]
	return ordered


def main():
	p = argparse.ArgumentParser(description="Compare response times across local Ollama models")
	p.add_argument("--prompt", "-p", required=True, help="Prompt text to send to each model")
	p.add_argument("--models", "-m", default="gemma3:4b,llama3.1:8b,phi3:mini",
				   help="Comma-separated list of Ollama model names to call")
	p.add_argument("--workers", type=int, default=0, help="Number of parallel workers (0 = #models)")
	p.add_argument("--out", "-o", help="Optional JSON file path to save results")
	p.add_argument("--full", action="store_true", help="Print full model responses instead of truncated preview")
	args = p.parse_args()

	models = [s.strip() for s in args.models.split(",") if s.strip()]
	if not models:
		print("No models specified; exiting")
		return

	print(f"Running prompt against {len(models)} model(s): {models}")
	start_all = perf_counter()
	results = run_all(models, args.prompt, max_workers=(args.workers or None))
	total_ms = (perf_counter() - start_all) * 1000.0

	print("\nResults:")
	for r in results:
		if r is None:
			print("- missing result for a model")
			continue
		if r.get("error"):
			err = r['error']
			msg = f"- {r['model']}: ERROR after {r['ms']:.1f} ms -> {err}"
			# offer hint when model not found (404)
			if "not found" in err.lower() or "status code: 404" in err.lower() or "404" in err:
				msg += f"\n  Hint: model '{r['model']}' is not available locally. Try running: ollama pull {r['model']}"
			print(msg)
		else:
			text = r.get('text')
			raw = r.get('raw')
			if args.full:
				# print raw if present, else full text
				to_print = raw or text or ''
			else:
				to_print = (text[:300] + '...') if text and len(text) > 300 else (text or (str(raw) if raw else ''))
			line = f"- {r['model']}: {r['ms']:.1f} ms; response: {to_print}"
			mt = r.get('model_timings') or {}
			if mt:
				parts = []
				for k, v in mt.items():
					try:
						parts.append(f"{k}={v:.1f}ms")
					except Exception:
						parts.append(f"{k}={v}")
				line += "; model_timings: " + ", ".join(parts)
			print(line)

	print(f"\nTotal wall-clock for concurrent run: {total_ms:.1f} ms")

	if args.out:
		with open(args.out, "w", encoding="utf-8") as fh:
			json.dump({"prompt": args.prompt, "models": models, "results": results, "total_ms": total_ms}, fh, indent=2)
		print(f"Saved results to {args.out}")


if __name__ == "__main__":
	main()

