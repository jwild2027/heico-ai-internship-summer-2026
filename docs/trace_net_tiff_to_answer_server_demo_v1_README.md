# TRACE-Net raw TIFF → answer server demo v1

This patch adds a read-only, boss-friendly end-to-end demonstration. It does **not** rebuild the 509-page ingestion pipeline during the meeting and does not mutate any database. Instead, it selects a real raw TIFF page, optionally reruns OCR for that one page, replays the production ingestion artifacts, calls the normal TRACE-Net public endpoint, and creates a self-contained HTML report.

## Twelve visible stages

1. Raw TIFF and source hash
2. Image signals and artifact detection
3. OCR extraction
4. Page route and classifier validation
5. V2/V3 page intelligence
6. Table, visual, and part extraction
7. Postgres/Qdrant/OpenSearch storage contracts
8. Interconnected graph SVG
9. Discovery Machine retrieval
10. Typed evidence, Self-RAG, and CRAG
11. One Gemma answer-writing step
12. Citation/safety validation and final output

## Important design choices

- The script calls `/v1/chat/completions` on the normal public model.
- The API key is never written into the HTML report or manifest.
- Raw page extraction is read-only and writes only to the selected demo output directory.
- Qdrant is queried only with `GET` for collection health/counts.
- No Postgres, Qdrant, OpenSearch, graph, or source-artifact mutation is performed.
- `--present` pauses after each terminal stage.
- `--serve` hosts the generated report, defaulting to `127.0.0.1:8099`.

## Recommended demo page

The default page is `t_p_120_1176_p000343` and the default question is:

> What bigger assembly is 120-20970-001 installed inside?

Pass the source ZIP explicitly for a strict raw-TIFF demo:

```bash
--source-package /path/to/metadata.zip --require-raw-tiff
```

A completed `raw_to_answer_e2e_smoke_*` directory is required. The script auto-discovers the known repository artifacts, or you can pass `--pipeline-root` explicitly.

## Strict executive-demo gate

For the final rehearsal, add:

```bash
--require-raw-tiff --require-qdrant --require-one-model-call --min-citations 1 --strict
```

This makes the command fail unless it has the real raw TIFF, the live Qdrant collection, exactly one model call exposed by the endpoint, at least one citation object, and a non-empty final answer.
