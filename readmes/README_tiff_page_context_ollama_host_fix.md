# TIFF Page Context Ollama Host Fix

This patch normalizes `OLLAMA_HOST` before the page-context generator calls Ollama's local HTTP API.

It fixes Windows/local cases where `OLLAMA_HOST` is set to a bind address like:

```text
0.0.0.0
0.0.0.0:11434
```

The generator now converts those into a client-safe URL:

```text
http://127.0.0.1:11434
```

It also adds `http://` and the default Ollama port when missing.
