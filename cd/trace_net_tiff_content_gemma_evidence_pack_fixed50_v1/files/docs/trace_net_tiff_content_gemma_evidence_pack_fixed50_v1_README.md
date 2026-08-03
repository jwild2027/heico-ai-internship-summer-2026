# TRACE-Net TIFF Content Gemma Evidence Pack Fixed-50 v1

This runner asks fixed questions about content extracted from scanned TIFF pages by building local evidence packs from TRACE-Net artifacts and then calling Gemma through Ollama.

It does **not** use the old demo endpoint, because that endpoint only returns a small canned smoke response and does not search all OCR/table/visual/page-context artifacts.

## Inputs

- `--questions`: JSON file containing `{"questions": [...]}` or a raw list of question objects.
- `--artifact-root`: TRACE-Net local artifact root, usually `local_data/organization/trace_net`.
- `--output-dir`: output directory, preferably under `/data/trace_net_runs` on the server.
- `--ollama-host`: Ollama host.
- `--model`: local model, usually `gemma4:26b`.

## Outputs

- `answers.jsonl`: full answer records with retrieved evidence snippets.
- `question_answer_view.txt`: clean Question / Answer view.
- `summary.json`: run summary.
- `prompts/`: exact prompts sent to Gemma.

## Safety contract

Read-only. No database writes. No source-truth mutation. Evidence snippets are route/proof candidates; final answer must avoid claims not grounded in snippets.
