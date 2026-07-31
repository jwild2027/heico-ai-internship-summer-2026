# TRACE-Net Executive TIFF Demo v4

## Purpose

This is a separate deep-narration presentation mode. It does not replace:

- `run_trace_net_executive_tiff_demo_v2.py` — simple full 509-page demo
- `run_trace_net_executive_tiff_demo_v3.py` — fast 10-page demo

The v4 mode is intentionally verbose for a non-technical audience. It prints:

1. OCR progress and one OCR result line per page.
2. One final classification line per page.
3. Two explicit graph creation lines for nodes and relationships.
4. The six Engram layers: working, semantic, procedural, episodic, trait, and critic.
5. One real `bge-m3:latest` embedding operation per page, stored locally only.
6. Two example questions by default.
7. The deterministic query atoms, route, tunnels, vector guidance, evidence records, Engram update, one Gemma call, answer validation, and final answer.

The demo does not display private model chain-of-thought. It displays the safe audit trace around the model call.

## Safety

- No live Postgres writes.
- No live Qdrant writes.
- No live OpenSearch writes.
- No source-truth mutation.
- No production graph mutation.
- No shell termination settings or commands.

## Run

```bash
python -B scripts/run_trace_net_executive_tiff_demo_v4.py
```

The default output path is:

```text
/data/trace_net_runs/executive_deep_demo_v4_<timestamp>
```

To reuse a completed v4 ingestion folder without rerunning OCR:

```bash
python -B scripts/run_trace_net_executive_tiff_demo_v4.py \
  --output-dir /data/trace_net_runs/executive_deep_demo_v4_<timestamp> \
  --skip-ingestion
```

To omit the 509 real embedding calls during a rehearsal:

```bash
python -B scripts/run_trace_net_executive_tiff_demo_v4.py \
  --skip-embeddings
```

## v4.1 classification display fix

The final retry/probe artifact stores each authoritative page route in
`final_validated_operational_route`. The original v4 presenter looked for an
older field name and therefore displayed `UNKNOWN` even when the classifier
pipeline had passed.

v4.1 resolves routes in this order:

1. `final_validated_operational_route`
2. `validated_operational_route`
3. final/resolved/source operational-route fallbacks
4. earlier four-route/resolver fields only when needed

Every accepted value is normalized to exactly one of:

- `blank`
- `plain_text`
- `table`
- `image`

A classification gate now requires the page count to match and requires zero
unclassified pages before the demo may build its graph, Engram summary, or
embeddings. The presenter never substitutes `UNKNOWN` as a page type.

A completed OCR run can be corrected without repeating OCR:

```bash
python -B scripts/run_trace_net_executive_tiff_demo_v4.py \
  --output-dir /data/trace_net_runs/executive_deep_demo_v4_<timestamp> \
  --skip-ingestion \
  --skip-embeddings
```
