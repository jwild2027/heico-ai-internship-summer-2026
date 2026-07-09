# TRACE-Net TIFF Content Fixed-50 QA v1

This runner asks 50 deterministic questions about **content extracted from scanned TIFF pages**, not ZIP internals or XML byte metadata.

It scans TRACE-Net artifacts under `local_data/organization/trace_net` for OCR text, visual/page summaries, table signals, nomenclature, part numbers, ATA numbers, figure references, warnings/cautions/notes, and page/document references.

It prints progress while running:

```text
[001/050] START q01: ...
[001/050] DONE  q01
...
[050/050] DONE  q50
```

It writes:

- `answers.jsonl`
- `answers_question_answer.txt`
- `summary.json`

Safety contract:

- read-only
- no endpoint call
- no Ollama call
- no Postgres/Qdrant/OpenSearch writes
- no source-truth mutation
- no answer permission granted

Example:

```bash
python -B scripts/run_trace_net_tiff_content_fixed50_qa_v1.py \
  --sample-zip "/c/Users/juswil/Desktop/metadata.zip" \
  --artifact-root local_data/organization/trace_net \
  --output-dir local_data/organization/trace_net/tiff_content_fixed50_qa_v1
```

Then:

```bash
cat local_data/organization/trace_net/tiff_content_fixed50_qa_v1/answers_question_answer.txt
```
