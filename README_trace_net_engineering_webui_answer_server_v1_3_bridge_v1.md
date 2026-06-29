# TRACE-Net Engineering WebUI Answer Server v1.3 Bridge v1 writer-parent-dir fix

This patch keeps the v1.3 bridge server behavior but makes its in-process bridge preflight robust against older stage writer helpers that open JSON/JSONL/Markdown sidecars before creating their parent directories.

It does not grant answer permission, does not call databases, and does not mutate source truth.
