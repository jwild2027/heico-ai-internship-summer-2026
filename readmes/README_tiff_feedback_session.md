# TIFF/RAG feedback session

This adds a lightweight feedback loop for user-style testing.

The user types a question, the current `ask_tiff_rag.py` answer is shown, then the user grades it and gives a reason. Feedback is stored as append-only JSONL so it can later be connected into the graph/quality workflow without mutating source truth.

## Interactive use

Git Bash:

```bash
python scripts/run_feedback_session.py \
  --config local_config.yaml \
  --source-zip /c/Users/juswil/Documents/00000027/metadata.zip
```

PowerShell:

```powershell
python scripts/run_feedback_session.py --config local_config.yaml --source-zip "C:\\Users\\juswil\\Documents\\00000027\\metadata.zip"
```

Outputs:

```text
local_data/feedback/user_feedback.jsonl
local_data/feedback/user_feedback_summary.json
```

## One-off scripted feedback

```bash
python scripts/run_feedback_session.py \
  --config local_config.yaml \
  --source-zip /c/Users/juswil/Documents/00000027/metadata.zip \
  --question "What is part number 120-37313-001?" \
  --rating up \
  --category useful \
  --reason "Correct part name and sources were shown."
```

## What gets stored

Each feedback record includes question, answer text, rating, category, reason, LLM/embedding usage flags, answer runtime, source ZIP audit counts, config, timestamp, and session id.

Feedback should influence ranking, QA review, and future eval cases, but should not directly rewrite technical facts.
