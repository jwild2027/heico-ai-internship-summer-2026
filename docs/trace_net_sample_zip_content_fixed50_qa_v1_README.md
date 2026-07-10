# TRACE-Net Sample ZIP Content Fixed-50 QA v1

This module runs 50 deterministic questions over the actual content inside a sample metadata ZIP. It reads `metadata.xml`, METS/MODS fields, file records, checksums, technical image metadata, and structMap page mappings.

It is intentionally local and read-only:

- no TRACE-Net endpoint call
- no Ollama/Gemma call
- no Postgres/Qdrant/OpenSearch writes
- no source-truth mutation
- no answer permission

Main command:

```bash
python -B scripts/run_trace_net_sample_zip_content_fixed50_qa_v1.py \
  --sample-zip "/c/Users/juswil/Desktop/metadata.zip" \
  --output-dir local_data/organization/trace_net/sample_zip_content_fixed50_qa_v1
```

Outputs:

- `answers.jsonl`
- `answers_question_answer.txt`
- `summary.json`

The terminal prints progress like `[001/050] START ...` and `[001/050] DONE ...`, then prints the final question/answer output.
