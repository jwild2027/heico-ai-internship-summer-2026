# TRACE-Net NHA N7-N8 Runtime v1

This phase connects the real N4 NHA hierarchy to an OpenAI-compatible sidecar.

## N7 shadow mode

- Recognizes real NHA queries.
- Executes the deterministic N6 query engine.
- Writes privacy-minimized telemetry.
- Always returns the existing upstream answer unchanged.

## N8 gated mode

- Overrides only recognized, evidence-backed real NHA queries.
- Passes non-NHA requests to the existing cognitive endpoint.
- Blocks reserved `990-xxxxx-xxx` synthetic identifiers from the NHA route.
- Loads no N5 synthetic artifact.
- Makes no LLM call for deterministic NHA overrides.

## Safety

The runtime reads N4 JSON artifacts only. It does not mutate TIFFs, OCR, source
truth, Postgres, Qdrant, OpenSearch, or the production graph. Shadow mode cannot
override. Gated mode emits Answer/Evidence/Limits with source page references.

## Recommended deployment

Run the sidecar on port 8132 with upstream port 8131. Start in `shadow` mode,
run the N7-N8 gate, then restart the sidecar in `gated` mode for a limited
OpenWebUI connection. Do not replace port 8131 until the live smoke passes.
