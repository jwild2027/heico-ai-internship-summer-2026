# TRACE-Net Sample ZIP Fixed-50 QA Runner v1

This read-only runner asks 50 deterministic questions about a sample metadata/TIFF ZIP. It is meant for quick laptop/server smoke testing without needing the TRACE-Net endpoint, Ollama, Postgres, Qdrant, or OpenSearch.

## What it reads

- `metadata.xml` inside the sample ZIP
- TIFF inventory inside the sample ZIP
- METS/MODS/MIX metadata fields
- METS file records and TIFF sizes/checksums/hrefs

## What it writes

- `answers.jsonl` — one JSON record per question
- `answers_question_answer.txt` — simple human-readable output in Question/Answer format
- `sample_zip_facts.json` — parsed ZIP facts
- `summary.json` — run summary and safety/status counts

## Safety contract

- Read-only
- No source-truth mutation
- No database writes
- No endpoint calls
- No model/Ollama calls
- No answer permission granted

## Example

```bash
python3 -B scripts/run_trace_net_sample_zip_fixed50_qa_v1.py \
  --sample-zip /path/to/metadata.zip \
  --output-dir /data/trace_net_runs/sample_zip_fixed50_qa_v1
```

The runner prints progress like:

```text
[001/050] START q01: What ZIP file was inspected?
[001/050] DONE  q01
...
[050/050] DONE  q50
```

Then it prints the final answers like:

```text
Question 01: ...
Answer 01: ...
```
